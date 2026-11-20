"""Abläufe: Zeitpläne und Reaktionen – reine Logik ohne Home Assistant.

Ein **Zeitplan** ("plan") schaltet eine frei zusammengestellte Gruppe von Geräten
(Rollläden oder Licht/Steckdosen) zu festen **Schaltpunkten**: Uhrzeit oder
Sonnenauf-/-untergang ± Minuten, für bestimmte Tage, optional mit Bedingungen.
Ein Schaltpunkt ist ein *Befehl* zu diesem Zeitpunkt – was zwischendurch von Hand
geändert wird, bleibt bis zum nächsten Schaltpunkt.

Eine **Reaktion** ("react") wartet auf einen Auslöser (z. B. Bewegung, Knopf,
Leistung über X W) und führt dann Schritte der Reihe nach aus (an, warten, aus …).

Bedingungen sind verschachtelbare Gruppen::

    {"op": "or", "items": [
        {"key": "vacation", "op": "is", "value": "Urlaub unterwegs"},
        {"op": "and", "items": [{"key": "presence", "op": "is", "value": "away"},
                                {"key": "season", "op": "is", "value": "Winter"}]}]}

Sicherheit: Alles, was aus der Oberfläche kommt, läuft durch ``normalize_*``.
Dort werden Typen, Längen, Wertebereiche, Entity-IDs und erlaubte Domains geprüft.
Es gibt bewusst keine Templates oder frei wählbaren Dienste – so kann über einen
Ablauf nichts anderes ausgeführt werden als das Schalten der gewählten Geräte.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import hashlib
import math
import re
from typing import Any

# ---------------------------------------------------------------- Grenzen (gegen versehentlich riesige Daten)
MAX_FLOWS = 100
MAX_NAME = 60
MAX_DEVICES = 100
MAX_POINTS = 30
MAX_STEPS = 20
MAX_TRIGGERS = 10
MAX_CONDS = 12
MAX_DEPTH = 3  # Wurzel + zwei Ebenen Gruppen
MAX_WAIT = 24 * 3600

ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
NOTIFY_RE = re.compile(r"^notify\.[a-z0-9_]+$")
HM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
MD_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})\.?$")  # „24.12.“ oder „12-24“ (siehe parse_md)
MONTH_DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # 29.2. erlaubt – gilt dann nur in Schaltjahren
MAX_SPECIAL = 30  # bestimmte Tage je Zeitplan
# Taster je Zeitplan (Signaturen wie bei den Bedienteilen der Räume, siehe controls.py)
BUTTON_SIG_RE = re.compile(r"^(event|action|up|down|mode|plain):[a-z_]+\.[a-z0-9_]+(:.{1,64})?$")
BUTTON_DEV_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
BUTTON_ACTIONS = {"toggle": "umschalten", "on": "an", "off": "aus"}
BUTTON_SCOPES = {"always": "immer", "active": "nur wenn der Zeitplan gilt"}
MAX_AUTO_OFF = 12 * 60  # Minuten

# ---------------------------------------------------------------- Arten
KIND_COVER = "cover"
KIND_SWITCH = "switch"  # Licht, Steckdosen, Schalter
KINDS = {KIND_COVER: "Rollläden", KIND_SWITCH: "Licht & Steckdosen"}
KIND_DOMAINS = {KIND_COVER: ("cover",), KIND_SWITCH: ("light", "switch", "input_boolean", "fan")}
ACTIONS = {KIND_COVER: ("open", "close", "position"), KIND_SWITCH: ("on", "off")}
ACTION_NAMES = {"open": "öffnen", "close": "schließen", "position": "Position", "on": "einschalten", "off": "ausschalten"}
# Zustand, den ein Schaltpunkt herstellt (für Balken und „nur falls nötig“)
ACTION_STATE = {"open": "open", "close": "closed", "position": "pos", "on": "on", "off": "off"}
STATE_NAMES = {"open": "offen", "closed": "zu", "pos": "Position", "on": "an", "off": "aus"}

DAYS = {"daily": "täglich", "work": "Arbeitstag", "free": "freier Tag", "wd": "Mo–Fr", "we": "Sa + So", "custom": "eigene Tage", "type": "Tagesarten", "dates": "bestimmte Tage"}
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
REFS = {"time": "Uhrzeit", "sunrise": "Sonnenaufgang", "sunset": "Sonnenuntergang"}

# Tagesarten (wie bei der Heizung). Jeder Tag hat genau eine „rohe“ Tagesart:
# Feiertag vor Urlaub zu Hause vor Wochentag.
DAY_TYPES = {
    "mf": "Mo–Fr",
    "sa": "Samstag",
    "so": "Sonntag",
    "hol": "Feiertag",
    "vacwd": "Urlaub zu Hause Mo–Fr",
    "vacwe_sa": "Urlaub zu Hause Sa",
    "vacwe_so": "Urlaub zu Hause So",
}
# Zeilen im einfachen Modus und welche „wie …“-Auswahl sie anbieten
SIMPLE_ROWS = ("mf", "sa", "so", "hol", "vacwd", "vacwe")
SIMPLE_ROW_NAMES = {"mf": "Mo–Fr", "sa": "Samstag", "so": "Sonntag", "hol": "Feiertag", "vacwd": "Urlaub zu Hause an Werktagen", "vacwe": "Urlaub zu Hause am Wochenende"}
SIMPLE_LIKE = {
    "mf": ("own",),
    "sa": ("mf", "own"),
    "so": ("mf", "sa", "own"),
    "hol": ("mf", "sa", "so", "own"),
    "vacwd": ("own", "sa", "so"),
    "vacwe": ("keep", "own", "sa", "so", "vacwd"),
}
SIMPLE_LIKE_NAMES = {"own": "eigene Zeiten", "mf": "wie Mo–Fr", "sa": "wie Samstag", "so": "wie Sonntag", "vacwd": "wie Urlaub-Werktage", "keep": "unverändert (Sa wie Sa, So wie So)"}
SIMPLE_DEFAULT_LIKE = {"mf": "own", "sa": "own", "so": "own", "hol": "so", "vacwd": "so", "vacwe": "keep"}
REFS_SIMPLE = ("time", "sunrise", "sunset", "none")

# Bedingungen: Schlüssel → Anzeigename. Werte von season/vacation sind die Optionen der Helfer des Nutzers.
COND_KEYS = {
    "season": "Jahreszeit",
    "vacation": "Urlaub",
    "event": "Ereignis",
    "occasion": "Anlass",
    "presence": "Anwesenheit",
    "workday": "Arbeitstag",
    "sun": "Sonne",
    "entity": "Gerät / Entität",
    "flow": "Zeitplan",
    "date": "Datum",
}
COND_FIXED_VALUES = {
    "occasion": {"christmas": "Weihnachten"},
    "presence": {"home": "jemand da", "away": "niemand da"},
    "workday": {"yes": "ja", "no": "nein"},
    "sun": {"up": "hell (über dem Horizont)", "down": "dunkel"},
}
COND_OPS = {"is": "ist", "not": "ist nicht", "above": "über", "below": "unter"}
DATE_OPS = {"is": "zwischen", "not": "nicht zwischen"}  # Anzeige für die Bedingung „Datum“

# Gerätearten auf Deutsch – für die Suche („Bewegung“ findet auch „… Occupancy“)
DEVICE_CLASS_NAMES = {
    "motion": "Bewegung", "occupancy": "Bewegung Anwesenheit", "presence": "Anwesenheit Bewegung",
    "door": "Tür Kontakt", "window": "Fenster Kontakt", "opening": "Öffnung Tür Fenster Kontakt", "garage_door": "Garagentor",
    "power": "Leistung Strom Watt", "energy": "Energie Verbrauch", "current": "Strom", "illuminance": "Helligkeit Licht Lux",
    "temperature": "Temperatur", "humidity": "Luftfeuchte", "moisture": "Wasser Feuchte Leck", "smoke": "Rauch",
    "vibration": "Vibration Erschütterung", "sound": "Geräusch", "wind_speed": "Wind", "plug": "Steckdose", "outlet": "Steckdose",
    "shutter": "Rollladen", "blind": "Jalousie", "awning": "Markise", "garage": "Garage", "gate": "Tor", "lock": "Schloss",
}

# Reaktionen
TRIGGER_KINDS = {"state": "wird / ändert sich", "above": "steigt über", "below": "fällt unter"}
TRIGGER_DOMAINS = ("binary_sensor", "sensor", "input_button", "button", "event", "input_boolean", "switch", "light", "cover", "input_select", "lock", "person", "device_tracker")
STEP_KINDS = {
    "on": "einschalten",
    "off": "ausschalten",
    "open": "öffnen",
    "close": "schließen",
    "position": "auf Position",
    "toggle": "umschalten",
    "wait": "warten",
    "wait_until": "warten, bis …",
    "blink": "Warnblinken",
    "notify": "Nachricht",
}
STEP_DOMAINS = ("light", "switch", "input_boolean", "fan", "cover")
MODES_REACT = {"restart": "Zeit beginnt neu (neu starten)", "ignore": "ignorieren, solange es läuft"}


# ---------------------------------------------------------------- Kontext für die Auswertung
@dataclass
class Ctx:
    """Alles, was Bedingungen und Tage zur Auswertung brauchen (vom Controller befüllt)."""

    season: str = ""
    vacation: str = ""
    event: str = "keins"
    christmas: bool = False
    nobody_home: bool = False
    workday: bool = True
    daytype: str = ""  # rohe Tagesart dieses Tages (DAY_TYPES), leer = nur nach Wochentag
    prev_daytype: str = ""  # rohe Tagesart des Vortags (für Schaltzeiten nach Mitternacht)
    sun_up: bool = True
    day: date | None = None  # Kalendertag, für den ausgewertet wird (Bedingung „Datum“, bestimmte Tage)
    state: Callable[[str], str | None] = lambda _e: None  # Entität → Zustand
    flow_state: Callable[[str], str | None] = lambda _f: None  # Zeitplan-ID → geplanter Zustand
    known: set[str] = field(default_factory=set)  # vorhandene Zeitpläne (für flow-Bedingung)


@dataclass
class Sun:
    sunrise: int  # Minute des Tages (lokal)
    sunset: int


# ---------------------------------------------------------------- Hilfen
def hm(minute: int) -> str:
    minute %= 1440
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_hm(value: Any, field_name: str = "Uhrzeit") -> int:
    m = HM_RE.match(str(value or "").strip())
    if not m:
        raise ValueError(f"{field_name}: „{value}“ ist keine Uhrzeit (HH:MM)")
    return int(m.group(1)) * 60 + int(m.group(2))


def _str(value: Any, maxlen: int = MAX_NAME) -> str:
    return str(value if value is not None else "").strip()[:maxlen]


def _int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _float(value: Any, what: str) -> float:
    try:
        f = float(str(value).replace(",", "."))
    except ValueError as err:
        raise ValueError(f"{what} muss eine Zahl sein") from err
    if not math.isfinite(f):
        raise ValueError(f"{what} muss eine endliche Zahl sein")
    return f


def _entity(value: Any, domains: tuple[str, ...] | None = None) -> str:
    eid = str(value or "").strip()
    if not ENTITY_RE.match(eid):
        raise ValueError(f"„{eid}“ ist keine gültige Entität")
    if domains and eid.split(".")[0] not in domains:
        raise ValueError(f"{eid} passt hier nicht (erlaubt: {', '.join(domains)})")
    return eid


def new_id(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("_")[:30] or "ablauf"
    fid, i = base, 2
    while fid in taken:
        fid, i = f"{base}_{i}", i + 1
    return fid


def parse_md(value: Any, field_name: str = "Datum") -> str:
    """Tag und Monat ohne Jahr → „MM-TT“. Akzeptiert „24.12.“, „24.12“ und „12-24“ (gespeicherte Form)."""
    text = str(value or "").strip()
    m = MD_RE.match(text)
    if not m:
        raise ValueError(f"{field_name}: „{text}“ ist kein Datum (TT.MM.)")
    a, b = int(m.group(1)), int(m.group(2))
    day, month = (b, a) if "-" in text else (a, b)
    if not 1 <= month <= 12 or not 1 <= day <= MONTH_DAYS[month - 1]:
        raise ValueError(f"{field_name}: den {day}.{month}. gibt es nicht")
    return f"{month:02d}-{day:02d}"


def md_of(day: date) -> str:
    return f"{day.month:02d}-{day.day:02d}"


def md_text(md: str) -> str:
    """„12-24“ → „24.12.“"""
    month, day = md.split("-")
    return f"{int(day)}.{int(month)}."


def md_between(md: str, start: str, end: str) -> bool:
    """Liegt „MM-TT“ im Zeitraum start … end (jedes Jahr, beide Tage ganz)? Darf über den Jahreswechsel gehen."""
    return start <= md <= end if start <= end else (md >= start or md <= end)


# ---------------------------------------------------------------- Bedingungen
def normalize_cond(c: Any, depth: int = 0) -> dict[str, Any]:
    """Eine Bedingung oder Gruppe prüfen und vereinheitlichen."""
    if not isinstance(c, dict):
        raise ValueError("Bedingung hat ein falsches Format")
    if "items" in c:
        if depth >= MAX_DEPTH:
            raise ValueError("Bedingungen höchstens zwei Ebenen tief verschachteln")
        items = c.get("items") or []
        if not isinstance(items, list) or len(items) > MAX_CONDS:
            raise ValueError(f"Höchstens {MAX_CONDS} Bedingungen pro Gruppe")
        return {"op": "or" if c.get("op") == "or" else "and", "items": [normalize_cond(x, depth + 1) for x in items]}
    key = c.get("key")
    if key not in COND_KEYS:
        raise ValueError(f"Unbekannte Bedingung „{key}“")
    op = c.get("op", "is")
    if op not in COND_OPS or (op in ("above", "below") and key != "entity"):
        raise ValueError("Unbekannter Vergleich")
    out: dict[str, Any] = {"key": key, "op": op}
    if key == "entity":
        out["entity"] = _entity(c.get("entity"))
        if op in ("above", "below"):
            out["value"] = _float(c.get("value"), "Vergleichswert")
        else:
            out["value"] = _str(c.get("value"), 60)
    elif key == "date":
        if op not in ("is", "not"):
            raise ValueError("Datum: nur „zwischen“ oder „nicht zwischen“")
        out["from"] = parse_md(c.get("from"), "Datum von")
        out["to"] = parse_md(c.get("to"), "Datum bis")
    elif key == "flow":
        fid = str(c.get("flow") or "")
        if not ID_RE.match(fid):
            raise ValueError("Bedingung: Zeitplan fehlt")
        out["flow"] = fid
        out["value"] = _str(c.get("value"), 20)
    elif key in COND_FIXED_VALUES:
        if c.get("value") not in COND_FIXED_VALUES[key]:
            raise ValueError(f"Ungültiger Wert für {COND_KEYS[key]}")
        out["value"] = c["value"]
    else:  # season, vacation, event: freie Optionen der Helfer (ein Wert oder Liste)
        val = c.get("value")
        vals = val if isinstance(val, list) else [val]
        out["value"] = [_str(v, 60) for v in vals if _str(v, 60)][:10]
        if not out["value"]:
            raise ValueError(f"Wert für {COND_KEYS[key]} fehlt")
    return out


def normalize_group(g: Any) -> dict[str, Any]:
    if g is None or g == []:
        return {"op": "and", "items": []}
    if isinstance(g, list):
        g = {"op": "and", "items": g}
    res = normalize_cond(g)
    if "items" not in res:
        res = {"op": "and", "items": [res]}
    return res


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def cond_true(c: dict[str, Any], ctx: Ctx) -> bool:
    """Bedingung oder Gruppe auswerten. Unbekannte/nicht verfügbare Werte → nicht erfüllt."""
    if "items" in c:
        if not c["items"]:
            return True
        results = (cond_true(x, ctx) for x in c["items"])
        return any(results) if c["op"] == "or" else all(results)
    key, op = c["key"], c["op"]
    if key == "entity":
        st = ctx.state(c["entity"])
        if st is None or st in ("unavailable", "unknown"):
            return False
        if op in ("above", "below"):
            n = _num(st)
            return n is not None and (n > c["value"] if op == "above" else n < c["value"])
        hit = st == c["value"]
    elif key == "flow":
        st = ctx.flow_state(c["flow"])
        if st is None:
            return False
        hit = st == c["value"]
    elif key == "date":
        if ctx.day is None:
            return False
        hit = md_between(md_of(ctx.day), c["from"], c["to"])
    else:
        cur = {
            "season": ctx.season,
            "vacation": ctx.vacation,
            "event": ctx.event,
            "occasion": "christmas" if ctx.christmas else "",
            "presence": "away" if ctx.nobody_home else "home",
            "workday": "yes" if ctx.workday else "no",
            "sun": "up" if ctx.sun_up else "down",
        }[key]
        vals = c["value"] if isinstance(c["value"], list) else [c["value"]]
        hit = cur in vals
    return hit if op == "is" else not hit


VALUE_WORDS = {"on": "an", "off": "aus", "open": "offen", "closed": "zu", "home": "zu Hause", "not_home": "weg"}


def _val(v: Any) -> str:
    """Werte lesbar: on → an, 2.0 → 2."""
    if isinstance(v, float):
        return f"{v:g}"
    return VALUE_WORDS.get(str(v), str(v))


def cond_text(c: dict[str, Any], names: dict[str, str] | None = None) -> str:
    """Lesbarer Satz, z. B. „Urlaub ist Urlaub unterwegs oder (Anwesenheit ist niemand da und Jahreszeit ist Winter)“."""
    names = names or {}
    if "items" in c:
        inner = (" oder " if c["op"] == "or" else " und ").join(cond_text(x, names) for x in c["items"])
        return inner
    key, op = c["key"], COND_OPS[c["op"]]
    if key == "entity":
        return f"{names.get(c['entity'], c['entity'])} {op} {_val(c['value'])}"
    if key == "flow":
        return f"{names.get('flow:' + c['flow'], c['flow'])} {op} {STATE_NAMES.get(c['value'], c['value'])}"
    if key == "date":
        return f"Datum {DATE_OPS[c['op']]} {md_text(c['from'])} und {md_text(c['to'])}"
    if key in COND_FIXED_VALUES:
        val = COND_FIXED_VALUES[key][c["value"]]
    else:
        val = " / ".join(c["value"])
    return f"{COND_KEYS[key]} {op} {val}"


def group_text(g: dict[str, Any], names: dict[str, str] | None = None) -> str:
    parts = []
    for x in g.get("items", []):
        t = cond_text(x, names)
        parts.append(f"({t})" if "items" in x and len(x["items"]) > 1 else t)
    return (" oder " if g.get("op") == "or" else " und ").join(parts)


# ---------------------------------------------------------------- Zeitpläne
def normalize_point(p: Any, kind: str) -> dict[str, Any]:
    if not isinstance(p, dict):
        raise ValueError("Schaltpunkt hat ein falsches Format")
    days = p.get("days", "daily")
    if days not in DAYS:
        raise ValueError("Unbekannte Tage")
    ref = p.get("ref", "time")
    if ref not in REFS:
        raise ValueError("Unbekannter Zeitpunkt")
    action = p.get("action")
    if action not in ACTIONS[kind]:
        raise ValueError(f"Aktion „{action}“ passt nicht zu {KINDS[kind]}")
    out: dict[str, Any] = {"days": days, "ref": ref, "action": action}
    if days == "custom":
        wd = sorted({int(x) for x in p.get("weekdays") or [] if str(x).isdigit() and 0 <= int(x) <= 6})
        if not wd:
            raise ValueError("Eigene Tage: mindestens einen Wochentag wählen")
        out["weekdays"] = wd
    if days == "type":
        types = [t for t in DAY_TYPES if t in (p.get("types") or [])]
        if not types:
            raise ValueError("Tagesarten: mindestens eine wählen")
        out["types"] = types
    if days == "dates":
        dates = _md_list(p.get("dates"), "Bestimmte Tage")
        if not dates:
            raise ValueError("Bestimmte Tage: mindestens ein Datum eintragen (TT.MM.)")
        out["dates"] = dates
    if days in ("type", "dates") or p.get("prev"):
        # Schaltzeit nach Mitternacht: zählt zum Vortag (Tagesart, bestimmter Tag, „Zeitplan gilt“)
        out["prev"] = bool(p.get("prev"))
    exc = _md_list(p.get("except"), "Ausgenommen")
    if exc:
        out["except"] = exc  # an diesen Tagen nicht (dort gelten eigene Zeiten eines bestimmten Tages)
    if ref == "time":
        out["time"] = hm(parse_hm(p.get("time")))
    else:
        out["offset"] = _int(p.get("offset"), -300, 300, 0)
        for lim in ("earliest", "latest"):
            if p.get(lim):
                out[lim] = hm(parse_hm(p[lim], "frühestens" if lim == "earliest" else "spätestens"))
        if out.get("earliest") and out.get("latest") and parse_hm(out["earliest"]) > parse_hm(out["latest"]):
            raise ValueError("„frühestens“ liegt nach „spätestens“")
    if action == "position":
        out["position"] = _int(p.get("position"), 0, 100, 30)
    if action == "on" and p.get("brightness") not in (None, ""):
        out["brightness"] = _int(p.get("brightness"), 1, 100, 100)
    out["only_needed"] = bool(p.get("only_needed"))
    out["verify"] = bool(p.get("verify"))
    out["conds"] = normalize_group(p.get("conds"))
    out["note"] = _str(p.get("note"), 40)
    if p.get("guard"):
        out["guard"] = True  # Absicherung („nochmal schließen“) – nur für die Anzeige
    return out


def _md_list(raw: Any, what: str) -> list[str]:
    if raw in (None, "", []):
        return []
    items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw))
    items = [x for x in items if str(x).strip()]
    if len(items) > MAX_SPECIAL:
        raise ValueError(f"{what}: höchstens {MAX_SPECIAL} Tage")
    return sorted(dict.fromkeys(parse_md(x, what) for x in items))


def normalize_selector(s: Any) -> dict[str, str]:
    if not isinstance(s, dict) or s.get("by") not in ("area", "floor", "label"):
        raise ValueError("Auswahl über Bereich / Etage / Label ungültig")
    sid = str(s.get("id") or "")
    if not re.match(r"^[A-Za-z0-9_\-]{1,64}$", sid):
        raise ValueError("Auswahl: ungültige ID")
    return {"by": s["by"], "id": sid}


# ---------------------------------------------------------------- Einfacher Modus (Tagesarten wie bei der Heizung)
# Der einfache Modus ist nur eine bequeme Eingabe: beim Speichern wird er in gewöhnliche
# Schaltpunkte (days="type") umgerechnet. Ausführung, Vorschau und Export arbeiten nur mit
# Schaltpunkten – so verhalten sich „Einfach“ und „Erweitert“ garantiert gleich.

def raw_daytype(weekday: int, holiday: bool, vac_home: bool) -> str:
    """Rohe Tagesart eines Tages: Feiertag vor Urlaub zu Hause vor Wochentag."""
    if holiday:
        return "hol"
    if vac_home:
        return "vacwd" if weekday < 5 else ("vacwe_sa" if weekday == 5 else "vacwe_so")
    return "mf" if weekday < 5 else ("sa" if weekday == 5 else "so")


def _spec(s: Any, which: str, kind: str) -> dict[str, Any]:
    """Öffnen/Schließen einer Tagesart prüfen. which = "open" oder "close"."""
    s = s if isinstance(s, dict) else {}
    ref = s.get("ref", "time")
    if ref not in REFS_SIMPLE:
        raise ValueError("Unbekannter Zeitpunkt")
    out: dict[str, Any] = {"ref": ref}
    if ref == "time":
        out["time"] = hm(parse_hm(s.get("time"), "Öffnen" if which == "open" else "Schließen"))
    elif ref != "none":
        out["offset"] = _int(s.get("offset"), -300, 300, 0)
        out["unit"] = "h" if s.get("unit") == "h" else "min"  # nur Anzeige; gespeichert wird in Minuten
        for lim in ("earliest", "latest"):
            if s.get(lim):
                out[lim] = hm(parse_hm(s[lim], "frühestens" if lim == "earliest" else "spätestens"))
        if out.get("earliest") and out.get("latest") and parse_hm(out["earliest"]) > parse_hm(out["latest"]):
            raise ValueError("„frühestens“ liegt nach „spätestens“")
    if which == "open":
        if kind == KIND_COVER and s.get("position") not in (None, ""):
            out["position"] = _int(s.get("position"), 0, 100, 30)
        if kind == KIND_SWITCH and s.get("brightness") not in (None, ""):
            out["brightness"] = _int(s.get("brightness"), 1, 100, 100)
    return out


def normalize_simple(s: Any, kind: str) -> dict[str, Any]:
    if not isinstance(s, dict):
        raise ValueError("Einfacher Zeitplan hat ein falsches Format")
    raw_rows = s.get("rows") if isinstance(s.get("rows"), dict) else {}
    rows: dict[str, Any] = {}
    for key in SIMPLE_ROWS:
        r = raw_rows.get(key) if isinstance(raw_rows.get(key), dict) else {}
        like = r.get("like", SIMPLE_DEFAULT_LIKE[key])
        if like not in SIMPLE_LIKE[key]:
            raise ValueError(f"{SIMPLE_ROW_NAMES[key]}: ungültige Auswahl")
        rows[key] = {
            "like": like,
            "open": _spec(r.get("open") or {"ref": "time", "time": "07:00"}, "open", kind),
            "close": _spec(r.get("close") or {"ref": "sunset", "offset": 0}, "close", kind),
        }
    guard = s.get("guard") or ""
    return {
        "rows": rows,
        "days": _special_days(s.get("days"), kind),
        "close_per_row": bool(s.get("close_per_row")),
        "close": _spec(s.get("close") or {"ref": "sunset", "offset": 0}, "close", kind),
        "guard": hm(parse_hm(guard, "Absicherung")) if guard else "",
        "only_needed": bool(s.get("only_needed")),
        "verify": bool(s.get("verify")),
    }


SPECIAL_NORMAL = "normal"  # bestimmter Tag: „wie sonst“ – die Zeit der Tagesart bleibt


def _special_days(raw: Any, kind: str) -> list[dict[str, Any]]:
    """Bestimmte Tage (jedes Jahr am selben Datum): eigene Zeiten, gehen allen Tagesarten vor."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list) or len(raw) > MAX_SPECIAL:
        raise ValueError(f"Höchstens {MAX_SPECIAL} bestimmte Tage")
    out, seen = [], set()
    for d in raw:
        if not isinstance(d, dict):
            raise ValueError("Bestimmter Tag hat ein falsches Format")
        md = parse_md(d.get("date"), "Bestimmter Tag")
        name = _str(d.get("name"), 30)
        if md in seen:
            raise ValueError(f"Den {md_text(md)} gibt es doppelt")
        seen.add(md)
        item: dict[str, Any] = {"date": md, "name": name}
        for which in ("open", "close"):
            spec = d.get(which) if isinstance(d.get(which), dict) else {"ref": SPECIAL_NORMAL}
            label = f"{name or md_text(md)} – " + ("Einschalten" if which == "open" else "Ausschalten")
            if spec.get("ref", SPECIAL_NORMAL) == SPECIAL_NORMAL:
                item[which] = {"ref": SPECIAL_NORMAL}
            else:
                try:
                    item[which] = _spec(spec, which, kind)
                except ValueError as err:
                    raise ValueError(f"{label}: {err}") from err
        out.append(item)
    return sorted(out, key=lambda x: x["date"])


