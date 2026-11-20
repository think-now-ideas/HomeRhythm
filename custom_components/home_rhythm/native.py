"""Abläufe optional als echte Home-Assistant-Automation anlegen.

Ist bei einem Ablauf „Auch als Automation in Home Assistant anlegen“ eingeschaltet,
übersetzt HomeRhythm ihn in eine Automation und schreibt sie in ``automations.yaml``
(dieselbe Datei, die der Automations-Editor von HA benutzt). HomeRhythm führt den
Ablauf dann *nicht* selbst aus – sonst würde doppelt geschaltet.

Sicherheit und Datenschutz:
* Es wird nur der Eintrag mit der ID ``home_rhythm_<ablauf>`` angelegt, geändert oder
  entfernt. Alle anderen Automationen bleiben unverändert erhalten.
* Vor jedem Schreiben wird die Datei vollständig eingelesen und geprüft (muss eine
  Liste sein). Ist sie unlesbar, wird nichts geschrieben.
* Vor jedem Schreiben legt HomeRhythm eine Sicherung ``automations.yaml.home_rhythm.bak``
  der vorherigen Fassung an. Nutzt die Datei ``!include`` oder ``!secret``, wird nichts geschrieben.
* Geschrieben wird atomar (temporäre Datei + Umbenennen), danach ``automation.reload``.
* Es werden keine vom Nutzer eingegebenen Templates erzeugt; die wenigen Templates
  (Weihnachtszeit) sind fest im Code. Texte (Name, Nachricht) landen nur als
  YAML-Strings im Feld ``alias`` bzw. ``message``.

Nicht alles lässt sich 1:1 übertragen – ``unsupported()`` liefert die Liste, die die
Karte als Hinweis anzeigt (z. B. „nachprüfen & wiederholen“, Zufall, Überspringen).
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import yaml as yaml_util
from homeassistant.util.file import write_utf8_file_atomic

from . import flows as F

_LOGGER = logging.getLogger(__name__)

ID_PREFIX = "home_rhythm_"

# Weihnachtszeit (1. Advent bis 6. Januar) – fest im Code, keine Nutzereingabe.
CHRISTMAS_TEMPLATE = (
    "{% set d = now().date() %}{% set x = d.replace(month=12, day=25) %}"
    "{% set adv = x - timedelta(days=x.isoweekday() + 21) %}"
    "{{ d >= adv or (d.month == 1 and d.day <= 6) }}"
)


def _md_template(dates: list[str], prev: bool = False) -> str:
    """Template „heute (bzw. gestern bei nach Mitternacht) ist einer dieser Tage“. Daten sind geprüft (MM-TT)."""
    day = "(now() - timedelta(days=1)).date()" if prev else "now().date()"
    vals = ", ".join(f"'{d}'" for d in dates if len(d) == 5 and d[2] == "-" and d.replace("-", "").isdigit())
    return f"{{% set d = {day} %}}{{{{ '%02d-%02d' % (d.month, d.day) in [{vals}] }}}}"


def _between_template(start: str, end: str) -> str:
    """Datum zwischen zwei Tagen (jedes Jahr, auch über den Jahreswechsel). Werte sind geprüft (MM-TT)."""
    a, b = int(start.replace("-", "")), int(end.replace("-", ""))
    test = f"{a} <= k <= {b}" if a <= b else f"k >= {a} or k <= {b}"
    return f"{{% set k = now().month * 100 + now().day %}}{{{{ {test} }}}}"


def _offset(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    m = abs(minutes)
    return f"{sign}{m // 60:02d}:{m % 60:02d}:00"


def _cond(c: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any] | None:
    """Eine Home-Rhythm-Bedingung → HA-Bedingung. None = nicht übertragbar."""
    if "items" in c:
        items = [x for x in (_cond(i, opts) for i in c["items"]) if x is not None]
        return {"condition": "or" if c["op"] == "or" else "and", "conditions": items}
    key, op = c["key"], c["op"]

    def neg(cond: dict[str, Any]) -> dict[str, Any]:
        return cond if op == "is" else {"condition": "not", "conditions": [cond]}

    if key in ("season", "vacation"):
        ent = opts.get("season_entity" if key == "season" else "vacation_entity")
        return neg({"condition": "state", "entity_id": ent, "state": list(c["value"])}) if ent else None
    if key == "event":
        ent = opts.get("event_entity")
        if not ent:
            return None
        mapping = {"keins": "keins", "Party": "party", "Gäste": "gaeste"}
        return neg({"condition": "state", "entity_id": ent, "state": [mapping.get(v, v) for v in c["value"]]})
    if key == "occasion":
        return neg({"condition": "template", "value_template": CHRISTMAS_TEMPLATE})
    if key == "date":
        return neg({"condition": "template", "value_template": _between_template(c["from"], c["to"])})
    if key == "presence":
        ent = opts.get("presence_entity") or "zone.home"
        away = {"condition": "numeric_state", "entity_id": ent, "below": 1} if ent.startswith("zone.") else {"condition": "state", "entity_id": ent, "state": ["not_home", "off", "away"]}
        is_away = c["value"] == "away"
        return away if (is_away == (op == "is")) else {"condition": "not", "conditions": [away]}
    if key == "workday":
        ent = opts.get("workday_entity")
        if not ent:
            return None
        want = "on" if c["value"] == "yes" else "off"
        return neg({"condition": "state", "entity_id": ent, "state": want})
    if key == "sun":
        return neg({"condition": "state", "entity_id": "sun.sun", "state": "above_horizon" if c["value"] == "up" else "below_horizon"})
    if key == "entity":
        if op in ("above", "below"):
            return {"condition": "numeric_state", "entity_id": c["entity"], op: c["value"]}
        return neg({"condition": "state", "entity_id": c["entity"], "state": str(c["value"])})
    return None  # "flow" (Abhängigkeit von anderem Zeitplan) gibt es in HA nicht


def _days_cond(p: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any] | None:
    base = _days_cond_base(p, opts)
    if not p.get("except"):
        return base
    exc = {"condition": "not", "conditions": [{"condition": "template", "value_template": _md_template(p["except"], bool(p.get("prev")))}]}
    return exc if base is None else {"condition": "and", "conditions": [base, exc]}


def _days_cond_base(p: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any] | None:
    d = p["days"]
    names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    if d == "daily":
        return None
    if d == "dates":
        return {"condition": "template", "value_template": _md_template(p["dates"], bool(p.get("prev")))}
    if d in ("wd", "we", "custom"):
        days = {"wd": range(5), "we": (5, 6), "custom": p.get("weekdays", [])}[d]
        return {"condition": "time", "weekday": [names[i] for i in days]}
    if d == "type":
        return _type_cond(p.get("types", []), opts)
    ent = opts.get("workday_entity")
    work = {"condition": "state", "entity_id": ent, "state": "on"} if ent else {"condition": "time", "weekday": list(names[:5])}
    home = opts.get("vacation_entity"), opts.get("home_value")
    if home[0] and home[1]:
        not_home_vac = {"condition": "not", "conditions": [{"condition": "state", "entity_id": home[0], "state": home[1]}]}
        work = {"condition": "and", "conditions": [work, not_home_vac]}
    return work if d == "work" else {"condition": "not", "conditions": [work]}


def _type_cond(types: list[str], opts: dict[str, Any]) -> dict[str, Any]:
    """Tagesarten als HA-Bedingung. Feiertag = Workday „aus“ an einem Werktag (wie HomeRhythm für heute)."""
    names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    wd = {"condition": "time", "weekday": list(names[:5])}
    ent = opts.get("workday_entity")
    hol = {"condition": "and", "conditions": [wd, {"condition": "state", "entity_id": ent, "state": "off"}]} if ent else None
    vac_ent, vac_home = opts.get("vacation_entity"), opts.get("home_value")
    vac = {"condition": "state", "entity_id": vac_ent, "state": vac_home} if vac_ent and vac_home else None

    def no(c: dict[str, Any] | None) -> list[dict[str, Any]]:
        return [{"condition": "not", "conditions": [c]}] if c else []

    parts: dict[str, dict[str, Any] | None] = {
        "hol": hol,
        "vacwd": {"condition": "and", "conditions": [wd, vac, *no(hol)]} if vac else None,
        "vacwe_sa": {"condition": "and", "conditions": [{"condition": "time", "weekday": ["sat"]}, vac]} if vac else None,
        "vacwe_so": {"condition": "and", "conditions": [{"condition": "time", "weekday": ["sun"]}, vac]} if vac else None,
        "mf": {"condition": "and", "conditions": [wd, *no(hol), *no(vac)]},
        "sa": {"condition": "and", "conditions": [{"condition": "time", "weekday": ["sat"]}, *no(vac)]},
        "so": {"condition": "and", "conditions": [{"condition": "time", "weekday": ["sun"]}, *no(vac)]},
    }
    found = [parts[t] for t in types if parts.get(t)]
    if not found:
        return {"condition": "template", "value_template": "{{ false }}"}
    return found[0] if len(found) == 1 else {"condition": "or", "conditions": found}


def _service(kind_or_do: str, entity: str, position: int | None = None, brightness: int | None = None) -> dict[str, Any]:
    if kind_or_do in ("open", "close"):
        return {"action": f"cover.{kind_or_do}_cover", "target": {"entity_id": entity}}
    if kind_or_do == "position":
        return {"action": "cover.set_cover_position", "target": {"entity_id": entity}, "data": {"position": position}}
    if kind_or_do == "toggle":
        return {"action": "cover.toggle" if entity.startswith("cover.") else "homeassistant.toggle", "target": {"entity_id": entity}}
    if kind_or_do == "on" and brightness and entity.startswith("light."):
        return {"action": "light.turn_on", "target": {"entity_id": entity}, "data": {"brightness_pct": brightness}}
    return {"action": f"homeassistant.turn_{'on' if kind_or_do == 'on' else 'off'}", "target": {"entity_id": entity}}


def _state_cond(action: str, entity: str) -> dict[str, Any]:
    """„nur falls nötig“: Bedingung „Gerät steht noch nicht so“."""
    want = {"open": "open", "close": "closed", "on": "on", "off": "off"}.get(action)
    if want is None:
        return {"condition": "template", "value_template": "{{ true }}"}
    return {"condition": "not", "conditions": [{"condition": "state", "entity_id": entity, "state": want}]}


def plan_automation(fid: str, plan: dict[str, Any], devices: list[str], opts: dict[str, Any]) -> dict[str, Any]:
    triggers, branches = [], []
    for i, p in enumerate(plan["points"]):
        conds = [x for x in (_days_cond(p, opts), _cond(p["conds"], opts)) if x]
        acts = []
        for e in devices:
            pos = plan.get("overrides", {}).get(e, {}).get("position", p.get("position"))
            call = _service(p["action"], e, pos, p.get("brightness"))
            acts.append({"if": [_state_cond(p["action"], e)], "then": [call]} if p.get("only_needed") else call)
        acts = [{"continue_on_error": True, **a} for a in acts]
        if p["ref"] == "time":
            triggers.append({"trigger": "time", "at": f"{p['time']}:00", "id": f"p{i}"})
            branches.append({"conditions": [{"condition": "trigger", "id": f"p{i}"}, *conds], "sequence": acts})
            continue
        event = p["ref"]
        sun_off = _offset(p.get("offset", 0))
        triggers.append({"trigger": "sun", "event": event, "offset": sun_off, "id": f"p{i}"})
        guard = []
        if p.get("latest"):
            guard.append({"condition": "time", "before": f"{p['latest']}:00"})
        if p.get("earliest"):
            guard.append({"condition": "time", "after": f"{p['earliest']}:00"})
        branches.append({"conditions": [{"condition": "trigger", "id": f"p{i}"}, *guard, *conds], "sequence": acts})
        if p.get("latest"):  # Sonnenereignis noch nicht erreicht → um „spätestens“ schalten
            triggers.append({"trigger": "time", "at": f"{p['latest']}:00", "id": f"p{i}l"})
            branches.append({"conditions": [{"condition": "trigger", "id": f"p{i}l"},
                                            {"condition": "sun", "before": event, "before_offset": sun_off}, *conds], "sequence": acts})
        if p.get("earliest"):  # Sonnenereignis war schon vor „frühestens“ → um „frühestens“ schalten
            triggers.append({"trigger": "time", "at": f"{p['earliest']}:00", "id": f"p{i}e"})
            branches.append({"conditions": [{"condition": "trigger", "id": f"p{i}e"},
                                            {"condition": "sun", "after": event, "after_offset": sun_off}, *conds], "sequence": acts})
    top = _cond(plan["conds"], opts)
    return {"triggers": triggers, "conditions": [top] if top and top.get("conditions", True) else [], "actions": [{"choose": branches}], "mode": "queued"}


def react_automation(fid: str, flow: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any]:
    triggers = []
    for t in flow["triggers"]:
        if t["kind"] == "state":
            tr: dict[str, Any] = {"trigger": "state", "entity_id": t["entity"], "not_from": ["unavailable", "unknown"]}
            if t.get("to") is not None:
                tr["to"] = t["to"]
            else:
                tr["not_to"] = ["unavailable", "unknown"]
            triggers.append(tr)
        else:
            triggers.append({"trigger": "numeric_state", "entity_id": t["entity"], t["kind"]: t["value"]})
    actions: list[dict[str, Any]] = []
    for s in flow["steps"]:
        do = s["do"]
        if do in ("on", "off", "open", "close", "position", "toggle"):
            actions += [{"continue_on_error": True, **_service(do, e, s.get("position"), s.get("brightness"))} for e in s["entities"]]
        elif do == "wait":
            actions.append({"delay": {"seconds": s["seconds"]}})
        elif do == "wait_until":
            u = s["until"]
            if u["op"] in ("above", "below"):
                trig = {"trigger": "numeric_state", "entity_id": u["entity"], u["op"]: u["value"]}
            elif u["op"] == "is":
                trig = {"trigger": "state", "entity_id": u["entity"], "to": str(u["value"])}
            else:
                trig = {"trigger": "state", "entity_id": u["entity"], "from": str(u["value"])}
            cond = _cond(u, opts)
            actions.append({"if": [cond], "else": [{"wait_for_trigger": [trig], "timeout": {"seconds": s.get("timeout", 14400)}, "continue_on_timeout": True}]})
            if s.get("after"):
                actions.append({"delay": {"seconds": s["after"]}})
        elif do == "blink":
            # wie in HomeRhythm selbst: alle aus – Pause – alle an – Pause
            ms = s.get("pause", 5) * 100
            seq = [_service("off", e) for e in s["entities"]] + [{"delay": {"milliseconds": ms}}]
            seq += [_service("on", e) for e in s["entities"]] + [{"delay": {"milliseconds": ms}}]
            actions.append({"repeat": {"count": s.get("times", 2), "sequence": seq}})
        elif do == "notify":
            if s["target"] == "persistent":
                actions.append({"action": "persistent_notification.create", "data": {"title": "Home Rhythm", "message": s["message"]}})
            else:
                actions.append({"action": s["target"], "data": {"message": s["message"]}})
    top = _cond(flow["conds"], opts)
    return {"triggers": triggers, "conditions": [top] if top and top.get("conditions", True) else [],
            "actions": actions, "mode": "restart" if flow.get("mode") == "restart" else "single"}


def lost_conditions(flow: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    """Bedingungen, die sich in HA nicht abbilden lassen (fehlender Helfer, „Zeitplan ist …“)."""
    lost: list[str] = []

    def walk(c: dict[str, Any]) -> None:
        if "items" in c:
            for x in c["items"]:
                walk(x)
        elif _cond(c, opts) is None:
            lost.append(F.cond_text(c))

    walk(flow["conds"])
    for p in flow.get("points", []):
        walk(p["conds"])
        if p["days"] in ("work", "free") and not opts.get("workday_entity"):
            lost.append("Arbeitstag ohne Workday-Sensor")
        if p["days"] == "type":
            if "hol" in p.get("types", []) and not opts.get("workday_entity"):
                lost.append("Feiertag ohne Workday-Sensor")
            if any(t.startswith("vac") for t in p.get("types", [])) and not (opts.get("vacation_entity") and opts.get("home_value")):
                lost.append("Urlaub zu Hause ohne Urlaubs-Helfer")
            if p.get("prev"):
                lost.append("Schaltzeit nach Mitternacht (Tagesart des Vortags) – gilt in HA für den Tag selbst")
    return list(dict.fromkeys(lost))


def unsupported(flow: dict[str, Any]) -> list[str]:
    """Was bei „in HA anlegen“ verloren geht – für den Hinweis in der Karte."""
    out = []
    if flow["type"] == "plan":
        if any(p.get("verify") for p in flow["points"]):
            out.append("nachprüfen & wiederholen")
        if flow.get("random"):
            out.append("zufällige Verschiebung")
        if flow.get("selectors"):
            out.append("Bereich/Etage/Label werden beim Speichern aufgelöst (neue Geräte erst nach erneutem Speichern)")
        out.append("„Nächsten Schaltpunkt überspringen“")

    return out


def build(fid: str, flow: dict[str, Any], devices: list[str], opts: dict[str, Any]) -> dict[str, Any]:
    body = plan_automation(fid, flow, devices, opts) if flow["type"] == "plan" else react_automation(fid, flow, opts)
    return {
        "id": ID_PREFIX + fid,
        "alias": f"Home Rhythm: {flow['name']}",  # bleibt so: sonst würden bestehende Automationen umbenannt
        "description": "Verwaltet von Home Rhythm – bitte in der Home-Rhythm-Karte bearbeiten, Änderungen hier werden beim nächsten Speichern überschrieben.",
        **body,
    }


def _read(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    if "!include" in raw or "!secret" in raw:
        # Beim Zurückschreiben würden eingebundene Dateien bzw. Geheimnisse aufgelöst – lieber gar nicht schreiben.
        raise ValueError("automations.yaml nutzt !include oder !secret – HomeRhythm schreibt dort nichts hinein")
    data = yaml_util.load_yaml(path)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("automations.yaml hat ein unerwartetes Format – HomeRhythm schreibt nichts hinein")
    return data


def _write(path: str, wanted: dict[str, dict[str, Any]]) -> bool:
    """Home-Rhythm-Einträge in automations.yaml ersetzen. True, wenn sich etwas geändert hat."""
    current = _read(path)
    kept = [a for a in current if not str(a.get("id", "")).startswith(ID_PREFIX)]
    ours_old = {a["id"]: a for a in current if str(a.get("id", "")).startswith(ID_PREFIX)}
    if ours_old == wanted:
        return False
    if os.path.exists(path):  # vor jeder Änderung die letzte Fassung sichern
        shutil.copy2(path, path + ".home_rhythm.bak")
    write_utf8_file_atomic(path, yaml_util.dump(kept + list(wanted.values())))
    return True


async def async_sync(hass: HomeAssistant, wanted: dict[str, dict[str, Any]]) -> None:
    """Gewünschte HR-Automationen (id → Automation) in automations.yaml bringen und neu laden."""
    path = hass.config.path("automations.yaml")
    changed = await hass.async_add_executor_job(_write, path, wanted)
    if changed and hass.services.has_service("automation", "reload"):
        await hass.services.async_call("automation", "reload", blocking=True)
        _LOGGER.info("HomeRhythm: %d Automation(en) in automations.yaml aktualisiert", len(wanted))
