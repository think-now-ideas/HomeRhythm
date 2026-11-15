"""Voraussetzungen: Was braucht Home Rhythm von Home Assistant, was fehlt, was passt?

Die Kachel „Voraussetzungen“ in der Karte zeigt für Jahreszeit, Urlaub, Workday, Anwesenheit
und Außentemperatur, ob etwas eingestellt und vorhanden ist. Fehlt etwas, kann ein Admin

* einen vorhandenen Helfer übernehmen (Vorschlag oder Suche),
* einen neuen Helfer anlegen (das macht die Karte über die normale HA-Schnittstelle
  ``input_select/create`` – Home Rhythm trägt ihn danach hier ein),
* oder bewusst „ohne“ wählen – dann gibt es keinen Hinweis mehr.

Geändert werden nur die Einstellungen von Home Rhythm (Optionen des Config-Eintrags).
Alle Eingaben werden geprüft: nur vorhandene Entitäten der passenden Domain.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_AWAY_VALUE,
    CONF_COOL_VALUES,
    CONF_HOME_VALUE,
    CONF_OUTDOOR_ENTITIES,
    CONF_PRESENCE_ENTITY,
    CONF_SEASON_ENTITY,
    CONF_SUMMER_VALUE,
    CONF_VACATION_ENTITY,
    CONF_WINTER_VALUES,
    CONF_WORKDAY_ENTITY,
)

if TYPE_CHECKING:
    from .controller import HomeRhythmController

KEYS = ("season", "vacation", "workday", "outdoor")
CONF_OF = {"season": CONF_SEASON_ENTITY, "vacation": CONF_VACATION_ENTITY, "workday": CONF_WORKDAY_ENTITY, "outdoor": CONF_OUTDOOR_ENTITIES}
DOMAINS = {"season": ("input_select", "select"), "vacation": ("input_select", "select"), "workday": ("binary_sensor",), "outdoor": ("sensor", "weather")}
# Was passiert ohne? (für Kachel und Hinweis)
WITHOUT = {
    "season": "Ohne Jahreszeit wird immer geheizt und nie gekühlt.",
    "vacation": "Ohne Urlaub gibt es keine Urlaubstemperatur, kein „Urlaub zu Hause“ und keine Urlaubssimulation.",
    "workday": "Ohne Workday gilt Mo–Fr als Arbeitstag, Feiertage werden nicht erkannt.",
    "outdoor": "Ohne Außentemperatur gibt es keine automatische Jahreszeit und keine Wahl zwischen Klima und Heizkörper.",
}
# Werte für neu angelegte Helfer (die Karte legt sie über HA an)
NEW_HELPERS = {
    "season": {"name": "Jahreszeit", "icon": "mdi:sun-snowflake-variant", "options": ["Winter", "Sommer", "Heißphase"]},
    "vacation": {"name": "Urlaub", "icon": "mdi:bag-suitcase", "options": ["kein Urlaub", "Urlaub zu Hause", "Urlaub unterwegs"]},
}


def _match(options: list[str], *words: str) -> list[str]:
    """Optionen, in denen eines der Wörter als ganzes Wort (bzw. Wortanfang mehrteiliger Wörter) vorkommt."""
    return [o for o in options if any(re.search(rf"(^|[\s\-/]){re.escape(w)}", o.casefold()) for w in words)]


def _usable(st: Any) -> bool:
    return st is not None and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def suggest(hass: HomeAssistant) -> dict[str, str]:
    """Passende vorhandene Entitäten finden – statt fest eingebauter Namen (für Neuinstallationen)."""
    out: dict[str, str] = {}
    for st in hass.states.async_all(("input_select", "select")):
        opts = [str(o) for o in st.attributes.get("options") or []]
        if "season" not in out and _match(opts, "winter") and _match(opts, "sommer", "summer"):
            out["season"] = st.entity_id
        if "vacation" not in out and _match(opts, "urlaub", "vacation", "holiday", "verreist"):
            out["vacation"] = st.entity_id
    reg = er.async_get(hass)
    for e in reg.entities.values():
        if e.platform == "workday" and e.domain == "binary_sensor" and not e.disabled_by:
            out["workday"] = e.entity_id
            break
    if hass.states.get("zone.home"):
        out["presence"] = "zone.home"
    for st in hass.states.async_all("sensor"):
        name = f"{st.entity_id} {st.attributes.get('friendly_name', '')}".casefold()
        if st.attributes.get("device_class") == "temperature" and any(w in name for w in ("aussen", "außen", "outdoor", "outside", "draussen", "draußen")):
            out["outdoor"] = st.entity_id
            break
    else:
        weather = hass.states.async_all("weather")
        if weather:
            out["outdoor"] = weather[0].entity_id
    return out


def _workday_detail(hass: HomeAssistant) -> str:
    for entry in hass.config_entries.async_entries("workday"):
        conf = {**entry.data, **entry.options}
        country, prov = conf.get("country") or "", conf.get("province") or ""
        return " ".join(x for x in (country, prov) if x)
    return ""


def state(ctrl: HomeRhythmController) -> dict[str, Any]:
    """Status aller Voraussetzungen für die Karte."""
    hass, o = ctrl.hass, ctrl.options
    sugg = suggest(hass)
    items: dict[str, Any] = {}
    for key in KEYS:
        val = o.get(CONF_OF[key])
        ents = [e for e in (val if isinstance(val, list) else [val]) if e]
        sts = [hass.states.get(e) for e in ents]
        if key in ctrl.req_none and not ents:
            status = "none"
        elif not ents:
            status = "unset"
        elif any(s is None for s in sts):
            status = "missing"  # eingestellt, gibt es aber nicht (mehr)
        else:
            status = "ok"
        item: dict[str, Any] = {
            "status": status,
            "entities": ents,
            "names": [ctrl._name(e) for e in ents],  # noqa: SLF001
            "states": [s.state if s else None for s in sts],
            "suggestion": sugg.get(key) if status in ("unset", "missing", "none") and sugg.get(key) not in ents else None,
            "without": WITHOUT[key],
        }
        if key in ("season", "vacation") and sts and sts[0] is not None:
            item["options"] = list(sts[0].attributes.get("options") or [])
        if key == "workday":
            item["detail"] = _workday_detail(hass)
        items[key] = item
    pres = o.get(CONF_PRESENCE_ENTITY) or ""
    persons = [p for p in hass.states.async_all("person") if _usable(p)]
    pst = hass.states.get(pres) if pres else None
    items["presence"] = {"status": "info", "entities": [pres] if pres else [], "states": [pst.state if pst else None],
                         "persons": len(persons), "nobody_home": ctrl._nobody_home()}  # noqa: SLF001
    missing = [k for k in ("season", "vacation", "workday") if items[k]["status"] in ("unset", "missing")]
    return {
        "items": items,
        "missing": missing,
        "new_helpers": NEW_HELPERS,
        "season_auto": ctrl.season_auto,
        "season_auto_possible": ctrl.season_auto_possible() and items["outdoor"]["status"] == "ok",
    }


def _values_for(key: str, options: list[str]) -> dict[str, Any]:
    """Werte des neuen Helfers in die Einstellungen übernehmen (Winter/Sommer/Heißphase, zu Hause/unterwegs)."""
    if key == "season":
        out: dict[str, Any] = {}
        if w := _match(options, "winter"):
            out[CONF_WINTER_VALUES] = ", ".join(w)
        if s := _match(options, "sommer", "summer"):
            out[CONF_SUMMER_VALUE] = s[0]
        if h := _match(options, "heiß", "heiss", "hitze", "hot"):
            out[CONF_COOL_VALUES] = ", ".join(h)
        return out
    if key == "vacation":
        out = {}
        if a := _match(options, "unterwegs", "away", "verreist"):
            out[CONF_AWAY_VALUE] = a[0]
        if h := _match(options, "zu hause", "home", "daheim", "zuhause", "urlaub zu hause"):
            out[CONF_HOME_VALUE] = h[0]
        return out
    return {}


async def async_set(ctrl: HomeRhythmController, key: str, entity: str | None, none: bool = False) -> None:
    """Eine Voraussetzung setzen (Entität) oder bewusst „ohne“. Nur aus der Karte durch einen Admin."""
    if key not in KEYS:
        raise ValueError("Unbekannte Voraussetzung")
    hass = ctrl.hass
    changes: dict[str, Any] = {}
    if none:
        changes[CONF_OF[key]] = [] if key == "outdoor" else ""
        ctrl.req_none.add(key)
    else:
        eid = str(entity or "").strip()
        st = hass.states.get(eid)
        if st is None:
            raise ValueError(f"„{eid}“ gibt es nicht")
        if eid.split(".")[0] not in DOMAINS[key]:
            raise ValueError(f"{eid} passt hier nicht (erlaubt: {', '.join(DOMAINS[key])})")
        current = ctrl.options.get(CONF_OF[key])
        changes[CONF_OF[key]] = [eid] if key == "outdoor" else eid
        if current != changes[CONF_OF[key]]:  # nur bei einem anderen Helfer die Werte neu ableiten – sonst bleiben eigene Einstellungen
            changes.update(_values_for(key, [str(x) for x in st.attributes.get("options") or []]))
        ctrl.req_none.discard(key)
    entry = ctrl.entry
    hass.config_entries.async_update_entry(entry, options={**entry.options, **changes})
    await ctrl.async_save()
    # Neu laden, damit alle Beobachter (Hausmodi, Außentemperatur, HA-Automationen) die neuen Entitäten nutzen
    hass.config_entries.async_schedule_reload(entry.entry_id)