def special_day(simple: dict[str, Any] | None, day: date) -> dict[str, Any] | None:
    for d in (simple or {}).get("days") or []:
        if d["date"] == md_of(day):
            return d
    return None


def simple_resolve(simple: dict[str, Any], raw: str) -> str:
    """Welche Zeile liefert die Zeiten für diese rohe Tagesart? (folgt „wie …“)"""
    rows = simple["rows"]
    if raw in ("vacwe_sa", "vacwe_so"):
        like = rows["vacwe"]["like"]
        if like == "keep":
            return simple_resolve(simple, "sa" if raw == "vacwe_sa" else "so")
        key = "vacwe"
    else:
        key = raw
    for _ in range(6):  # Kette ist kurz und ohne Schleifen (siehe SIMPLE_LIKE)
        like = rows[key]["like"]
        if like == "own":
            return key
        key = like
    return key


def simple_day_label(simple: dict[str, Any], raw: str) -> str:
    """Lesbarer Text für einen Tag, z. B. „Feiertag → wie Sonntag“."""
    row = simple_resolve(simple, raw)
    name = DAY_TYPES[raw]
    own_key = {"vacwe_sa": "vacwe", "vacwe_so": "vacwe"}.get(raw, raw)
    if row == own_key or (raw in ("mf", "sa", "so") and row == raw):
        return name
    return f"{name} → wie {SIMPLE_ROW_NAMES[row]}"


