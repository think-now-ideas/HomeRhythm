"""Bedienteile (ab 0.9.6, Anlernen ab 0.9.7): Geräte zum Bedienen eines Raums.

Ein Bedienteil ist ein GERÄT (z. B. Aqara W100, SONOFF SNZB-01M, Hue Dimmer). Für jede Funktion (wärmer, kälter,
zurück zum Plan …) wird einmal die Taste gedrückt; Home Rhythm merkt sich, was das Gerät dabei meldet (die
„Signatur“), und erkennt genau das wieder:

    event:<entität>:<ereignis>    Ereignis-Entität (Zigbee2MQTT 2.x), z. B. single_button_1
    action:<entität>:<wert>       alte Aktions-Entität (sensor.…_action)
    up:<entität> / down:<entität> Sollwert einer Thermostat-Anzeige hoch / runter (z. B. W100 + / −)
    mode:<entität>:<zustand>      Ein/Aus einer Thermostat-Anzeige
    plain:<entität>               Tastendruck-Meldung OHNE neuen Wert (W100: PMTSD ohne Anhang = Mitteltaste)

Grundsätze
- Ein Bedienteil spricht nie direkt mit dem Thermostat: Es löst eine Hand-Änderung des Raums aus, die Home Rhythm
  wie gewohnt an das Thermostat gibt (FRITZ!DECT, Better Thermostat, Integration, direkt).
- Eigene Befehle an das Gerät sind nie ein Tastendruck (eigener Kontext, gleicher Wert kurz danach, Meldung ohne
  Anhang kurz nach einem eigenen Befehl). Werte beim Wiedererreichen des Geräts ebenso nicht.
- Geräte mit Anzeige (Thermostat-Entität, z. B. W100 im Thermostat-Modus) zeigen den Sollwert des Raums. Nach jedem
  Tastendruck schreibt Home Rhythm den Wert SOFORT zurück – das W100 aktualisiert sein Display erst dann.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, Event, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .controller import HomeRhythmController

_LOGGER = logging.getLogger(__name__)

ACTIONS = ("warmer", "colder", "back", "boost", "comfort", "off")
MAX_CONTROLS = 10  # je Raum
MAX_MAPPINGS = 24  # je Gerät
OWN_CONTEXT_KEEP = 200
ECHO_WINDOW = timedelta(seconds=60)  # so lange nach einem eigenen Befehl gilt der GLEICHE Wert als Echo
OWN_WRITE_QUIET = timedelta(seconds=5)  # Meldung ohne Anhang so kurz nach eigenem Befehl = Antwort, kein Tastendruck
PRESS_CONFIRM_DELAY = 3  # s – auf die Tastendruck-Meldung mit Anhang warten
PRESS_CONFIRM_WINDOW = timedelta(seconds=20)
LEARN_TIMEOUT = timedelta(seconds=20)
ANY = "*"  # Anlernen „Taste drücken zum Erkennen“: auf alle Taster-Geräte hören, der erste Druck legt Gerät und Taste fest
BOOST_DURATION = timedelta(hours=1)
SIG_RE = re.compile(r"^(event|action|up|down|mode|plain):[a-z_]+\.[a-z0-9_]+(:.{1,64})?$")
PSEUDO = "entity:"  # Gerät ohne Registry-Eintrag: „entity:<entity_id>“


# --------------------------------------------------------------------------- Prüfen / Umwandeln
def normalize(raw: Any, room_entities: list[str], hass=None) -> list[dict[str, Any]]:
    """Bedienteile eines Raums prüfen; Einträge aus 0.9.6 (je Entität) werden umgewandelt."""
    if not raw:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_CONTROLS:
        raise ValueError(f"Höchstens {MAX_CONTROLS} Bedienteile je Raum")
    out, seen = [], set()
    for c in raw:
        if not isinstance(c, dict):
            raise ValueError("Ungültiges Bedienteil")
        if "type" in c and "device_id" not in c:
            c = migrate(c, hass)
        dev = c.get("device_id")
        if not isinstance(dev, str) or not dev or len(dev) > 128:
            raise ValueError("Ungültiges Bedienteil")
        if dev in seen:
            raise ValueError("Ein Bedienteil ist doppelt eingetragen")
        seen.add(dev)
        display = c.get("display") or None
        if display is not None:
            if not isinstance(display, str) or not display.startswith("climate."):
                raise ValueError("Die Anzeige eines Bedienteils muss eine Thermostat-Entität sein")
            if display in room_entities:
                raise ValueError("Ein Thermostat des Raums kann nicht zugleich Bedienteil sein")
        mapping = c.get("map") or {}
        if not isinstance(mapping, dict) or len(mapping) > MAX_MAPPINGS:
            raise ValueError("Zu viele Tastenzuordnungen")
        clean, used_actions = {}, set()
        for sig, act in mapping.items():
            if act in (None, "", "none"):
                continue
            if not isinstance(sig, str) or not SIG_RE.match(sig) or act not in ACTIONS:
                raise ValueError("Ungültige Tastenzuordnung")
            if act in used_actions:
                raise ValueError("Jede Funktion kann nur einer Taste zugeordnet werden")
            used_actions.add(act)
            clean[sig] = act
        try:
            step = float(c.get("step", 0.5))
        except (TypeError, ValueError) as err:
            raise ValueError("Ungültige Schrittweite") from err
        if step not in (0.5, 1.0):
            raise ValueError("Schrittweite 0,5 oder 1 °C")
        out.append({"device_id": dev, "display": display, "map": clean, "step": step})
    return out


def migrate(old: dict[str, Any], hass=None) -> dict[str, Any]:
    """0.9.6 → 0.9.7: {type, entity_id, center|map} → {device_id, display, map(Signatur → Aktion)}."""
    eid = old.get("entity_id") or ""
    dev = None
    if hass is not None and eid:
        e = er.async_get(hass).async_get(eid)
        dev = e.device_id if e else None
    dev = dev or f"{PSEUDO}{eid}"
    if old.get("type") == "display":
        # + / − = wärmer / kälter; die Mitteltaste wird neu angelernt (meldete sich anders als erwartet)
        return {"device_id": dev, "display": eid, "map": {f"up:{eid}": "warmer", f"down:{eid}": "colder"}, "step": 0.5}
    kind = "event" if eid.startswith("event.") else "action"
    mapping, used = {}, set()
    for name, act in (old.get("map") or {}).items():
        if act in ACTIONS and act not in used:
            mapping[f"{kind}:{eid}:{name}"] = act
            used.add(act)
    return {"device_id": dev, "display": None, "map": mapping, "step": old.get("step", 0.5)}


def label(sig: str) -> str:
    """Signatur verständlich anzeigen."""
    kind, _, rest = sig.partition(":")
    ent, _, val = rest.partition(":")
    return {
        "event": f"Ereignis „{val}“",
        "action": f"Aktion „{val}“",
        "up": "Sollwert hoch (+)",
        "down": "Sollwert runter (−)",
        "mode": f"Ein/Aus → {val}",
        "plain": "Tastendruck ohne Wert (z. B. Mitteltaste)",
    }.get(kind, sig)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _step_of(state) -> float:
    s = _num(state.attributes.get("target_temp_step")) if state else None
    return s if s and s > 0 else 0.5


def round_to(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


def _is_stamp(entity_id: str, unique_id: str | None = None) -> bool:
    return entity_id.startswith("sensor.") and "pmtsd" in f"{entity_id} {unique_id or ''}".lower()


# --------------------------------------------------------------------------- Laufzeit
class ControlManager:
    """Hört auf Bedienteil-Geräte, lernt Tasten an und hält Anzeigen aktuell."""

    def __init__(self, ctrl: HomeRhythmController) -> None:
        self.ctrl = ctrl
        self.hass = ctrl.hass
        self._unsub = None
        self._own: list[str] = []  # Kontext-IDs eigener Befehle
        self._sent: dict[str, dict[str, Any]] = {}  # Anzeige → {"temp", "mode", "at"}
        self._wrote: dict[str, datetime] = {}  # Gerät → letzter eigener Befehl
        self._pending: dict[str, Any] = {}
        self._learn: dict[str, dict[str, Any]] = {}  # Gerät → {"since", "sig"}
        self._watch_map: dict[str, str] = {}  # Entität → Gerät

    # ------------------------------------------------------------------ Geräte und Entitäten
    def device_entities(self, device_id: str) -> list[str]:
        if device_id.startswith(PSEUDO):
            return [device_id[len(PSEUDO):]]
        reg = er.async_get(self.hass)
        return [e.entity_id for e in er.async_entries_for_device(reg, device_id) if not e.disabled_by]

    def _stamp_of(self, device_id: str) -> str | None:
        reg = er.async_get(self.hass)
        for eid in self.device_entities(device_id):
            e = reg.async_get(eid)
            if _is_stamp(eid, e.unique_id if e else None):
                return eid
        return None

    def controls_of(self, room: dict[str, Any]) -> list[dict[str, Any]]:
        return room.get("controls") or []

    def owner(self, device_id: str) -> tuple[str, dict[str, Any]] | None:
        for rid, room in self.ctrl.rooms.items():
            for c in self.controls_of(room):
                if c["device_id"] == device_id:
                    return rid, c
        return None

    def flow_buttons(self) -> list[tuple[str, dict[str, Any]]]:
        """(Zeitplan-ID, Taster) aller Zeitpläne mit angelerntem Taster."""
        runner = getattr(self.ctrl, "runner", None)
        if runner is None:
            return []
        return [(fid, f["button"]) for fid, f in runner.flows.items() if f.get("type") == "plan" and f.get("button")]

    def track(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        self._watch_map = {}
        devices = {c["device_id"] for r in self.ctrl.rooms.values() for c in self.controls_of(r)} | (set(self._learn) - {ANY})
        devices |= {b["device_id"] for _fid, b in self.flow_buttons()}
        if ANY in self._learn:
            devices |= {c["device_id"] for c in self.candidates()}
        for dev in devices:
            for eid in self.device_entities(dev):
                self._watch_map[eid] = dev
        if self._watch_map:
            self._unsub = async_track_state_change_event(self.hass, list(self._watch_map), self._on_change)

    def unload(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        for cancel in self._pending.values():
            cancel()
        self._pending.clear()

    def _context(self, device_id: str) -> Context:
        ctx = Context()
        self._own.append(ctx.id)
        del self._own[: max(0, len(self._own) - OWN_CONTEXT_KEEP)]
        self._wrote[device_id] = dt_util.utcnow()
        return ctx

    # ------------------------------------------------------------------ Anzeige
    async def async_sync(self, only_room: str | None = None, force: bool = False) -> None:
        """Sollwert jedes Raums auf den Anzeigen seiner Bedienteile zeigen (force: auch wenn HA den Wert schon hat)."""
        for rid, room in self.ctrl.rooms.items():
            if only_room and rid != only_room:
                continue
            if not room.get("enabled", True):
                continue
            res = self.ctrl.results.get(rid)
            if res is None:
                continue
            for c in self.controls_of(room):
                if c.get("display"):
                    try:
                        await self._async_show(c["device_id"], c["display"], res.temperature, res.hvac_mode, force)
                    except Exception:  # noqa: BLE001 – eine Anzeige darf die Steuerung nie stören
                        _LOGGER.exception("Home Rhythm: Bedienteil %s nicht aktualisiert", c["display"])

    async def _async_show(self, device_id: str, entity_id: str, temp: float | None, mode: str, force: bool) -> None:
        if entity_id in self._pending:
            return  # Tastendruck wird gerade geprüft – Anzeige nicht überschreiben
        st = self.hass.states.get(entity_id)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        want_mode = "off" if mode == "off" or temp is None else "heat"
        if want_mode not in (st.attributes.get("hvac_modes") or []):
            want_mode = st.state
        sent = self._sent.get(entity_id) or {"at": datetime.min.replace(tzinfo=dt_util.UTC)}
        sent["mode"], sent["temp"] = want_mode, None
        if st.state != want_mode:
            sent["at"] = dt_util.utcnow()
            self._sent[entity_id] = sent
            await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": want_mode}, blocking=True, context=self._context(device_id))
        if want_mode == "heat" and temp is not None:
            step = _step_of(st)
            want = round_to(temp, step)
            lo, hi = _num(st.attributes.get("min_temp")), _num(st.attributes.get("max_temp"))
            want = max(want, lo) if lo is not None else want
            want = min(want, hi) if hi is not None else want
            sent["temp"] = want
            cur = _num(st.attributes.get("temperature"))
            if force or cur is None or abs(cur - want) > step / 2 - 0.01:
                sent["at"] = dt_util.utcnow()
                self._sent[entity_id] = sent
                await self.hass.services.async_call("climate", "set_temperature", {"entity_id": entity_id, "temperature": want}, blocking=True, context=self._context(device_id))
        self._sent[entity_id] = sent

    # ------------------------------------------------------------------ Signatur einer Zustandsänderung
    def _signature(self, eid: str, old, new) -> tuple[str | None, float | None]:
        """Was hat das Gerät gemeldet? (Signatur, neuer Sollwert) – None = kein Tastendruck."""
        if new is None or new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) and not eid.startswith("event."):
            return None, None
        if new.context.id in self._own:
            return None, None  # eigener Befehl
        if eid.startswith("event."):
            if new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) or old is None or old.state == STATE_UNAVAILABLE or old.state == new.state:
                return None, None  # Start / Wiederverbinden („unknown“ = noch nie gedrückt → zählt)
            et = new.attributes.get("event_type")
            return (f"event:{eid}:{str(et)[:64]}", None) if et else (None, None)
        if old is None or old.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None, None  # Gerät (wieder) erreichbar – gemeldete Werte sind kein Tastendruck
        if eid.startswith("sensor.") and eid.endswith("_action"):
            if new.state in ("", "None") or new.state == old.state and new.last_changed == old.last_changed:
                return None, None
            return f"action:{eid}:{str(new.state)[:64]}", None
        if eid.startswith("climate."):
            t_old, t_new = _num(old.attributes.get("temperature")), _num(new.attributes.get("temperature"))
            sent = self._sent.get(eid)
            recent = sent is not None and dt_util.utcnow() - sent["at"] < ECHO_WINDOW
            if old.state != new.state:
                if recent and new.state == sent.get("mode"):
                    return None, None  # Rückmeldung des eigenen Befehls
                return f"mode:{eid}:{new.state}", None
            if t_old is not None and t_new is not None and abs(t_old - t_new) > 0.01:
                if recent and sent.get("temp") is not None and abs(t_new - sent["temp"]) < 0.01:
                    return None, None  # gleicher Wert wie gesendet = Echo
                return (f"up:{eid}" if t_new > t_old else f"down:{eid}"), t_new
            return None, None  # nur die Messung o. Ä. hat sich geändert
        if _is_stamp(eid):
            if str(new.state) == str(old.state) or "_" in str(new.state):
                return None, None  # mit Anhang: der neue Wert kommt über die Thermostat-Entität
            dev = self._watch_map.get(eid)
            wrote = self._wrote.get(dev) if dev else None
            if wrote and dt_util.utcnow() - wrote < OWN_WRITE_QUIET:
                return None, None  # Antwort auf einen eigenen Befehl
            return f"plain:{eid}", None
        return None, None

    # ------------------------------------------------------------------ Ereignisse
    @callback
    def _on_change(self, event: Event) -> None:
        eid = event.data["entity_id"]
        dev = self._watch_map.get(eid)
        if dev is None:
            return
        sig, value = self._signature(eid, event.data.get("old_state"), event.data.get("new_state"))
        if sig is None:
            return
        learning = self._learn.get(dev) if dev in self._learn else self._learn.get(ANY)
        if learning is not None and learning["sig"] is None:
            learning["sig"] = sig  # Anlernen: Signatur (und bei „Erkennen“ das Gerät) merken, nichts ausführen
            learning["device"] = dev
            if hit := self.owner(dev):
                self.hass.async_create_task(self.async_sync(hit[0], force=True))  # Anzeige wieder auf den Raum
            return
        for fid, btn in self.flow_buttons():  # Taster eines Zeitplans: alle Geräte gemeinsam schalten
            if btn["device_id"] == dev and (what := btn["map"].get(sig)):
                self.hass.async_create_task(self._async_flow_press(fid, what, dev))
        hit = self.owner(dev)
        if hit is None:
            return
        room_id, ctl = hit
        action = ctl["map"].get(sig)
        if action is None:
            return
        press = {"room_id": room_id, "device_id": dev, "entity_id": eid, "sig": sig, "action": action, "value": value, "at": dt_util.utcnow()}
        stamp = self._stamp_of(dev) if sig.startswith(("up:", "down:")) else None
        if stamp is None:
            self.hass.async_create_task(self._async_run(press))
            return
        # Gerät mit Tastendruck-Meldung (W100): + / − nur, wenn die Meldung mit Anhang den neuen Wert trägt
        if eid in self._pending:
            self._pending.pop(eid)()
        if self._stamp_confirms(stamp, press):
            self.hass.async_create_task(self._async_run(press))
            return

        @callback
        def _confirm(_now) -> None:
            self._pending.pop(eid, None)
            cur = self.hass.states.get(eid)
            still = cur is not None and value is not None and abs((_num(cur.attributes.get("temperature")) or -99) - value) < 0.01
            if still and self._stamp_confirms(stamp, press):
                self.hass.async_create_task(self._async_run(press))
            else:
                _LOGGER.info("Home Rhythm: %s meldet neuen Sollwert ohne Tastendruck – ignoriert", eid)
                self.hass.async_create_task(self.async_sync(room_id))

        self._pending[eid] = async_call_later(self.hass, PRESS_CONFIRM_DELAY, _confirm)

    async def _async_flow_press(self, fid: str, what: str, dev: str) -> None:
        try:
            name = self._device_name(dev)
            await self.ctrl.runner.async_button(fid, what, name if name.lower().startswith("taster") else f"Taster {name}")
        except Exception:  # noqa: BLE001 – ein Taster darf nichts anderes stören
            _LOGGER.exception("Home Rhythm: Taster für Zeitplan %s fehlgeschlagen", fid)

    def _stamp_confirms(self, stamp: str, press: dict[str, Any]) -> bool:
        """Aqara W100: „JJJJ-MM-TT hh:mm:ss_MW1_TW20“ – mit Anhang und passendem TW = am Gerät gedrückt."""
        st = self.hass.states.get(stamp)
        if st is None or not st.last_changed or abs(st.last_changed - press["at"]) > PRESS_CONFIRM_WINDOW:
            return False
        text = str(st.state)
        if "_" not in text:
            return False
        fields = {part[:2]: part[2:] for part in text.split("_")[1:] if len(part) > 2}
        if press.get("value") is not None and "TW" in fields:
            try:
                return abs(float(fields["TW"]) - press["value"]) < 0.01
            except ValueError:
                return True
        return True

    async def _async_run(self, press: dict[str, Any]) -> None:
        hit = self.owner(press["device_id"])
        if hit is None:
            return
        room_id, ctl = hit
        name = self._device_name(press["device_id"])
        own_value = press["value"] if press["sig"].startswith(("up:", "down:")) and press["entity_id"] == ctl.get("display") else None
        await self.async_action(room_id, press["action"], name, step=ctl.get("step", 0.5), value=own_value)
        await self.async_sync(room_id, force=True)  # Display sofort aktualisieren (W100 wartet darauf)

    # ------------------------------------------------------------------ Aktionen
    async def async_action(self, room_id: str, action: str, name: str, step: float = 0.5, value: float | None = None) -> None:
        from . import engine as E  # noqa: PLC0415

        room = self.ctrl.rooms.get(room_id)
        if room is None:
            return
        res = self.ctrl.results.get(room_id)
        src = f"Bedienteil {name}"
        if action in ("warmer", "colder"):
            if value is None:
                base = res.temperature if res and res.temperature is not None else E.level_temperature(room, "komfort")
                value = round_to(base + (step if action == "warmer" else -step), 0.5)
            await self.ctrl.async_room_manual(room_id, max(5.0, min(30.0, value)), "heat", None, src)
        elif action == "back":
            await self.ctrl.async_clear_manual(room_id)
        elif action == "boost":
            await self.ctrl.async_room_manual(room_id, E.level_temperature(room, "bad"), "heat", dt_util.now() + BOOST_DURATION, src)
        elif action == "comfort":
            await self.ctrl.async_room_manual(room_id, E.level_temperature(room, "komfort"), "heat", None, src)
        elif action == "off":
            await self.ctrl.async_room_manual(room_id, None, "off", None, src)

    # ------------------------------------------------------------------ Anlernen
    def learn_start(self, device_id: str) -> None:
        self._learn = {k: v for k, v in self._learn.items() if dt_util.utcnow() - v["since"] < LEARN_TIMEOUT}
        self._learn[device_id] = {"since": dt_util.utcnow(), "sig": None}
        self.track()

    def learn_result(self, device_id: str) -> dict[str, Any]:
        cur = self._learn.get(device_id)
        if cur is None:
            return {"state": "idle"}
        if cur["sig"]:
            sig, dev = cur["sig"], cur.get("device") or device_id
            self._learn.pop(device_id, None)
            self.track()
            return {"state": "done", "signature": sig, "label": label(sig), "device_id": dev, "name": self._device_name(dev)}
        if dt_util.utcnow() - cur["since"] > LEARN_TIMEOUT:
            self._learn.pop(device_id, None)
            self.track()
            return {"state": "timeout"}
        return {"state": "waiting"}

    def learn_cancel(self, device_id: str) -> None:
        if self._learn.pop(device_id, None) is not None:
            self.track()

    # ------------------------------------------------------------------ Auswahl im Editor
    def _device_name(self, device_id: str) -> str:
        if device_id.startswith(PSEUDO):
            eid = device_id[len(PSEUDO):]
            st = self.hass.states.get(eid)
            return (st.attributes.get("friendly_name") if st else None) or eid
        d = dr.async_get(self.hass).async_get(device_id)
        return (d.name_by_user or d.name) if d else device_id

    def candidates(self) -> list[dict[str, Any]]:
        """Geräte, die als Bedienteil taugen: mit Ereignis-/Aktions-Entität oder Thermostat-Anzeige ohne Ventil."""
        reg, dreg = er.async_get(self.hass), dr.async_get(self.hass)
        used = {e for r in self.ctrl.rooms.values() for e in (list(r.get("climate_entities") or []) + list(r.get("ac_entities") or []))}
        panels = self.ctrl.panel_climates()
        out: dict[str, dict[str, Any]] = {}
        for e in reg.entities.values():
            if e.disabled_by or not e.device_id:
                continue
            is_btn = e.domain == "event" or (e.domain == "sensor" and (e.entity_id.endswith("_action") or _is_stamp(e.entity_id, e.unique_id)))
            is_disp = e.domain == "climate" and e.entity_id not in used and e.platform not in ("better_thermostat", "versatile_thermostat", "home_rhythm")
            if not (is_btn or is_disp):
                continue
            d = dreg.async_get(e.device_id)
            if d is None:
                continue
            item = out.setdefault(e.device_id, {"device_id": e.device_id, "name": d.name_by_user or d.name or e.entity_id,
                                                "area_id": d.area_id, "display": None, "panel": False, "buttons": False})
            if is_disp and (item["display"] is None or e.entity_id in panels):
                item["display"] = e.entity_id
                item["panel"] = e.entity_id in panels
            if is_btn:
                item["buttons"] = True
        # nur Thermostat ohne Tasten und ohne „Bedienteil“-Merkmal ist eher ein Heizkörperthermostat → nicht anbieten
        items = [i for i in out.values() if i["buttons"] or i["panel"]]
        return sorted(items, key=lambda x: (not x["panel"], x["name"].lower()))

    def view(self, room: dict[str, Any]) -> list[dict[str, Any]]:
        """Bedienteile eines Raums für die Karte (mit lesbaren Tastennamen)."""
        out = []
        for c in self.controls_of(room):
            out.append({**c, "name": self._device_name(c["device_id"]), "labels": {sig: label(sig) for sig in c["map"]}})
        return out
