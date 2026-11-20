"""Ausführung der Abläufe (Zeitpläne und Reaktionen) in Home Assistant.

Grundsätze:
* **Zeitpläne** schalten nur zu ihren Schaltpunkten. Pro Minute (Sekunde 0) prüft
  der Runner, welche Schaltpunkte fällig sind. Nach einem Neustart wird nichts
  nachgeholt; fehlt ein Hausmodus (Helfer „nicht verfügbar“), wird nicht geschaltet.
* Stehen zwei Zeitpläne zur selben Minute auf demselben Gerät, gilt der obere
  (Reihenfolge in der Liste).
* **Reaktionen** laufen als eigene asyncio-Aufgaben. „Zeit beginnt neu“ bricht einen
  laufenden Durchgang ab und startet neu; „ignorieren“ lässt ihn weiterlaufen.
* Ein fehlerhafter Ablauf oder ein hängendes Gerät hält nie die Heizung oder andere
  Abläufe auf: jeder Dienstaufruf hat eine Zeitgrenze, Fehler werden protokolliert.

Datenschutz: Das Protokoll je Ablauf enthält nur Zeitpunkte, Gerätenamen und das
Ergebnis (höchstens ``LOG_SIZE`` Einträge). Es bleibt im HA-Speicher (.storage) und
verlässt das System nicht.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from datetime import date, datetime, timedelta
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Context, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

from . import engine as E
from . import flows as F
from . import native as N
from .const import SIGNAL_FLOWS
from .const import CONF_AWAY_VALUE, CONF_HOME_VALUE, CONF_PRESENCE_ENTITY, CONF_SEASON_ENTITY, CONF_VACATION_ENTITY, CONF_WORKDAY_ENTITY

if TYPE_CHECKING:
    from .controller import HomeRhythmController

_LOGGER = logging.getLogger(__name__)

LOG_SIZE = 30
CALL_TIMEOUT = 15  # s je Dienstaufruf
VERIFY_AFTER = 300  # s – „nachprüfen & wiederholen“
VERIFY_TRIES = 2
CATCH_UP = 10  # Minuten – verzögerte Ticks (z. B. hohe Last) holt der Runner bis dahin nach


class FlowRunner:
    """Hält die Abläufe, führt sie aus und liefert Daten für die Karte."""

    def __init__(self, hass: HomeAssistant, ctrl: HomeRhythmController) -> None:
        self.hass = hass
        self.ctrl = ctrl
        self.flows: dict[str, dict[str, Any]] = {}  # in Listen-Reihenfolge (dict behält sie)
        self.logs: dict[str, deque[dict[str, Any]]] = {}
        self.skip: set[str] = set()  # Zeitpläne, deren nächster Schaltpunkt ausgelassen wird
        self.runs: dict[str, dict[str, Any]] = {}  # laufende Reaktionen (Anzeige)
        self._tasks: dict[str, asyncio.Task] = {}
        self._unsubs: list[CALLBACK_TYPE] = []
        self._trigger_unsub: CALLBACK_TYPE | None = None
        self._last_minute: datetime | None = None
        self._holidays: dict[int, Any] = {}
        self.native_error: str | None = None
        self._sim: dict[str, Any] | None = None  # nur während simulate(): Hausmodi „so tun als ob“
        self._cache: dict[Any, Any] | None = None  # Zwischenspeicher während einer Berechnung (snapshot, Tick …)
        self._computing: set[str] = set()  # Schutz gegen Zirkelbezüge bei „Zeitplan ist …“
        self._verify_unsubs: dict[str, list[CALLBACK_TYPE]] = {}
        self._done_minutes: set[tuple[str, int]] = set()  # (Datum, Minute) schon ausgeführt – Sommer-/Winterzeit
        self._notify_unsub: CALLBACK_TYPE | None = None
        self.broken: dict[str, Any] = {}  # gespeicherte Abläufe, die nicht mehr gültig sind (bleiben erhalten)
        self.stopped = False
        self._native_lock = asyncio.Lock()
        # Von Hand geschaltet (Taster, HA-Schalter, Schnellbedienung): je Zeitplan {at, action, until, auto, src}.
        # Gilt bis zum nächsten Schaltpunkt; „auto“ = nach X Minuten von selbst wieder aus.
        self.hand: dict[str, dict[str, Any]] = {}
        self._hand_unsubs: dict[str, CALLBACK_TYPE] = {}

    # ------------------------------------------------------------------ Laden / Speichern
    def load(self, stored: dict[str, Any] | None) -> None:
        stored = stored or {}
        for fid, raw in (stored.get("items") or {}).items():
            try:
                self.flows[fid] = F.normalize_flow(raw)
            except (ValueError, TypeError, KeyError, AttributeError) as err:
                self.broken[fid] = raw  # nicht verwerfen – beim Speichern unverändert behalten
                _LOGGER.warning("HomeRhythm: Ablauf %s nicht geladen: %s", fid, err)
        for fid in list(self.flows):  # Zirkelbezüge („Zeitplan ist …“) beim Laden entschärfen
            if self._cycle(fid, F.flow_refs(self.flows[fid])):
                self.flows[fid]["enabled"] = False
                _LOGGER.warning("HomeRhythm: Ablauf %s verweist im Kreis auf sich selbst – ausgeschaltet", fid)
        for fid, entries in (stored.get("logs") or {}).items():
            if fid in self.flows:
                self.logs[fid] = deque(entries[-LOG_SIZE:], maxlen=LOG_SIZE)
        self.skip = {f for f in stored.get("skip") or [] if f in self.flows}
        for fid, h in (stored.get("hand") or {}).items():
            if fid in self.flows and isinstance(h, dict) and isinstance(h.get("at"), str):
                self.hand[fid] = {k: h.get(k) for k in ("at", "action", "until", "auto", "src")}

    def storage_data(self) -> dict[str, Any]:
        return {"flows": {"items": {**self.broken, **self.flows}, "logs": {k: list(v) for k, v in self.logs.items() if k in self.flows}, "skip": sorted(self.skip),
                          "hand": {k: v for k, v in self.hand.items() if k in self.flows}}}

    def _cycle(self, fid: str, refs: set[str]) -> bool:
        """Würde fid über „Zeitplan ist …“ (auch über Umwege) wieder auf sich selbst verweisen?"""
        seen, todo = set(), list(refs)
        while todo:
            x = todo.pop()
            if x == fid:
                return True
            if x in seen or x not in self.flows:
                continue
            seen.add(x)
            todo += list(F.flow_refs(self.flows[x]))
        return False

    # ------------------------------------------------------------------ Zwischenspeicher
    def _begin(self) -> bool:
        """Zwischenspeicher für eine Berechnung öffnen (verschachtelt: nur der äußere zählt)."""
        if self._cache is not None:
            return False
        self._cache = {}
        return True

    def _end(self, opened: bool) -> None:
        if opened:
            self._cache = None

    @callback
    def _notify(self) -> None:
        """Karte gebündelt benachrichtigen (höchstens einmal pro Sekunde)."""
        if self._notify_unsub or self.stopped:
            return

        @callback
        def _fire(_now: datetime) -> None:
            self._notify_unsub = None
            self.ctrl.notify_update()

        self._notify_unsub = async_call_later(self.hass, 1, _fire)

    # ------------------------------------------------------------------ Start / Stopp
    async def async_start(self) -> None:
        self._last_minute = dt_util.now().replace(second=0, microsecond=0)  # nichts nachholen
        self._unsubs.append(async_track_time_change(self.hass, self._on_minute, second=0))
        self._subscribe_triggers()
        self.ctrl.controls.track()  # Taster der Zeitpläne
        now = dt_util.now()
        for fid, h in list(self.hand.items()):  # „nach X wieder aus“ über einen Neustart retten
            until = dt_util.parse_datetime(h.get("until") or "") if h.get("auto") else None
            if until is not None:
                self._hand_timer(fid, max(1.0, (until - now).total_seconds()))

    async def async_stop(self) -> None:
        self.stopped = True
        for unsub in self._unsubs + [u for lst in self._verify_unsubs.values() for u in lst]:
            unsub()
        self._unsubs.clear()
        self._verify_unsubs.clear()
        if self._notify_unsub:
            self._notify_unsub()
            self._notify_unsub = None
        if self._trigger_unsub:
            self._trigger_unsub()
            self._trigger_unsub = None
        for unsub in self._hand_unsubs.values():
            unsub()
        self._hand_unsubs.clear()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    # ------------------------------------------------------------------ Kontext
    def _opts(self) -> dict[str, Any]:
        return self.ctrl.options

    def inputs_ok(self) -> bool:
        """Hausmodi bekannt? Sonst nicht schalten (z. B. kurz nach dem Start)."""
        if not self.hass.is_running:
            return False
        o = self._opts()
        for key in (CONF_SEASON_ENTITY, CONF_VACATION_ENTITY, CONF_WORKDAY_ENTITY, CONF_PRESENCE_ENTITY):
            eid = o.get(key)
            st = self.hass.states.get(eid) if eid else None
            if st is not None and st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return False
        return True

    def holiday_name(self, day: date) -> str | None:
        """Feiertag aus der Konfiguration des Workday-Sensors (Land/Region), falls ermittelbar."""
        try:
            import holidays  # noqa: PLC0415 – kommt mit der Workday-Integration

            if day.year not in self._holidays:
                entries = self.hass.config_entries.async_entries("workday")
                if not entries:
                    return None  # ohne Workday keine Feiertage (so steht es auch in der Kachel „Voraussetzungen“)
                conf = {**entries[0].data, **entries[0].options}
                country, subdiv = conf.get("country") or "DE", conf.get("province") or None
                self._holidays[day.year] = holidays.country_holidays(country, subdiv=subdiv, years=day.year, language="de")
            return self._holidays[day.year].get(day)
        except Exception:  # noqa: BLE001 – ohne holidays-Paket einfach keine Feiertage für andere Tage
            return None

    def is_holiday(self, day: date, sim_hol: set[str] | None = None) -> bool:
        """Feiertag? Nur Mo–Fr – wie bei der Heizung und in der HA-Automation (ein Feiertag am Samstag bleibt Samstag).

        Heute entscheidet der Workday-Sensor (aus an einem Werktag = Feiertag), sonst die Feiertagsliste.
        """
        if day.weekday() >= 5:
            return False
        if sim_hol and day.isoformat() in sim_hol:
            return True
        if day == dt_util.now().date():
            eid = self._opts().get(CONF_WORKDAY_ENTITY)
            st = self.hass.states.get(eid) if eid else None
            if st is not None and st.state in ("on", "off"):
                return st.state == "off"
        return bool(self.holiday_name(day))

    def is_workday(self, day: date) -> bool:
        """Heute: Workday-Sensor. Andere Tage: Mo–Fr ohne Feiertag. „Urlaub zu Hause“ = frei."""
        modes = self.ctrl.modes()
        if modes.home_vacation:
            return False
        today = dt_util.now().date()
        if day == today:
            eid = self._opts().get(CONF_WORKDAY_ENTITY)
            st = self.hass.states.get(eid) if eid else None
            if st is not None and st.state in ("on", "off"):
                return st.state == "on"
        return day.weekday() < 5 and not self.holiday_name(day)

    def ctx(self, day: date | None = None, sun_up: bool | None = None) -> F.Ctx:
        key = ("ctx", day, sun_up, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in (self._sim or {}).items())))
        if self._cache is not None and key in self._cache:
            return self._cache[key]
        res = self._make_ctx(day, sun_up)
        if self._cache is not None:
            self._cache[key] = res
        return res

    def _make_ctx(self, day: date | None, sun_up: bool | None) -> F.Ctx:
        modes = self.ctrl.modes()
        today = dt_util.now().date()
        day = day or today
        o = self._opts()
        season_st = self.hass.states.get(o.get(CONF_SEASON_ENTITY) or "")
        vac_st = self.hass.states.get(o.get(CONF_VACATION_ENTITY) or "")
        if sun_up is None:
            sun_st = self.hass.states.get("sun.sun")
            sun_up = sun_st.state == "above_horizon" if sun_st else True
        sim = self._sim or {}
        vacation = sim.get("vacation") or (vac_st.state if vac_st else "")
        sim_hol = set(sim.get("holidays") or ())
        workday = self.is_workday(day)
        if sim.get("vacation") or sim_hol:
            home = o.get(CONF_HOME_VALUE)
            workday = (day.weekday() < 5 and not self.holiday_name(day) and day.isoformat() not in sim_hol) if vacation != home else False
        vac_home = bool(vacation) and vacation == o.get(CONF_HOME_VALUE)
        return F.Ctx(
            daytype=F.raw_daytype(day.weekday(), self.is_holiday(day, sim_hol), vac_home),
            prev_daytype=F.raw_daytype((day - timedelta(days=1)).weekday(), self.is_holiday(day - timedelta(days=1), sim_hol), vac_home),
            season=sim.get("season") or (season_st.state if season_st else modes.season),
            vacation=vacation,
            event=sim.get("event") or self.ctrl.event,
            christmas=E.christmas(day) if sim.get("christmas") in (None, "") else sim["christmas"] == "1",
            nobody_home=modes.nobody_home if sim.get("presence") in (None, "") else sim["presence"] == "away",
            workday=workday,
            sun_up=sun_up,
            day=day,
            state=lambda e: (s.state if (s := self.hass.states.get(e)) else None),
            flow_state=self.planned_state,
            known=set(self.flows),
        )

    # ------------------------------------------------------------------ Geräte eines Zeitplans
    def resolve(self, flow: dict[str, Any]) -> list[str]:
        """Geräte inkl. Auswahl über Bereich / Etage / Label (zum Ausführungszeitpunkt aufgelöst)."""
        out = list(flow.get("devices") or [])
        sels = flow.get("selectors") or []
        if sels:
            ent_reg, area_reg = er.async_get(self.hass), ar.async_get(self.hass)
            domains = F.KIND_DOMAINS[flow["kind"]]
            for e in ent_reg.entities.values():
                if e.domain not in domains or e.disabled_by or e.hidden_by or e.entity_category is not None:
                    continue
                area_id = self.ctrl._area_of(e)  # noqa: SLF001
                area = area_reg.async_get_area(area_id) if area_id else None
                labels = set(e.labels)
                if e.device_id and (dev := self.ctrl._device(e.device_id)):  # noqa: SLF001
                    labels |= set(dev.labels)
                for s in sels:
                    if (s["by"] == "area" and area_id == s["id"]) or (s["by"] == "floor" and area and area.floor_id == s["id"]) or (s["by"] == "label" and s["id"] in labels):
                        out.append(e.entity_id)
                        break
        return list(dict.fromkeys(out))

    # ------------------------------------------------------------------ Zeitpläne: jede Minute
    async def _on_minute(self, now: datetime) -> None:
        """Fällige Schaltpunkte ausführen – nach Wanduhr-Minuten.

        Sommerzeit (Uhr springt vor): übersprungene Minuten werden nachgeholt.
        Winterzeit (Stunde doppelt): jede Wanduhr-Minute läuft nur einmal.
        """
        if self.stopped:
            return
        now = dt_util.as_local(now).replace(second=0, microsecond=0)
        wall_now = now.replace(tzinfo=None)
        prev = self._last_minute
        last = dt_util.as_local(prev).replace(tzinfo=None) if prev else wall_now - timedelta(minutes=1)
        # Sprung der Wanduhr ohne echte Zeit (Sommerzeit: 02:00 → 03:00) zählt nicht gegen das Nachhol-Limit
        jump = (wall_now - last) - (dt_util.as_utc(now) - dt_util.as_utc(prev)) if prev else timedelta(0)
        self._last_minute = now
        if wall_now <= last:
            return  # Stunde doppelt (Winterzeit) oder Uhr zurückgestellt – diese Minuten liefen schon
        if not self.inputs_ok():
            return
        minute = max(last + timedelta(minutes=1), wall_now - timedelta(minutes=CATCH_UP) - max(jump, timedelta(0)))
        opened = self._begin()
        try:
            while minute <= wall_now:
                key = (minute.date().isoformat(), minute.hour * 60 + minute.minute)
                if key not in self._done_minutes:
                    self._done_minutes.add(key)
                    await self._run_minute(minute.replace(tzinfo=now.tzinfo))
                minute += timedelta(minutes=1)
        finally:
            self._end(opened)
        if len(self._done_minutes) > 3000:  # nur die letzten zwei Tage merken
            cut = (wall_now.date() - timedelta(days=2)).isoformat()
            self._done_minutes = {k for k in self._done_minutes if k[0] >= cut}

    async def _run_minute(self, when: datetime) -> None:
        day, m = when.date(), when.hour * 60 + when.minute
        sun = self.ctrl.sun_for(day)
        ctx = self.ctx(day)
        prev_ctx = self.ctx(day - timedelta(days=1))  # Schaltzeiten nach Mitternacht gehören zum Vortag
        used: set[str] = set()  # Geräte, die in dieser Minute schon ein oberer Zeitplan geschaltet hat
        changed = False
        for fid, flow in list(self.flows.items()):
            if flow["type"] != "plan" or not flow["enabled"] or flow["native"]:
                continue
            try:  # ein fehlerhafter Zeitplan darf die anderen nicht aufhalten
                # „Zeitplan gilt“ je Schaltpunkt: nach Mitternacht zählt der Vortag (z. B. „aus 01:00“ am letzten Tag eines Zeitraums)
                due = [(i, p) for minute, i, p in F.day_events(fid, flow, day, sun, ctx, prev_ctx, check_plan=True) if minute == m]
                if not due:
                    continue
                for idx, point in due:
                    if fid in self.skip:
                        self.skip.discard(fid)
                        self._log(fid, "info", f"{F.hm(m)} übersprungen ({F.ACTION_NAMES[point['action']]})")
                        changed = True
                        continue
                    await self._exec_point(fid, flow, point, idx, used)
                    changed = True
            except Exception:  # noqa: BLE001
                _LOGGER.exception("HomeRhythm: Zeitplan %s um %s fehlgeschlagen", flow.get("name"), F.hm(m))
        if changed:
            self.ctrl.schedule_save()
            self._notify()

    def _target_reached(self, entity_id: str, action: str, position: int | None) -> bool:
        st = self.hass.states.get(entity_id)
        if st is None:
            return False
        if action == "position":
            cur = st.attributes.get("current_position")
            return cur is not None and abs(int(cur) - int(position or 0)) <= 2
        want = {"open": ("open", "opening"), "close": ("closed", "closing"), "on": ("on",), "off": ("off",)}[action]
        return st.state in want

    async def _call(self, domain: str, service: str, data: dict[str, Any], context: Context) -> None:
        async with asyncio.timeout(CALL_TIMEOUT):
            await self.hass.services.async_call(domain, service, data, blocking=True, context=context)

    async def _switch(self, entity_id: str, action: str, position: int | None, brightness: int | None, context: Context) -> None:
        if action in ("open", "close"):
            await self._call("cover", f"{action}_cover", {ATTR_ENTITY_ID: entity_id}, context)
        elif action == "position":
            await self._call("cover", "set_cover_position", {ATTR_ENTITY_ID: entity_id, "position": position}, context)
        elif action == "toggle":
            domain = "cover" if entity_id.startswith("cover.") else "homeassistant"
            await self._call(domain, "toggle", {ATTR_ENTITY_ID: entity_id}, context)
        elif action == "on" and brightness and entity_id.startswith("light."):
            await self._call("light", "turn_on", {ATTR_ENTITY_ID: entity_id, "brightness_pct": brightness}, context)
        else:
            await self._call("homeassistant", f"turn_{'on' if action == 'on' else 'off'}", {ATTR_ENTITY_ID: entity_id}, context)

    async def _exec_point(self, fid: str, flow: dict[str, Any], point: dict[str, Any], idx: int, used: set[str], force: bool = False) -> None:
        self._hand_clear(fid)  # ein Schaltpunkt beendet jede Hand-Bedienung (auch „nach X wieder aus“)
        context = self.ctrl.own_context()
        done, skipped, failed = 0, 0, []
        targets = []
        for eid in self.resolve(flow):
            if eid in used:
                continue
            used.add(eid)
            pos = flow.get("overrides", {}).get(eid, {}).get("position", point.get("position"))
            st = self.hass.states.get(eid)
            if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                failed.append(self.ctrl._name(eid))  # noqa: SLF001
                continue
            if point.get("only_needed") and not force and self._target_reached(eid, point["action"], pos):
                skipped += 1
                continue
            try:
                await self._switch(eid, point["action"], pos, point.get("brightness"), context)
                done += 1
                targets.append((eid, pos))
            except Exception as err:  # noqa: BLE001 – ein Gerät darf die anderen nicht blockieren
                failed.append(self.ctrl._name(eid))  # noqa: SLF001
                _LOGGER.warning("HomeRhythm: %s konnte %s nicht schalten: %s", flow["name"], eid, err)
        act = F.ACTION_NAMES[point["action"]] + (f" {point.get('position')} %" if point["action"] == "position" else "")
        text = f"{act}: {done} geschaltet" + (f", {skipped} standen schon so" if skipped else "") + (f" – nicht erreicht: {', '.join(failed)}" if failed else "")
        self._log(fid, "bad" if failed else "ok", text)
        if point.get("verify") and targets:
            self._schedule_verify(fid, point, targets, 1)

    def _schedule_verify(self, fid: str, point: dict[str, Any], targets: list[tuple[str, int | None]], attempt: int) -> None:
        handles = self._verify_unsubs.setdefault(fid, [])

        @callback
        def _later(_now: datetime) -> None:
            if unsub in handles:
                handles.remove(unsub)
            self.hass.async_create_background_task(self._verify(fid, point, targets, attempt), f"home_rhythm_verify_{fid}")

        unsub = async_call_later(self.hass, VERIFY_AFTER, _later)
        handles.append(unsub)

    async def _verify(self, fid: str, point: dict[str, Any], targets: list[tuple[str, int | None]], attempt: int) -> None:
        flow = self.flows.get(fid)
        if self.stopped or not flow or not flow["enabled"] or point not in flow.get("points", []):
            return  # Zeitplan gelöscht, ausgeschaltet oder geändert – alte Nachprüfung verfällt
        missing = [(e, p) for e, p in targets if not self._target_reached(e, point["action"], p)]
        if not missing:
            return
        names = ", ".join(self.ctrl._name(e) for e, _ in missing)  # noqa: SLF001
        if attempt > VERIFY_TRIES:
            self._log(fid, "bad", f"Nachprüfung: {names} weiterhin nicht {F.ACTION_NAMES[point['action']]} – aufgegeben")
        else:
            context = self.ctrl.own_context()
            for eid, pos in missing:
                try:
                    await self._switch(eid, point["action"], pos, point.get("brightness"), context)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("HomeRhythm: erneutes Schalten von %s fehlgeschlagen: %s", eid, err)
            self._log(fid, "bad", f"Nachprüfung: {names} nicht wie geplant – Versuch {attempt + 1}")
            self._schedule_verify(fid, point, missing, attempt + 1)
        self.ctrl.schedule_save()
        self._notify()

    def _log(self, fid: str, kind: str, text: str) -> None:
        if fid not in self.flows or self.stopped:
            return
        self.logs.setdefault(fid, deque(maxlen=LOG_SIZE)).append({"at": dt_util.now().isoformat(), "kind": kind, "text": text[:300]})

    # ------------------------------------------------------------------ Zeitpläne: Zustand, Vorschau
    def _last_event(self, fid: str, flow: dict[str, Any], when: datetime) -> tuple[datetime, dict[str, Any]] | None:
        for back in range(8):
            day = when.date() - timedelta(days=back)
            evs = F.day_events(fid, flow, day, self.ctrl.sun_for(day), self.ctx(day))
            evs = [e for e in evs if back > 0 or e[0] <= when.hour * 60 + when.minute]
            if evs:
                m, _i, p = evs[-1]
                return datetime.combine(day, datetime.min.time(), tzinfo=when.tzinfo) + timedelta(minutes=m), p
        return None

    def planned_state(self, fid: str) -> str | None:
        """Zustand, den der Zeitplan gerade vorsieht (für Bedingung „Zeitplan ist …“)."""
        flow = self.flows.get(fid)
        if not flow or flow["type"] != "plan" or fid in self._computing:
            return None  # unbekannt oder Zirkelbezug → Bedingung nicht erfüllt
        key = ("planned", fid, self._minute_key(), tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in (self._sim or {}).items())))
        if self._cache is not None and key in self._cache:
            return self._cache[key]
        self._computing.add(fid)
        try:
            last = self._last_event(fid, flow, dt_util.now())
        finally:
            self._computing.discard(fid)
        res = F.ACTION_STATE[last[1]["action"]] if last else None
        if self._cache is not None:
            self._cache[key] = res
        return res

    @staticmethod
    def _minute_key() -> str:
        return dt_util.now().strftime("%Y%m%d%H%M")

    def next_event(self, fid: str, flow: dict[str, Any], now: datetime) -> tuple[datetime, dict[str, Any]] | None:
        """Nächster Schaltpunkt, der wirklich ausgeführt würde (mit „Zeitplan gilt“; nach Mitternacht mit dem Vortag)."""
        for k in range(8):
            day = now.date() + timedelta(days=k)
            for m, _i, p in F.day_events(fid, flow, day, self.ctrl.sun_for(day), self.ctx(day), self.ctx(day - timedelta(days=1)), check_plan=True):
                if k > 0 or m > now.hour * 60 + now.minute:
                    return datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo) + timedelta(minutes=m), p
        return None

    def wait_reason(self, flow: dict[str, Any], ctx: F.Ctx) -> str | None:
        if not flow["enabled"]:
            return "ausgeschaltet"
        if flow["native"]:
            return None
        if flow["type"] == "plan" and not F.cond_true(flow["conds"], ctx):
            return "wartet – nur wenn " + F.group_text(flow["conds"], self._names())
        return None

    # ------------------------------------------------------------------ Aktionen aus der Karte
    async def async_apply_now(self, fid: str) -> None:
        """„Jetzt auf Plan setzen“: letzten fälligen Schaltpunkt erneut ausführen (ohne „falls nötig“)."""
        flow = self._get(fid)
        if flow["type"] != "plan":
            raise ValueError("Nur für Zeitpläne")
        if not flow["enabled"]:
            raise ValueError("Der Zeitplan ist ausgeschaltet")
        if flow["native"]:
            raise ValueError("Dieser Zeitplan läuft als Automation in Home Assistant")
        last = self._last_event(fid, flow, dt_util.now())
        if not last:
            raise ValueError("Noch kein Schaltpunkt in den letzten Tagen")
        await self._exec_point(fid, flow, last[1], 0, set(), force=True)
        self.ctrl.schedule_save()
        self.ctrl.notify_update()

    def _get(self, fid: str) -> dict[str, Any]:
        if not isinstance(fid, str) or fid not in self.flows:
            raise ValueError("Unbekannter Ablauf")
        return self.flows[fid]

    async def async_switch_all(self, fid: str, action: str, src: str = "") -> int:
        """Schnellbedienung aus der Karte: alle Geräte eines Ablaufs öffnen/schließen bzw. an/aus.

        Wie eine Hand-Änderung: gilt bis zum nächsten Schaltpunkt. Nur die Geräte des Ablaufs, nur feste Aktionen.
        """
        flow = self._get(fid)
        if action not in ("open", "close", "on", "off"):
            raise ValueError("Unbekannte Aktion")
        if flow["type"] == "plan":
            if action not in F.ACTIONS[flow["kind"]]:
                raise ValueError("Aktion passt nicht zu diesem Zeitplan")
            ents = self.resolve(flow)
        else:
            ents = [e for s in flow["steps"] for e in s.get("entities", [])]
            ents = [e for e in dict.fromkeys(ents) if (e.startswith("cover.") == (action in ("open", "close")))]
        context = self.ctrl.own_context()
        failed: list[str] = []
        for eid in ents:
            await self._safe_switch(eid, action, None, None, context, failed)
        self._log(fid, "bad" if failed else "info", f"{src or 'von Hand'}: alle {F.ACTION_NAMES[action]}" + (f" – nicht erreicht: {', '.join(failed)}" if failed else ""))
        if flow["type"] == "plan":
            self._hand_set(fid, flow, action, src or "Karte")
        self.ctrl.schedule_save()
        self.ctrl.notify_update()
        return len(ents) - len(failed)

    # ------------------------------------------------------------------ Taster / HA-Schalter je Zeitplan
    def any_on(self, flow: dict[str, Any]) -> bool:
        """Ist mindestens ein Gerät des Zeitplans an bzw. (teilweise) offen?"""
        for eid in self.resolve(flow):
            st = self.hass.states.get(eid)
            if st is None:
                continue
            if st.state in ("on", "open", "opening"):
                return True
            if eid.startswith("cover.") and st.state not in ("closed", "closing", STATE_UNAVAILABLE, STATE_UNKNOWN):
                return True
        return False

    async def async_button(self, fid: str, what: str, src: str) -> str | None:
        """Taster oder HA-Schalter: alle Geräte des Zeitplans gemeinsam schalten (wie von Hand).

        what: toggle (mind. eins an → alle aus, sonst alle an), on, off. Der Plan läuft danach normal weiter.
        Rückgabe: ausgeführte Aktion oder None (z. B. „nur wenn der Zeitplan gilt“ trifft nicht zu).
        """
        flow = self._get(fid)
        if flow["type"] != "plan" or what not in F.BUTTON_ACTIONS:
            raise ValueError("Nur für Zeitpläne")
        btn = flow.get("button") or {}
        if btn.get("scope") == "active" and (not flow["enabled"] or not F.cond_true(flow["conds"], self.ctx())):
            self._log(fid, "info", f"{src}: gedrückt – Zeitplan gilt gerade nicht, nichts geschaltet")
            self._notify()
            return None
        on = (not self.any_on(flow)) if what == "toggle" else what == "on"
        action = ("open" if on else "close") if flow["kind"] == F.KIND_COVER else ("on" if on else "off")
        await self.async_switch_all(fid, action, src)
        return action

    def _hand_set(self, fid: str, flow: dict[str, Any], action: str, src: str) -> None:
        now = dt_util.now()
        self._hand_clear(fid)
        auto = int((flow.get("button") or {}).get("auto_off") or 0)
        nxt = self.next_event(fid, flow, now) if flow["enabled"] else None
        until = nxt[0] if nxt else None
        use_auto = bool(auto) and action in ("on", "open") and (until is None or now + timedelta(minutes=auto) < until)
        if use_auto:
            until = now + timedelta(minutes=auto)
            self._hand_timer(fid, auto * 60)
        self.hand[fid] = {"at": now.isoformat(), "action": action, "until": until.isoformat() if until else None, "auto": use_auto, "src": src[:60]}

    def _hand_clear(self, fid: str) -> None:
        self.hand.pop(fid, None)
        if unsub := self._hand_unsubs.pop(fid, None):
            unsub()

    def _hand_timer(self, fid: str, seconds: float) -> None:
        if unsub := self._hand_unsubs.pop(fid, None):
            unsub()

        @callback
        def _fire(_now: datetime) -> None:
            self._hand_unsubs.pop(fid, None)
            self.hass.async_create_background_task(self._hand_auto_off(fid), f"home_rhythm_auto_off_{fid}")

        self._hand_unsubs[fid] = async_call_later(self.hass, seconds, _fire)

    async def _hand_auto_off(self, fid: str) -> None:
        flow, h = self.flows.get(fid), self.hand.get(fid)
        if self.stopped or not flow or not h or not h.get("auto"):
            return
        mins = int((flow.get("button") or {}).get("auto_off") or 0)
        action = "close" if flow["kind"] == F.KIND_COVER else "off"
        try:
            await self.async_switch_all(fid, action, f"nach{F.offset_text(mins, 'h').replace('+', '')} wieder {'zu' if action == 'close' else 'aus'} (Taster)")
        finally:
            self._hand_clear(fid)
            self.ctrl.schedule_save()
            self._notify()

    async def async_toggle_skip(self, fid: str) -> bool:
        self._get(fid)
        if fid in self.skip:
            self.skip.discard(fid)
        else:
            self.skip.add(fid)
        await self.ctrl.async_save()
        self.ctrl.notify_update()
        return fid in self.skip

    async def async_save_flow(self, data: dict[str, Any], sync: bool = True) -> str:
        flow = F.normalize_flow(data)
        fid = data.get("id")
        if fid and fid not in self.flows:
            raise ValueError("Unbekannter Ablauf")
        if not fid:
            if len(self.flows) + len(self.broken) >= F.MAX_FLOWS:
                raise ValueError(f"Höchstens {F.MAX_FLOWS} Abläufe")
            fid = F.new_id(flow["name"], set(self.flows) | set(self.broken))
        refs = F.flow_refs(flow)
        if fid in refs or self._cycle(fid, refs):
            raise ValueError("Bedingung „Zeitplan ist …“ verweist (auch über Umwege) auf diesen Ablauf selbst")
        if any(r not in self.flows or self.flows[r]["type"] != "plan" for r in refs):
            raise ValueError("Bedingung „Zeitplan ist …“ verweist auf einen unbekannten Zeitplan")
        self.flows[fid] = flow
        self._cancel(fid)
        await self._after_change(sync)
        return fid

    async def async_delete_flow(self, fid: str) -> None:
        self._get(fid)
        users = [f["name"] for other, f in self.flows.items() if other != fid and fid in F.flow_refs(f)]
        if users:
            raise ValueError(f"Wird noch in Bedingungen verwendet: {', '.join(users)}")
        self.flows.pop(fid)
        self.logs.pop(fid, None)
        self.skip.discard(fid)
        self._hand_clear(fid)
        self._cancel(fid)
        await self._after_change()

    async def async_set_enabled(self, fid: str, enabled: bool) -> None:
        self._get(fid)["enabled"] = bool(enabled)
        if not enabled:
            self._cancel(fid)
        await self._after_change()

    async def async_order(self, order: list[str]) -> None:
        if sorted(order) != sorted(self.flows):
            raise ValueError("Reihenfolge passt nicht zu den Abläufen")
        self.flows = {fid: self.flows[fid] for fid in order}
        await self._after_change()

    async def _after_change(self, sync: bool = True) -> None:
        self._subscribe_triggers()
        self.ctrl.controls.track()  # Taster der Zeitpläne beobachten
        async_dispatcher_send(self.hass, SIGNAL_FLOWS)  # HA-Schalter der Zeitpläne anlegen / entfernen
        if sync:
            await self.async_sync_native()
        await self.ctrl.async_save()
        self.ctrl.notify_update()

    def native_opts(self) -> dict[str, Any]:
        opts = {k: self._opts().get(k) for k in ("season_entity", "vacation_entity", "workday_entity", "presence_entity", "home_value")}
        opts["event_entity"] = er.async_get(self.hass).async_get_entity_id("select", "home_rhythm", f"{self.ctrl.entry.entry_id}_event")
        return opts

    async def async_sync_native(self) -> None:
        """Abläufe mit „in HA anlegen“ nach automations.yaml schreiben (andere bleiben unberührt).

        Ein Ablauf, dessen Bedingungen sich in HA nicht vollständig abbilden lassen, wird nicht geschrieben –
        sonst liefe die Automation öfter oder seltener als gedacht.
        """
        async with self._native_lock:  # nie zwei Schreibvorgänge gleichzeitig; Stand erst im Lock ermitteln
            opts = self.native_opts()
            wanted, problems = {}, []
            for fid, flow in self.flows.items():
                if flow["native"] and flow["enabled"]:
                    if lost := N.lost_conditions(flow, opts):
                        problems.append(f"„{flow['name']}“: {', '.join(lost)} lässt sich in HA nicht abbilden")
                        continue
                    devices = self.resolve(flow) if flow["type"] == "plan" else []
                    auto = N.build(fid, flow, devices, opts)
                    wanted[auto["id"]] = auto
            try:
                await N.async_sync(self.hass, wanted)
                self.native_error = "; ".join(problems) or None
            except Exception as err:  # noqa: BLE001 – Zeitpläne sollen trotzdem gespeichert werden
                self.native_error = str(err)
                _LOGGER.error("HomeRhythm: Automationen konnten nicht geschrieben werden: %s", err)

    # ------------------------------------------------------------------ Reaktionen
    def _subscribe_triggers(self) -> None:
        if self._trigger_unsub:
            self._trigger_unsub()
            self._trigger_unsub = None
        entities = {t["entity"] for f in self.flows.values() if f["type"] == "react" and f["enabled"] and not f["native"] for t in f["triggers"]}
        if entities:
            self._trigger_unsub = async_track_state_change_event(self.hass, sorted(entities), self._on_trigger)

    @callback
    def _on_trigger(self, event: Event[EventStateChangedData]) -> None:
        if not self.hass.is_running:
            return
        eid = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        old_s, new_s = (old.state if old else None), (new.state if new else None)
        if old and new and old.state == new.state and eid.split(".")[0] not in ("input_button", "button", "event"):
            return  # nur Attribute geändert
        for fid, flow in self.flows.items():
            if flow["type"] != "react" or not flow["enabled"] or flow["native"]:
                continue
            if not any(t["entity"] == eid and F.trigger_fires(t, old_s, new_s) for t in flow["triggers"]):
                continue
            if not F.cond_true(flow["conds"], self.ctx()):
                continue
            self.start_reaction(fid, why=self.ctrl._name(eid))  # noqa: SLF001

    def start_reaction(self, fid: str, why: str = "Test") -> None:
        flow = self.flows[fid]
        running = self._tasks.get(fid)
        if running and not running.done():
            if flow["mode"] == "ignore":
                return
            running.cancel()
        self._tasks[fid] = self.hass.async_create_background_task(self._run_reaction(fid, flow, why), f"home_rhythm_{fid}")

    def _cancel(self, fid: str) -> None:
        task = self._tasks.pop(fid, None)
        if task and not task.done():
            task.cancel()
        self.runs.pop(fid, None)
        for unsub in self._verify_unsubs.pop(fid, []):
            unsub()

    async def async_stop_reaction(self, fid: str) -> None:
        self._get(fid)
        if fid not in self._tasks:
            return
        self._cancel(fid)
        self._log(fid, "info", "von Hand abgebrochen")
        self.ctrl.schedule_save()
        self.ctrl.notify_update()

    async def _sleep(self, seconds: float) -> None:
        """Warten über den HA-Zeitplaner (verträgt Zeitsprünge und lässt sich sauber abbrechen)."""
        fut: asyncio.Future[None] = self.hass.loop.create_future()

        @callback
        def _done(_now: datetime) -> None:
            if not fut.done():
                fut.set_result(None)

        unsub = async_call_later(self.hass, seconds, _done)
        try:
            await fut
        finally:
            unsub()

    async def _wait_until(self, cond: dict[str, Any], timeout: int) -> bool:
        """Warten, bis die Bedingung (eine Entität) erfüllt ist. False bei Zeitüberschreitung."""
        ctx = self.ctx()
        if F.cond_true(cond, ctx):
            return True
        fut: asyncio.Future[bool] = self.hass.loop.create_future()

        @callback
        def _changed(_event: Event[EventStateChangedData]) -> None:
            if not fut.done() and F.cond_true(cond, self.ctx()):
                fut.set_result(True)

        @callback
        def _timeout(_now: datetime) -> None:
            if not fut.done():
                fut.set_result(False)

        unsub = async_track_state_change_event(self.hass, [cond["entity"]], _changed)
        unsub_t = async_call_later(self.hass, timeout, _timeout)
        try:
            return await fut
        finally:
            unsub()
            unsub_t()

    async def _run_reaction(self, fid: str, flow: dict[str, Any], why: str) -> None:
        started = dt_util.now()
        self.runs[fid] = {"started": started.isoformat(), "step": 0, "until": None}
        self._notify()
        context = self.ctrl.own_context()
        failed: list[str] = []
        try:
            for i, step in enumerate(flow["steps"]):
                self.runs[fid].update(step=i, until=None)
                do = step["do"]
                if do == "wait":
                    self.runs[fid]["until"] = (dt_util.now() + timedelta(seconds=step["seconds"])).isoformat()
                    self._notify()
                    await self._sleep(step["seconds"])
                elif do == "wait_until":
                    self._notify()
                    if not await self._wait_until(step["until"], step.get("timeout", 14400)):
                        self._log(fid, "info", "Zeitgrenze beim Warten erreicht – weiter")
                    if step.get("after"):
                        self.runs[fid]["until"] = (dt_util.now() + timedelta(seconds=step["after"])).isoformat()
                        self._notify()
                        await self._sleep(step["after"])
                elif do == "blink":
                    for _ in range(step.get("times", 2)):
                        for eid in step["entities"]:
                            await self._safe_switch(eid, "off", None, None, context, failed)
                        await asyncio.sleep(step.get("pause", 5) / 10)
                        for eid in step["entities"]:
                            await self._safe_switch(eid, "on", None, None, context, failed)
                        await asyncio.sleep(step.get("pause", 5) / 10)
                elif do == "notify":
                    try:
                        if step["target"] == "persistent":
                            await self._call("persistent_notification", "create", {"title": "HomeRhythm", "message": step["message"]}, context)
                        else:
                            domain, service = step["target"].split(".", 1)
                            await self._call(domain, service, {"message": step["message"]}, context)
                    except Exception as err:  # noqa: BLE001
                        failed.append(f"Nachricht ({err})")
                else:
                    for eid in step["entities"]:
                        await self._safe_switch(eid, do, step.get("position"), step.get("brightness"), context, failed)
            secs = int((dt_util.now() - started).total_seconds())
            dur = f"{secs // 60} min" if secs >= 60 else f"{secs} s"
            self._log(fid, "bad" if failed else "ok", f"ausgelöst durch {why}, fertig nach {dur}" + (f" – Probleme: {', '.join(failed)}" if failed else ""))
        except asyncio.CancelledError:
            self._log(fid, "info", f"ausgelöst durch {why}, neu gestartet bzw. abgebrochen")
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.exception("HomeRhythm: Reaktion %s fehlgeschlagen", flow["name"])
            self._log(fid, "bad", "Fehler – siehe Protokoll von Home Assistant")
        finally:
            if self._tasks.get(fid) is asyncio.current_task():
                self.runs.pop(fid, None)
                self._tasks.pop(fid, None)
            self.ctrl.schedule_save()
            self._notify()

    async def _safe_switch(self, eid: str, do: str, position: int | None, brightness: int | None, context: Context, failed: list[str]) -> None:
        st = self.hass.states.get(eid)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            failed.append(self.ctrl._name(eid))  # noqa: SLF001
            return
        try:
            await self._switch(eid, do, position, brightness, context)
        except Exception as err:  # noqa: BLE001
            failed.append(self.ctrl._name(eid))  # noqa: SLF001
            _LOGGER.warning("HomeRhythm: %s nicht geschaltet: %s", eid, err)

    # ------------------------------------------------------------------ Daten für die Karte
    def _names(self) -> dict[str, str]:
        names = {f"flow:{fid}": f["name"] for fid, f in self.flows.items()}
        for f in self.flows.values():
            for e in self._entities_of(f):
                names[e] = self.ctrl._name(e)  # noqa: SLF001
        return names

    def _entities_of(self, flow: dict[str, Any]) -> list[str]:
        ents = list(flow.get("devices") or [])
        if flow["type"] == "react":
            ents += [t["entity"] for t in flow["triggers"]]
            for s in flow["steps"]:
                ents += s.get("entities", [])
                if s.get("until"):
                    ents.append(s["until"]["entity"])

        def walk(c: dict[str, Any]) -> None:
            if "items" in c:
                for x in c["items"]:
                    walk(x)
            elif c.get("entity"):
                ents.append(c["entity"])

        walk(flow["conds"])
        for p in flow.get("points", []):
            walk(p["conds"])
        return list(dict.fromkeys(ents))

    def _week_marks(self, fid: str, f: dict[str, Any], week: list[tuple[date, F.Sun, F.Ctx]]) -> list[list[dict[str, Any]]]:
        """Schaltpunkte je Wochentag (mit „Zeitplan gilt“; nach Mitternacht mit dem Vortag)."""
        out = []
        for i, (d, s, c) in enumerate(week):
            prev = week[i - 1][2] if i else self.ctx(d - timedelta(days=1))
            out.append(F.day_marks(fid, f, d, s, c, prev))
        return out

    def _week_ctx(self, monday: date) -> list[tuple[date, F.Sun, F.Ctx]]:
        out = []
        for i in range(7):
            d = monday + timedelta(days=i)
            out.append((d, self.ctrl.sun_for(d), self.ctx(d)))
        return out

    def snapshot(self) -> dict[str, Any]:
        opened = self._begin()
        try:
            return self._snapshot()
        finally:
            self._end(opened)

    def _snapshot(self) -> dict[str, Any]:
        now = dt_util.now()
        ctx = self.ctx()
        names = self._names()
        monday = now.date() - timedelta(days=now.weekday())
        week = self._week_ctx(monday)
        items = []
        device_owner: dict[str, list[str]] = {}
        for fid, f in self.flows.items():
            if f["type"] == "plan":
                for e in self.resolve(f):
                    device_owner.setdefault(f"{f['kind']}|{e}", []).append(fid)
        for fid, f in self.flows.items():
            wait = self.wait_reason(f, ctx)
            item: dict[str, Any] = {"id": fid, **f, "wait": wait, "cond_text": F.group_text(f["conds"], names), "log": list(self.logs.get(fid, []))[-10:][::-1]}
            ents = self.resolve(f) if f["type"] == "plan" else []
            item["resolved"] = [self._entity_info(e) for e in ents]
            item["unsupported"] = (N.unsupported(f) + N.lost_conditions(f, self.native_opts())) if f["native"] else []
            if f["type"] == "plan":
                last = self._last_event(fid, f, now)
                nxt = self.next_event(fid, f, now)
                item["state"] = F.ACTION_STATE[last[1]["action"]] if last else None
                item["next"] = {"at": nxt[0].isoformat(), "text": F.ACTION_NAMES[nxt[1]["action"]]} if nxt and not wait else None
                item["skip"] = fid in self.skip
                item["hand"] = self.hand.get(fid)
                item["week"] = [] if wait else [F.day_strip(fid, f, week, i) for i in range(7)]
                item["week_marks"] = [] if wait else self._week_marks(fid, f, week)
                item["week_ticks"] = [[x["m"] for x in day] for day in item["week_marks"]]
                item["day_labels"] = [F.day_label(f, c, d) for d, _s, c in week]
                item["point_texts"] = [F.point_text(p) + (f" – nur wenn {F.group_text(p['conds'], names)}" if p["conds"]["items"] else "") for p in f["points"]]
                item["overlaps"] = []
                others: dict[str, int] = {}
                for e in ents:
                    for other in device_owner.get(f"{f['kind']}|{e}", []):
                        if other != fid:
                            others[other] = others.get(other, 0) + 1
                item["overlaps"] = [{"id": o, "name": self.flows[o]["name"], "n": n} for o, n in others.items()]
            else:
                item["trigger_texts"] = [self._trigger_text(t, names) for t in f["triggers"]]
                item["step_texts"] = [F.step_text(s, names) for s in f["steps"]]
                item["run"] = self.runs.get(fid)
            items.append(item)
        return {"items": items, "native_error": self.native_error, "meta": self._meta(), "candidates": self._candidates(), "selectors": self._selectors()}

    def preview(self, data: dict[str, Any]) -> dict[str, Any]:
        opened = self._begin()
        try:
            return self._preview(data)
        finally:
            self._end(opened)

    def _preview(self, data: dict[str, Any]) -> dict[str, Any]:
        """Editor-Vorschau für einen ungespeicherten Ablauf (prüft dabei auch alle Eingaben)."""
        flow = F.normalize_flow(data)
        sim = data.get("sim") if isinstance(data.get("sim"), dict) else {}
        clean: dict[str, Any] = {k: str(sim[k])[:60] for k in ("season", "vacation") if sim.get(k) not in (None, "")}
        hol = [str(x)[:10] for x in (sim.get("holidays") or []) if isinstance(x, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", x)][:7]
        if hol:
            clean["holidays"] = hol
        self._sim = clean or None
        try:
            return self._preview_inner(data, flow)
        finally:
            self._sim = None

    def _preview_inner(self, data: dict[str, Any], flow: dict[str, Any]) -> dict[str, Any]:
        fid = data.get("id") or "neu"
        names = self._names()
        ctx = self.ctx()
        out: dict[str, Any] = {"cond_text": F.group_text(flow["conds"], names), "active": F.cond_true(flow["conds"], ctx),
                               "unsupported": (N.unsupported(flow) + N.lost_conditions(flow, self.native_opts())) if flow["native"] else []}
        if flow["type"] == "plan":
            now = dt_util.now()
            day = now.date()
            wanted = data.get("week")  # Editor: andere Woche zeigen (ein Tag daraus, JJJJ-MM-TT); höchstens ±2 Jahre
            if isinstance(wanted, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", wanted):
                try:
                    pick = date.fromisoformat(wanted)
                except ValueError:
                    pick = None
                if pick is not None and abs((pick - day).days) <= 730:
                    day = pick
            week = self._week_ctx(day - timedelta(days=day.weekday()))
            out["week"] = [F.day_strip(fid, flow, week, i) for i in range(7)]
            out["workdays"] = [c.workday for _d, _s, c in week]
            out["week_marks"] = self._week_marks(fid, flow, week)
            out["week_ticks"] = [[x["m"] for x in day] for day in out["week_marks"]]
            out["day_labels"] = [F.day_label(flow, c, d) for d, _s, c in week]
            out["dates"] = [d.isoformat() for d, _s, _c in week]
            out["sun"] = [{"rise": s.sunrise, "set": s.sunset} for _d, s, _c in week]
            out["sun_year"] = self.ctrl.sun_year(dt_util.now().year)  # Jahresband bei „frühestens/spätestens“
            out["point_texts"] = [F.point_text(p) for p in flow["points"]]
            if flow.get("mode") == "simple":
                out["points"] = flow["points"]  # für „Erweitert“: so sehen die Schaltpunkte aus
            out["devices"] = len(self.resolve(flow))
        else:
            out["trigger_texts"] = [self._trigger_text(t, names) for t in flow["triggers"]]
            out["step_texts"] = [F.step_text(s, names) for s in flow["steps"]]
        return out

    def simulate(self, sim: dict[str, Any]) -> dict[str, Any]:
        """Zeitpläne mit angenommenen Hausmodi berechnen (nur Anzeige, es wird nichts geschaltet)."""
        allowed = {"season", "vacation", "christmas", "presence", "event"}
        clean = {k: str(v)[:60] for k, v in (sim or {}).items() if k in allowed and v not in (None, "")}
        self._sim = clean
        try:
            return {"items": [i for i in self.snapshot()["items"] if i["type"] == "plan"]}
        finally:
            self._sim = None

    def _trigger_text(self, t: dict[str, Any], names: dict[str, str]) -> str:
        n = names.get(t["entity"], t["entity"])
        if t["kind"] == "state":
            return f"{n} wird {F._val(t['to'])}" if t.get("to") is not None else f"{n} ausgelöst / gedrückt"
        return f"{n} {'über' if t['kind'] == 'above' else 'unter'} {t['value']:g}"

    def _entity_info(self, eid: str) -> dict[str, Any]:
        st = self.hass.states.get(eid)
        bri = st.attributes.get("brightness") if st else None
        return {
            "entity_id": eid,
            "name": self.ctrl._name(eid),  # noqa: SLF001
            "state": st.state if st else "unavailable",
            "position": st.attributes.get("current_position") if st else None,
            "brightness": round(bri / 2.55) if bri is not None else None,
        }

    def _meta(self) -> dict[str, Any]:
        o = self._opts()
        return {
            "kinds": F.KINDS, "kind_domains": F.KIND_DOMAINS, "actions": F.ACTIONS, "action_names": F.ACTION_NAMES, "state_names": F.STATE_NAMES,
            "days": F.DAYS, "refs": F.REFS, "weekdays": F.WEEKDAYS, "day_types": F.DAY_TYPES,
            "simple_rows": F.SIMPLE_ROW_NAMES, "simple_like": F.SIMPLE_LIKE, "simple_like_names": F.SIMPLE_LIKE_NAMES,
            "home_value": o.get(CONF_HOME_VALUE) or "", "away_value": o.get(CONF_AWAY_VALUE) or "", "cond_keys": F.COND_KEYS, "cond_ops": F.COND_OPS, "date_ops": F.DATE_OPS,
            "cond_fixed": F.COND_FIXED_VALUES, "trigger_kinds": F.TRIGGER_KINDS, "trigger_domains": F.TRIGGER_DOMAINS, "step_kinds": F.STEP_KINDS, "react_modes": F.MODES_REACT,
            "cond_values": {
                "season": self.ctrl._options_of(o.get(CONF_SEASON_ENTITY)) or ["Winter", "Sommer", "Heißphase"],  # noqa: SLF001
                "vacation": self.ctrl._options_of(o.get(CONF_VACATION_ENTITY)) or ["kein Urlaub", o.get(CONF_HOME_VALUE) or "Urlaub zu Hause", "Urlaub unterwegs"],  # noqa: SLF001
                "event": list(E.EVENTS),
            },
            "notify_services": sorted(f"notify.{s}" for s in self.hass.services.async_services().get("notify", {})),
            "limits": {"flows": F.MAX_FLOWS, "points": F.MAX_POINTS, "steps": F.MAX_STEPS},
        }

    def _candidates(self) -> list[dict[str, Any]]:
        ent_reg = er.async_get(self.hass)
        out = []
        doms = set(F.KIND_DOMAINS[F.KIND_COVER] + F.KIND_DOMAINS[F.KIND_SWITCH] + F.TRIGGER_DOMAINS)
        for e in ent_reg.entities.values():
            if e.domain not in doms or e.disabled_by or e.hidden_by:
                continue
            if e.domain == "sensor" and (e.device_class or e.original_device_class) not in ("power", "illuminance", "temperature", "humidity", "energy", "current", "wind_speed"):
                continue
            st = self.hass.states.get(e.entity_id)
            dc = e.device_class or e.original_device_class or (st.attributes.get("device_class") if st else None)
            out.append({
                "entity_id": e.entity_id, "domain": e.domain, "name": self.ctrl._name(e.entity_id),  # noqa: SLF001
                "area_id": self.ctrl._area_of(e), "device_class": dc, "kind": F.DEVICE_CLASS_NAMES.get(dc or "", ""),  # noqa: SLF001
                "unit": st.attributes.get("unit_of_measurement") if st else None,
                "options": (st.attributes.get("options") or [])[:20] if st and e.domain == "input_select" else None,
                "position": bool(st and int(st.attributes.get("supported_features") or 0) & 4) if e.domain == "cover" else None,
            })
        # Entitäten ohne Registry-Eintrag (YAML, Templates) ebenfalls anbieten
        known = {c["entity_id"] for c in out}
        for st in self.hass.states.async_all():
            if st.entity_id in known or st.domain not in doms:
                continue
            dc = st.attributes.get("device_class")
            if st.domain == "sensor" and dc not in ("power", "illuminance", "temperature", "humidity", "energy", "current", "wind_speed"):
                continue
            out.append({"entity_id": st.entity_id, "domain": st.domain, "name": self.ctrl._name(st.entity_id),  # noqa: SLF001
                        "area_id": None, "device_class": dc, "kind": F.DEVICE_CLASS_NAMES.get(dc or "", ""), "unit": st.attributes.get("unit_of_measurement"),
                        "options": None, "position": None})
        return sorted(out, key=lambda x: x["name"].lower())

    def _selectors(self) -> dict[str, list[dict[str, str]]]:
        return {
            "area": [{"id": a.id, "name": a.name} for a in ar.async_get(self.hass).async_list_areas()],
            "floor": [{"id": f.floor_id, "name": f.name} for f in fr.async_get(self.hass).async_list_floors()],
            "label": [{"id": label.label_id, "name": label.name} for label in lr.async_get(self.hass).async_list_labels()],
        }

    def devices(self) -> list[dict[str, Any]]:
        opened = self._begin()
        try:
            return self._devices()
        finally:
            self._end(opened)

    def _devices(self) -> list[dict[str, Any]]:
        """Alle Geräte der Abläufe (für den Reiter „Geräte“)."""
        ent_reg = er.async_get(self.hass)
        roles: dict[str, tuple[str, str]] = {}
        loose: list[tuple[str, str]] = []
        used_by: dict[str, list[str]] = {}
        for f in self.flows.values():
            ents = (self.resolve(f) if f["type"] == "plan" else []) + self._entities_of(f)
            for eid in dict.fromkeys(ents):
                used_by.setdefault(eid, []).append(f["name"])
                e = ent_reg.async_get(eid)
                role = {"cover": "Rollladen", "light": "Licht", "switch": "Steckdose / Schalter", "binary_sensor": "Sensor", "sensor": "Sensor"}.get(eid.split(".")[0], "Gerät")
                if e and e.device_id:
                    roles.setdefault(e.device_id, (role, eid))
                else:
                    loose.append((role, eid))
        out = self.ctrl.device_infos(roles)
        for role, eid in dict.fromkeys(loose):
            st = self.hass.states.get(eid)
            out.append({"device_id": None, "name": self.ctrl._name(eid), "model": None, "role": role, "entity_id": eid,  # noqa: SLF001
                        "battery": None, "battery_low": False, "battery_entity": None,
                        "available": bool(st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)),
                        "last_changed": st.last_changed.isoformat() if st else None})
        # Taster der Zeitpläne (auch wenn sie in keinem Raum hängen)
        known = {d["device_id"] for d in out if d.get("device_id")}
        extra = {f["button"]["device_id"]: ("Taster", "") for f in self.flows.values() if f.get("button") and f["button"]["device_id"] not in known
                 and not str(f["button"]["device_id"]).startswith("entity:")}
        if extra:
            out += self.ctrl.device_infos(extra)
        for d in out:
            d["flows"] = used_by.get(d["entity_id"], [])
            d["uses"] = self.ctrl._flow_uses(self.ctrl._device_entities(d.get("device_id")) or {d["entity_id"]}, d.get("device_id"))  # noqa: SLF001
        return out

    # ------------------------------------------------------------------ Zeitleiste
    def timeline(self, day: date, assume: dict[str, Any] | None = None) -> dict[str, Any]:
        opened = self._begin()
        self._sim = self._clean_assume(assume, day)
        try:
            return self._timeline(day, assume or {})
        finally:
            self._sim = None
            self._end(opened)

    @staticmethod
    def _clean_assume(assume: dict[str, Any] | None, day: date) -> dict[str, Any] | None:
        """„Angenommen“ aus der Übersicht → Simulationswerte für die Abläufe (nur Anzeige)."""
        a = assume if isinstance(assume, dict) else {}
        out: dict[str, Any] = {k: str(a[k])[:60] for k in ("season", "vacation", "event") if a.get(k) not in (None, "")}
        if a.get("presence") in ("home", "away"):
            out["presence"] = a["presence"]
        if a.get("christmas") in ("0", "1"):
            out["christmas"] = a["christmas"]
        if a.get("holiday") == "1":
            out["holidays"] = [day.isoformat()]
        return out or None

    def at(self, day: date, minute: int, assume: dict[str, Any] | None = None) -> dict[str, Any]:
        """Stand zu einem Zeitpunkt (Übersicht, Zeitregler): Soll je Raum und Zustand je Zeitplan. Schaltet nichts."""
        opened = self._begin()
        self._sim = self._clean_assume(assume, day)
        try:
            return self._at(day, max(0, min(1439, int(minute))), assume or {})
        finally:
            self._sim = None
            self._end(opened)

    def day_states(self, day: date, assume: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ganzer Tag in Viertelstunden (96 Werte) – damit der Regler in der Übersicht ohne Rückfrage reagiert.

        rooms/flows: feste Angaben; slots[i] = {"r": [je Raum: level, temp, hvac, next_at, next_level, next_temp, manual],
        "f": [je Zeitplan: state, next_minute, next_text]}. Es wird nichts geschaltet.
        """
        opened = self._begin()
        self._sim = self._clean_assume(assume, day)
        try:
            return self._day_states(day, assume or {})
        finally:
            self._sim = None
            self._end(opened)

    def _day_states(self, day: date, assume: dict[str, Any]) -> dict[str, Any]:
        now = dt_util.now()
        tz = now.tzinfo
        ctx = self.ctx(day, sun_up=True)
        prev_ctx = self.ctx(day - timedelta(days=1))
        m_day = self._day_modes(day, ctx, assume)
        start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
        rooms, rcalc = [], []
        for rid, room in self.ctrl.rooms.items():
            if not room.get("enabled", True):
                rooms.append({"id": rid, "name": room["name"], "area_id": room.get("area_id"), "paused": True})
                continue
            if not (room.get("climate_entities") or room.get("ac_entities")):
                continue
            rooms.append({"id": rid, "name": room["name"], "area_id": room.get("area_id")})
            rcalc.append((rid, room))
        flows, fcalc = [], []
        week = self._week_ctx(day - timedelta(days=day.weekday()))
        for fid, f in self.flows.items():
            if f["type"] != "plan":
                continue
            flows.append({"id": fid, "name": f["name"], "icon": f["icon"], "kind": f["kind"], "enabled": f["enabled"],
                          "why": F.day_label(f, ctx, day) if f["enabled"] else "ausgeschaltet"})
            if f["enabled"]:
                strip = F.day_strip(fid, f, week, day.weekday())
                evs = [(m, F.ACTION_NAMES[p["action"]]) for m, _i, p in F.day_events(fid, f, day, self.ctrl.sun_for(day), ctx, prev_ctx, check_plan=True)]
                fcalc.append((fid, strip, evs))
            else:
                fcalc.append((fid, None, []))
        slots = []
        for q in range(96):
            t = start + timedelta(minutes=q * 15)
            r_out = []
            for rid, room in rcalc:
                manual = self.ctrl.manual.get(rid)
                manual = manual if manual and manual.until and manual.until > t and (manual.since is None or manual.since <= t + timedelta(minutes=15)) and not assume else None
                override = self.ctrl.overrides.get(rid)
                override = override if override and override.until > t else None
                r = E.evaluate(room, m_day, t, manual, with_until=False, today=day, override=override)
                nxt, nlvl = E.next_plan_change(room, t, m_day, horizon_days=4) if r.hvac_mode != "off" else (None, None)
                r_out.append([r.level, r.temperature, r.hvac_mode, nxt.isoformat() if nxt else None, nlvl,
                              E.level_temperature(room, nlvl) if nlvl and nlvl in (room.get("levels") or {}) else None, manual is not None, r.reason])
            f_out = []
            for _fid, strip, evs in fcalc:
                if strip is None:
                    f_out.append([None, None, None])
                    continue
                st = strip[q] if strip else "none"
                nx = next(((m, txt) for m, txt in evs if m > q * 15), None)
                f_out.append([None if st == "none" else st, nx[0] if nx else None, nx[1] if nx else None])
            slots.append({"r": r_out, "f": f_out})
        return {"date": day.isoformat(), "level_names": E.LEVEL_NAMES, "rooms": rooms, "flows": flows, "slots": slots,
                "holiday": self.holiday_name(day) or ("angenommen" if assume.get("holiday") == "1" else None), "workday": ctx.workday}

    def _day_modes(self, day: date, ctx: F.Ctx, assume: dict[str, Any]) -> E.Modes:
        modes = self.ctrl.modes_assumed(assume)
        return replace(modes, holiday_today=(not ctx.workday and day.weekday() < 5) or assume.get("holiday") == "1",
                       occasion="Weihnachten" if ctx.christmas else "", party_until=None)

    def _at(self, day: date, minute: int, assume: dict[str, Any]) -> dict[str, Any]:
        now = dt_util.now()
        tz = now.tzinfo
        t = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(minutes=minute)
        is_now = abs((t - now).total_seconds()) < 15 * 60 and not any(assume.get(k) for k in ("season", "vacation", "presence", "event", "christmas", "holiday"))
        rise, sets = self.ctrl.sun_times(day)
        ctx = self.ctx(day, sun_up=rise <= t < sets)
        m_day = self._day_modes(day, ctx, assume)
        rooms = []
        for rid, room in self.ctrl.rooms.items():
            item: dict[str, Any] = {"id": rid, "name": room["name"], "area_id": room.get("area_id")}
            if not room.get("enabled", True):
                rooms.append({**item, "paused": True})
                continue
            if not (room.get("climate_entities") or room.get("ac_entities")):
                continue
            manual = self.ctrl.manual.get(rid)
            manual = manual if manual and manual.until and manual.until > t and not assume else None  # Hand-Änderung nur, solange sie gilt
            override = self.ctrl.overrides.get(rid)
            override = override if override and override.until > t else None
            r = E.evaluate(room, m_day, t, manual, with_until=False, today=day, override=override)
            nxt, nlvl = E.next_plan_change(room, t, m_day, horizon_days=4) if r.hvac_mode != "off" or r.level != "aus" else (None, None)
            item.update({"level": r.level, "level_name": E.LEVEL_NAMES.get(r.level, r.level), "temperature": r.temperature, "hvac": r.hvac_mode,
                         "reason": r.reason, "rule": r.rule, "manual": manual is not None,
                         "next_at": nxt.isoformat() if nxt else None, "next_level": nlvl,
                         "next_level_name": E.LEVEL_NAMES.get(nlvl, nlvl) if nlvl else None,
                         "next_temp": E.level_temperature(room, nlvl) if nlvl and nlvl in (room.get("levels") or {}) else None})
            rooms.append(item)
        flows = []
        monday = day - timedelta(days=day.weekday())
        week = self._week_ctx(monday)
        idx = day.weekday()
        for fid, f in self.flows.items():
            if f["type"] != "plan":
                continue
            item = {"id": fid, "name": f["name"], "icon": f["icon"], "kind": f["kind"], "enabled": f["enabled"]}
            if not f["enabled"]:
                flows.append({**item, "state": None, "why": "ausgeschaltet"})
                continue
            strip = F.day_strip(fid, f, week, idx)
            st = strip[minute // 15] if strip else "none"
            why = F.day_label(f, ctx, day)
            nxt = None
            prev_ctx = self.ctx(day - timedelta(days=1))
            for m, _i, p in F.day_events(fid, f, day, self.ctrl.sun_for(day), ctx, prev_ctx, check_plan=True):
                if m > minute:
                    nxt = {"minute": m, "action": p["action"], "text": F.ACTION_NAMES[p["action"]]}
                    break
            flows.append({**item, "state": None if st == "none" else st, "why": why, "next": nxt})
        return {"date": day.isoformat(), "minute": minute, "now": is_now, "season": m_day.season, "workday": ctx.workday,
                "holiday": self.holiday_name(day) or ("angenommen" if assume.get("holiday") == "1" else None),
                "christmas": ctx.christmas, "rooms": rooms, "flows": flows}

    def _timeline(self, day: date, assume: dict[str, Any] | None = None) -> dict[str, Any]:
        """Alles, was an einem Tag geplant ist: Heizung, Zeitpläne, (heute) ausgelöste Reaktionen."""
        now = dt_util.now()
        tz = now.tzinfo
        sun = self.ctrl.sun_for(day)
        rise, sets = self.ctrl.sun_times(day)
        ctx = self.ctx(day, sun_up=None if day == now.date() else True)
        prev_ctx = self.ctx(day - timedelta(days=1), sun_up=True)
        events: list[dict[str, Any]] = []
        # Heizung: Wechsel von Stufe/Temperatur je Raum (5-Minuten-Raster, gleiche Minute zusammengefasst)
        events += self._heat_events(day, tz, ctx, assume or {})
        # Zeitpläne
        for fid, f in self.flows.items():
            if f["type"] != "plan" or not f["enabled"]:
                continue
            n = len(self.resolve(f))
            for m, _i, p in F.day_events(fid, f, day, sun, ctx, prev_ctx, check_plan=True):
                act = F.ACTION_NAMES[p["action"]] + (f" {p['position']} %" if p["action"] == "position" else "") + (f" {p['brightness']} %" if p.get("brightness") else "")
                extra = " (falls nötig)" if p.get("only_needed") else ""
                events.append({"minute": m, "cat": f["kind"], "icon": f["icon"], "title": f["name"], "text": f"{act}{extra} · {n} Gerät{'e' if n != 1 else ''}", "flow": fid,
                               "skip": fid in self.skip})
        # Reaktionen: heute ausgelöst (aus dem Protokoll)
        if day == now.date():
            for fid, f in self.flows.items():
                if f["type"] != "react":
                    continue
                for entry in self.logs.get(fid, []):
                    at = dt_util.parse_datetime(entry["at"])
                    if at and dt_util.as_local(at).date() == day:
                        loc = dt_util.as_local(at)
                        events.append({"minute": loc.hour * 60 + loc.minute, "cat": "react", "icon": f["icon"], "title": f["name"], "text": entry["text"], "flow": fid, "kind": entry["kind"]})
            for fid, run in self.runs.items():
                events.append({"minute": now.hour * 60 + now.minute, "cat": "react", "icon": self.flows[fid]["icon"], "title": self.flows[fid]["name"], "text": "läuft gerade", "flow": fid, "running": True})
        events.sort(key=lambda e: e["minute"])
        return {
            "date": day.isoformat(), "today": day == now.date(), "now": now.hour * 60 + now.minute,
            "workday": ctx.workday, "holiday": self.holiday_name(day), "christmas": ctx.christmas,
            "sunrise": rise.isoformat(), "sunset": sets.isoformat(), "events": events,
        }

    def _heat_events(self, day: date, tz, ctx: F.Ctx, assume: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        assume = assume or {}
        modes = self.ctrl.modes_assumed(assume)
        if not modes.heating_season:
            return [{"minute": 0, "cat": "heat", "icon": "🔥", "title": "Heizung", "text": f"aus – Jahreszeit {modes.season}"}]
        if modes.away:
            return [{"minute": 0, "cat": "heat", "icon": "🧳", "title": "Heizung", "text": f"alle Räume Urlaubstemperatur {modes.away_temp:g} °C"}]
        m_day = self._day_modes(day, ctx, assume)
        today = dt_util.now().date()
        by_min: dict[int, list[tuple[str, str]]] = {}
        for rid, room in self.ctrl.rooms.items():
            if not room.get("enabled", True) or not (room.get("climate_entities") or room.get("ac_entities")):
                continue
            override = self.ctrl.overrides.get(rid) if day == today and not assume else None
            prev = None
            for step in range(288):
                t = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(minutes=step * 5)
                r = E.evaluate(room, m_day, t, with_until=False, today=day, override=override)
                sig = (r.level, r.temperature, r.hvac_mode)
                if sig != prev and step > 0:
                    txt = "aus" if r.hvac_mode == "off" else f"{E.LEVEL_NAMES.get(r.level, r.level)} {r.temperature:g} °C"
                    by_min.setdefault(step * 5, []).append((room["name"], txt))
                prev = sig
        out = []
        for m, lst in sorted(by_min.items()):
            groups: dict[str, list[str]] = {}
            for room_name, txt in lst:
                groups.setdefault(txt, []).append(room_name)
            n = len(lst)
            title = lst[0][0] if n == 1 else f"Heizung · {n} Räume"
            text = " · ".join(f"{'' if n == 1 else ', '.join(rs) + ' '}→ {txt}" for txt, rs in groups.items())
            out.append({"minute": m, "cat": "heat", "icon": "🔥", "title": title, "text": text})
        return out