def _spec_point(spec: dict[str, Any], action: str) -> dict[str, Any]:
    p: dict[str, Any] = {"ref": spec["ref"], "action": action}
    if spec["ref"] == "time":
        p["time"] = spec["time"]
    else:
        p["offset"] = spec.get("offset", 0)
        for lim in ("earliest", "latest"):
            if spec.get(lim):
                p[lim] = spec[lim]
    return p


def after_midnight(spec: dict[str, Any]) -> bool:
    """Schließzeit vor 12:00 (z. B. 00:30) gehört zum Vorabend."""
    return spec["ref"] == "time" and parse_hm(spec["time"]) < 12 * 60


def close_after_guard(simple: dict[str, Any], row: str) -> bool:
    """Kann die Schließzeit dieser Zeile nach der Absicherung liegen? Dann dort keine Absicherung."""
    cl = simple["rows"][row]["close"] if simple["close_per_row"] else simple["close"]
    if cl["ref"] == "none":
        return False
    guard = parse_hm(simple["guard"])
    if cl["ref"] == "time":
        return after_midnight(cl) or parse_hm(cl["time"]) > guard
    latest = cl.get("latest")
    return latest is None or parse_hm(latest) > guard  # Sonne ohne „spätestens“ kann im Sommer später sein


def simple_points(simple: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Einfachen Zeitplan in Schaltpunkte umrechnen."""
    groups: dict[str, list[str]] = {}
    for raw in DAY_TYPES:
        groups.setdefault(simple_resolve(simple, raw), []).append(raw)
    flags = {"only_needed": simple["only_needed"], "verify": simple["verify"], "conds": {"op": "and", "items": []}}
    act_close = "close" if kind == KIND_COVER else "off"
    points: list[dict[str, Any]] = []
    special = simple.get("days") or []
    # Bestimmte Tage mit eigener Zeit: dort fallen die normalen Punkte dieser Art weg
    exc_open = [d["date"] for d in special if d["open"]["ref"] != SPECIAL_NORMAL]
    exc_close = [d["date"] for d in special if d["close"]["ref"] != SPECIAL_NORMAL]
    for row in SIMPLE_ROWS:
        types = groups.get(row)
        if not types:
            continue
        r = simple["rows"][row]
        op = r["open"]
        if op["ref"] != "none":
            action = ("position" if op.get("position") is not None else "open") if kind == KIND_COVER else "on"
            p = {**_spec_point(op, action), "days": "type", "types": types, "except": exc_open, **flags}
            if action == "position":
                p["position"] = op["position"]
            if op.get("brightness"):
                p["brightness"] = op["brightness"]
            points.append(p)
        if simple["close_per_row"] and r["close"]["ref"] != "none":
            cl = r["close"]
            points.append({**_spec_point(cl, act_close), "days": "type", "types": types, "prev": after_midnight(cl), "except": exc_close, **flags})
    if not simple["close_per_row"] and simple["close"]["ref"] != "none":
        cl = simple["close"]
        points.append({**_spec_point(cl, act_close), "days": "daily", "prev": after_midnight(cl), "except": exc_close, **flags})
    for d in special:
        op, cl = d["open"], d["close"]
        note = d["name"] or md_text(d["date"])
        if op["ref"] not in (SPECIAL_NORMAL, "none"):
            action = ("position" if op.get("position") is not None else "open") if kind == KIND_COVER else "on"
            p = {**_spec_point(op, action), "days": "dates", "dates": [d["date"]], "note": note, **flags}
            if action == "position":
                p["position"] = op["position"]
            if op.get("brightness"):
                p["brightness"] = op["brightness"]
            points.append(p)
        if cl["ref"] not in (SPECIAL_NORMAL, "none"):
            points.append({**_spec_point(cl, act_close), "days": "dates", "dates": [d["date"]], "prev": after_midnight(cl), "note": note, **flags})
    if simple["guard"]:
        # Die Absicherung darf eine spätere Schließzeit nicht vorwegnehmen (z. B. 23:00 vor „00:30“).
        safe = [t for row, types in groups.items() for t in types if not close_after_guard(simple, row)]
        if safe:
            points.append({"ref": "time", "time": simple["guard"], "action": act_close, "days": "type" if len(safe) < len(DAY_TYPES) else "daily",
                           "types": safe, "except": exc_close, "only_needed": True, "verify": simple["verify"], "conds": {"op": "and", "items": []},
                           "note": "Absicherung", "guard": True})
    if not points:
        raise ValueError("Der Zeitplan schaltet nie – bitte mindestens eine Zeit eintragen")
    return [normalize_point(p, kind) for p in points]


def _base(f: dict[str, Any]) -> dict[str, Any]:
    name = _str(f.get("name"))
    if not name:
        raise ValueError("Bitte einen Namen eingeben")
    return {
        "name": name,
        "icon": _str(f.get("icon"), 8) or "⏰",
        "enabled": bool(f.get("enabled", True)),
        "native": bool(f.get("native", False)),
        "conds": normalize_group(f.get("conds")),
    }


def normalize_plan(f: dict[str, Any]) -> dict[str, Any]:
    kind = f.get("kind")
    if kind not in KINDS:
        raise ValueError("Art muss Rollläden oder Licht & Steckdosen sein")
    out = {"type": "plan", "kind": kind, **_base(f)}
    raw_dev = f.get("devices") or []
    if not isinstance(raw_dev, list):
        raise ValueError("Geräte haben ein falsches Format")
    devices = list(dict.fromkeys(_entity(e, KIND_DOMAINS[kind]) for e in raw_dev))
    if len(devices) > MAX_DEVICES:
        raise ValueError(f"Höchstens {MAX_DEVICES} Geräte")
    out["devices"] = devices
    sels = f.get("selectors") or []
    if not isinstance(sels, list):
        raise ValueError("Auswahl hat ein falsches Format")
    out["selectors"] = [normalize_selector(s) for s in sels][:10]
    if not devices and not out["selectors"]:
        raise ValueError("Bitte mindestens ein Gerät, einen Bereich oder ein Label wählen")
    overrides = {}
    raw_ov = f.get("overrides") or {}
    if not isinstance(raw_ov, dict):
        raise ValueError("Abweichungen haben ein falsches Format")
    for eid, ov in raw_ov.items():
        if eid in devices and isinstance(ov, dict) and ov.get("position") not in (None, ""):
            overrides[eid] = {"position": _int(ov["position"], 0, 100, 0)}
    out["overrides"] = overrides
    if f.get("mode") == "simple":
        out["mode"] = "simple"
        out["simple"] = normalize_simple(f.get("simple"), kind)
        out["points"] = simple_points(out["simple"], kind)
    else:
        out["mode"] = "advanced"
        points = f.get("points") or []
        if not isinstance(points, list) or not points or len(points) > MAX_POINTS:
            raise ValueError(f"1 bis {MAX_POINTS} Schaltpunkte")
        out["points"] = [normalize_point(p, kind) for p in points]
        # Aus „Einfach“ umgeschaltet und nichts geändert? Dann bleibt der Weg zurück offen.
        if f.get("simple"):
            try:
                simple = normalize_simple(f["simple"], kind)
                if simple_points(simple, kind) == out["points"]:
                    out["simple"] = simple
            except ValueError:
                pass
    out["random"] = _int(f.get("random"), 0, 60, 0) if kind == KIND_SWITCH else 0
    out["button"] = normalize_button(f.get("button"))
    out["switch"] = bool(f.get("switch"))  # auch als Schalter in Home Assistant (schaltet die Geräte wie der Taster)
    return out


def normalize_button(b: Any) -> dict[str, Any] | None:
    """Taster eines Zeitplans: ein Gerät, bis zu drei angelernte Tasten (umschalten / an / aus).

    Ein Tastendruck schaltet alle Geräte des Zeitplans gemeinsam – wie von Hand; der Plan läuft danach weiter.
    """
    if not b:
        return None
    if not isinstance(b, dict):
        raise ValueError("Taster hat ein falsches Format")
    dev = str(b.get("device_id") or "")
    if not dev:
        return None
    if not BUTTON_DEV_RE.match(dev):
        raise ValueError("Taster: ungültiges Gerät")
    raw = b.get("map") or {}
    if not isinstance(raw, dict) or len(raw) > len(BUTTON_ACTIONS):
        raise ValueError("Taster: zu viele Tasten")
    mapping, used = {}, set()
    for sig, act in raw.items():
        if act in (None, ""):
            continue
        if not isinstance(sig, str) or not BUTTON_SIG_RE.match(sig) or act not in BUTTON_ACTIONS:
            raise ValueError("Taster: ungültige Tastenzuordnung")
        if act in used:
            raise ValueError("Taster: jede Funktion nur einer Taste zuordnen")
        used.add(act)
        mapping[sig] = act
    scope = b.get("scope") if b.get("scope") in BUTTON_SCOPES else "always"
    return {"device_id": dev, "map": mapping, "auto_off": _int(b.get("auto_off"), 0, MAX_AUTO_OFF, 0), "scope": scope}


def normalize_step(s: Any) -> dict[str, Any]:
    if not isinstance(s, dict) or s.get("do") not in STEP_KINDS:
        raise ValueError("Unbekannter Schritt")
    do = s["do"]
    out: dict[str, Any] = {"do": do}
    if do in ("on", "off", "open", "close", "position", "blink", "toggle"):
        doms = ("cover",) if do in ("open", "close", "position") else ("light", "switch", "input_boolean", "fan", "cover") if do == "toggle" else ("light", "switch", "input_boolean", "fan")
        ents = list(dict.fromkeys(_entity(e, doms) for e in s.get("entities") or []))
        if not ents:
            raise ValueError(f"Schritt „{STEP_KINDS[do]}“: Gerät wählen")
        out["entities"] = ents[:MAX_DEVICES]
    if do == "position":
        out["position"] = _int(s.get("position"), 0, 100, 50)
    if do == "on" and s.get("brightness") not in (None, ""):
        out["brightness"] = _int(s.get("brightness"), 1, 100, 100)
    if do == "wait":
        out["seconds"] = _int(s.get("seconds"), 1, MAX_WAIT, 60)
    if do == "wait_until":
        cond = normalize_cond(s.get("until") or {})
        if "items" in cond or cond["key"] != "entity":
            raise ValueError("„warten, bis …“ braucht eine Entität")
        out["until"] = cond
        out["after"] = _int(s.get("after"), 0, 3600, 0)  # Nachlauf in Sekunden
        out["timeout"] = _int(s.get("timeout"), 60, MAX_WAIT, 4 * 3600)
    if do == "blink":
        out["times"] = _int(s.get("times"), 1, 10, 2)
        # Dauer je Phase (aus bzw. an) in Zehntelsekunden: 3 = 0,3 s … 30 = 3 s; Standard 0,5 s
        out["pause"] = _int(s.get("pause"), 3, 30, 5)
    if do == "notify":
        target = str(s.get("target") or "persistent")
        if target != "persistent" and not NOTIFY_RE.match(target):
            raise ValueError("Nachricht: Ziel muss „persistent“ oder ein notify-Dienst sein")
        out["target"] = target
        out["message"] = _str(s.get("message"), 200) or "HomeRhythm"
        if any(tok in out["message"] for tok in ("{{", "{%", "{#")):
            raise ValueError("Nachricht: geschweifte Template-Klammern sind nicht erlaubt")
    return out


def normalize_trigger(t: Any) -> dict[str, Any]:
    if not isinstance(t, dict) or t.get("kind") not in TRIGGER_KINDS:
        raise ValueError("Unbekannter Auslöser")
    out: dict[str, Any] = {"kind": t["kind"], "entity": _entity(t.get("entity"), TRIGGER_DOMAINS)}
    if t["kind"] == "state":
        to = t.get("to")
        out["to"] = _str(to, 60) if to not in (None, "") else None  # None = jede Änderung (z. B. Knopf gedrückt)
        if out["to"] is None and out["entity"].split(".")[0] == "sensor":
            raise ValueError("Bei Messwerten bitte „steigt über“ / „fällt unter“ wählen – „jede Änderung“ würde ständig auslösen")
    else:
        out["value"] = _float(t.get("value"), "Auslöser: Schwellwert")
    return out


def normalize_react(f: dict[str, Any]) -> dict[str, Any]:
    out = {"type": "react", **_base(f)}
    triggers = f.get("triggers") or []
    if not isinstance(triggers, list) or not triggers or len(triggers) > MAX_TRIGGERS:
        raise ValueError(f"1 bis {MAX_TRIGGERS} Auslöser")
    out["triggers"] = [normalize_trigger(t) for t in triggers]
    steps = f.get("steps") or []
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise ValueError(f"1 bis {MAX_STEPS} Schritte")
    out["steps"] = [normalize_step(s) for s in steps]
    out["mode"] = f.get("mode") if f.get("mode") in MODES_REACT else "restart"
    return out


def flow_refs(flow: dict[str, Any]) -> set[str]:
    """IDs anderer Zeitpläne, auf die ein Ablauf in Bedingungen verweist."""
    refs: set[str] = set()

    def walk(c: dict[str, Any]) -> None:
        if "items" in c:
            for x in c["items"]:
                walk(x)
        elif c.get("key") == "flow":
            refs.add(c["flow"])

    walk(flow["conds"])
    for p in flow.get("points", []):
        walk(p["conds"])
    return refs


def normalize_flow(f: Any) -> dict[str, Any]:
    if not isinstance(f, dict):
        raise ValueError("Ablauf hat ein falsches Format")
    return normalize_plan(f) if f.get("type", "plan") == "plan" else normalize_react(f)


# ---------------------------------------------------------------- Zeitplan: wann wird geschaltet?
def point_owner(point: dict[str, Any], day: date) -> date:
    """Zu welchem Tag gehört ein Schaltpunkt an ``day``? Nach Mitternacht („prev“) zum Vortag."""
    return day - timedelta(days=1) if point.get("prev") else day


def day_matches(point: dict[str, Any], day: date, workday: bool, ctx: Ctx | None = None) -> bool:
    d = point["days"]
    wd = day.weekday()
    owner = md_of(point_owner(point, day))
    if owner in point.get("except", ()):
        return False  # an diesem Tag gelten die eigenen Zeiten eines bestimmten Tages
    if d == "dates":
        return owner in point.get("dates", ())
    if d == "type":
        if point.get("prev"):
            dt = (ctx.prev_daytype if ctx else "") or raw_daytype((wd - 1) % 7, False, False)
        else:
            dt = (ctx.daytype if ctx else "") or raw_daytype(wd, False, False)
        return dt in point.get("types", [])
    return {
        "daily": True,
        "work": workday,
        "free": not workday,
        "wd": wd < 5,
        "we": wd >= 5,
        "custom": wd in point.get("weekdays", []),
    }[d]


def _random_shift(flow_id: str, day: date, idx: int, spread: int) -> int:
    """Urlaubssimulation: jeden Tag eine andere, aber reproduzierbare Verschiebung (−spread … +spread)."""
    if spread <= 0:
        return 0
    h = hashlib.sha256(f"{flow_id}|{day.isoformat()}|{idx}".encode()).digest()
    return h[0] % (2 * spread + 1) - spread


def point_minute(point: dict[str, Any], sun: Sun, flow_id: str = "", day: date | None = None, idx: int = 0, spread: int = 0) -> int:
    if point["ref"] == "time":
        m = parse_hm(point["time"])
    else:
        m = (sun.sunrise if point["ref"] == "sunrise" else sun.sunset) + point.get("offset", 0)
        if point.get("earliest"):
            m = max(m, parse_hm(point["earliest"]))
        if point.get("latest"):
            m = min(m, parse_hm(point["latest"]))
    if spread and day is not None:
        m += _random_shift(flow_id, day, idx, spread)
    return max(0, min(1439, m))


def point_active(plan: dict[str, Any], point: dict[str, Any], ctx: Ctx, prev_ctx: Ctx | None) -> bool:
    """„Zeitplan gilt“ für diesen Schaltpunkt? Nach Mitternacht zählt der Vortag (z. B. „aus 01:00“ am letzten Tag eines Zeitraums)."""
    return plan_active(plan, prev_ctx if point.get("prev") and prev_ctx is not None else ctx)


def day_events(flow_id: str, plan: dict[str, Any], day: date, sun: Sun, ctx: Ctx, prev_ctx: Ctx | None = None, check_plan: bool = False) -> list[tuple[int, int, dict[str, Any]]]:
    """(Minute, Index, Schaltpunkt) aller Schaltpunkte dieses Tages – nach Zeit sortiert.

    Bedingungen des Schaltpunkts werden mit dem übergebenen Kontext geprüft. ``check_plan``: auch
    „Zeitplan gilt“ prüfen (je Schaltpunkt; nach Mitternacht mit ``prev_ctx`` = Kontext des Vortags).
    """
    out = []
    for i, p in enumerate(plan["points"]):
        if check_plan and not point_active(plan, p, ctx, prev_ctx):
            continue
        if day_matches(p, day, ctx.workday, ctx) and cond_true(p["conds"], ctx):
            out.append((point_minute(p, sun, flow_id, day, i, plan.get("random", 0)), i, p))
    return sorted(out, key=lambda x: (x[0], x[1]))


def day_strip(flow_id: str, plan: dict[str, Any], days: list[tuple[date, Sun, Ctx]], index: int) -> list[str]:
    """96 Viertelstunden-Zustände für Tag ``days[index]`` (Zustand läuft vom Vortag weiter).

    Tage, an denen „Zeitplan gilt“ nicht zutrifft, sind „none“ (ruht) und schalten nichts.
    """
    n = len(days)
    events = [day_events(flow_id, plan, d, s, c, days[(i - 1) % n][2], check_plan=True) for i, (d, s, c) in enumerate(days)]
    if not plan_active(plan, days[index][2]) and not events[index]:
        return ["none"] * 96
    # Zustand um Mitternacht = letzter Befehl davor. Die Woche wird als Kreis gerechnet
    # (vor Montag kommt Sonntag) – so beginnt Montag nicht mit einem erfundenen Zustand.
    start = None
    for back in range(1, len(days) + 1):
        prev = events[(index - back) % len(days)]
        if prev:
            start = ACTION_STATE[prev[-1][2]["action"]]
            break
    state = start or "none"  # schaltet die ganze Woche nie → unbekannt
    out, evs, j = [], events[index], 0
    for q in range(96):
        minute = q * 15 + 7
        while j < len(evs) and evs[j][0] <= minute:
            state = ACTION_STATE[evs[j][2]["action"]]
            j += 1
        out.append(state)
    return out


def plan_active(plan: dict[str, Any], ctx: Ctx) -> bool:
    """Trifft „Zeitplan gilt“ (Bedingung des ganzen Plans) an diesem Tag zu?"""
    return cond_true(plan.get("conds") or {"op": "and", "items": []}, ctx)


def day_marks(flow_id: str, plan: dict[str, Any], day: date, sun: Sun, ctx: Ctx, prev_ctx: Ctx | None = None) -> list[dict[str, Any]]:
    """Schaltpunkte eines Tages für die Balken: Minute, nach Sonne?, Absicherung?"""
    return [{"m": m, "a": p["action"], "sun": p["ref"] != "time", "guard": bool(p.get("guard")), "prev": bool(p.get("prev"))}
            for m, _i, p in day_events(flow_id, plan, day, sun, ctx, prev_ctx, check_plan=True)]


def day_label(plan: dict[str, Any], ctx: Ctx, day: date) -> str:
    """Was gilt an diesem Tag? Für die Zeile neben dem Wochenbalken."""
    raw = ctx.daytype or raw_daytype(day.weekday(), False, False)
    if not plan_active(plan, ctx):
        return "ruht (Zeitplan gilt nicht)"
    if plan.get("mode") == "simple" and plan.get("simple"):
        if sp := special_day(plan["simple"], day):
            return f"{sp['name'] or md_text(sp['date'])} – bestimmter Tag"
        return simple_day_label(plan["simple"], raw)
    if any(p["days"] == "type" for p in plan["points"]):
        return DAY_TYPES[raw]
    return "Arbeitstag" if ctx.workday else ("Feiertag" if raw == "hol" else "frei")


def offset_text(off: int, unit: str = "min") -> str:
    """Versatz immer mit Einheit: „+90 min“, „+1 Std.“, „+1 Std. 30 min“."""
    if not off:
        return ""
    sign, a = ("+" if off > 0 else "−"), abs(off)
    if unit == "h" or a >= 60:
        h, mi = divmod(a, 60)
        return f" {sign}{h} Std." + (f" {mi} min" if mi else "") if h else f" {sign}{mi} min"
    return f" {sign}{a} min"


def point_text(p: dict[str, Any]) -> str:
    if p["days"] == "custom":
        days = ", ".join(WEEKDAYS[i] for i in p["weekdays"])
    elif p["days"] == "type":
        days = ", ".join(DAY_TYPES[t] for t in p["types"]) + (" (Vorabend, nach Mitternacht)" if p.get("prev") else "")
    elif p["days"] == "dates":
        days = ", ".join(md_text(x) for x in p["dates"]) + (" (Vorabend, nach Mitternacht)" if p.get("prev") else "")
    else:
        days = DAYS[p["days"]]
    if p.get("except"):
        days += " außer " + ", ".join(md_text(x) for x in p["except"])
    if p["ref"] == "time":
        when = p["time"]
    else:
        off = p.get("offset", 0)
        when = REFS[p["ref"]] + offset_text(off)
        lim = [f"frühestens {p['earliest']}" if p.get("earliest") else "", f"spätestens {p['latest']}" if p.get("latest") else ""]
        lim = ", ".join(x for x in lim if x)
        if lim:
            when += f" ({lim})"
    act = ACTION_NAMES[p["action"]] + (f" {p['position']} %" if p["action"] == "position" else "") + (f" {p['brightness']} %" if p.get("brightness") else "")
    return f"{days} · {when} → {act}"


# ---------------------------------------------------------------- Reaktionen
def trigger_fires(t: dict[str, Any], old: str | None, new: str | None) -> bool:
    """Löst eine Zustandsänderung old → new diesen Auslöser aus?"""
    if new is None or new in ("unavailable", "unknown"):
        return False
    if old is None or old in ("unavailable", "unknown"):
        return False  # Gerät kommt (z. B. nach einem Neustart) wieder online – das ist kein Auslöser
    if t["kind"] == "state":
        if t.get("to") is None:  # Knopf / Ereignis: jede neue Zeitmarke zählt
            return old is not None and old != new and old not in ("unavailable",)
        return new == t["to"] and old != t["to"]
    n_new, n_old = _num(new), _num(old)
    if n_new is None:
        return False
    if t["kind"] == "above":
        return n_new > t["value"] and (n_old is None or n_old <= t["value"])
    return n_new < t["value"] and (n_old is None or n_old >= t["value"])


def step_text(s: dict[str, Any], names: dict[str, str] | None = None) -> str:
    names = names or {}
    ents = ", ".join(names.get(e, e) for e in s.get("entities", []))
    do = s["do"]
    if do == "wait":
        sec = s["seconds"]
        return f"{sec // 60} min warten" if sec % 60 == 0 and sec >= 60 else f"{sec} s warten"
    if do == "wait_until":
        after = s.get("after", 0)
        return f"warten, bis {cond_text(s['until'], names)}" + (f", dann {after // 60} min Nachlauf" if after >= 60 else f", dann {after} s Nachlauf" if after else "")
    if do == "blink":
        pause = str(s.get("pause", 5) / 10).replace(".", ",").replace(",0", "")
        return f"{ents}: {s['times']}× blinken (je {pause} s aus/an, endet an)"
    if do == "notify":
        return f"Nachricht: „{s['message']}“"
    if do == "position":
        return f"{ents} auf {s['position']} %"
    extra = f" {s['brightness']} %" if s.get("brightness") else ""
    return f"{ents} {STEP_KINDS[do]}{extra}"
