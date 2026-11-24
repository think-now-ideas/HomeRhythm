"""Steuerung: wertet Regeln aus, setzt Thermostate und erkennt Hand-Änderungen."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from datetime import date, datetime, timedelta
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Context, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import engine as E
from . import flows as F
from . import requirements as R
from . import controls as CT
from . import roomtemp as RT
from .const import (
    CONF_HOLIDAY_AS,
    CONF_VACATION_AS,
    CONF_AWAY_TEMP,
    CONF_BOILER_EFF,
    CONF_COOL_VALUES,
    CONF_PRESENCE_ENTITY,
    CONF_GAS_PRICE,
    CONF_GAS_PRICE_ENTITY,
    CONF_HOT_ABOVE,
    CONF_HYSTERESIS,
    CONF_SUMMER_VALUE,
    CONF_WINTER_BELOW,
    CONF_OUTDOOR_AGG,
    CONF_OUTDOOR_ENTITIES,
    CONF_OUTDOOR_MINUTES,
    CONF_POWER_PRICE,
    CONF_POWER_PRICE_ENTITY,
    CONF_AWAY_VALUE,
    CONF_HOME_VALUE,
    CONF_SEASON_ENTITY,
    CONF_VACATION_ENTITY,
    CONF_WINTER_VALUES,
    CONF_WORKDAY_ENTITY,
    DEFAULTS,
    EVENT_UPDATED,
    VERSION,
    GRACE_SECONDS,
    RESYNC_SECONDS,
    SLOW_ECHO_SECONDS,
    STUCK_SECONDS,
    STUCK_SECONDS_SLOW,
    START_TABS,
    MAX_EXCEPTION_DAYS,
    SIGNAL_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
    TICK_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def room_entities(room: dict[str, Any]) -> list[str]:
    """Thermostate eines Raums (ab 0.2.0 mehrere; 0.1.0 speicherte climate_entity)."""
    ents = room.get("climate_entities")
    if ents is None:
        ents = [room["climate_entity"]] if room.get("climate_entity") else []
    return [e for e in ents if e]


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def room_acs(room: dict[str, Any]) -> list[str]:
    """Klimaanlagen eines Raums, die mitheizen."""
    return [e for e in room.get("ac_entities") or [] if e]


def all_entities(room: dict[str, Any]) -> list[str]:
    return room_entities(room) + room_acs(room)


DEFAULT_AC = {"mode": "auto", "cop": E.DEFAULT_COP_POINTS, "min_outdoor": -15.0, "night_off": True, "reserve": 2.0, "boost_after": 30}
WRAPPERS = {"better_thermostat": "BT", "versatile_thermostat": "VT"}  # Regler, die ein echtes Gerät steuern
COLD_MARGIN = 1.5
BATTERY_LOW = 20  # % – darunter gilt eine Batterie als schwach  # K unter Soll → Heizkörper helfen mit


def slugify_id(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "raum"


def tidy_name(name: str) -> str:
    """Doppelte Namen kürzen: „Rollladen Arbeitszimmer EG Arbeitszimmer EG Rollladen“ → „Arbeitszimmer EG Rollladen“.

    Entsteht, wenn Gerätename und Entitätsname dieselben Wörter in anderer Reihenfolge haben.
    """
    words = name.split()
    n = len(words)
    if n >= 2 and n % 2 == 0 and not any(w.isdigit() for w in words):  # „Bad 1 1 Bad“ nicht anfassen
        first, second = words[: n // 2], words[n // 2:]
        if sorted(w.casefold() for w in first) == sorted(w.casefold() for w in second):
            return " ".join(second)
    for k in range(1, n // 2 + 1):  # „Küche Küche Licht“ → „Küche Licht“
        if [w.casefold() for w in words[:k]] == [w.casefold() for w in words[k:2 * k]]:
            return " ".join(words[k:])
    return name


class HomeRhythmController:
    """Hält Konfiguration und Laufzeitzustand, setzt die Geräte."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.req_none: set[str] = set()
        self.start_tab = "overview"  # Reiter beim Öffnen der Karte (Einrichtung → Weiteres)
        self.rooms: dict[str, dict[str, Any]] = {}
        self.manual: dict[str, E.Manual] = {}
        self.results: dict[str, E.Result] = {}  # Raum (ohne Abweichung je Thermostat)
        self.dev_results: dict[str, E.Result] = {}  # "raum|climate.x" → Ergebnis für dieses Thermostat
        self._last_sent: dict[str, dict[str, Any]] = {}
        self._own_contexts: deque[str] = deque(maxlen=200)
        self._unsubs: list[CALLBACK_TYPE] = []
        self._climate_unsub: CALLBACK_TYPE | None = None
        self.sources: dict[str, str] = {}  # Raum → zuletzt gewählte Wärmequelle (für Hysterese)
        self.room_energy: dict[str, dict[str, Any]] = {}
        self._cold_since: dict[str, datetime] = {}
        self._outdoor_samples: deque[tuple[datetime, float]] = deque(maxlen=2000)
        self._sun_cache: dict[str, tuple[datetime, datetime]] = {}
        self._sun_year_cache: dict[int, dict[str, Any]] = {}
        self.runner = None  # FlowRunner (Zeitpläne und Reaktionen), wird in __init__.py gesetzt
        self.stopped = False
        self.foreign_log: dict[str, list[dict[str, Any]]] = {}  # Gerät → fremde Änderungen (neueste zuletzt)
        self.dismissed: set[str] = set()  # ausgeblendete Hinweise ("ist gewollt")
        self._user_names: dict[str, str] = {}
        self.overrides: dict[str, E.Today] = {}  # Raum → "Heute anders" / Ausnahme (je Raum höchstens eine)
        self._override_started: set[str] = set()  # geplante Ausnahmen, deren Beginn schon behandelt wurde
        # 0.9.5 Raumtemperatur: Beobachtungen (Fritz), zuletzt gesendete Raumwerte (Thermostat direkt)
        self.observations: dict[str, list[dict[str, Any]]] = {}
        self._pushed: dict[str, dict[str, Any]] = {}
        self._remote_tried: dict[str, datetime] = {}
        self._closed_since: dict[str, datetime] = {}
        # 0.9.6 Bedienteile und Ventil-Zustand
        self.controls = CT.ControlManager(self)
        self._heat_log: dict[str, list[tuple[datetime, bool]]] = {}  # Thermostat → Wechsel heizt/zu (letzte 2 Std.)
        self._heat_start_temp: dict[str, float | None] = {}
        self.level_defs: dict[str, dict[str, Any]] = E.normalize_level_defs(None)
        self.event: str = "keins"  # Ereignis: keins / Party / Gäste
        self.party_until: datetime | None = None
        self.season_auto: bool = False  # Jahreszeit automatisch nach Ø Außentemperatur
        self.daily_temps: dict[str, list[float]] = {}  # "2026-11-01" → [Summe, Anzahl]
        self._season_checked: str | None = None
        self._season_set: tuple[str, datetime] | None = None  # zuletzt automatisch gesetzt (Echo nicht als "von Hand" werten)
        self._lock = asyncio.Lock()  # Abgleiche nie überlappend (Tick, Hand-Änderung, Speichern)

    # ------------------------------------------------------------------ Konfiguration
    @property
    def options(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.entry.data, **self.entry.options}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.rooms = data.get("rooms", {})
        for room in self.rooms.values():  # 0.9.7: Bedienteile als Gerät + angelernte Tasten
            if any(isinstance(c, dict) and "type" in c and "device_id" not in c for c in room.get("controls") or []):
                try:
                    room["controls"] = CT.normalize(room["controls"], all_entities(room), self.hass)
                except ValueError:
                    _LOGGER.warning("HomeRhythm: Bedienteile von %s nicht übernommen", room.get("name"))
                    room["controls"] = []
        self.foreign_log = data.get("foreign", {}) or {}
        self.stored_flows = data.get("flows") or {}  # wird vom FlowRunner übernommen
        self.dismissed = set(data.get("dismissed", []) or [])
        self.req_none = {k for k in (data.get("req_none") or []) if isinstance(k, str)}  # Voraussetzungen bewusst „ohne“
        self.start_tab = data.get("start_tab") if data.get("start_tab") in START_TABS else "overview"
        for rid, o in (data.get("overrides") or {}).items():
            try:
                until = dt_util.parse_datetime(o["until"])
                if until is None:
                    continue
                start = dt_util.parse_datetime(o["start"]) if o.get("start") else None
                level = o.get("level")
                if o["kind"] == "stufe" and level not in E.PLAN_LEVELS:
                    continue
                self.overrides[rid] = E.Today(o["kind"], until, level=level, start=start)
            except (KeyError, TypeError, ValueError):
                continue
        self.event = data.get("event") or "keins"
        self.party_until = dt_util.parse_datetime(data["party_until"]) if data.get("party_until") else None
        if self.event == "Party" and self.party_until is None:
            self.event = "keins"
        self.season_auto = bool(data.get("season_auto", False))
        try:
            self.level_defs = E.normalize_level_defs(data.get("level_defs"))
        except ValueError:
            self.level_defs = E.normalize_level_defs(None)
        E.apply_level_defs(self.level_defs)
        self.daily_temps = data.get("daily_temps") or {}
        self.observations = {k: v for k, v in (data.get("observations") or {}).items() if isinstance(v, list)}
        for room in self.rooms.values():  # Migration 0.1.0 → 0.2.0
            room["climate_entities"] = room_entities(room)
            room.pop("climate_entity", None)
            if room.get("kind") not in RT.KINDS:  # 0.9.5: Art aus den Thermostaten – Verhalten bleibt gleich
                room["kind"] = self.derive_kind(room)
            if room.pop("programs", None):  # 0.7.0: Rollläden/Licht im Raum – ab 0.8.0 als Abläufe
                _LOGGER.info("HomeRhythm: Rollläden/Licht-Einstellungen aus Raum %s entfernt – bitte als Ablauf anlegen", room.get("name"))
        for room_id, m in (data.get("manual") or {}).items():
            try:
                self.manual[room_id] = E.Manual(
                    temperature=m.get("temperature"),
                    hvac_mode=m.get("hvac_mode", "heat"),
                    until=dt_util.parse_datetime(m["until"]),
                    source=m.get("source", ""),
                    since=dt_util.parse_datetime(m["since"]) if m.get("since") else None,
                )
            except (KeyError, TypeError, ValueError):
                continue

    async def async_save(self) -> None:
        if self.stopped:
            return  # nach dem Entfernen nichts mehr zurückschreiben (Datenschutz)
        await self._store.async_save(self._data_to_save())

    @callback
    def schedule_save(self) -> None:
        """Gebündelt speichern (für Protokolle) – schont z. B. SD-Karten."""
        if not self.stopped:
            self._store.async_delay_save(self._data_to_save, 30)

    def _data_to_save(self) -> dict[str, Any]:
        return (
            {
                "rooms": self.rooms,
                "foreign": self.foreign_log,
                **(self.runner.storage_data() if self.runner else {"flows": self.stored_flows}),
                "dismissed": sorted(self.dismissed),
                "req_none": sorted(self.req_none),
                "start_tab": self.start_tab,
                "observations": self.observations,
                "overrides": {
                    rid: {"kind": o.kind, "until": o.until.isoformat(), **({"level": o.level} if o.level else {}), **({"start": o.start.isoformat()} if o.start else {})}
                    for rid, o in self.overrides.items()
                },
                "event": self.event,
                "party_until": self.party_until.isoformat() if self.party_until else None,
                "season_auto": self.season_auto,
                "daily_temps": self.daily_temps,
                "level_defs": self.level_defs,
                "manual": {
                    rid: {
                        "temperature": m.temperature,
                        "hvac_mode": m.hvac_mode,
                        "until": m.until.isoformat(),
                        "source": m.source,
                        "since": m.since.isoformat() if m.since else None,
                    }
                    for rid, m in self.manual.items()
                },
            }
        )

    # ------------------------------------------------------------------ Start/Stopp
    async def _async_load_users(self) -> None:
        try:
            self._user_names = {u.id: u.name for u in await self.hass.auth.async_get_users() if u.name}
        except Exception:  # noqa: BLE001 – nur für schönere Texte
            self._user_names = {}

    async def async_start(self) -> None:
        await self._async_load_users()
        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_tick_cb, timedelta(seconds=TICK_SECONDS))
        )
        mode_entities = [
            e
            for e in (
                self.options[CONF_SEASON_ENTITY],
                self.options[CONF_VACATION_ENTITY],
                self.options[CONF_WORKDAY_ENTITY],
                self.options.get(CONF_PRESENCE_ENTITY),
            )
            if e
        ]
        if mode_entities:
            self._unsubs.append(async_track_state_change_event(self.hass, mode_entities, self._on_mode_change))
        if outdoor := list(self.options[CONF_OUTDOOR_ENTITIES] or []):
            self._unsubs.append(async_track_state_change_event(self.hass, outdoor, self._on_outdoor_change))
        self._sample_outdoor()
        self._track_climates()
        await self.async_update(apply=True)

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self.controls.unload()
        if self._climate_unsub:
            self._climate_unsub()
            self._climate_unsub = None

    def _track_climates(self) -> None:
        if self._climate_unsub:
            self._climate_unsub()
            self._climate_unsub = None
        entities = [e for r in self.rooms.values() for e in all_entities(r)]
        if entities:
            self._climate_unsub = async_track_state_change_event(self.hass, entities, self._on_climate_change)
        for e in entities:
            self._note_heating(e, self.hass.states.get(e))
        self.controls.track()

    # ------------------------------------------------------------------ Hausmodi
    def modes(self) -> E.Modes:
        o = self.options
        season_state = self.hass.states.get(o[CONF_SEASON_ENTITY]) if o[CONF_SEASON_ENTITY] else None
        season = season_state.state if season_state else "Winter"
        winter_values = [v.strip() for v in str(o[CONF_WINTER_VALUES]).split(",") if v.strip()]
        heating = season in winter_values if season_state and season not in (STATE_UNKNOWN, STATE_UNAVAILABLE) else True

        vac_state = self.hass.states.get(o[CONF_VACATION_ENTITY]) if o[CONF_VACATION_ENTITY] else None
        vac = vac_state.state if vac_state else ""
        work_state = self.hass.states.get(o[CONF_WORKDAY_ENTITY]) if o[CONF_WORKDAY_ENTITY] else None
        now = dt_util.now()
        # Workday ist am Wochenende ohnehin "off"; als Feiertag zählt nur Mo–Fr.
        holiday = bool(work_state and work_state.state == "off" and now.weekday() < 5)
        cool_values = [v.strip() for v in str(o.get(CONF_COOL_VALUES) or "").split(",") if v.strip()]
        cooling = bool(season_state) and season in cool_values and not heating
        return E.Modes(
            cooling_season=cooling,
            nobody_home=self._nobody_home(),
            season=season,
            heating_season=heating,
            away=vac == o[CONF_AWAY_VALUE],
            home_vacation=vac == o[CONF_HOME_VALUE],
            holiday_today=holiday,
            away_temp=float(o[CONF_AWAY_TEMP]),
            vacation_label=vac,
            event=self.event,
            occasion="Weihnachten" if E.christmas(now.date()) else "",
            party_until=self.party_until if self.event == "Party" else None,
            holiday_as=o.get(CONF_HOLIDAY_AS) or "so",
            vacation_as=o.get(CONF_VACATION_AS) or "so",
        )

    def modes_assumed(self, assume: dict[str, Any] | None) -> E.Modes:
        """Hausmodi „angenommen“ (Übersicht, nur Anzeige): Jahreszeit, Urlaub, Anwesenheit, Ereignis, Weihnachten.

        Werte, die nicht angegeben sind, bleiben wie jetzt. Feiertag/Tagesart ergeben sich aus dem gewählten Tag.
        """
        m = self.modes()
        a = assume or {}
        o = self.options
        if a.get("season"):
            season = str(a["season"])[:40]
            winter = [v.strip() for v in str(o[CONF_WINTER_VALUES]).split(",") if v.strip()]
            cool = [v.strip() for v in str(o.get(CONF_COOL_VALUES) or "").split(",") if v.strip()]
            heating = season in winter
            m = replace(m, season=season, heating_season=heating, cooling_season=season in cool and not heating)
        if a.get("vacation"):
            vac = str(a["vacation"])[:60]
            m = replace(m, away=vac == o[CONF_AWAY_VALUE], home_vacation=vac == o[CONF_HOME_VALUE], vacation_label=vac)
        if a.get("presence") in ("home", "away"):
            m = replace(m, nobody_home=a["presence"] == "away")
        if a.get("event") in E.EVENTS:
            m = replace(m, event=a["event"], party_until=None)
        return m

    def _nobody_home(self) -> bool:
        eid = self.options.get(CONF_PRESENCE_ENTITY)
        st = self.hass.states.get(eid) if eid else None
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False  # unbekannt → so tun, als wäre jemand da
        if eid.startswith("zone.") and not any(
            p.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN) for p in self.hass.states.async_all("person")
        ):
            return False  # ohne Personen mit Standort ist zone.home immer 0 – das heißt nicht "niemand da"
        try:
            return float(st.state) <= 0  # zone.home: Anzahl Personen
        except ValueError:
            return st.state in ("not_home", "off", "away")

    @callback
    def _on_mode_change(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is not None and new is not None and old.state == new.state:
            return
        echo = bool(
            self._season_set
            and new is not None
            and new.state == self._season_set[0]
            and (dt_util.utcnow() - self._season_set[1]).total_seconds() < 600
        )
        if (
            event.data["entity_id"] == self.options[CONF_SEASON_ENTITY]
            and self.season_auto
            and event.context.id not in self._own_contexts
            and not echo
            and old is not None
            and new is not None
            and old.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            and new.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        ):
            # Jahreszeit von Hand gewählt → festhalten (Automatik aus)
            self.season_auto = False
            self.hass.async_create_task(self.async_save())
        # Moduswechsel heben Hand-Änderungen auf – danach gilt sofort der neue Modus.
        if event.data["entity_id"] not in (self.options[CONF_WORKDAY_ENTITY], self.options.get(CONF_PRESENCE_ENTITY)) and self.manual:
            self.manual.clear()
            self.hass.async_create_task(self.async_save())
        self.hass.async_create_task(self.async_update(apply=True))

    async def _async_tick_cb(self, _now: datetime) -> None:
        await self._async_housekeeping()
        await self.async_update(apply=True)

    async def _async_housekeeping(self) -> None:
        """Abgelaufenes "Heute anders" und Party beenden, Tagesmittel sammeln, Jahreszeit automatisch."""
        now = dt_util.now()
        changed = False
        for rid in [rid for rid, o in self.overrides.items() if o.until <= now or rid not in self.rooms]:
            self.overrides.pop(rid)
            self._override_started.discard(rid)
            changed = True
        # Geplante Ausnahme beginnt: wie beim sofortigen Setzen eine laufende Hand-Änderung beenden
        for rid, o in self.overrides.items():
            if o.start is not None and o.active(now) and rid not in self._override_started:
                self._override_started.add(rid)
                if o.start > now - timedelta(minutes=5):  # nicht nach einem Neustart Stunden später
                    self._forget_manual(rid)
                    self._forget_sent(rid)
                    changed = True
        if self.event == "Party" and self.party_until and now >= self.party_until:
            self.event, self.party_until = "keins", None
            changed = True
        value = self._outdoor_now()
        if value is not None:
            key = now.date().isoformat()
            acc = self.daily_temps.setdefault(key, [0.0, 0])
            acc[0] += value
            acc[1] += 1
            for old in sorted(self.daily_temps)[:-10]:
                self.daily_temps.pop(old)
            changed = changed or acc[1] % 30 == 1  # etwa jede halbe Stunde speichern
        if self.season_auto and self._season_checked != now.date().isoformat() and now.hour >= 4:
            await self.async_apply_season_auto()
        try:
            await self._async_room_temps(now)
        except Exception:  # noqa: BLE001 – Senden/Beobachten darf die übrige Steuerung nie aufhalten
            _LOGGER.exception("HomeRhythm: Raumtemperatur (Senden/Beobachten) fehlgeschlagen")
        if changed:
            await self.async_save()
            async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    MIN_SAMPLES_PER_DAY = 860  # ~60 % eines Tages (1 Messung pro Minute)
    SEASON_BAND = 2.0  # K: so weit muss Ø über/unter die Grenze, um eine Jahreszeit wieder zu verlassen

    def season_average(self) -> tuple[float | None, int]:
        """Ø Außentemperatur der letzten 3 vollständig gemessenen Tage (heute zählt nicht)."""
        today = dt_util.now().date().isoformat()
        days = [k for k in sorted(self.daily_temps) if k < today and self.daily_temps[k][1] >= self.MIN_SAMPLES_PER_DAY][-3:]
        vals = [self.daily_temps[k][0] / self.daily_temps[k][1] for k in days]
        return (round(sum(vals) / len(vals), 1), len(vals)) if vals else (None, 0)

    def season_suggestion(self) -> str | None:
        """Vorschlag mit Schaltband – erst ab 2 vollen Messtagen."""
        avg, n = self.season_average()
        if avg is None or n < 2:
            return None
        o = self.options
        winter = next((v.strip() for v in str(o[CONF_WINTER_VALUES]).split(",") if v.strip()), "Winter")
        hot = next((v.strip() for v in str(o.get(CONF_COOL_VALUES) or "").split(",") if v.strip()), None)
        summer = o.get(CONF_SUMMER_VALUE) or "Sommer"
        lo, hi, band = float(o[CONF_WINTER_BELOW]), float(o[CONF_HOT_ABOVE]), self.SEASON_BAND
        st = self.hass.states.get(o[CONF_SEASON_ENTITY]) if o[CONF_SEASON_ENTITY] else None
        current = st.state if st else None
        if current == winter:
            return winter if avg < lo + band else (hot if hot and avg > hi else summer)
        if hot and current == hot:
            return hot if avg > hi - band else (winter if avg < lo else summer)
        if avg < lo:
            return winter
        if hot and avg > hi:
            return hot
        return summer

    def season_auto_possible(self) -> bool:
        eid = self.options[CONF_SEASON_ENTITY]
        st = self.hass.states.get(eid) if eid else None
        return bool(st and st.attributes.get("options") and eid.split(".")[0] in ("input_select", "select"))

    async def async_apply_season_auto(self) -> None:
        eid = self.options[CONF_SEASON_ENTITY]
        st = self.hass.states.get(eid) if eid else None
        if not st or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) or not self.season_auto_possible():
            return  # später noch einmal versuchen
        self._season_checked = dt_util.now().date().isoformat()
        want = self.season_suggestion()
        if not want or st.state == want or want not in (st.attributes.get("options") or []):
            return
        ctx = Context()
        self._own_contexts.append(ctx.id)
        self._season_set = (want, dt_util.utcnow())
        await self.hass.services.async_call(eid.split(".")[0], "select_option", {ATTR_ENTITY_ID: eid, "option": want}, blocking=True, context=ctx)
        _LOGGER.info("HomeRhythm: Jahreszeit automatisch auf %s (Ø %s °C)", want, self.season_average()[0])

    async def async_set_season_auto(self, enabled: bool) -> None:
        self.season_auto = enabled
        self._season_checked = None
        await self.async_save()
        if enabled:
            await self.async_apply_season_auto()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        self.hass.bus.async_fire(EVENT_UPDATED, {})

    async def async_set_event(self, event: str) -> None:
        if event not in E.EVENTS:
            raise ValueError(f"Unbekanntes Ereignis: {event}")
        self.event = event
        self.party_until = E.party_end(dt_util.now()) if event == "Party" else None
        await self.async_save()
        await self.async_update(apply=True)

    async def async_set_today(
        self,
        room_id: str,
        kind: str,
        level: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        until_day: date | None = None,
    ) -> None:
        """„Heute anders“ bzw. Ausnahme setzen – je Raum höchstens eine, eine neue ersetzt die alte.

        - kind "stufe": ``level`` von ``start`` (None = jetzt) bis ``end`` (Pflicht), höchstens MAX_EXCEPTION_DAYS voraus.
        - "sonntag" / "werktag" / "leer": ganze Tage bis einschließlich ``until_day`` (None = heute).
        - "party": bis 1 Uhr nachts, "komfort": heute.
        """
        if room_id not in self.rooms:
            raise ValueError("Unbekannter Raum")
        now = dt_util.now()
        if kind == "normal":
            self.overrides.pop(room_id, None)
        elif kind == "stufe":
            if level not in E.PLAN_LEVELS or not (self.level_defs.get(level) or {}).get("enabled", True):
                raise ValueError("Unbekannte oder nicht wählbare Stufe")
            if end is None:
                raise ValueError("Ende fehlt")
            start_at = dt_util.as_local(start) if start is not None else None
            if start_at is not None and start_at <= now:
                start_at = None  # Beginn schon vorbei → ab jetzt
            end_at = dt_util.as_local(end)
            if end_at <= (start_at or now):
                raise ValueError("Das Ende muss nach dem Beginn liegen")
            if end_at > now + timedelta(days=MAX_EXCEPTION_DAYS):
                raise ValueError(f"Höchstens {MAX_EXCEPTION_DAYS} Tage im Voraus")
            # Beginn merken (auch „jetzt“), damit die Anzeige „bis 21:23“ den Tag kennt
            self.overrides[room_id] = E.Today("stufe", end_at, level=level, start=start_at or now.replace(second=0, microsecond=0))
            if start_at is None:
                self._override_started.add(room_id)
                self._forget_manual(room_id)  # bewusste Entscheidung ersetzt eine Hand-Änderung
            else:
                self._override_started.discard(room_id)
        elif kind in E.TODAY_KINDS:
            if until_day is not None and kind in ("sonntag", "werktag", "leer"):
                if until_day < now.date() or until_day > now.date() + timedelta(days=MAX_EXCEPTION_DAYS):
                    raise ValueError(f"Endtag muss zwischen heute und in {MAX_EXCEPTION_DAYS} Tagen liegen")
                until = dt_util.start_of_local_day(until_day + timedelta(days=1))
            else:
                until = E.today_until(kind, now)
            self.overrides[room_id] = E.Today(kind, until)
            self._override_started.add(room_id)
            self._forget_manual(room_id)  # bewusste Entscheidung für heute ersetzt eine Hand-Änderung
        else:
            raise ValueError(f"Unbekannte Auswahl: {kind}")
        self._forget_sent(room_id)
        await self.async_save()
        await self.async_update(apply=True)

    def today_kind(self, room_id: str) -> str:
        """Art der Ausnahme – auch wenn sie erst später beginnt (geplant)."""
        o = self.overrides.get(room_id)
        return o.kind if o and o.until > dt_util.now() else "normal"

    def today_info(self, room_id: str) -> dict[str, Any] | None:
        o = self.overrides.get(room_id)
        now = dt_util.now()
        if not o or o.until <= now:
            return None
        return {
            "kind": o.kind,
            "until": o.until.isoformat(),
            "level": o.level,
            "start": o.start.isoformat() if o.start else None,
            "planned": o.planned(now),
            "label": E.today_label(o),
        }

    # ------------------------------------------------------------------ Energie
    def _outdoor_now(self) -> float | None:
        values = []
        for eid in self.options[CONF_OUTDOOR_ENTITIES] or []:
            st = self.hass.states.get(eid)
            if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            raw = st.attributes.get("temperature") if eid.startswith("weather.") else st.state
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
        if not values:
            return None
        return min(values) if self.options[CONF_OUTDOOR_AGG] == "min" else sum(values) / len(values)

    def _sample_outdoor(self) -> None:
        value = self._outdoor_now()
        if value is not None:
            self._outdoor_samples.append((dt_util.utcnow(), value))

    @callback
    def _on_outdoor_change(self, event: Event[EventStateChangedData]) -> None:
        self._sample_outdoor()

    def outdoor(self) -> float | None:
        """Außentemperatur, gemittelt über das eingestellte Fenster."""
        minutes = int(self.options[CONF_OUTDOOR_MINUTES] or 0)
        now = dt_util.utcnow()
        while self._outdoor_samples and (now - self._outdoor_samples[0][0]).total_seconds() > max(minutes, 1) * 60:
            if len(self._outdoor_samples) == 1:
                break  # letzten Wert behalten, falls sich der Sensor lange nicht ändert
            self._outdoor_samples.popleft()
        if minutes <= 0 or not self._outdoor_samples:
            return self._outdoor_now()
        vals = [v for _t, v in self._outdoor_samples]
        return round(sum(vals) / len(vals), 1)

    def _price(self, value_key: str, entity_key: str) -> tuple[float, str]:
        """Preis in ct/kWh – aus Entität (falls gesetzt und gültig), sonst fester Wert."""
        eid = self.options.get(entity_key)
        if eid and (st := self.hass.states.get(eid)):
            try:
                val = float(st.state)
                unit = str(st.attributes.get("unit_of_measurement") or "")
                if ("EUR" in unit or "€" in unit) and "ct" not in unit.lower() or (not unit and val < 2):
                    val *= 100  # €/kWh → ct/kWh
                return val, eid
            except (TypeError, ValueError):
                pass
        return float(self.options[value_key]), "fest"

    def prices(self) -> E.Prices:
        gas, _ = self._price(CONF_GAS_PRICE, CONF_GAS_PRICE_ENTITY)
        power, _ = self._price(CONF_POWER_PRICE, CONF_POWER_PRICE_ENTITY)
        return E.Prices(gas_ct=gas, boiler_efficiency=float(self.options[CONF_BOILER_EFF]) / 100, power_ct=power)

    def _room_temp(self, room: dict[str, Any]) -> float | None:
        """Raumtemperatur: Mittel der Heizkörper-Thermostate (Klimaanlagen messen unter der Decke)."""
        vals = []
        # Klimaanlagen messen unter der Decke – außer sie laufen über einen Regler mit Raumsensor (VT/BT).
        sources = room_entities(room) + [e for e in room_acs(room) if self.wrapper_kind(e)]
        for eid in sources or room_acs(room):
            st = self.hass.states.get(eid)
            if st and (v := st.attributes.get("current_temperature")) is not None:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
        return sum(vals) / len(vals) if vals else None

    def _energy_for(self, room_id: str, room: dict[str, Any], result: E.Result, outdoor: float | None, prices: E.Prices, now: datetime) -> dict[str, Any] | None:
        if not room_acs(room) or (self.modes().cooling_season and E.cooling_config(room)["enabled"]):
            return None
        ac = {**DEFAULT_AC, **(room.get("ac") or {})}
        points = ac["cop"]
        threshold = E.ac_threshold(points, prices.break_even_cop)
        info: dict[str, Any] = {
            "threshold": threshold,
            "cop_now": round(E.cop_at(points, outdoor), 2) if outdoor is not None else None,
            "break_even_cop": round(prices.break_even_cop, 2),
            "cost_gas": round(prices.heat_cost_gas, 1),
            "cost_ac": round(prices.power_ct / E.cop_at(points, outdoor), 1) if outdoor is not None else None,
            "outdoor": outdoor,
        }
        if not (E.plan_like(result) or result.rule == E.RULE_MANUAL) or result.hvac_mode == "off":
            info.update(source=E.SOURCE_RADIATOR, reason=result.reason, boost=False)
            self.sources.pop(room_id, None)
            return info
        if room_entities(room) and not any(
            (st := self.hass.states.get(e)) and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN) for e in room_acs(room)
        ):
            info.update(source=E.SOURCE_RADIATOR, reason="Klimaanlage nicht erreichbar – Heizkörper", boost=False)
            return info
        ac_manuals = [self.manual.get(f"{room_id}|{e}") for e in room_acs(room)]
        if room_entities(room) and all(m is not None and m.until > now and m.hvac_mode != "heat" for m in ac_manuals):
            info.update(source=E.SOURCE_RADIATOR, reason="Klimaanlage von Hand aus/anders – Heizkörper", boost=False)
            return info
        if ac["night_off"] and result.level == "nacht" and room_entities(room):
            info.update(source=E.SOURCE_RADIATOR, reason="nachts kein Klima", boost=False)
            return info  # Hysterese-Zustand behalten
        src, why = E.choose_source(
            ac["mode"] if room_entities(room) else "ac",  # nur Klimaanlage im Raum → immer Klima
            outdoor, threshold, self.sources.get(room_id), float(self.options[CONF_HYSTERESIS]), ac.get("min_outdoor")
        )
        self.sources[room_id] = src
        boost = False
        if src == E.SOURCE_AC and result.temperature is not None:
            cur = self._room_temp(room)
            if cur is not None and cur < result.temperature - COLD_MARGIN:
                since = self._cold_since.setdefault(room_id, now)
                boost = (now - since).total_seconds() >= float(ac.get("boost_after", 30)) * 60
                if boost:
                    why += " · zu kalt, Heizkörper helfen mit"
            else:
                self._cold_since.pop(room_id, None)
        else:
            self._cold_since.pop(room_id, None)
        info.update(source=src, reason=why, boost=boost)
        return info

    def _ac_result(self, room: dict[str, Any], base: E.Result, energy: dict[str, Any] | None, manual: E.Manual | None, modes: E.Modes, now: datetime) -> E.Result:
        if manual is not None and manual.until > now and base.rule not in (E.RULE_SEASON, E.RULE_AWAY):
            return E.evaluate(room, modes, now, manual, override=self.overrides.get(next((rid for rid, r in self.rooms.items() if r is room), "")))
        if energy and energy["source"] == E.SOURCE_AC and base.temperature is not None and base.hvac_mode != "off":
            return replace(base, reason=f"{base.reason} · {energy['reason']}")
        why = energy["reason"] if energy and (E.plan_like(base) or base.rule == E.RULE_MANUAL) else base.reason
        return E.Result("aus", None, "off", base.rule, why)

    def _radiator_result(self, room: dict[str, Any], dev: E.Result, energy: dict[str, Any] | None) -> E.Result:
        if (
            not energy
            or energy["source"] != E.SOURCE_AC
            or dev.temperature is None
            or dev.hvac_mode == "off"
            or not E.plan_like(dev)  # Hand-Änderung am Heizkörper bleibt, wie sie ist
        ):
            if energy and E.plan_like(dev) and energy.get("reason"):
                return replace(dev, reason=f"{dev.reason} · {energy['reason']}")
            return dev
        if energy.get("boost"):
            return replace(dev, reason=f"{dev.reason} · {energy['reason']}")
        reserve = float({**DEFAULT_AC, **(room.get("ac") or {})}["reserve"])
        return replace(dev, temperature=round(dev.temperature - reserve, 1), reason=f"{dev.reason} · Klima heizt, Heizkörper {reserve:g} K tiefer als Reserve")

    # ------------------------------------------------------------------ Auswertung
    def evaluate_room(self, room_id: str, now: datetime | None = None) -> E.Result:
        room = self.rooms[room_id]
        now = now or dt_util.now()
        return E.evaluate(room, self.modes(), now, self.manual.get(room_id), override=self.overrides.get(room_id))

    async def async_update(self, apply: bool = True) -> None:
        async with self._lock:
            await self._async_update(apply)
        if apply:
            try:
                await self.controls.async_sync()  # Bedienteile mit Anzeige zeigen den Sollwert des Raums
            except Exception:  # noqa: BLE001
                _LOGGER.exception("HomeRhythm: Bedienteile nicht aktualisiert")

    async def async_room_manual(self, room_id: str, temperature: float | None, hvac: str, until: datetime | None, source: str) -> None:
        """Hand-Änderung für den ganzen Raum (z. B. von einem Bedienteil) – Werte als Raumtemperatur."""
        room = self.rooms.get(room_id)
        if room is None:
            return
        now = dt_util.now()
        if until is None:
            until = E.manual_until(room, now, E.effective_modes(room, self.modes(), now, self.overrides.get(room_id)), self.overrides.get(room_id))
        manual = E.Manual(temperature=temperature, hvac_mode=hvac, until=until, source=source, since=now)
        self._forget_manual(room_id)
        if room.get("linked", True):
            self.manual[room_id] = manual
        else:
            for e in room_entities(room):
                self.manual[f"{room_id}|{e}"] = manual
        self._forget_sent(room_id)
        _LOGGER.info("HomeRhythm: Hand-Änderung in %s (%s)", room_id, source)
        await self.async_save()
        await self.async_update(apply=True)

    async def async_card_manual(self, room_id: str, temperature: float | None = None, level: str | None = None, off: bool = False,
                                until: str | None = None, minutes: int | None = None) -> None:
        """Raumkarte: Temperatur, Stufe oder aus – bis wie eingestellt, zum nächsten Wechsel, für Minuten oder bis Uhrzeit."""
        room = self.rooms.get(room_id)
        if room is None:
            raise ValueError("Unbekannter Raum")
        now = dt_util.now()
        if off:
            temp, hvac, what = None, "off", "Aus"
        elif level:
            if level not in E.PLAN_LEVELS:
                raise ValueError("Unbekannte Stufe")
            temp, hvac, what = E.level_temperature(room, level), "heat", E.LEVEL_NAMES.get(level, level)
        elif temperature is not None:
            temp, hvac, what = float(temperature), "heat", None
        else:
            raise ValueError("Temperatur, Stufe oder aus angeben")
        end: datetime | None
        if minutes:
            end = now + timedelta(minutes=minutes)
        elif until in (None, "", "default"):
            end = None
        elif until == "next":
            override = self.overrides.get(room_id)
            modes = E.effective_modes(room, self.modes(), now, override)
            end, _ = E.next_plan_change(room, now, modes)
            end = end or now + timedelta(hours=24)
        else:
            end = dt_util.parse_datetime(until)
            if end is None:
                raise ValueError("Ungültige Zeitangabe")
            end = dt_util.as_local(end)
        if end is not None and not now < end <= now + timedelta(days=MAX_EXCEPTION_DAYS):
            raise ValueError("Das Ende muss in der Zukunft liegen (höchstens 14 Tage)")
        await self.async_room_manual(room_id, temp, hvac, end, f"Raumkarte{': ' + what if what else ''}")

    async def _async_update(self, apply: bool) -> None:
        now = dt_util.now()
        changed = False
        for key in list(self.manual):
            room_id = key.split("|")[0]
            if self.manual[key].until <= now or room_id not in self.rooms:
                self.manual.pop(key)
                changed = True
        if changed:
            await self.async_save()
        modes = self.modes()
        self._sample_outdoor()
        outdoor, prices = self.outdoor(), self.prices()
        dev_results: dict[str, E.Result] = {}
        room_energy: dict[str, dict[str, Any]] = {}
        rooms = list(self.rooms.items())
        for room_id, room in rooms:
            linked = room.get("linked", True)
            override = self.overrides.get(room_id)
            result = E.evaluate(room, modes, now, self.manual.get(room_id) if linked else None, override=override)
            self.results[room_id] = result
            energy = self._energy_for(room_id, room, result, outdoor, prices, now)
            if energy:
                room_energy[room_id] = energy
            for entity_id in room_entities(room):
                key = f"{room_id}|{entity_id}"
                dev = result if linked else E.evaluate(room, modes, now, self.manual.get(key), override=override)
                dev_results[key] = self._with_correction(room, self._radiator_result(room, self._with_offset(room, entity_id, dev), energy))
            cooling = modes.cooling_season and E.cooling_config(room)["enabled"]
            for entity_id in room_acs(room):
                key = f"{room_id}|{entity_id}"
                if cooling:
                    dev = E.evaluate_cooling(room, modes, now, self.manual.get(key), override=override)
                else:
                    dev = self._ac_result(room, result, energy, self.manual.get(key), modes, now)
                dev_results[key] = self._with_offset(room, entity_id, dev)
            if cooling and room_acs(room):
                # Anzeige: im Sommer zählt das Kühlen (Plan ohne Hand-Änderung einzelner Geräte)
                self.results[room_id] = E.evaluate_cooling(room, modes, now, override=override)
        self.dev_results, self.room_energy = dev_results, room_energy
        if apply:
            for room_id, room in rooms:
                if room_id not in self.rooms or not room.get("enabled", True):
                    continue
                for entity_id in all_entities(room):
                    if (res := dev_results.get(f"{room_id}|{entity_id}")) is not None:
                        await self._async_apply(room_id, entity_id, res, one_shot=entity_id in room_acs(room))
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        self.hass.bus.async_fire(EVENT_UPDATED, {})

    @staticmethod
    def _with_offset(room: dict[str, Any], entity_id: str, result: E.Result) -> E.Result:
        """Abweichung je Thermostat (z. B. Eingang +1 °C) – nur für Plan-Stufen, nicht für Urlaub/Hand/Aus."""
        off = float((room.get("offsets") or {}).get(entity_id) or 0)
        if not off or not E.plan_like(result) or result.temperature is None:
            return result
        return replace(result, temperature=round(result.temperature + off, 1))

    @staticmethod
    def _with_correction(room: dict[str, Any], result: E.Result) -> E.Result:
        """Feste Korrektur (0.9.5): misst der Fühler c °C daneben, bekommt das Thermostat Soll − c."""
        c = RT.correction(room)
        if not c or result.temperature is None or result.hvac_mode == "off":
            return result
        return replace(result, temperature=round(result.temperature - c, 1))

    def derive_kind(self, room: dict[str, Any]) -> str:
        """Art eines Raums aus seinen Thermostaten (für Räume aus Versionen vor 0.9.5)."""
        if room.get("kind") in RT.KINDS:
            return room["kind"]
        reg = er.async_get(self.hass)
        plats = [(e.platform if (e := reg.async_get(eid)) else None) for eid in room_entities(room)]
        return RT.kind_for(plats)

    def kind_hint(self, room: dict[str, Any]) -> dict[str, Any] | None:
        """0.9.15: Hinweis „Art passt nicht zu den Thermostaten“ (z. B. nach einem Thermostat-Tausch), sonst None."""
        kind = room.get("kind")
        if kind not in RT.KINDS:
            return None
        reg = er.async_get(self.hass)
        plats = [(e.platform if (e := reg.async_get(eid)) else None) for eid in room_entities(room)]
        want = RT.kind_mismatch(kind, plats)
        if not want:
            return None
        hint_id = f"kind:{room['id']}:{kind}:{want}"  # neue Art → neue ID → Hinweis kommt bei neuem Fehlstand wieder
        if hint_id in self.dismissed:
            return None
        return {"id": hint_id, "kind": kind, "suggest": want}

    async def async_set_kind(self, room_id: str, kind: str) -> None:
        """Art eines Raums umstellen (Knopf am Hinweis). Alles andere am Raum bleibt; Unpassendes fällt weg wie im Editor."""
        room = self.rooms.get(room_id)
        if room is None:
            raise ValueError("Unbekannter Raum")
        if kind not in RT.KINDS:
            raise ValueError("Unbekannte Art von Thermostat")
        data = {**room, "kind": kind}
        if data.get("temp_source") == "box" and kind != "fritz":
            data["temp_source"] = "device"  # „in der Fritz!Box eingestellt“ gibt es nur bei FRITZ!DECT
        await self.async_save_room(data)

    def manual_key(self, room_id: str, entity_id: str) -> str:
        room = self.rooms[room_id]
        if entity_id in room_acs(room) or not room.get("linked", True):
            return f"{room_id}|{entity_id}"  # Klimaanlagen haben immer eine eigene Hand-Änderung
        return room_id

    def _desired(self, entity_id: str, result: E.Result) -> dict[str, Any] | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if result.hvac_mode != "off" and result.temperature is None:
            return None
        hvac_modes = state.attributes.get("hvac_modes") or []
        if result.hvac_mode == "off":
            if "off" in hvac_modes:
                return {"hvac": "off", "temp": None}
            return {"hvac": "heat", "temp": float(state.attributes.get("min_temp", 5))}
        if result.hvac_mode in ("cool", "dry", "fan_only") and result.hvac_mode not in hvac_modes:
            # Gerät kann nicht kühlen → aus, niemals stattdessen heizen
            return {"hvac": "off", "temp": None} if "off" in hvac_modes else None
        # Hand-Änderung auf z. B. "cool" an einer Klimaanlage bleibt so; sonst heizen.
        if result.hvac_mode in hvac_modes and result.hvac_mode != "heat":
            mode = result.hvac_mode  # Hand-Änderung z. B. "cool" an einer Klimaanlage bleibt
        else:
            mode = next((m for m in ("heat", "heat_cool", "auto") if m in hvac_modes), "heat")
        step = float(state.attributes.get("target_temp_step") or 0.5)
        temp = round(round(float(result.temperature) / step) * step, 2)
        lo, hi = state.attributes.get("min_temp"), state.attributes.get("max_temp")
        if lo is not None:
            temp = max(temp, float(lo))
        if hi is not None:
            temp = min(temp, float(hi))
        return {"hvac": mode, "temp": temp}

    @staticmethod
    def _tolerance(state) -> float:
        """Geräte ohne Schrittweite runden oft auf ganze Grad – sonst ewiges Nachsenden oder falsche Hand-Änderung."""
        return 0.05 if state.attributes.get("target_temp_step") else 0.51

    def _matches(self, state, want: dict[str, Any]) -> bool:
        if want["hvac"] == "off":
            return state.state == "off"
        cur = state.attributes.get(ATTR_TEMPERATURE)
        hvac_ok = state.state == want["hvac"] if want["hvac"] in (state.attributes.get("hvac_modes") or []) else state.state != "off"
        try:
            return hvac_ok and cur is not None and abs(float(cur) - want["temp"]) <= self._tolerance(state)
        except (TypeError, ValueError):
            return False

    async def _async_apply(self, room_id: str, entity_id: str, result: E.Result, one_shot: bool = False) -> None:
        # Bei Hand-Änderung folgen die übrigen Thermostate des Raums dem neuen Wert.
        want = self._desired(entity_id, result)
        if want is None:
            return
        state = self.hass.states.get(entity_id)
        key = f"{room_id}|{entity_id}"
        last = self._last_sent.get(key)
        now = dt_util.utcnow()
        # Klimaanlage im Sommer/Urlaub: einmal ausschalten, danach in Ruhe lassen (z. B. zum Kühlen).
        if one_shot and result.rule in (E.RULE_SEASON, E.RULE_AWAY, E.RULE_ABSENT):
            if last and last.get("rule") == result.rule:
                return  # in dieser Phase schon gehandelt (ausgeschaltet oder Hand-Änderung gemerkt)
            if self._matches(state, want):
                self._last_sent[key] = {"want": want, "at": now, "rule": result.rule}
                return
            await self._async_send(key, entity_id, state, want, result.rule)
            return
        if last and last["want"] == want:
            if self._matches(state, want):
                self._clear_stuck(key, entity_id)
                return
            if (now - last["at"]).total_seconds() < RESYNC_SECONDS:
                self._check_stuck(room_id, key, entity_id)
                return  # Gerät hat den Befehl evtl. noch nicht übernommen (träge Funkgeräte)
        elif self._matches(state, want):
            self._clear_stuck(key, entity_id)
            self._last_sent[key] = {"want": want, "at": now, "rule": result.rule}
            return
        await self._async_send(key, entity_id, state, want, result.rule)
        self._check_stuck(room_id, key, entity_id)

    # ------------------------------------------------------------------ Übernimmt nicht (0.9.16)
    def _stuck_limit(self, room_id: str) -> int:
        room = self.rooms.get(room_id) or {}
        return STUCK_SECONDS_SLOW if room.get("kind") == "fritz" else STUCK_SECONDS

    def stuck_info(self, room_id: str, entity_id: str) -> dict[str, Any] | None:
        """Hat das Thermostat einen gesendeten Wert noch nicht übernommen – und zwar schon zu lange?

        Nur Anzeige: erst nach STUCK_SECONDS (FRITZ!DECT: STUCK_SECONDS_SLOW), damit normale Funk-Verzögerungen
        kein Warnzeichen auslösen. Nicht erreichbare Geräte zeigt die Karte ohnehin als „nicht erreichbar“.
        """
        last = self._last_sent.get(f"{room_id}|{entity_id}")
        if not last or not last.get("since"):
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if (dt_util.utcnow() - last["since"]).total_seconds() < self._stuck_limit(room_id):
            return None
        want = last["want"]
        return {
            "since": last["since"].isoformat(),
            "tries": int(last.get("tries") or 1),
            "want_hvac": want.get("hvac"),
            "want_temp": want.get("temp"),
            "state": state.state,
            "temp": state.attributes.get(ATTR_TEMPERATURE),
        }

    def _check_stuck(self, room_id: str, key: str, entity_id: str) -> None:
        """Einmal pro Vorfall ins HA-Protokoll schreiben, sobald die Karte das rote ⚠ zeigt."""
        last = self._last_sent.get(key)
        if not last or last.get("warned") or not (info := self.stuck_info(room_id, entity_id)):
            return
        last["warned"] = True
        _LOGGER.warning(
            "HomeRhythm: %s übernimmt den Sollwert nicht – seit %s, %s (gesendet %s %s, Gerät meldet %s %s). "
            "Meist ein Funkproblem (Reichweite, Batterie, Zigbee-Netz).",
            entity_id, dt_util.as_local(last["since"]).strftime("%H:%M"),
            "1 Versuch" if info["tries"] == 1 else f"{info['tries']} Versuche",
            info["want_hvac"], info["want_temp"], info["state"], info["temp"],
        )

    def _clear_stuck(self, key: str, entity_id: str) -> None:
        last = self._last_sent.get(key)
        if not last or not last.get("since"):
            return
        if last.get("warned"):
            _LOGGER.info("HomeRhythm: %s hat den Sollwert jetzt übernommen", entity_id)
        for k in ("since", "tries", "warned"):
            last.pop(k, None)

    async def _async_send(self, key: str, entity_id: str, state, want: dict[str, Any], rule: str | None = None) -> None:
        ctx = Context()
        self._own_contexts.append(ctx.id)
        before = self._last_sent.get(key) or {}
        self._last_sent[key] = {
            "want": want,
            "at": dt_util.utcnow(),
            "rule": rule,
            "prev": (state.state, state.attributes.get(ATTR_TEMPERATURE)),  # alter Wert – träge Geräte melden ihn evtl. noch einmal
            # 0.9.16: seit wann ein gesendeter Wert nicht übernommen ist und wie oft gesendet wurde. Wechselt der Plan,
            # während das Gerät noch nicht reagiert, zählt das weiter (es ist dasselbe Problem).
            "since": before.get("since") or dt_util.utcnow(),
            "tries": int(before.get("tries") or 0) + 1,
            "warned": before.get("warned", False),
        }
        hvac_modes = state.attributes.get("hvac_modes") or []
        try:
            if want["hvac"] == "off":
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": "off"},
                    blocking=True, context=ctx,
                )
                return
            # Ein übrig gebliebenes Preset (z. B. "away" der alten Automation) würde unsere Temperatur verfälschen.
            preset = state.attributes.get("preset_mode")
            if preset and preset != "none" and "none" in (state.attributes.get("preset_modes") or []):
                await self.hass.services.async_call(
                    "climate", "set_preset_mode", {ATTR_ENTITY_ID: entity_id, "preset_mode": "none"},
                    blocking=True, context=ctx,
                )
            if state.state != want["hvac"] and want["hvac"] in hvac_modes:  # z. B. Klima auf Kühlen, TRV im Eigenprogramm
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": want["hvac"]},
                    blocking=True, context=ctx,
                )
            await self.hass.services.async_call(
                "climate", "set_temperature", {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: want["temp"]},
                blocking=True, context=ctx,
            )
            _LOGGER.debug("%s: %s gesetzt", entity_id, want)
        except Exception as err:  # noqa: BLE001 – ein Gerät darf die anderen nicht blockieren
            _LOGGER.warning("HomeRhythm konnte %s nicht setzen: %s", entity_id, err)

    # ------------------------------------------------------------------ Sicherung
    def export_config(self) -> dict[str, Any]:
        """Einrichtung als Datei (ohne Protokolle, Hand-Änderungen, Benutzernamen)."""
        rooms = {rid: {k: v for k, v in room.items() if k != "id"} for rid, room in self.rooms.items()}
        return {
            "home_rhythm": VERSION,
            "exported": dt_util.now().isoformat(),
            "rooms": rooms,
            "level_defs": self.level_defs,
            "flows": dict(self.runner.flows) if self.runner else {},
        }

    async def async_import_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sicherung einlesen. Jeder Raum und Ablauf wird wie beim Speichern geprüft."""
        if not isinstance(data, dict) or "home_rhythm" not in data:
            raise ValueError("Das ist keine Home-Rhythm-Sicherung")
        rooms, flows = data.get("rooms") or {}, data.get("flows") or {}
        if not isinstance(rooms, dict) or not isinstance(flows, dict) or len(rooms) > 100 or len(flows) > F.MAX_FLOWS:
            raise ValueError("Sicherung hat ein unerwartetes Format")
        if data.get("level_defs"):
            await self.async_save_levels(data["level_defs"])
        done_rooms, done_flows, errors = 0, 0, []
        for rid, room in rooms.items():
            try:
                if not isinstance(room, dict):
                    raise ValueError("falsches Format")
                await self.async_save_room({**room, "id": rid} if rid in self.rooms else {**room})
                done_rooms += 1
            except (ValueError, KeyError, TypeError, AttributeError) as err:
                errors.append(f"Raum {room.get('name', rid)}: {err}")
        for fid, flow in flows.items():
            try:
                if not isinstance(flow, dict):
                    raise ValueError("falsches Format")
                await self.runner.async_save_flow({**flow, "id": fid} if fid in self.runner.flows else {**flow, "id": None}, sync=False)
                done_flows += 1
            except (ValueError, KeyError, TypeError, AttributeError) as err:
                errors.append(f"Ablauf {flow.get('name', fid) if isinstance(flow, dict) else fid}: {err}")
        await self.runner.async_sync_native()
        return {"rooms": done_rooms, "flows": done_flows, "errors": errors[:20]}

    # ------------------------------------------------------------------ Hilfen für den FlowRunner
    def own_context(self) -> Context:
        """Kontext für eigene Befehle – so erkennt HomeRhythm sie später nicht als „fremd“."""
        ctx = Context()
        self._own_contexts.append(ctx.id)
        return ctx

    @callback
    def notify_update(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        self.hass.bus.async_fire(EVENT_UPDATED, {})

    def _device(self, device_id: str):
        return dr.async_get(self.hass).async_get(device_id)

    # ------------------------------------------------------------------ Sonne
    def sun_times(self, day) -> tuple[datetime, datetime]:
        """Sonnenaufgang/-untergang (lokal) für einen Tag – aus dem Standort von Home Assistant."""
        key = day.isoformat()
        if key not in self._sun_cache:
            from homeassistant.helpers.sun import get_astral_event_date  # noqa: PLC0415

            rise = get_astral_event_date(self.hass, "sunrise", day)
            sets = get_astral_event_date(self.hass, "sunset", day)
            tz = dt_util.get_default_time_zone()
            if rise is None or sets is None:  # Polartag/-nacht: feste Ersatzzeiten
                rise = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=7)
                sets = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=18)
            self._sun_cache[key] = (dt_util.as_local(rise), dt_util.as_local(sets))
            if len(self._sun_cache) > 40:
                self._sun_cache.pop(next(iter(self._sun_cache)))
        return self._sun_cache[key]

    def sun_for(self, day) -> F.Sun:
        rise, sets = self.sun_times(day)
        return F.Sun(rise.hour * 60 + rise.minute, sets.hour * 60 + sets.minute)

    def sun_year(self, year: int) -> dict[str, Any]:
        """Sonnenauf-/-untergang (Minute des Tages, lokal) für jeden Tag eines Jahres.

        Für das Jahresband im Zeitplan-Editor („frühestens 18:00 greift ca. 27.10.–27.1.“). Eigener Speicher je Jahr,
        damit der kleine Tages-Speicher von ``sun_times`` nicht verdrängt wird. Standort ändert sich praktisch nie –
        nach einem Neustart wird ohnehin neu gerechnet.
        """
        if year not in self._sun_year_cache:
            from homeassistant.helpers.sun import get_astral_event_date  # noqa: PLC0415

            rise_l: list[int] = []
            set_l: list[int] = []
            day = date(year, 1, 1)
            while day.year == year:
                rise = get_astral_event_date(self.hass, "sunrise", day)
                sets = get_astral_event_date(self.hass, "sunset", day)
                if rise is None or sets is None:  # Polartag/-nacht: wie sun_times
                    rise_l.append(7 * 60)
                    set_l.append(18 * 60)
                else:
                    r, s = dt_util.as_local(rise), dt_util.as_local(sets)
                    rise_l.append(r.hour * 60 + r.minute)
                    set_l.append(s.hour * 60 + s.minute)
                day += timedelta(days=1)
            self._sun_year_cache = {year: {"year": year, "rise": rise_l, "set": set_l}}  # nur ein Jahr merken
        return self._sun_year_cache[year]

    # ------------------------------------------------------------------ Hand-Änderungen
    def _note_heating(self, entity_id: str, state) -> None:
        """Wechsel heizt ↔ zu merken (für „seit …“, „% der letzten Stunde“ und den Hinweis „wird nicht wärmer“)."""
        if state is None:
            return
        action = state.attributes.get("hvac_action")
        if action not in ("heating", "idle", "off", "preheating"):
            return
        heating = action in ("heating", "preheating")
        log = self._heat_log.setdefault(entity_id, [])
        now = dt_util.utcnow()
        if not log or log[-1][1] != heating:
            log.append((now, heating))
            if heating:
                self._heat_start_temp[entity_id] = self._room_temp_for(entity_id)
        cut = now - timedelta(hours=2)
        while len(log) > 1 and log[1][0] <= cut:
            log.pop(0)

    def _room_temp_for(self, entity_id: str) -> float | None:
        for room in self.rooms.values():
            if entity_id in room_entities(room):
                r = self.room_reading(room)
                if r is not None and r.ok:
                    return r.value
        st = self.hass.states.get(entity_id)
        return _num(st.attributes.get("current_temperature")) if st else None

    def gone(self, entity_id: str) -> bool:
        """Thermostat gibt es in Home Assistant nicht mehr (gelöscht, kein Zustand, kein Registry-Eintrag)."""
        return self.hass.states.get(entity_id) is None and er.async_get(self.hass).async_get(entity_id) is None

    def heat_info(self, entity_id: str) -> dict[str, Any] | None:
        """heizt / zu, seit wann, Anteil der letzten Stunde (vom Gerät oder selbst gezählt), „wird nicht wärmer“."""
        log = self._heat_log.get(entity_id)
        if not log:
            return None
        now = dt_util.utcnow()
        heating, since = log[-1][1], log[-1][0]
        pct, source = None, None
        dev = self._device_heat_pct(entity_id)
        if dev is not None:
            pct, source = dev, "device"
        elif log[0][0] <= now - timedelta(minutes=15):
            start = now - timedelta(hours=1)
            on = 0.0
            for i, (t, h) in enumerate(log):
                a = max(t, start)
                b = log[i + 1][0] if i + 1 < len(log) else now
                if h and b > a:
                    on += (b - a).total_seconds()
            span = (now - max(log[0][0], start)).total_seconds()
            if span > 0:
                pct, source = round(on / span * 100), "counted"
        stuck = False
        if heating and now - since >= timedelta(hours=1):
            t0, t1 = self._heat_start_temp.get(entity_id), self._room_temp_for(entity_id)
            stuck = t0 is not None and t1 is not None and t1 - t0 < 0.3
        return {"heating": heating, "since": since.isoformat(), "pct": pct, "pct_source": source, "stuck": stuck}

    def _device_heat_pct(self, entity_id: str) -> float | None:
        reg = er.async_get(self.hass)
        e = reg.async_get(entity_id)
        if not e or not e.device_id:
            return None
        for x in er.async_entries_for_device(reg, e.device_id):
            if x.domain == "sensor" and "heat_percentage" in f"{x.entity_id} {x.unique_id or ''}".lower() and not x.disabled_by:
                st = self.hass.states.get(x.entity_id)
                return _num(st.state) if st else None
        return None

    @callback
    def _on_climate_change(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        self._note_heating(event.data["entity_id"], new)
        if old is None or new is None:
            return
        if new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        if old.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # Gerät kommt (wieder) online – keine Hand-Änderung, beim nächsten Abgleich neu senden
            for rid in self.rooms:
                self._last_sent.pop(f"{rid}|{event.data['entity_id']}", None)
            return
        if old.state == new.state and old.attributes.get(ATTR_TEMPERATURE) == new.attributes.get(ATTR_TEMPERATURE):
            return  # nur Ist-Temperatur o. Ä. geändert
        ctx = event.context
        if ctx.id in self._own_contexts or (ctx.parent_id and ctx.parent_id in self._own_contexts):
            return
        entity_id = event.data["entity_id"]
        if ctx.user_id and ctx.user_id not in self._user_names:
            self.hass.async_create_task(self._async_load_users())
        room_id = next((rid for rid, r in self.rooms.items() if entity_id in all_entities(r)), None)
        if room_id is None or not self.rooms[room_id].get("enabled", True):
            return
        last = self._last_sent.get(f"{room_id}|{entity_id}")
        if last:
            age = (dt_util.utcnow() - last["at"]).total_seconds()
            if age < GRACE_SECONDS and self._is_echo(new, last):
                return  # Echo eines eigenen Befehls von einem trägen Gerät
            if age < SLOW_ECHO_SECONDS and not ctx.user_id and not ctx.parent_id and self._is_old_value(new, last):
                return  # Fritz!DECT meldet nach dem Aufwachen noch einmal den alten Wert – keine Hand-Änderung
        result = self.dev_results.get(f"{room_id}|{entity_id}") or self.results.get(room_id)
        hvac = new.state if new.state in ("heat", "off", "cool", "dry", "fan_only", "heat_cool", "auto") else "heat"
        temp = new.attributes.get(ATTR_TEMPERATURE)
        want = self._desired(entity_id, result) if result else None
        if want and self._matches(new, want):
            return
        kind, name, ref = self._source_of(ctx)
        if kind == "device" and self._at_limit(new):
            # „Dauerhaft an“ (HA meldet bei Fritz!DECT 30 °C) oder Höchstwert ohne HA-Ursache – z. B. Boost am Gerät,
            # Fenster-/Frostlogik oder ein Regler darunter. Nicht als Hand-Änderung übernehmen und NICHT an die
            # anderen Thermostate des Raums weitergeben; nach RESYNC_SECONDS wird der Plan erneut gesendet.
            self._log_foreign(entity_id, kind, name, ref, new, note="nicht übernommen (Höchstwert)")
            key = f"{room_id}|{entity_id}"
            plan = self._desired(entity_id, result) if result else None
            if plan is not None:
                self._last_sent[key] = {**(self._last_sent.get(key) or {}), "want": plan, "at": dt_util.utcnow(), "rule": result.rule}
            _LOGGER.info("HomeRhythm: %s meldet Höchstwert ohne HA-Ursache – nicht als Hand-Änderung übernommen", entity_id)
            self.hass.async_create_task(self.async_save())
            return
        self._log_foreign(entity_id, kind, name, ref, new)
        is_ac = entity_id in room_acs(self.rooms[room_id])
        if result and (result.rule == E.RULE_SEASON or (result.rule in (E.RULE_AWAY, E.RULE_ABSENT) and not is_ac)):
            self.hass.async_create_task(self.async_save())
            return  # Sommer/Urlaub haben Vorrang, Gerät wird beim nächsten Abgleich zurückgesetzt
        # Klimaanlage unterwegs von Hand eingeschaltet (z. B. vorkühlen vor der Heimkehr): als Hand-Änderung merken,
        # damit sie bei der Ankunft nicht sofort vom Plan überschrieben wird.
        source = f"Automation „{name}“" if kind in ("automation", "script") and ref else name
        now = dt_util.now()
        mkey = self.manual_key(room_id, entity_id)
        room_temp = _num(temp)
        if room_temp is not None and entity_id in room_entities(self.rooms[room_id]) and (c := RT.correction(self.rooms[room_id])):
            room_temp = round(room_temp + c, 1)  # am Gerät gedreht: Gerätewert → Raumtemperatur (Korrektur herausrechnen)
        self.manual[mkey] = E.Manual(
            temperature=room_temp,
            hvac_mode=hvac,
            until=E.manual_until(
                self.rooms[room_id], now, E.effective_modes(self.rooms[room_id], self.modes(), now, self.overrides.get(room_id)), self.overrides.get(room_id)
            ),
            source=source,
            since=now,
        )
        # Das geänderte Gerät hat den Wert schon – nicht erneut senden.
        self._last_sent[f"{room_id}|{entity_id}"] = {
            "want": {"hvac": hvac, "temp": None if hvac == "off" else _num(temp)},
            "at": dt_util.utcnow() - timedelta(seconds=GRACE_SECONDS),
            "rule": result.rule if result and result.rule in (E.RULE_AWAY, E.RULE_ABSENT) else None,
        }
        _LOGGER.info("HomeRhythm: Hand-Änderung in %s an %s (%s)", room_id, entity_id, source)
        self.hass.async_create_task(self._async_after_manual())

    async def _async_after_manual(self) -> None:
        await self.async_save()
        await self.async_update(apply=True)  # gemeinsam gesteuert: weitere Thermostate im Raum ziehen nach

    def _source_of(self, ctx: Context) -> tuple[str, str, str | None]:
        """Wer hat geändert? (Art, Name, Entität/Benutzer-ID)"""
        # Automationen/Skripte rufen Dienste mit ihrem eigenen Lauf-Kontext auf (auch bei Zeit-Auslösern ohne parent_id).
        ids = {ctx.id, ctx.parent_id} - {None}
        for st in self.hass.states.async_all(["automation", "script"]):
            if st.context.id in ids:
                return st.domain, st.attributes.get("friendly_name") or st.entity_id, st.entity_id
        if ctx.user_id:
            return "user", self._user_names.get(ctx.user_id, "Benutzer"), ctx.user_id
        if ctx.parent_id:
            return "automation", "Automation / Skript", None
        return "device", "am Gerät / extern", None

    @staticmethod
    def _at_limit(state) -> bool:
        """Sollwert am oder über dem Höchstwert des Geräts (Fritz!DECT „an“ meldet HA als 30 °C bei max. 28 °C)."""
        if state.state == "off":
            return False
        try:
            return float(state.attributes.get(ATTR_TEMPERATURE)) >= float(state.attributes.get("max_temp"))
        except (TypeError, ValueError):
            return False

    def _is_old_value(self, new, last: dict[str, Any]) -> bool:
        """Meldet das Gerät genau den Wert von VOR unserem letzten Befehl?"""
        prev = last.get("prev")
        if prev is None or new.state != prev[0]:
            return False
        cur, prev_temp = new.attributes.get(ATTR_TEMPERATURE), prev[1]
        if cur is None or prev_temp is None:
            return cur == prev_temp
        try:
            return abs(float(cur) - float(prev_temp)) <= self._tolerance(new)
        except (TypeError, ValueError):
            return False

    def _log_foreign(self, entity_id: str, kind: str, name: str, ref: str | None, new, note: str | None = None) -> None:
        try:
            temp = float(new.attributes.get(ATTR_TEMPERATURE))
            t = f"{temp:g} °C"
            hi = new.attributes.get("max_temp")
            if hi is not None and temp > float(hi):
                t = "dauerhaft an"  # z. B. Fritz!DECT „ON“ – HA meldet einen Wert über dem Höchstwert
        except (TypeError, ValueError):
            t = None
        if new.state == "off":
            value = "aus"
        elif t is None:
            value = new.state
        else:
            value = t if new.state == "heat" else f"{new.state} {t}"
        now = dt_util.now()
        log = self.foreign_log.setdefault(entity_id, [])
        entry = {"at": now.isoformat(), "kind": kind, "name": name, "ref": ref, "value": value, "minute": now.hour * 60 + now.minute}
        if note:
            entry["note"] = note
        log.append(entry)
        del log[:-40]

    # ------------------------------------------------------------------ Hinweise auf fremde Steuerung
    def _underlying(self, entity_id: str) -> list[str]:
        return [dev for dev, wrapper in self.bt_wrapped().items() if wrapper == entity_id]

    def _users_of(self, entity_id: str) -> list[dict[str, Any]]:
        """Automationen, Skripte und Szenen, die das Gerät (oder das Gerät unter BT/VT) verwenden – von HA ermittelt."""
        out: dict[str, dict[str, Any]] = {}
        ent_reg = er.async_get(self.hass)
        targets = [entity_id] + self._underlying(entity_id)
        try:
            from homeassistant.components.automation import automations_with_device, automations_with_entity  # noqa: PLC0415
            from homeassistant.components.script import scripts_with_device, scripts_with_entity  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            return []
        try:
            from homeassistant.components.homeassistant.scene import scenes_with_entity  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            scenes_with_entity = None
        for target in targets:
            found: list[str] = []
            for fn in (automations_with_entity, scripts_with_entity, scenes_with_entity):
                if fn is None:
                    continue
                try:
                    found += fn(self.hass, target)
                except Exception:  # noqa: BLE001 – Komponente nicht geladen
                    continue
            entry = ent_reg.async_get(target)
            if entry and entry.device_id:
                for fn in (automations_with_device, scripts_with_device):
                    try:
                        found += fn(self.hass, entry.device_id)
                    except Exception:  # noqa: BLE001
                        continue
            for user in found:
                if user in out or user.startswith("climate."):
                    continue
                st = self.hass.states.get(user)
                out[user] = {
                    "id": f"use:{entity_id}:{user}",
                    "entity_id": entity_id,
                    "kind": "static",
                    "source": user,
                    "config_id": st.attributes.get("id") if st else None,
                    "text": f"{ {'automation': 'Automation', 'script': 'Skript', 'scene': 'Szene'}.get(user.split('.')[0], user.split('.')[0]) } „{(st.attributes.get('friendly_name') if st else None) or user}“ verwendet "
                    + ("dieses Gerät" if target == entity_id else f"direkt {self._name(target)} (am Regler vorbei)")
                    + " – prüfen, ob sie es nur beobachtet oder auch verstellt",
                }
        return list(out.values())

    def _recurring(self, entity_id: str) -> list[dict[str, Any]]:
        """Fremde Änderungen, die an mindestens 3 Tagen etwa zur gleichen Uhrzeit kommen → vermutlich ein Zeitplan."""
        cutoff = dt_util.now() - timedelta(days=14)
        entries = []
        for e in self.foreign_log.get(entity_id, []):
            t = dt_util.parse_datetime(e["at"])
            if t and t >= cutoff and e["kind"] in ("device", "automation", "script"):
                entries.append((t, e))

        def near(a: int, b: int) -> bool:
            d = abs(a - b) % 1440
            return min(d, 1440 - d) <= 15  # auch über Mitternacht

        best: dict[tuple, tuple[set, int, dict]] = {}
        for t, e in entries:
            key = (e["kind"], e.get("ref"))
            days = {t2.date() for t2, e2 in entries if (e2["kind"], e2.get("ref")) == key and near(e2["minute"], e["minute"])}
            if len(days) >= 3 and (key not in best or len(days) > len(best[key][0])):
                best[key] = (days, e["minute"], e)
        hints = []
        for (kind, ref), (days, minute, e) in best.items():
            slot = int(round(minute / 15) * 15) % 1440
            hm = f"{slot // 60:02d}:{slot % 60:02d}"
            if kind == "device":
                text = f"Wird an {len(days)} Tagen gegen {hm} ohne HA-Ursache verstellt – vermutlich Zeitplan in der Fritz!Box oder am Gerät"
            else:
                text = f"„{e['name']}“ verstellt an {len(days)} Tagen gegen {hm}"
            # ID ohne Uhrzeit: ein Hinweis je Quelle, bleibt ausgeblendet, auch wenn sich die Uhrzeit leicht verschiebt
            hints.append({"id": f"rec:{entity_id}:{kind}:{ref or ''}", "entity_id": entity_id, "kind": "recurring", "text": text, "source": ref})
        return hints

    def hints_for(self, room: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for eid in all_entities(room):
            for h in self._users_of(eid) + self._recurring(eid):
                if h["id"] not in self.dismissed:
                    out.append(h)
        return out

    async def async_set_start_tab(self, tab: str) -> None:
        if tab not in START_TABS:
            raise ValueError("Unbekannter Reiter")
        self.start_tab = tab
        await self.async_save()
        self.hass.bus.async_fire(EVENT_UPDATED, {})

    async def async_dismiss_hint(self, hint_id: str) -> None:
        self.dismissed.add(hint_id)
        await self.async_save()
        self.hass.bus.async_fire(EVENT_UPDATED, {})

    async def async_reset_hints(self, room_id: str) -> None:
        room = self.rooms.get(room_id) or {}
        ents = all_entities(room)
        self.dismissed = {h for h in self.dismissed if not any(f":{e}:" in h for e in ents) and not h.startswith(f"kind:{room_id}:")}
        await self.async_save()
        self.hass.bus.async_fire(EVENT_UPDATED, {})

    def _is_echo(self, new, last: dict[str, Any]) -> bool:
        """Meldet das Gerät nur unseren Befehl oder noch den alten Wert? Alles andere ist eine echte Änderung."""
        if self._matches(new, last["want"]):
            return True
        prev = last.get("prev")
        if prev is None:
            return True
        prev_state, prev_temp = prev
        if new.state != prev_state:
            return False
        cur = new.attributes.get(ATTR_TEMPERATURE)
        if cur is None or prev_temp is None:
            return cur == prev_temp
        try:
            return abs(float(cur) - float(prev_temp)) <= self._tolerance(new)
        except (TypeError, ValueError):
            return cur == prev_temp

    def _forget_sent(self, room_id: str) -> None:
        for key in [k for k in self._last_sent if k.startswith(f"{room_id}|")]:
            self._last_sent.pop(key, None)

    def _forget_manual(self, room_id: str) -> None:
        for key in [k for k in self.manual if k == room_id or k.startswith(f"{room_id}|")]:
            self.manual.pop(key, None)

    async def async_clear_manual(self, room_id: str) -> None:
        self._forget_manual(room_id)
        self._forget_sent(room_id)
        await self.async_save()
        await self.async_update(apply=True)

    # ------------------------------------------------------------------ Räume verwalten
    async def async_save_room(self, data: dict[str, Any]) -> str:
        room_id = data.get("id") or slugify_id(data.get("area_id") or data.get("name", "raum"))
        if not data.get("id"):
            base, i = room_id, 2
            while room_id in self.rooms:
                room_id, i = f"{base}_{i}", i + 1
        old = self.rooms.get(room_id, {})
        room = {
            "id": room_id,
            "name": data.get("name") or old.get("name") or room_id,
            "area_id": data.get("area_id", old.get("area_id")),
            "climate_entities": self._entities_from(data, old),
            "levels": self._levels(data.get("levels") or old.get("levels") or E.DEFAULT_LEVEL_TEMPS),
            "default_level": data.get("default_level") or old.get("default_level") or "absenkung",
            "schedule": E.normalize_schedule(data.get("schedule") if "schedule" in data else old.get("schedule")),
            "manual_mode": str(data.get("manual_mode") or old.get("manual_mode") or E.MANUAL_NEXT),
            "enabled": bool(data.get("enabled", old.get("enabled", True))),
            "linked": bool(data.get("linked", old.get("linked", True))),
            "party_room": bool(data.get("party_room", old.get("party_room", False))),
            "humidity_entity": str(data.get("humidity_entity", old.get("humidity_entity", "")) or ""),
            "rules": E.normalize_rules(data.get("rules") if "rules" in data else old.get("rules")),
        }
        room["ac_entities"] = list(dict.fromkeys(e for e in (data.get("ac_entities", room_acs(old)) or []) if e))
        room["ac"] = self._normalize_ac(data.get("ac", old.get("ac")))
        if set(room["ac_entities"]) & set(room["climate_entities"]):
            raise ValueError("Ein Gerät kann nicht gleichzeitig Heizkörper und Klimaanlage sein")
        offs = data.get("offsets", old.get("offsets")) or {}
        room["offsets"] = {
            e: max(-5.0, min(5.0, float(v))) for e, v in offs.items() if e in all_entities(room) and v not in (None, "") and float(v)
        }
        self._validate_entities(room_id, all_entities(room))
        # 0.9.5: Art, Temperaturquelle, Korrektur – fehlt etwas, bleibt es beim bisherigen Verhalten
        room.update(RT.normalize(data, old, self.derive_kind(room)))
        room["controls"] = CT.normalize(data["controls"] if "controls" in data else old.get("controls"), all_entities(room), self.hass)
        if room["default_level"] not in E.PLAN_LEVELS:
            raise ValueError("Unbekannte Standard-Stufe")
        is_new = room_id not in self.rooms
        entity_changed = all_entities(old) != all_entities(room)
        if old and old.get("linked", True) != room["linked"]:
            self._forget_manual(room_id)  # Hand-Änderungen passen nicht mehr zum neuen Modus
        self.rooms[room_id] = room
        self._forget_sent(room_id)
        await self.async_save()
        if is_new or entity_changed:
            self._track_climates()
        elif old.get("controls") != room["controls"]:
            self.controls.track()
        if is_new:
            async_dispatcher_send(self.hass, f"{SIGNAL_UPDATED}_new", room_id)
        await self.async_update(apply=True)
        return room_id

    @staticmethod
    def _levels(levels: Any) -> dict[str, float]:
        if not isinstance(levels, dict):
            raise ValueError("Stufen-Temperaturen fehlen")
        out = {}
        for k, v in levels.items():
            if v in (None, ""):
                continue
            t = float(v)
            if not 5 <= t <= 30:
                raise ValueError(f"{E.LEVEL_NAMES.get(k, k)}: {t:g} °C liegt außerhalb 5…30 °C")
            out[k] = t
        return out

    @staticmethod
    def _normalize_ac(ac: dict[str, Any] | None) -> dict[str, Any]:
        ac = {**DEFAULT_AC, **(ac or {})}
        if ac["mode"] not in E.AC_MODES:
            raise ValueError("Unbekannte Einstellung für die Klimaanlage")
        out = {
            "mode": ac["mode"],
            "cop": E.normalize_cop_points(ac["cop"]),
            "min_outdoor": None if ac.get("min_outdoor") in (None, "") else float(ac["min_outdoor"]),
            "night_off": bool(ac.get("night_off", True)),
            "reserve": max(0.0, min(10.0, float(ac["reserve"] if ac.get("reserve") is not None else DEFAULT_AC["reserve"]))),
            "cooling": E.normalize_cooling(ac.get("cooling")),
            "boost_after": max(5, min(240, int(ac["boost_after"] if ac.get("boost_after") is not None else DEFAULT_AC["boost_after"]))),
        }
        return out

    @staticmethod
    def _entities_from(data: dict[str, Any], old: dict[str, Any]) -> list[str]:
        if "climate_entities" in data:
            ents = data["climate_entities"] or []
        elif data.get("climate_entity"):
            ents = [data["climate_entity"]]
        else:
            ents = room_entities(old)
        return list(dict.fromkeys(str(e) for e in ents if e))  # Reihenfolge behalten, doppelte raus

    def _validate_entities(self, room_id: str, entities: list[str]) -> None:
        if not entities:
            raise ValueError("Kein Thermostat gewählt")
        wrapped = self.bt_wrapped()
        for eid in entities:
            if not eid.startswith("climate."):
                raise ValueError(f"{eid} ist kein Thermostat")
            for rid, other in self.rooms.items():
                if rid != room_id and eid in all_entities(other):
                    raise ValueError(f"{self._name(eid)} gehört schon zu Raum „{other['name']}“")
            if eid in wrapped:
                raise ValueError(
                    f"{self._name(eid)} wird schon von „{self._name(wrapped[eid])}“ ({self.wrapper_kind(wrapped[eid])}) geregelt – "
                    f"bitte diese Entität wählen, sonst stellen beide dasselbe Gerät"
                )

    def _name(self, entity_id: str) -> str:
        st = self.hass.states.get(entity_id)
        return tidy_name((st.attributes.get("friendly_name") if st else None) or entity_id)

    def bt_wrapped(self) -> dict[str, str]:
        """Echte Geräte, die in einem (aktiven) Better/Versatile Thermostat stecken: Gerät → Regler-Entität."""
        out: dict[str, str] = {}
        ent_reg = er.async_get(self.hass)
        for entry in ent_reg.entities.values():
            if entry.domain != "climate" or entry.platform not in WRAPPERS or entry.disabled_by:
                continue
            cfg = self.hass.config_entries.async_get_entry(entry.config_entry_id) if entry.config_entry_id else None
            if cfg is None:
                continue
            conf = {**cfg.data, **(cfg.options or {})}
            if entry.platform == "better_thermostat":
                items = conf.get("thermostat") or []
                if isinstance(items, (str, dict)):
                    items = [items]
                found = [i.get("trv") if isinstance(i, dict) else i for i in items]
            else:  # versatile_thermostat: neue Versionen "underlying_entity_ids", ältere climate_entity_id … 4
                found = list(conf.get("underlying_entity_ids") or [])
                found += [conf.get(k) for k in ("climate_entity_id", "climate_entity2_id", "climate_entity3_id", "climate_entity4_id")]
            for dev in found:
                if isinstance(dev, str) and dev.startswith("climate.") and dev != entry.entity_id:
                    out[dev] = entry.entity_id
        return out

    def wrapper_kind(self, entity_id: str) -> str | None:
        entry = er.async_get(self.hass).async_get(entity_id)
        return WRAPPERS.get(entry.platform) if entry else None

    async def async_save_levels(self, defs: dict[str, Any]) -> None:
        new = E.normalize_level_defs(defs)
        for key, d in new.items():
            if d["enabled"]:
                continue
            users = [r["name"] for r in self.rooms.values() if key in E.levels_in_use(r)]
            if users:
                raise ValueError(f"„{self.level_defs[key]['name']}“ wird noch verwendet in: {', '.join(users)}")
        self.level_defs = new
        E.apply_level_defs(new)
        await self.async_save()
        await self.async_update(apply=True)

    # ------------------------------------------------------------------ Luftfeuchte und Batterien
    def _area_of(self, entry) -> str | None:
        if entry.area_id:
            return entry.area_id
        if entry.device_id and (dev := dr.async_get(self.hass).async_get(entry.device_id)):
            return dev.area_id
        return None

    def _is_humidity(self, entity_id: str) -> bool:
        st = self.hass.states.get(entity_id)
        if st is not None and st.attributes.get("device_class") == "humidity":
            return True
        e = er.async_get(self.hass).async_get(entity_id)
        return bool(e and (e.device_class or e.original_device_class) == "humidity")

    def _alive(self, entity_id: str | None) -> bool:
        st = self.hass.states.get(entity_id) if entity_id else None
        if st is None:
            return False
        if entity_id.startswith("climate."):
            return _num(st.attributes.get("current_humidity")) is not None
        return _num(st.state) is not None

    def _device_humidity(self, entity_id: str | None) -> list[str]:
        """Feuchtesensoren am selben Gerät wie entity_id (z. B. FRITZ!DECT 440, SNZB-02, TRV)."""
        if not entity_id:
            return []
        ent_reg = er.async_get(self.hass)
        e = ent_reg.async_get(entity_id)
        if not e or not e.device_id:
            return []
        return sorted(x.entity_id for x in er.async_entries_for_device(ent_reg, e.device_id) if x.domain == "sensor" and not x.disabled_by and self._is_humidity(x.entity_id))

    def _wrapper_conf(self, entity_id: str) -> dict[str, Any]:
        e = er.async_get(self.hass).async_get(entity_id)
        if not e or e.platform not in WRAPPERS or not e.config_entry_id:
            return {}
        cfg = self.hass.config_entries.async_get_entry(e.config_entry_id)
        return {**cfg.data, **(cfg.options or {})} if cfg else {}

    def humidity_candidates(self, room: dict[str, Any]) -> list[tuple[str, str]]:
        """Feuchtequellen in Vorrang-Reihenfolge: (Entität, Herkunft)."""
        out: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(eid: Any, why: str) -> None:
            if isinstance(eid, str) and eid and eid not in seen:
                seen.add(eid)
                out.append((eid, why))

        wrapped = self.bt_wrapped()
        climates = list(room_entities(room)) + list(room_acs(room))
        # 1. Better Thermostat / Versatile Thermostat: eingetragener Feuchte- bzw. Temperatursensor
        for c in climates:
            conf = self._wrapper_conf(c)
            if not conf:
                continue
            kind = self.wrapper_kind(c)
            for key in ("humidity_sensor", "humidity_sensor_id", "humidity_sensor_entity_id"):
                add(conf.get(key), f"{kind}-Feuchtesensor")
            for key in ("temperature_sensor", "temperature_sensor_id", "temperature_sensor_entity_id"):
                for h in self._device_humidity(conf.get(key) if isinstance(conf.get(key), str) else None):
                    add(h, f"Raumsensor von {kind}")
            add(c, kind)  # Feuchte-Attribut des Reglers (BT übernimmt den Raumsensor)
        # 2. Thermostat-Geräte selbst (FRITZ!DECT, TRV) – auch die unter BT/VT
        devices = climates + [d for d, w in wrapped.items() if w in climates]
        for c in devices:
            for h in self._device_humidity(c):
                add(h, "am Thermostat")
            add(c, "Thermostat")
        # 3. Sensoren im Bereich: FRITZ!DECT zuerst, dann Geräte mit Temperatur (Raumsensoren), dann der Rest
        if room.get("area_id"):
            ent_reg = er.async_get(self.hass)
            area = [e for e in ent_reg.entities.values() if e.domain == "sensor" and not e.disabled_by and self._area_of(e) == room["area_id"] and self._is_humidity(e.entity_id)]

            def rank(e) -> tuple:
                has_temp = bool(e.device_id) and any(
                    (x.device_class or x.original_device_class) == "temperature" for x in er.async_entries_for_device(ent_reg, e.device_id)
                )
                return (e.platform != "fritzbox", not has_temp, e.entity_id)

            for e in sorted(area, key=rank):
                add(e.entity_id, "im Bereich")
        return out

    def humidity_entity(self, room: dict[str, Any]) -> str | None:
        """Feuchtequelle des Raums: eingestellt, sonst BT/VT- bzw. FRITZ!DECT-Sensor, sonst Raumsensor im Bereich."""
        chosen = room.get("humidity_entity")
        if chosen == "none":
            return None
        if chosen:
            return chosen
        for eid, _why in self.humidity_candidates(room):
            if self._alive(eid):
                return eid
        return None

    def _humidity(self, room: dict[str, Any]) -> dict[str, Any] | None:
        eid = self.humidity_entity(room)
        st = self.hass.states.get(eid) if eid else None
        if st is None:
            return None
        value = _num(st.attributes.get("current_humidity")) if eid.startswith("climate.") else _num(st.state)
        why = next((w for e, w in self.humidity_candidates(room) if e == eid), None) if not room.get("humidity_entity") else "gewählt"
        return {"entity_id": eid, "value": value, "auto": not room.get("humidity_entity"), "source": why,
                "name": st.attributes.get("friendly_name") or eid}

    def devices_of(self, room: dict[str, Any]) -> list[dict[str, Any]]:
        """Geräte des Raums mit Batterie und Erreichbarkeit: Thermostate, Geräte unter BT/VT, Raumsensoren."""
        ent_reg, dev_reg = er.async_get(self.hass), dr.async_get(self.hass)
        roles: dict[str, tuple[str, str]] = {}  # device_id → (Rolle, Haupt-Entität)
        acs = set(room_acs(room))
        for eid in all_entities(room):
            e = ent_reg.async_get(eid)
            if e and e.device_id:
                kind = "Regler (" + WRAPPERS[e.platform] + ")" if e.platform in WRAPPERS else ("Klimaanlage" if eid in acs else "Thermostat")
                roles.setdefault(e.device_id, (kind, eid))
            for dev_eid in self._underlying(eid):
                u = ent_reg.async_get(dev_eid)
                if u and u.device_id:
                    roles.setdefault(u.device_id, ("Thermostat" if eid not in acs else "Klimaanlage", dev_eid))
        if room.get("area_id"):
            for e in ent_reg.entities.values():
                if (
                    e.domain == "sensor"
                    and e.device_id
                    and not e.disabled_by
                    and (e.device_class or e.original_device_class) in ("temperature", "humidity")
                    and self._area_of(e) == room["area_id"]
                ):
                    roles.setdefault(e.device_id, ("Sensor", e.entity_id))
        if hum := self.humidity_entity(room):
            h = ent_reg.async_get(hum)
            if h and h.device_id:
                roles.setdefault(h.device_id, ("Sensor", hum))
        for eid in [*(room.get("temp_sensors") or []), room.get("box_sensor") or ""]:  # gewählte Raumsensoren, auch aus anderen Bereichen
            e = ent_reg.async_get(eid) if eid else None
            if e and e.device_id:
                roles.setdefault(e.device_id, ("Sensor", eid))
        for c in self.controls.controls_of(room):  # Bedienteile (W100, Taster) des Raums
            if c.get("device_id") and not str(c["device_id"]).startswith("entity:"):
                roles.setdefault(c["device_id"], ("Bedienteil", c.get("display") or ""))
        out = self.device_infos(roles)
        for d in out:
            d["uses"] = self._room_uses(room, d["device_id"])
        return out

    def _device_entities(self, device_id: str | None) -> set[str]:
        if not device_id:
            return set()
        ent_reg = er.async_get(self.hass)
        return {e.entity_id for e in er.async_entries_for_device(ent_reg, device_id)}

    def _room_uses(self, room: dict[str, Any], device_id: str | None) -> list[dict[str, Any]]:
        """Wofür benutzt HomeRhythm dieses Gerät? (Heizung: Rolle im Raum; Abläufe kommen in uses_flows dazu)."""
        ents = self._device_entities(device_id)
        uses: list[dict[str, Any]] = []
        name = room["name"]
        rid = room.get("id") or next((k for k, v in self.rooms.items() if v is room), None)

        def add(text: str) -> None:
            uses.append({"kind": "heat", "text": f"Heizung {name}: {text}", "room": rid})

        if ents & set(room_acs(room)):
            add("Klimaanlage")
        elif ents & set(all_entities(room)) or any(ents & set(self._underlying(e)) for e in all_entities(room)):
            add("Thermostat" + (" (pausiert)" if not room.get("enabled", True) else ""))
        if ents & set(room.get("temp_sensors") or []) or (room.get("box_sensor") and room["box_sensor"] in ents):
            add("Raumsensor" + (" · beobachten" if room.get("correction") == "observe" else ""))
        if (hum := self.humidity_entity(room)) and hum in ents and not uses:
            add("Luftfeuchte")
        if any(c.get("device_id") == device_id for c in self.controls.controls_of(room)):
            add("Bedienteil")
        return uses + self._flow_uses(ents, device_id)

    def _flow_uses(self, ents: set[str], device_id: str | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if self.runner is None:
            return out
        for fid, f in self.runner.flows.items():
            mine = set(self.runner.resolve(f) if f["type"] == "plan" else []) | set(self.runner._entities_of(f))  # noqa: SLF001
            if ents & mine:
                kind = "Reaktion" if f["type"] == "react" else "Zeitplan"
                out.append({"kind": "flow", "text": f"{kind} {f['name']}", "flow": fid, "icon": f.get("icon") or "", "off": not f["enabled"]})
            b = f.get("button") or {}
            if device_id and b.get("device_id") == device_id:
                out.append({"kind": "flow", "text": f"Taster für {f['name']}", "flow": fid, "icon": "🔘", "off": not f["enabled"]})
        if ents & set(self.options.get(CONF_OUTDOOR_ENTITIES) or []):
            out.append({"kind": "heat", "text": "Außentemperatur (Jahreszeit, Energie)", "room": None})
        return out

    def device_infos(self, roles: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
        """Batterie und Erreichbarkeit je Gerät. roles: Geräte-ID → (Rolle, Haupt-Entität)."""
        ent_reg, dev_reg = er.async_get(self.hass), dr.async_get(self.hass)
        by_device: dict[str, list] = {}
        for e in ent_reg.entities.values():
            if e.device_id in roles and not e.disabled_by:
                by_device.setdefault(e.device_id, []).append(e)
        out = []
        for device_id, (kind, main) in roles.items():
            dev = dev_reg.async_get(device_id)
            level, low, bat_entity = None, None, None
            for e in by_device.get(device_id, []):
                dc = e.device_class or e.original_device_class
                st = self.hass.states.get(e.entity_id)
                if dc != "battery" or st is None:
                    continue
                if e.domain == "sensor" and (v := _num(st.state)) is not None:
                    level, bat_entity = v, e.entity_id
                elif e.domain == "binary_sensor" and st.state in ("on", "off"):
                    low = st.state == "on"
                    bat_entity = bat_entity or e.entity_id
            if low is None and level is not None:
                low = level <= BATTERY_LOW
            st = self.hass.states.get(main)
            out.append(
                {
                    "device_id": device_id,
                    "name": (dev.name_by_user or dev.name) if dev else main,
                    "model": dev.model if dev else None,
                    "role": kind,
                    "entity_id": main,
                    "battery": level,
                    "battery_low": bool(low),
                    "battery_entity": bat_entity,
                    "available": bool(st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)),
                    "last_changed": st.last_changed.isoformat() if st else None,
                }
            )
        order = {"Thermostat": 0, "Klimaanlage": 1, "Sensor": 3}
        return sorted(out, key=lambda d: (order.get(d["role"], 2), d["name"] or ""))

    async def async_delete_room(self, room_id: str) -> None:
        self.rooms.pop(room_id, None)
        self._forget_manual(room_id)
        self.results.pop(room_id, None)
        self.sources.pop(room_id, None)
        self._cold_since.pop(room_id, None)
        self.overrides.pop(room_id, None)
        self.observations.pop(room_id, None)  # Beobachtungen gehören zum Raum (Datenschutz: mit löschen)
        await self.async_save()
        self._track_climates()
        ent_reg = er.async_get(self.hass)
        if entity_id := ent_reg.async_get_entity_id("sensor", "home_rhythm", f"{self.entry.entry_id}_{room_id}"):
            ent_reg.async_remove(entity_id)
        if entity_id := ent_reg.async_get_entity_id("select", "home_rhythm", f"{self.entry.entry_id}_{room_id}_today"):
            ent_reg.async_remove(entity_id)
        await self.async_update(apply=False)

    # ------------------------------------------------------------------ Daten für die Karte
    def _result_dict(self, room_id: str) -> dict[str, Any]:
        return self._res(self.results.get(room_id))

    @staticmethod
    def _res(r: E.Result | None) -> dict[str, Any]:
        if r is None:
            return {}
        return {
            "level": r.level,
            "level_name": E.LEVEL_NAMES.get(r.level, r.level),
            "temperature": r.temperature,
            "hvac_mode": r.hvac_mode,
            "rule": r.rule,
            "reason": r.reason,
            "until": r.until.isoformat() if r.until else None,
            "next_level": r.next_level,
            "next_level_name": E.LEVEL_NAMES.get(r.next_level) if r.next_level else None,
        }

    def room_temp_entities(self, room: dict[str, Any]) -> tuple[str, list[str]]:
        """Fühler, mit denen der Raum gemessen wird: (Quelle, Entitäten) – „sensors“, „box“, „integration“ oder „device“."""
        src = room.get("temp_source", "device")
        if src == "sensors" and room.get("temp_sensors"):
            return "sensors", list(room["temp_sensors"])
        if src == "box" and room.get("box_sensor"):
            return "box", [room["box_sensor"]]
        try:
            sensor = self._integration_sensor(room)
        except Exception:  # noqa: BLE001 – reine Anzeige
            sensor = None
        if sensor:
            return "integration", [sensor]
        return "device", []

    def rooms_light(self) -> list[dict[str, Any]]:
        """0.9.13: leichte Raumliste für andere Karten (HomeCockpit) – ohne Verlauf, Hinweise, Geräte."""
        out = []
        now = dt_util.utcnow()
        for room_id, room in self.rooms.items():
            ents = all_entities(room)
            states = {e: self.hass.states.get(e) for e in ents}
            bad = [e for e, st in states.items() if st is None or st.state in ("unavailable", "unknown")]
            rads = [e for e in room_entities(room) if e not in bad] or [e for e in ents if e not in bad]
            cur = [float(v) for e in rads if (v := states[e].attributes.get("current_temperature")) is not None]
            ist = round(sum(cur) / len(cur), 1) if cur else None
            try:
                reading = self.room_reading(room, now)
            except Exception:  # noqa: BLE001 – reine Anzeige
                reading = None
            if reading is not None and reading.value is not None:
                ist = round(reading.value, 1)
            res = self._result_dict(room_id)
            m = self.manual.get(room_id) or next((v for k, v in self.manual.items() if k.startswith(f"{room_id}|")), None)
            src, temp_ents = self.room_temp_entities(room)
            out.append({
                "id": room_id,
                "name": room.get("name") or room_id,
                "area_id": room.get("area_id"),
                "enabled": bool(room.get("enabled", True)),
                "climate_entities": list(room.get("climate_entities") or []),
                "ac_entities": room_acs(room),
                "room_temp_entities": temp_ents,
                "room_temp_source": src,
                "ist": ist,
                "soll": None if res.get("hvac_mode") == "off" else res.get("temperature"),
                "hvac_mode": res.get("hvac_mode"),
                "level": res.get("level"),
                "level_name": res.get("level_name"),
                "manual_until": m.until.isoformat() if m else None,
                "unavailable": bool(bad) and bool(ents),
                # 0.9.16: ein Thermostat übernimmt den gesendeten Sollwert seit Minuten nicht (z. B. Funkproblem)
                "not_taken": any(self.stuck_info(room_id, e) for e in ents),
            })
        return out

    def snapshot(self) -> dict[str, Any]:
        hass = self.hass
        area_reg, floor_reg = ar.async_get(hass), fr.async_get(hass)
        dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
        modes = self.modes()
        rooms = []
        for room_id, room in self.rooms.items():
            devs = []
            acs = set(room_acs(room))
            for eid in all_entities(room):
                st = hass.states.get(eid)
                devs.append(
                    {
                        "entity_id": eid,
                        "state": st.state if st else "unavailable",
                        "current_temperature": st.attributes.get("current_temperature") if st else None,
                        "temperature": st.attributes.get(ATTR_TEMPERATURE) if st else None,
                        "hvac_action": st.attributes.get("hvac_action") if st else None,
                        "name": (st.attributes.get("friendly_name") if st else None) or (f"{eid} (gelöscht)" if self.gone(eid) else eid),
                        "offset": (room.get("offsets") or {}).get(eid, 0),
                        "role": "ac" if eid in acs else "radiator",
                        "result": self._res(self.dev_results.get(f"{room_id}|{eid}")),
                        "heat": None if (g := self.gone(eid)) else self.heat_info(eid),
                        "not_taken": self.stuck_info(room_id, eid),
                        "gone": g,
                    }
                )
            ok = [d for d in devs if d["state"] not in ("unavailable", "unknown")]
            rad = [d for d in ok if d["role"] == "radiator"] or ok
            cur = [float(d["current_temperature"]) for d in rad if d["current_temperature"] is not None]
            targets = {d["temperature"] for d in rad if d["state"] != "off"}
            try:
                rt = self.room_temp_info(room_id, room)
            except Exception:  # noqa: BLE001 – reine Anzeige: darf die Karte nie leer machen
                _LOGGER.exception("HomeRhythm: Raumtemperatur-Anzeige für %s fehlgeschlagen", room_id)
                rt = {"kind": room.get("kind"), "source": "device", "correction": "none", "correction_value": 0, "value": None,
                      "sensors": [], "integration_sensor": None, "push": [], "observe": None, "checks": []}
            if rt["value"] is not None:
                cur = [rt["value"]]  # Raumsensor(en) bzw. Sensor der Fritz!Box statt Fühler am Thermostat
            climate = {
                "state": "unavailable" if not ok else ("off" if all(d["state"] == "off" for d in ok) else "heat"),
                "some_unavailable": len(ok) < len(devs),
                "current_temperature": round(sum(cur) / len(cur), 1) if cur else None,
                "temperature": next(iter(targets)) if len(targets) == 1 else None,
                "hvac_action": "heating" if any(d["hvac_action"] == "heating" for d in ok) else (ok[0]["hvac_action"] if ok else None),
                "name": ", ".join(d["name"] for d in devs),
            }
            m = self.manual.get(room_id) or next(
                (v for k, v in self.manual.items() if k.startswith(f"{room_id}|")), None
            )
            rooms.append(
                {
                    **room,
                    "result": self._result_dict(room_id),
                    "today": self.today_info(room_id),
                    "room_temp": rt,
                    "rule_texts": [E.rule_text(x) for x in room.get("rules") or []],
                    "active_rule": E.rule_text(ar_) if (ar_ := E.matching_rule(room, modes)) else None,
                    "manual": {
                        "temperature": m.temperature,
                        "hvac_mode": m.hvac_mode,
                        "until": m.until.isoformat(),
                        "source": m.source,
                    }
                    if m
                    else None,
                    "climate": climate,
                    "energy": self.room_energy.get(room_id),
                    "hints": self.hints_for(room),
                    "kind_hint": self.kind_hint(room),
                    "humidity": self._humidity(room),
                    "devices": self.devices_of(room),
                    "dismissed_count": sum(1 for h in self.dismissed if any(f":{e}:" in h for e in all_entities(room)) or h.startswith(f"kind:{room_id}:")),
                    "foreign": sorted(
                        ({**e, "entity_id": eid} for eid in all_entities(room) for e in self.foreign_log.get(eid, [])),
                        key=lambda e: e["at"],
                        reverse=True,
                    )[:8],
                    "climates": devs,
                }
            )
        climates = []
        wrapped = self.bt_wrapped()
        panels = self.panel_climates()
        for entry in ent_reg.entities.values():
            if entry.domain != "climate" or entry.disabled_by:
                continue
            area_id = entry.area_id
            if not area_id and entry.device_id and (dev := dev_reg.async_get(entry.device_id)):
                area_id = dev.area_id
            st = hass.states.get(entry.entity_id)
            climates.append(
                {
                    "entity_id": entry.entity_id,
                    "name": (st.attributes.get("friendly_name") if st else None) or entry.name or entry.original_name or entry.entity_id,
                    "area_id": area_id,
                    "platform": entry.platform,
                    "kind": RT.kind_for([entry.platform]),
                    "better_thermostat": entry.platform == "better_thermostat",
                    "wrapper": WRAPPERS.get(entry.platform),
                    "wrapped_by": wrapped.get(entry.entity_id),
                    "can_cool": bool(st and "cool" in (st.attributes.get("hvac_modes") or [])),
                    "panel": entry.entity_id in panels,
                }
            )
        known = {c["entity_id"] for c in climates}
        for st in hass.states.async_all("climate"):  # Thermostate ohne Registry-Eintrag (z. B. YAML)
            if st.entity_id not in known:
                climates.append(
                    {
                        "entity_id": st.entity_id,
                        "name": st.attributes.get("friendly_name") or st.entity_id,
                        "area_id": None,
                        "platform": None,
                        "kind": "direct",
                        "better_thermostat": False,
                        "wrapper": None,
                        "wrapped_by": wrapped.get(st.entity_id),
                        "can_cool": "cool" in (st.attributes.get("hvac_modes") or []),
                        "panel": st.entity_id in panels,
                    }
                )
        known = {c["entity_id"] for c in climates}
        for room in self.rooms.values():  # gelöschte Thermostate eines Raums: im Editor sichtbar, damit man sie abwählen kann
            for eid in all_entities(room):
                if eid not in known:
                    known.add(eid)
                    climates.append({"entity_id": eid, "name": f"{eid} (in Home Assistant gelöscht)", "area_id": room.get("area_id"), "platform": None,
                                     "kind": room.get("kind") or "direct", "better_thermostat": False, "wrapper": None, "wrapped_by": None,
                                     "can_cool": False, "panel": False, "gone": True})
        prices = self.prices()
        gas_src = self._price(CONF_GAS_PRICE, CONF_GAS_PRICE_ENTITY)[1]
        power_src = self._price(CONF_POWER_PRICE, CONF_POWER_PRICE_ENTITY)[1]
        energy = {
            "outdoor": self.outdoor(),
            "outdoor_entities": list(self.options[CONF_OUTDOOR_ENTITIES] or []),
            "outdoor_minutes": int(self.options[CONF_OUTDOOR_MINUTES] or 0),
            "gas_ct": round(prices.gas_ct, 2),
            "gas_source": gas_src,
            "power_ct": round(prices.power_ct, 2),
            "power_source": power_src,
            "boiler_efficiency": prices.boiler_efficiency,
            "heat_cost_gas": round(prices.heat_cost_gas, 2),
            "break_even_cop": round(prices.break_even_cop, 2),
            "hysteresis": float(self.options[CONF_HYSTERESIS]),
            "default_ac": DEFAULT_AC,
        }
        return {
            "start_tab": self.start_tab,
            "requirements": R.state(self),
            "energy": energy,
            "modes": {
                "event": modes.event,
                "occasion": modes.occasion,
                "party_until": modes.party_until.isoformat() if modes.party_until else None,
                "season_auto": self.season_auto,
                "season_auto_possible": self.season_auto_possible(),
                "season_average": self.season_average()[0],
                "season_average_days": self.season_average()[1],
                "season_suggestion": self.season_suggestion(),
                "winter_below": float(self.options[CONF_WINTER_BELOW]),
                "hot_above": float(self.options[CONF_HOT_ABOVE]),
                "season": modes.season,
                "heating_season": modes.heating_season,
                "vacation": modes.vacation_label,
                "away": modes.away,
                "home_vacation": modes.home_vacation,
                "holiday_today": modes.holiday_today,
                "away_temp": modes.away_temp,
                "cooling_season": modes.cooling_season,
                "nobody_home": modes.nobody_home,
            },
            "entities": {
                "season": self.options[CONF_SEASON_ENTITY],
                "vacation": self.options[CONF_VACATION_ENTITY],
                "workday": self.options[CONF_WORKDAY_ENTITY],
                "presence": self.options.get(CONF_PRESENCE_ENTITY),
            },
            "rooms": rooms,
            "areas": [
                {"id": a.id, "name": a.name, "floor_id": a.floor_id} for a in area_reg.async_list_areas()
            ],
            "floors": [
                {"id": f.floor_id, "name": f.name, "level": f.level} for f in floor_reg.async_list_floors()
            ],
            "climates": climates,
            "level_names": E.LEVEL_NAMES,
            "events": list(E.EVENTS),
            "today_kinds": E.TODAY_KINDS,
            "rule_modes": E.RULE_MODES,
            "rule_actions": E.RULE_ACTIONS,
            "rule_values": {
                "vacation": (self._options_of(self.options[CONF_VACATION_ENTITY]) or ["kein Urlaub", "Urlaub zu Hause", "Urlaub unterwegs"]),
                "event": list(E.EVENTS),
                "occasion": ["Weihnachten", "keiner"],
                "season": (self._options_of(self.options[CONF_SEASON_ENTITY]) or ["Winter", "Sommer", "Heißphase"]),
                "presence": ["jemand zu Hause", "niemand zu Hause"],
            },
            "plan_levels": list(E.ENABLED_LEVELS),
            "level_defs": self.level_defs,
            "battery_low": BATTERY_LOW,
            "sun": {k: v.isoformat() for k, v in zip(("sunrise", "sunset"), self.sun_times(dt_util.now().date()), strict=True)},
            "flows": self.runner.snapshot() if self.runner else None,
            "flow_devices": self.runner.devices() if self.runner else [],
            "humidity_sensors": self._humidity_sensor_list(),
            "temperature_sensors": self._temperature_sensor_list(),
            "control_candidates": self.controls.candidates(),
            "default_temps": E.DEFAULT_LEVEL_TEMPS,
            "now": dt_util.now().isoformat(),
        }

    def _humidity_sensor_list(self) -> list[dict[str, Any]]:
        """Alle Feuchtesensoren – aus Registry und Zuständen (auch YAML-/Template-Sensoren ohne unique_id)."""
        ent_reg = er.async_get(self.hass)
        ids = {e.entity_id for e in ent_reg.entities.values() if e.domain == "sensor" and not e.disabled_by and (e.device_class or e.original_device_class) == "humidity"}
        ids |= {st.entity_id for st in self.hass.states.async_all("sensor") if st.attributes.get("device_class") == "humidity"}
        out = []
        for eid in ids:
            st, e = self.hass.states.get(eid), ent_reg.async_get(eid)
            out.append({"entity_id": eid, "name": (st.attributes.get("friendly_name") if st else None) or eid, "area_id": self._area_of(e) if e else None,
                        "value": _num(st.state) if st else None})
        return sorted(out, key=lambda x: x["name"].lower())

    # ------------------------------------------------------------------ Raumtemperatur (0.9.5)
    def panel_climates(self) -> set[str]:
        """Thermostat-Entitäten, die Bedienteile sind (kein Ventil): als Bedienteil eingetragen oder mit
        „thermostat_mode“ am Gerät (z. B. Aqara W100 im Thermostat-Modus)."""
        reg = er.async_get(self.hass)
        out = {c["display"] for r in self.rooms.values() for c in (r.get("controls") or []) if c.get("display")}
        mode_devices = {e.device_id for e in reg.entities.values() if e.device_id and "thermostat_mode" in f"{e.entity_id} {e.unique_id or ''}".lower()}
        for e in reg.entities.values():
            if e.domain == "climate" and e.device_id in mode_devices:
                out.add(e.entity_id)
        return out

    def _temperature_sensor_list(self) -> list[dict[str, Any]]:
        """Alle Temperatursensoren (Registry + Zustände) mit Bereich und Wert – für die Auswahl im Raum."""
        ent_reg = er.async_get(self.hass)
        ids = {e.entity_id for e in ent_reg.entities.values() if e.domain == "sensor" and not e.disabled_by and (e.device_class or e.original_device_class) == "temperature"}
        ids |= {st.entity_id for st in self.hass.states.async_all("sensor") if st.attributes.get("device_class") == "temperature"}
        # Keine Werte von Thermostaten selbst (Fühler, Komfort-/Eco-Temperatur, nächste geplante …) und keine
        # Rechenwerte von Regel-Integrationen – nur echte Raumsensoren. Geräte ohne Thermostat (z. B. FRITZ!DECT 440) bleiben.
        panels = self.panel_climates()  # Bedienteile wie das W100 messen die Raumtemperatur – deren Sensoren bleiben
        climate_devices = {e.device_id for e in ent_reg.entities.values() if e.domain == "climate" and e.device_id and e.entity_id not in panels}
        skip_platforms = {"better_thermostat", "versatile_thermostat", "home_rhythm"}
        out = []
        for eid in ids:
            st, e = self.hass.states.get(eid), ent_reg.async_get(eid)
            if e and (e.platform in skip_platforms or (e.device_id and e.device_id in climate_devices)):
                continue
            out.append({"entity_id": eid, "name": (st.attributes.get("friendly_name") if st else None) or eid,
                        "area_id": self._area_of(e) if e else None, "value": _num(st.state) if st else None,
                        "platform": e.platform if e else None})
        return sorted(out, key=lambda x: x["name"].lower())

    def _sensor_area(self, entity_id: str) -> str | None:
        e = er.async_get(self.hass).async_get(entity_id)
        return self._area_of(e) if e else None

    def room_reading(self, room: dict[str, Any], now: datetime | None = None) -> RT.Reading | None:
        """Raumwert aus Raumsensoren bzw. dem Sensor der Fritz!Box – None bei „Fühler am Thermostat“."""
        now = now or dt_util.utcnow()
        src = room.get("temp_source", "device")
        if src == "sensors" and room.get("temp_sensors"):
            return RT.read_sensors(self.hass, room["temp_sensors"], now, self._sensor_area)
        if src == "box" and room.get("box_sensor"):
            return RT.read_sensors(self.hass, [room["box_sensor"]], now, self._sensor_area)
        return None

    def _integration_sensor(self, room: dict[str, Any]) -> str | None:
        """Temperatursensor, den Better/Versatile Thermostat in diesem Raum benutzt."""
        for c in room_entities(room):
            conf = self._wrapper_conf(c)
            for key in ("temperature_sensor", "temperature_sensor_id", "temperature_sensor_entity_id", "temperature_sensor_entity"):
                if isinstance(conf.get(key), str) and conf[key]:
                    return conf[key]
        return None

    def room_temp_info(self, room_id: str, room: dict[str, Any]) -> dict[str, Any]:
        """Anzeige „Art / misst mit / Korrektur“ und Hinweise ⚠ – reine Anzeige, ändert nichts an der Regelung."""
        now = dt_util.utcnow()
        kind = room.get("kind") or self.derive_kind(room)
        area = room.get("area_id")
        checks: list[str] = []
        area_name = lambda a: (ar.async_get(self.hass).async_get_area(a).name if a and ar.async_get(self.hass).async_get_area(a) else a)  # noqa: E731
        info: dict[str, Any] = {"kind": kind, "source": room.get("temp_source", "device"), "correction": room.get("correction", "none"),
                                "correction_value": RT.correction(room), "value": None, "sensors": [], "integration_sensor": None,
                                "push": [], "observe": None, "checks": checks}
        reading = self.room_reading(room, now)
        if reading is not None:
            info["value"] = reading.value
            info["sensors"] = reading.used
            info["spread"] = reading.spread
            for u in reading.used:
                if area and u["area_id"] and u["area_id"] != area:
                    checks.append(f"{room.get('name', room_id)} misst mit einem Sensor aus dem Bereich {area_name(u['area_id'])} ({u['name']}).")
            if reading.value is None:
                checks.append("Kein Raumsensor liefert einen Wert (nicht verfügbar oder seit über 12 Std. keine Meldung) – " + ("es wird nichts ans Thermostat gesendet, es nutzt seinen eigenen Fühler." if RT.pushes(room) else "Anzeige und Beobachtung ruhen."))
            else:
                if reading.stale:
                    checks.append(f"{len(reading.stale)} von {len(reading.used)} Raumsensoren sind nicht verfügbar oder melden seit über 12 Std. nichts und zählen nicht mit.")
                fresh = [u for u in reading.used if not u["stale"]]
                heating = any((st := self.hass.states.get(e)) and st.attributes.get("hvac_action") == "heating" for e in room_entities(room))
                if heating and fresh and all(u["changed"] and now - dt_util.parse_datetime(u["changed"]) > RT.STUCK_AFTER for u in fresh):
                    checks.append("Der Raumsensor zeigt seit über 3 Std. denselben Wert, obwohl geheizt wird – misst er noch?")
            if reading.spread > RT.SPREAD_WARN:
                checks.append(f"Die Raumsensoren liegen {str(round(reading.spread, 1)).replace('.', ',')} °C auseinander – richtig zugeordnet?")
        if kind in ("bt", "integration"):
            sensor = self._integration_sensor(room)
            if sensor:
                st = self.hass.states.get(sensor)
                s_area = self._sensor_area(sensor)
                info["integration_sensor"] = {"entity_id": sensor, "name": (st.attributes.get("friendly_name") if st else None) or sensor,
                                              "value": _num(st.state) if st else None, "area_id": s_area}
                if area and s_area and s_area != area:
                    checks.append(f"{'Better Thermostat' if kind == 'bt' else 'Die Regel-Integration'} misst mit einem Sensor aus dem Bereich {area_name(s_area)} ({info['integration_sensor']['name']}).")
        for eid in all_entities(room):
            if self.gone(eid):
                checks.append(f"{eid} gibt es in Home Assistant nicht mehr – Raum bearbeiten und den Haken bei diesem Thermostat entfernen.")
        for eid in room_entities(room):
            if self.gone(eid):
                continue
            hi = self.heat_info(eid)
            if hi and hi["stuck"]:
                checks.append(f"{self._name(eid)} heizt seit über 1 Std., der Raum wird aber kaum wärmer – Heizkörper warm? Ventilstift / Adapter prüfen, Heizkörper entlüften.")
        if RT.pushes(room):
            for eid in room_entities(room):
                if self.gone(eid):
                    continue
                num, sel = RT.push_targets(self.hass, eid)
                sel_state = self.hass.states.get(sel).state if sel and self.hass.states.get(sel) else None
                last = self._pushed.get(eid)
                info["push"].append({"entity_id": eid, "name": self._name(eid), "number": num, "select": sel, "select_state": sel_state,
                                     "value": last["value"] if last else None, "at": last["at"].isoformat() if last else None})
                if not num:
                    checks.append(f"{self._name(eid)}: kein Eingang für externe Temperatur gefunden – Raumwert kann nicht gesendet werden.")
                if sel_state == RT.OFFLINE_OPTION:
                    checks.append(f"{self._name(eid)} ist auf seinen eigenen Fühler zurückgefallen (Raumwert kam nicht an).")
                cst = self.hass.states.get(eid)
                if cst and cst.state == "auto":
                    checks.append(f"{self._name(eid)} steht auf „auto“ (eigener Wochenplan im Gerät) statt „heat“.")
        if RT.observes(room):
            info["observe"] = RT.stats(self.observations.get(room_id) or [], dt_util.now())
        return info

    async def _async_room_temps(self, now: datetime) -> None:
        """Jede Minute: Raumwert an Thermostate senden (Thermostat direkt) und beobachten (Fritz). Nur wo eingestellt."""
        utc = dt_util.utcnow()
        for room_id, room in list(self.rooms.items()):
            if not room.get("enabled", True):
                continue
            if RT.pushes(room):
                reading = self.room_reading(room, utc)
                if reading is not None and reading.ok:
                    for eid in room_entities(room):
                        await self._async_push(eid, reading.value, utc)
            if RT.observes(room):
                self._observe(room_id, room, utc)

    async def _async_push(self, entity_id: str, value: float, now: datetime) -> None:
        num, sel = RT.push_targets(self.hass, entity_id)
        if not num:
            return
        value = round(value, 1)
        nst = self.hass.states.get(num)
        if nst is None or nst.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        lo, hi = _num(nst.attributes.get("min")), _num(nst.attributes.get("max"))
        if lo is not None:
            value = max(value, lo)
        if hi is not None:
            value = min(value, hi)
        if RT.push_due(self._pushed.get(entity_id), value, now):
            try:
                await self.hass.services.async_call("number", "set_value", {"entity_id": num, "value": value}, blocking=False, context=Context())
                self._pushed[entity_id] = {"value": value, "at": now}
            except Exception as err:  # noqa: BLE001 – Senden darf die Regelung nie stören
                _LOGGER.warning("HomeRhythm: Raumwert an %s nicht gesendet: %s", num, err)
        if sel and (sst := self.hass.states.get(sel)) and sst.state != RT.REMOTE_OPTION and RT.REMOTE_OPTION in (sst.attributes.get("options") or []):
            tried = self._remote_tried.get(entity_id)
            if tried is None or now - tried >= RT.REMOTE_RETRY:
                self._remote_tried[entity_id] = now
                try:
                    await self.hass.services.async_call("select", "select_option", {"entity_id": sel, "option": RT.REMOTE_OPTION}, blocking=False, context=Context())
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("HomeRhythm: %s nicht auf externe Temperatur gestellt: %s", sel, err)

    def _observe(self, room_id: str, room: dict[str, Any], now: datetime) -> None:
        reading = self.room_reading(room, now)
        if reading is None or not reading.ok:
            return
        samples = self.observations.setdefault(room_id, [])
        for eid in room_entities(room):
            st = self.hass.states.get(eid)
            closed = RT.valve_closed(st)
            if not closed:
                self._closed_since.pop(eid, None)
                continue
            since = self._closed_since.setdefault(eid, now)
            if now - since < RT.CLOSED_FOR or not RT.sample_due(samples, eid, now):
                continue
            trv = _num(st.attributes.get("current_temperature"))
            if trv is None:
                continue
            samples.append({"at": now.isoformat(), "entity_id": eid, "trv": trv, "set": _num(st.attributes.get(ATTR_TEMPERATURE)),
                            "room": reading.value, "diff": round(trv - reading.value, 2)})
            del samples[: max(0, len(samples) - RT.MAX_SAMPLES)]
            self.schedule_save()

    def observations_csv(self, room_id: str) -> str:
        if room_id not in self.rooms:
            raise ValueError("Unbekannter Raum")
        return RT.to_csv(self.observations.get(room_id) or [])

    def _options_of(self, entity_id: str | None) -> list[str]:
        st = self.hass.states.get(entity_id) if entity_id else None
        return list(st.attributes.get("options") or []) if st else []

    def preview(self, room: dict[str, Any], room_id: str | None) -> list[dict[str, Any]]:
        candidate = dict(room)
        candidate["schedule"] = E.normalize_schedule(candidate.get("schedule"))
        modes = self.modes()
        cooling = bool(modes.cooling_season and candidate.get("ac_entities") and E.cooling_config(candidate)["enabled"])
        manual = self.manual.get(room_id) if room_id and not cooling else None  # nur gemeinsame Hand-Änderung
        if candidate.get("rules") is not None:
            candidate["rules"] = E.normalize_rules(candidate.get("rules"))
        override = self.overrides.get(room_id) if room_id else None
        return E.week_preview(candidate, modes, dt_util.now(), manual, cooling=cooling, override=override)
