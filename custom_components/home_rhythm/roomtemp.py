"""Raumtemperatur je Raum (ab 0.9.5): Art des Thermostats, Sensoren, Korrektur, Senden, Beobachten.

Grundsatz: Ohne eigene Einstellung ändert sich NICHTS. Ein Raum ohne die neuen Felder verhält sich wie bisher
(„Fühler am Thermostat“, keine Korrektur). Alles hier ist entweder reine Berechnung oder wird nur für Räume
aktiv, in denen der Nutzer es eingestellt hat.

Begriffe
- kind:        fritz | bt | integration | direct   (eine Art je Raum)
- temp_source: device (Fühler am Thermostat) | sensors (Raumsensoren, Durchschnitt) | box (in der Fritz!Box, z. B. 440)
- correction:  none | fixed | observe
               fixed: c °C wird zum gemessenen Wert addiert gedacht (wie der Versatz in der Fritz!Box):
                      misst der Fühler 1,5 °C zu viel → c = −1,5 → Home Rhythm schickt Soll − c = Soll + 1,5.
               observe: nichts an der Regelung ändern, nur die Abweichung Fühler ↔ Raum messen.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

KINDS = ("fritz", "bt", "integration", "direct")
SOURCES = ("device", "sensors", "box")
CORRECTIONS = ("none", "fixed", "observe")

# Viele Sensoren melden sich nur bei einer Änderung – bei gleichbleibender Temperatur stundenlang nichts.
# Deshalb zählt ein Sensor erst nach langer Funkstille nicht mehr (oder sofort, wenn er „nicht verfügbar“ ist).
STALE_AFTER = timedelta(hours=12)
STUCK_AFTER = timedelta(hours=3)  # gleicher Wert so lange, während geheizt wird → nur Hinweis
PUSH_EVERY = timedelta(minutes=10)  # spätestens so oft an das Thermostat senden
PUSH_MIN_DELTA = 0.1  # °C – kleinere Änderungen nicht sofort senden
REMOTE_RETRY = timedelta(hours=1)  # „remote“ höchstens so oft erneut einstellen
CLOSED_FOR = timedelta(minutes=60)  # Ventil so lange zu, bevor eine Beobachtung zählt
SAMPLE_EVERY = timedelta(minutes=10)
MAX_SAMPLES = 3000  # je Raum (≈ 3 Wochen bei 1 Messung / 10 min)
SPREAD_WARN = 2.0  # °C zwischen den Raumsensoren
MAX_CORRECTION = 5.0

REMOTE_OPTION = "remote_temperature"
OFFLINE_OPTION = "remote_source_offline"


# --------------------------------------------------------------------------- Einstellungen
def kind_for(platforms: list[str | None]) -> str:
    """Art aus den Plattformen der Thermostate eines Raums ableiten (Migration bestehender Räume)."""
    if "better_thermostat" in platforms:
        return "bt"
    if "versatile_thermostat" in platforms:
        return "integration"
    if platforms and all(p == "fritzbox" for p in platforms):
        return "fritz"
    if "fritzbox" in platforms:
        return "fritz"
    return "direct"


def normalize(data: dict[str, Any], old: dict[str, Any], kind_default: str) -> dict[str, Any]:
    """Neue Raumfelder prüfen. Fehlende Felder → bisheriges Verhalten."""

    def pick(key: str, default: Any) -> Any:
        return data[key] if key in data else old.get(key, default)

    kind = pick("kind", None) or kind_default
    if kind not in KINDS:
        raise ValueError("Unbekannte Art von Thermostat")
    source = pick("temp_source", "device") or "device"
    if source not in SOURCES:
        raise ValueError("Unbekannte Temperaturquelle")
    if kind in ("bt", "integration"):
        source = "device"  # misst die Integration selbst
    if source == "box" and kind != "fritz":
        raise ValueError("„In der Fritz!Box eingestellt“ gibt es nur bei FRITZ!DECT")
    sensors = [s for s in dict.fromkeys(pick("temp_sensors", []) or []) if isinstance(s, str) and s.startswith("sensor.")]
    if source == "sensors" and not sensors:
        raise ValueError("Bitte mindestens einen Raumsensor wählen")
    box = pick("box_sensor", "") or ""
    if source == "box" and not (isinstance(box, str) and box.startswith("sensor.")):
        raise ValueError("Bitte den Sensor wählen, den die Fritz!Box nutzt (z. B. FRITZ!DECT 440)")
    corr = pick("correction", "none") or "none"
    if corr not in CORRECTIONS:
        raise ValueError("Unbekannte Korrektur")
    if kind in ("bt", "integration") or source == "box" or (kind == "direct" and source == "sensors"):
        corr = "none"  # macht die Integration / die Fritz!Box / das Thermostat selbst
    if corr == "observe" and not (kind == "fritz" and source == "sensors"):
        corr = "none"
    try:
        value = float(pick("correction_value", 0) or 0)
    except (TypeError, ValueError) as err:
        raise ValueError("Korrektur ist keine Zahl") from err
    value = max(-MAX_CORRECTION, min(MAX_CORRECTION, round(value * 2) / 2))
    return {
        "kind": kind,
        "temp_source": source,
        "temp_sensors": sensors if source == "sensors" else [],
        "box_sensor": box if source == "box" else "",
        "correction": corr,
        "correction_value": value if corr == "fixed" else 0.0,
    }


def correction(room: dict[str, Any]) -> float:
    """Feste Korrektur des Raums (0, wenn keine)."""
    if room.get("correction") != "fixed":
        return 0.0
    try:
        return float(room.get("correction_value") or 0)
    except (TypeError, ValueError):
        return 0.0


def pushes(room: dict[str, Any]) -> bool:
    return room.get("kind") == "direct" and room.get("temp_source") == "sensors" and bool(room.get("temp_sensors"))


def observes(room: dict[str, Any]) -> bool:
    return room.get("correction") == "observe" and room.get("temp_source") == "sensors" and bool(room.get("temp_sensors"))


# --------------------------------------------------------------------------- Messwerte
def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if -40 <= x <= 80 else None


def reported_at(state) -> datetime | None:
    """Letzte Meldung eines Sensors – `last_reported` zählt auch unveränderte Werte (HA ≥ 2024.3)."""
    return getattr(state, "last_reported", None) or getattr(state, "last_updated", None)


@dataclass
class Reading:
    value: float | None  # Durchschnitt der gültigen Sensoren
    used: list[dict[str, Any]] = field(default_factory=list)  # [{entity_id, name, value, stale, area_id}]
    stale: list[str] = field(default_factory=list)
    spread: float = 0.0

    @property
    def ok(self) -> bool:
        return self.value is not None


def read_sensors(hass, entity_ids: list[str], now: datetime, area_of=None) -> Reading:
    used, vals, stale = [], [], []
    for eid in entity_ids:
        st = hass.states.get(eid)
        v = _num(st.state) if st else None
        at = reported_at(st) if st else None
        old = v is None or at is None or now - at > STALE_AFTER
        changed = getattr(st, "last_changed", None) if st else None
        used.append(
            {
                "entity_id": eid,
                "changed": changed.isoformat() if changed else None,
                "name": (st.attributes.get("friendly_name") if st else None) or eid,
                "value": v,
                "stale": old,
                "area_id": area_of(eid) if area_of else None,
            }
        )
        if old:
            stale.append(eid)
        else:
            vals.append(v)
    avg = round(sum(vals) / len(vals), 2) if vals else None
    spread = round(max(vals) - min(vals), 2) if len(vals) > 1 else 0.0
    return Reading(avg, used, stale, spread)


# --------------------------------------------------------------------------- Thermostat direkt: Raumwert senden
def push_targets(hass, climate_entity: str) -> tuple[str | None, str | None]:
    """Eingang für externe Temperatur (number) und Quellenwahl (select) am selben Gerät finden (Zigbee2MQTT & Co.)."""
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    reg = er.async_get(hass)
    entry = reg.async_get(climate_entity)
    if not entry or not entry.device_id:
        return None, None
    num = sel = None
    for e in er.async_entries_for_device(reg, entry.device_id):
        if e.disabled_by:
            continue
        key = f"{e.entity_id} {e.translation_key or ''} {e.unique_id or ''}".lower()
        if e.domain == "number" and "external_temperature" in key and num is None:
            num = e.entity_id
        elif e.domain == "select" and "temperature_sensor" in key and sel is None:
            sel = e.entity_id
    return num, sel


def push_due(last: dict[str, Any] | None, value: float, now: datetime) -> bool:
    if not last:
        return True
    if abs(float(last.get("value", -999)) - value) >= PUSH_MIN_DELTA:
        return True
    return now - last["at"] >= PUSH_EVERY


# --------------------------------------------------------------------------- Beobachten (Fritz)
def valve_closed(state) -> bool | None:
    """Ist das Ventil gerade zu? None = unbekannt / Gerät aus."""
    if state is None or state.state in ("unavailable", "unknown", "off"):
        return None
    action = state.attributes.get("hvac_action")
    if action in ("idle", "off"):
        return True
    if action in ("heating", "preheating"):
        return False
    cur, target = _num(state.attributes.get("current_temperature")), _num(state.attributes.get("temperature"))
    if cur is None or target is None:
        return None
    return cur >= target + 0.3  # Thermostate ohne hvac_action (z. B. FRITZ!DECT): Fühler über Soll → zu


def sample_due(samples: list[dict[str, Any]], entity_id: str, now: datetime) -> bool:
    for s in reversed(samples):
        if s["entity_id"] == entity_id:
            return now - datetime.fromisoformat(s["at"]) >= SAMPLE_EVERY
    return True


def stats(samples: list[dict[str, Any]], now: datetime, days: int = 7) -> dict[str, Any]:
    """Mittlere Abweichung Fühler − Raum der letzten Tage (für die Anzeige)."""
    since = now - timedelta(days=days)
    diffs = [s["diff"] for s in samples if datetime.fromisoformat(s["at"]) >= since]
    if not diffs:
        return {"n": 0, "mean": None, "min": None, "max": None, "since": None}
    first = min(datetime.fromisoformat(s["at"]) for s in samples)
    return {
        "n": len(diffs),
        "mean": round(sum(diffs) / len(diffs), 2),
        "min": round(min(diffs), 2),
        "max": round(max(diffs), 2),
        "since": first.isoformat(),
    }


def to_csv(samples: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["zeit", "thermostat", "fuehler_c", "soll_c", "raum_c", "abweichung_c"])
    for s in samples:
        w.writerow([s["at"], s["entity_id"], _de(s["trv"]), _de(s["set"]), _de(s["room"]), _de(s["diff"])])
    return out.getvalue()


def _de(v: Any) -> str:
    return "" if v is None else f"{float(v):.2f}".replace(".", ",")
