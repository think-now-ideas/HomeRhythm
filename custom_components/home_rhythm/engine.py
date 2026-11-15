"""Regel-Engine von Home Rhythm (ohne Home-Assistant-Abhängigkeiten, dadurch testbar)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any

DAY_TYPES = ("wd", "sa", "so")
DAY_TYPE_NAMES = {"wd": "Mo–Fr", "sa": "Samstag", "so": "So / Feiertag"}
PLAN_NAMES = {"wd": "Werktagsplan", "sa": "Samstagsplan", "so": "Sonntagsplan"}

# Stufen der Heizung. Reihenfolge = Anzeige-Reihenfolge.
BASE_LEVELS = ("komfort", "absenkung", "nacht", "bad")  # "bad" heißt in der Oberfläche "Booster"
EXTRA_LEVELS = ("extra1", "extra2", "extra3", "extra4")  # eigene Stufen, in der Einrichtung einschaltbar
PLAN_LEVELS = BASE_LEVELS + EXTRA_LEVELS
LEVEL_NAMES = {
    "komfort": "Komfort",
    "absenkung": "Absenkung",
    "nacht": "Nacht",
    "bad": "Booster",
    "extra1": "Stufe 5",
    "extra2": "Stufe 6",
    "extra3": "Stufe 7",
    "extra4": "Stufe 8",
    "urlaub": "Urlaub",
    "hand": "Hand",
    "aus": "Aus",
    "kuehlen": "Kühlen",
    "vorkuehlen": "Vorkühlen",
}
DEFAULT_LEVEL_TEMPS = {"komfort": 21.0, "absenkung": 18.0, "nacht": 17.0, "bad": 23.0,
                       "extra1": 20.0, "extra2": 20.0, "extra3": 20.0, "extra4": 20.0}
COOL_USE = {"komfort", "bad"}  # Stufen, bei denen der Raum genutzt wird → Klimaanlage kühlt im Sommer
ENABLED_LEVELS = list(BASE_LEVELS)  # in der Oberfläche angebotene Stufen
BASE_NAMES = {"komfort": "Komfort", "absenkung": "Absenkung", "nacht": "Nacht", "bad": "Booster"}

RULE_SEASON = "season"
RULE_AWAY = "away"
RULE_MANUAL = "man"
RULE_HOLIDAY = "hol"
RULE_PLAN = "plan"
RULE_ABSENT = "absent"
RULE_ROOM = "room"  # Raumregel ("Wenn Ereignis = Gäste, dann Komfort")
RULE_TODAY = "today"  # "Heute anders" für einen Raum
RULE_PARTY = "party"  # Ereignis Party in Party-Räumen

EVENTS = ("keins", "Party", "Gäste")


def plan_like(result: "Result") -> bool:
    """Stufe aus Plan, Feiertag, Raumregel, Heute anders oder Party (nicht Urlaub, Hand, Aus)."""
    return result.rule in (RULE_PLAN, RULE_HOLIDAY, RULE_TODAY, RULE_PARTY, RULE_ROOM) and result.level in PLAN_LEVELS
TODAY_KINDS = {
    "normal": "normal",
    "sonntag": "wie Sonntag",
    "werktag": "wie Mo–Fr",
    "party": "Party bis 1 Uhr",
    "komfort": "Komfort den ganzen Tag",
    "leer": "niemand im Raum",
}
RULE_MODES = {"vacation": "Urlaub", "event": "Ereignis", "occasion": "Anlass", "season": "Jahreszeit", "presence": "Anwesenheit"}
RULE_ACTIONS = {
    "komfort": "Komfort",
    "absenkung": "Absenkung",
    "nacht": "Nacht",
    "bad": "Booster",
    "extra1": "Stufe 5",
    "extra2": "Stufe 6",
    "extra3": "Stufe 7",
    "extra4": "Stufe 8",
    "sonntag": "Sonntagsplan",
    "urlaub": "Urlaubstemperatur",
    "aus": "aus",
}

MANUAL_NEXT = "next"  # Hand-Änderung gilt bis zum nächsten Wechsel im Plan


@dataclass
class Modes:
    """Hausmodi zum Zeitpunkt der Auswertung."""

    season: str = "Winter"
    heating_season: bool = True
    away: bool = False
    home_vacation: bool = False
    holiday_today: bool = False
    away_temp: float = 16.0
    vacation_label: str = ""
    cooling_season: bool = False  # z. B. Jahreszeit "Heißphase"
    nobody_home: bool = False
    event: str = "keins"  # keins / Party / Gäste
    occasion: str = ""  # z. B. "Weihnachten"
    party_until: datetime | None = None  # Ereignis Party gilt in Party-Räumen bis dahin
    holiday_as: str = "so"  # Feiertag heizt wie: "wd" (Mo–Fr), "sa" oder "so"
    vacation_as: str = "so"  # Urlaub zu Hause heizt wie: "wd", "sa" oder "so"
    sunday_all: bool = False  # Raumregel „Sonntagsplan“: jeden Tag Sonntag
    sunday_today: bool = False  # „Heute anders: wie Sonntag“ (nur noch für ältere Aufrufe)
    force_dtype: str | None = None  # „Heute anders: wie Sonntag / wie Mo–Fr“ – dieser Wochenplan …
    force_until: datetime | None = None  # … für alle Tage vor diesem Zeitpunkt


@dataclass
class Today:
    """„Heute anders“ bzw. Ausnahme für einen Raum (immer nur eine je Raum).

    kind "stufe": eine Stufe von ``start`` bis ``until`` (auch über mehrere Tage), außerhalb gilt der Plan.
    Andere Arten gelten ganze Tage bis ``until``. ``start`` None = sofort.
    """

    kind: str  # stufe / sonntag / werktag / party / komfort / leer
    until: datetime
    level: str | None = None
    start: datetime | None = None

    def active(self, now: datetime) -> bool:
        return self.until > now and (self.start is None or self.start <= now)

    def planned(self, now: datetime) -> bool:
        return self.start is not None and self.start > now


def today_label(o: Today) -> str:
    """Kurztext für Anzeige und Grund, z. B. „Homeoffice bis 21:23“."""
    if o.kind == "stufe":
        name = LEVEL_NAMES.get(o.level or "", o.level or "")
        return f"{name} bis {_fmt_until(o)}"
    return TODAY_KINDS.get(o.kind, o.kind)


def _fmt_until(o: Today) -> str:
    """Ende kurz: „21:23“ (am selben Tag), „Tagesende“, sonst mit Wochentag und Datum."""
    u = o.until
    ref = (o.start or u).date()
    midnight = u.hour == 0 and u.minute == 0
    day = (u - timedelta(minutes=1)).date() if midnight else u.date()
    clock = "Tagesende" if midnight else f"{u.hour:02d}:{u.minute:02d}"
    return clock if day == ref else f"{_WD[day.weekday()]} {day.day}.{day.month}. {clock}"


_WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


@dataclass
class Manual:
    """Aktive Hand-Änderung eines Raums."""

    temperature: float | None
    hvac_mode: str  # "heat" oder "off"
    until: datetime
    source: str = ""  # z. B. "Benutzer", "am Gerät / extern"
    since: datetime | None = None


@dataclass
class Result:
    level: str
    temperature: float | None
    hvac_mode: str
    rule: str
    reason: str
    until: datetime | None = None
    next_level: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def parse_hm(value: str) -> int:
    """'07:30' -> 450 Minuten. '24:00' ist erlaubt."""
    hours, minutes = value.strip().split(":")
    total = int(hours) * 60 + int(minutes)
    if not 0 <= total <= 24 * 60:
        raise ValueError(f"Ungültige Uhrzeit: {value}")
    return total


def fmt_hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_schedule(schedule: dict[str, Any] | None) -> dict[str, list[list[Any]]]:
    """Prüft und sortiert Zeitblöcke. Blöcke: [start, ende, stufe]."""
    out: dict[str, list[list[Any]]] = {}
    schedule = schedule or {}
    for dt in DAY_TYPES:
        blocks = []
        for block in schedule.get(dt, []) or []:
            start, end, level = block[0], block[1], block[2]
            s_min, e_min = parse_hm(start), parse_hm(end)
            if e_min <= s_min:
                raise ValueError(f"Block {start}–{end}: Ende muss nach dem Beginn liegen")
            if level not in PLAN_LEVELS:
                raise ValueError(f"Unbekannte Stufe: {level}")
            blocks.append([fmt_hm(s_min), fmt_hm(e_min), level])
        blocks.sort(key=lambda b: parse_hm(b[0]))
        for prev, nxt in zip(blocks, blocks[1:]):
            if parse_hm(nxt[0]) < parse_hm(prev[1]):
                raise ValueError(
                    f"{DAY_TYPE_NAMES[dt]}: {prev[0]}–{prev[1]} und {nxt[0]}–{nxt[1]} überschneiden sich"
                )
        out[dt] = blocks
    return out


def day_type_for(day: date, holiday: bool) -> str:
    if holiday:
        return "so"
    wd = day.weekday()
    if wd < 5:
        return "wd"
    return "sa" if wd == 5 else "so"


def plan_level(room: dict[str, Any], day_type: str, minute: int) -> str:
    for start, end, level in room.get("schedule", {}).get(day_type, []):
        if parse_hm(start) <= minute < parse_hm(end):
            return level
    return room.get("default_level", "absenkung")


def level_temperature(room: dict[str, Any], level: str) -> float:
    levels = room.get("levels") or {}
    if level in levels and levels[level] is not None:
        return float(levels[level])
    return DEFAULT_LEVEL_TEMPS.get(level, 18.0)


def _special(day: date, today: date, modes: Modes) -> str | None:
    """Besonderer Tag? "force" (Sonntagsplan erzwungen), "vac" (Urlaub zu Hause), "hol" (Feiertag) oder None.

    Feiertag kennen wir nur für heute (Workday). Urlaub zu Hause gilt jeden Tag.
    """
    if modes.sunday_all or (modes.sunday_today and day == today):
        return "force"
    if modes.home_vacation:
        return "vac"
    if modes.holiday_today and day == today:
        return "hol"
    return None


def _holiday_for(day: date, today: date, modes: Modes) -> bool:
    return _special(day, today, modes) is not None


def _dtype(day: date, today: date, modes: Modes) -> str:
    """Welcher Wochenplan gilt? Feiertag / Urlaub zu Hause wie eingestellt (Standard: wie Sonntag)."""
    if modes.force_dtype and modes.force_until is not None and datetime.combine(day, time(0), tzinfo=modes.force_until.tzinfo) < modes.force_until:
        return modes.force_dtype
    sp = _special(day, today, modes)
    if sp == "force":
        return "so"
    if sp in ("vac", "hol"):
        as_ = modes.vacation_as if sp == "vac" else modes.holiday_as
        return as_ if as_ in DAY_TYPES else "so"
    return day_type_for(day, False)


def _plan_at(room: dict[str, Any], when: datetime, today: date, modes: Modes) -> str:
    return plan_level(room, _dtype(when.date(), today, modes), when.hour * 60 + when.minute)


def next_plan_change(
    room: dict[str, Any], now: datetime, modes: Modes, horizon_days: int = 3
) -> tuple[datetime | None, str | None]:
    """Nächster Zeitpunkt, an dem sich die Plan-Stufe ändert (nur Blockgrenzen prüfen)."""
    today = now.date()
    current = _plan_at(room, now, today, modes)
    sched = room.get("schedule", {})
    for offset in range(horizon_days):
        day = today + timedelta(days=offset)
        dtype = _dtype(day, today, modes)
        cands = {0}
        for start, end, _lvl in sched.get(dtype, []):
            cands.add(parse_hm(start))
            e = parse_hm(end)
            if e < 24 * 60:
                cands.add(e)
        for minute in sorted(cands):
            t = datetime.combine(day, time(minute // 60, minute % 60), tzinfo=now.tzinfo)
            if t <= now:
                continue
            lvl = _plan_at(room, t, today, modes)
            if lvl != current:
                return t, lvl
    return None, None


def manual_until(room: dict[str, Any], now: datetime, modes: Modes, override: "Today | None" = None) -> datetime:
    """Bis wann gilt eine Hand-Änderung, die jetzt passiert?

    Während einer Ausnahme „Stufe“ ist ihr Ende der nächste Wechsel.
    """
    mode = room.get("manual_mode", MANUAL_NEXT)
    if mode == MANUAL_NEXT and override is not None and override.kind == "stufe" and override.active(now):
        return override.until
    if mode != MANUAL_NEXT:
        try:
            minutes = int(mode)
        except (TypeError, ValueError):
            minutes = 0
        if minutes > 0:
            return now + timedelta(minutes=minutes)
    change, _ = next_plan_change(room, now, modes)
    return change or (now + timedelta(hours=24))


def mode_value(modes: Modes, key: str) -> str:
    if key == "vacation":
        return modes.vacation_label or "kein Urlaub"
    if key == "event":
        return modes.event or "keins"
    if key == "occasion":
        return modes.occasion or "keiner"
    if key == "season":
        return modes.season
    if key == "presence":
        return "niemand zu Hause" if modes.nobody_home else "jemand zu Hause"
    return ""


def normalize_rules(rules: Any) -> list[dict[str, Any]]:
    out = []
    for rule in rules or []:
        cond = rule.get("if") or {}
        mode, op, value = cond.get("mode"), cond.get("op", "is"), str(cond.get("value", "")).strip()
        then = rule.get("then")
        if mode not in RULE_MODES:
            raise ValueError(f"Raumregel: unbekannter Modus {mode}")
        if op not in ("is", "not"):
            raise ValueError("Raumregel: „ist“ oder „ist nicht“")
        if not value:
            raise ValueError("Raumregel: Wert fehlt")
        if then not in RULE_ACTIONS:
            raise ValueError(f"Raumregel: unbekannte Aktion {then}")
        out.append({"if": {"mode": mode, "op": op, "value": value}, "then": then})
    return out


def rule_matches(rule: dict[str, Any], modes: Modes) -> bool:
    cond = rule["if"]
    current = mode_value(modes, cond["mode"])
    if current in ("unavailable", "unknown", ""):
        return False  # Helfer gerade nicht verfügbar → Regel nicht anwenden
    hit = current.casefold() == str(cond["value"]).casefold()
    return hit if cond.get("op", "is") == "is" else not hit


def rule_text(rule: dict[str, Any]) -> str:
    c = rule["if"]
    return f"Wenn {RULE_MODES[c['mode']]} {'=' if c.get('op', 'is') == 'is' else '≠'} {c['value']} → {RULE_ACTIONS[rule['then']]}"


def matching_rule(room: dict[str, Any], modes: Modes) -> dict[str, Any] | None:
    return next((r for r in room.get("rules") or [] if rule_matches(r, modes)), None)


def christmas(day: date) -> bool:
    """Anlass Weihnachten: 1. Advent bis 6. Januar."""
    if day.month == 1 and day.day <= 6:
        return True
    dec24 = date(day.year, 12, 24)
    advent4 = dec24 - timedelta(days=(dec24.weekday() + 1) % 7)  # Sonntag vor/an Heiligabend
    return advent4 - timedelta(days=21) <= day <= date(day.year, 12, 31)


def party_end(now: datetime) -> datetime:
    """Party gilt bis 1 Uhr nachts."""
    end = now.replace(hour=1, minute=0, second=0, microsecond=0)
    return end if now < end else end + timedelta(days=1)


def today_until(kind: str, now: datetime) -> datetime:
    if kind == "party":
        return party_end(now)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def effective_modes(room: dict[str, Any], modes: Modes, now: datetime, override: Today | None = None) -> Modes:
    """Hausmodi inkl. Sonntagsplan aus Raumregel oder „Heute anders: wie Sonntag“ (für „bis wann“)."""
    rule = matching_rule(room, modes)
    if rule and rule["then"] == "sonntag":
        modes = replace(modes, sunday_all=True)
    if override is not None and override.active(now) and override.kind in FORCE_KINDS:
        modes = replace(modes, force_dtype=FORCE_KINDS[override.kind], force_until=override.until)
    return modes


FORCE_KINDS = {"sonntag": "so", "werktag": "wd"}


def _manual_result(manual: Manual) -> Result:
    temp = manual.temperature if manual.hvac_mode != "off" else None
    src = f" ({manual.source})" if manual.source else ""
    return Result("hand", temp, manual.hvac_mode, RULE_MANUAL, f"Hand-Änderung{src}", until=manual.until)


def evaluate(
    room: dict[str, Any],
    modes: Modes,
    now: datetime,
    manual: Manual | None = None,
    with_until: bool = True,
    today: date | None = None,
    override: Today | None = None,
) -> Result:
    """Wertet die Regeln eines Raums aus. Erste zutreffende Regel gewinnt.

    Jahreszeit → Raumregel → Urlaub unterwegs → Hand-Änderung → Heute anders / Party → Feiertag → Wochenplan
    """
    if not modes.heating_season:
        return Result("aus", None, "off", RULE_SEASON, f"Jahreszeit {modes.season}")

    rule = matching_rule(room, modes)
    sunday_why = None

    def apply_rule() -> Result | None:
        nonlocal modes, sunday_why
        act, why = rule["then"], f"Raumregel: {rule_text(rule)}"
        if act == "aus":
            return Result("aus", None, "off", RULE_ROOM, why)
        if act == "urlaub":
            return Result("urlaub", modes.away_temp, "heat", RULE_ROOM, why)
        if act in PLAN_LEVELS:
            return Result(act, level_temperature(room, act), "heat", RULE_ROOM, why)
        modes, sunday_why = replace(modes, sunday_all=True), why  # "sonntag": jeden Tag Sonntagsplan
        return None

    # Eine Raumregel, die sich ausdrücklich auf den Urlaub bezieht, geht dem Urlaub vor ("im Urlaub hier aus").
    if rule and rule["if"]["mode"] == "vacation" and (res := apply_rule()):
        return res

    if modes.away:
        return Result("urlaub", modes.away_temp, "heat", RULE_AWAY, modes.vacation_label or "Urlaub unterwegs")

    if manual is not None and manual.until > now:
        return _manual_result(manual)

    if override is not None and override.active(now):
        name = TODAY_KINDS.get(override.kind, override.kind)
        if override.kind == "stufe" and override.level in PLAN_LEVELS:
            lvl = override.level
            return Result(lvl, level_temperature(room, lvl), "heat", RULE_TODAY, f"Ausnahme: {today_label(override)}", until=override.until)
        if override.kind in ("party", "komfort"):
            return Result("komfort", level_temperature(room, "komfort"), "heat", RULE_TODAY, f"Heute anders: {name}", until=override.until)
        if override.kind == "leer":
            # niemand im Raum: Absenkung – aber nie wärmer als der Plan (z. B. nachts)
            plan_lvl = _plan_at(room, now, today or now.date(), modes)
            lvl = plan_lvl if level_temperature(room, plan_lvl) < level_temperature(room, "absenkung") else "absenkung"
            return Result(lvl, level_temperature(room, lvl), "heat", RULE_TODAY, f"Heute anders: {name}", until=override.until)
        if override.kind in FORCE_KINDS:
            modes = replace(modes, force_dtype=FORCE_KINDS[override.kind], force_until=override.until)
            sunday_why = f"Heute anders: {name}"

    if room.get("party_room") and modes.party_until and now < modes.party_until:
        return Result("komfort", level_temperature(room, "komfort"), "heat", RULE_PARTY, "Ereignis Party (Party-Raum)", until=modes.party_until)

    if rule and rule["if"]["mode"] != "vacation" and (res := apply_rule()):
        return res

    today = today or now.date()
    special = _special(now.date(), today, modes)
    holiday = special is not None or bool(modes.force_dtype)
    dtype = _dtype(now.date(), today, modes)
    level = plan_level(room, dtype, now.hour * 60 + now.minute)
    until, nxt = next_plan_change(room, now, modes) if with_until else (None, None)
    if modes.force_dtype and modes.force_until and (until is None or until > modes.force_until):
        until, nxt = modes.force_until, None
    if holiday:
        why = sunday_why or (("Urlaub zu Hause" if special == "vac" else "Feiertag") + " → " + PLAN_NAMES[dtype])
        rule_id = RULE_ROOM if sunday_why and sunday_why.startswith("Raumregel") else RULE_TODAY if sunday_why else RULE_HOLIDAY
    else:
        why, rule_id = "Wochenplan", RULE_PLAN
    return Result(level, level_temperature(room, level), "heat", rule_id, why, until=until, next_level=nxt)


def week_preview(
    room: dict[str, Any],
    modes: Modes,
    now: datetime,
    manual: Manual | None = None,
    cooling: bool = False,
    override: Today | None = None,
) -> list[dict[str, Any]]:
    """Ergebnis aller Regeln für die aktuelle Woche (Mo–So) in 30-Minuten-Schritten."""
    monday = now.date() - timedelta(days=now.weekday())
    days = []
    for i in range(7):
        day = monday + timedelta(days=i)
        slots = []
        for s in range(48):
            t = datetime.combine(day, time(s // 2, 15 if s % 2 == 0 else 45), tzinfo=now.tzinfo)
            # Hand-Änderung, "Heute anders" und Party nur ab jetzt anzeigen (davor galt noch der Plan)
            later = t >= now
            use_manual = manual if (day == now.date() and later) else None
            use_override = override if later else None
            m = modes if later else replace(modes, party_until=None)
            if cooling:
                r = evaluate_cooling(room, m, t, use_manual, with_until=False, today=now.date(), override=use_override)
            else:
                r = evaluate(room, m, t, use_manual, with_until=False, today=now.date(), override=use_override)
            slots.append(r.level)
        days.append(
            {
                "date": day.isoformat(),
                "day_type": _dtype(day, now.date(), modes),
                "today": day == now.date(),
                "slots": slots,
            }
        )
    return days


# ---------------------------------------------------------------------------
# Klimaanlage als zweite Wärmequelle: Gas-Heizkörper oder Klima – was ist billiger?

SOURCE_RADIATOR = "radiator"
SOURCE_AC = "ac"
AC_MODES = ("auto", "radiator", "ac")  # automatisch / immer Heizkörper / Klima bevorzugt
DEFAULT_COP_POINTS = [[-7.0, 2.6], [2.0, 3.4], [7.0, 4.3]]  # typische Split-Klimaanlage, bitte Datenblatt eintragen


@dataclass
class Prices:
    gas_ct: float = 12.0  # ct pro kWh Gas (Brennwert)
    boiler_efficiency: float = 0.9  # 0..1
    power_ct: float = 35.0  # ct pro kWh Strom

    @property
    def heat_cost_gas(self) -> float:
        """ct pro kWh Wärme aus dem Gaskessel."""
        return self.gas_ct / max(self.boiler_efficiency, 0.1)

    @property
    def break_even_cop(self) -> float:
        """Ab diesem COP ist Wärme aus der Klimaanlage billiger als aus Gas."""
        return self.power_ct / max(self.heat_cost_gas, 0.01)


def normalize_cop_points(points: Any) -> list[list[float]]:
    out = []
    for p in points or []:
        t, cop = float(p[0]), float(p[1])
        if not -30 <= t <= 30:
            raise ValueError(f"Außentemperatur {t} °C liegt außerhalb −30…30 °C")
        if not 0.5 <= cop <= 10:
            raise ValueError(f"COP {cop} ist unplausibel (0,5…10)")
        out.append([t, cop])
    out.sort(key=lambda p: p[0])
    if len(out) < 2:
        raise ValueError("Mindestens zwei COP-Werte nötig (z. B. bei −7 °C und +7 °C)")
    if len({p[0] for p in out}) != len(out):
        raise ValueError("Jede Außentemperatur nur einmal angeben")
    return out


def cop_at(points: list[list[float]], outdoor: float) -> float:
    """COP bei Außentemperatur – linear zwischen den Datenblatt-Punkten, außen fortgeführt."""
    pts = sorted(points, key=lambda p: p[0])
    if outdoor <= pts[0][0]:
        a, b = pts[0], pts[1]
    elif outdoor >= pts[-1][0]:
        a, b = pts[-2], pts[-1]
    else:
        a, b = next((p, q) for p, q in zip(pts, pts[1:]) if p[0] <= outdoor <= q[0])
    cop = a[1] + (b[1] - a[1]) * (outdoor - a[0]) / (b[0] - a[0])
    return max(cop, 0.5)


def ac_threshold(points: list[list[float]], break_even: float) -> float | None:
    """Außentemperatur, ab der die Klimaanlage billiger heizt. None = nie (bzw. im Bereich −30…30 °C nicht)."""
    lo, hi = -30.0, 30.0
    if cop_at(points, hi) < break_even:
        return None
    if cop_at(points, lo) >= break_even:
        return lo
    for _ in range(40):  # COP steigt mit der Außentemperatur → Bisektion
        mid = (lo + hi) / 2
        if cop_at(points, mid) >= break_even:
            hi = mid
        else:
            lo = mid
    return round(hi, 1)


def _de(v: float) -> str:
    return f"{v:.1f}".replace(".", ",").replace("-", "−")


def choose_source(
    mode: str,
    outdoor: float | None,
    threshold: float | None,
    previous: str | None,
    hysteresis: float = 1.0,
    min_outdoor: float | None = None,
) -> tuple[str, str]:
    """Wärmequelle wählen. Rückgabe: (Quelle, Begründung)."""
    if mode == "radiator":
        return SOURCE_RADIATOR, "Heizkörper (fest eingestellt)"
    if outdoor is None:
        return SOURCE_RADIATOR, "keine Außentemperatur – Heizkörper"
    if min_outdoor is not None and outdoor < min_outdoor:
        return SOURCE_RADIATOR, f"draußen {_de(outdoor)} °C – unter Einsatzgrenze der Klimaanlage"
    if mode == "ac":
        return SOURCE_AC, f"Klima bevorzugt (draußen {_de(outdoor)} °C)"
    if threshold is None:
        return SOURCE_RADIATOR, "Gas ist bei jeder Außentemperatur billiger"
    half = hysteresis / 2
    if previous == SOURCE_AC:
        use_ac = outdoor >= threshold - half
    elif previous == SOURCE_RADIATOR:
        use_ac = outdoor > threshold + half
    else:
        use_ac = outdoor >= threshold
    if use_ac:
        return SOURCE_AC, f"Klima billiger (draußen {_de(outdoor)} °C, Schwelle {_de(threshold)} °C)"
    return SOURCE_RADIATOR, f"Gas billiger (draußen {_de(outdoor)} °C, Schwelle {_de(threshold)} °C)"


# ---------------------------------------------------------------------------
# Kühlen mit Klimaanlage (Jahreszeit mit Kühlen, z. B. "Heißphase")

DEFAULT_COOLING = {"enabled": True, "temp": 25.0, "other": None, "precool": None}  # precool: ["11:00", "14:00", 24.0]


def cooling_config(room: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_COOLING, **((room.get("ac") or {}).get("cooling") or {})}


def normalize_cooling(cfg: Any) -> dict[str, Any]:
    c = {**DEFAULT_COOLING, **(cfg or {})}
    temp = float(c["temp"])
    if not 16 <= temp <= 30:
        raise ValueError(f"Kühlen auf {temp:g} °C liegt außerhalb 16…30 °C")
    other = None if c.get("other") in (None, "") else float(c["other"])
    if other is not None and not 16 <= other <= 32:
        raise ValueError(f"Kühlen außerhalb der Komfortzeiten: {other:g} °C liegt außerhalb 16…32 °C")
    pre = c.get("precool")
    if pre:
        s_min, e_min = parse_hm(pre[0]), parse_hm(pre[1])
        if e_min <= s_min:
            raise ValueError("Vorkühlen: Ende muss nach dem Beginn liegen")
        pt = float(pre[2])
        if not 16 <= pt <= 30:
            raise ValueError(f"Vorkühlen auf {pt:g} °C liegt außerhalb 16…30 °C")
        pre = [fmt_hm(s_min), fmt_hm(e_min), pt]
    return {"enabled": bool(c.get("enabled", True)), "temp": temp, "other": other, "precool": pre or None}


def _cool_level(room: dict[str, Any], modes: Modes, when: datetime, today: date) -> tuple[str, float | None, str, str]:
    cfg = cooling_config(room)
    holiday = _holiday_for(when.date(), today, modes)
    plan = plan_level(room, _dtype(when.date(), today, modes), when.hour * 60 + when.minute)
    rule = RULE_HOLIDAY if holiday else RULE_PLAN
    minute = when.hour * 60 + when.minute
    if plan in COOL_USE:
        return "kuehlen", cfg["temp"], rule, f"{LEVEL_NAMES[plan]} im Plan → kühlen"
    pre = cfg.get("precool")
    if pre and parse_hm(pre[0]) <= minute < parse_hm(pre[1]):
        return "vorkuehlen", float(pre[2]), rule, f"Vorkühlen {pre[0]}–{pre[1]}"
    if cfg.get("other") is not None:
        return "kuehlen", float(cfg["other"]), rule, "außerhalb der Komfortzeiten nur Hitzeschutz"
    return "aus", None, rule, f"{LEVEL_NAMES[plan]} im Plan → Klima aus"


def evaluate_cooling(
    room: dict[str, Any],
    modes: Modes,
    now: datetime,
    manual: Manual | None = None,
    with_until: bool = True,
    today: date | None = None,
    override: Today | None = None,
) -> Result:
    """Kühlen in der Kühl-Jahreszeit. Erste zutreffende Regel gewinnt."""
    cfg = cooling_config(room)
    if not modes.cooling_season or not cfg["enabled"]:
        return Result("aus", None, "off", RULE_SEASON, f"Jahreszeit {modes.season} – kein Kühlen")
    rule = matching_rule(room, modes)

    def apply_rule() -> Result | None:
        nonlocal modes
        why = f"Raumregel: {rule_text(rule)}"
        if rule["then"] in COOL_USE:
            return Result("kuehlen", cfg["temp"], "cool", RULE_ROOM, why)
        if rule["then"] == "sonntag":
            modes = replace(modes, sunday_all=True)
            return None
        return Result("aus", None, "off", RULE_ROOM, why)

    if rule and rule["if"]["mode"] == "vacation" and (res := apply_rule()):
        return res
    if modes.away:
        return Result("aus", None, "off", RULE_AWAY, modes.vacation_label or "Urlaub unterwegs")
    if modes.nobody_home:
        return Result("aus", None, "off", RULE_ABSENT, "niemand zu Hause")
    if manual is not None and manual.until > now:
        return _manual_result(manual)
    if override is not None and override.active(now):
        name = TODAY_KINDS.get(override.kind, override.kind)
        if override.kind == "stufe":
            why = f"Ausnahme: {today_label(override)}"
            if override.level in COOL_USE:
                return Result("kuehlen", cfg["temp"], "cool", RULE_TODAY, why, until=override.until)
            return Result("aus", None, "off", RULE_TODAY, why, until=override.until)
        if override.kind in ("party", "komfort"):
            return Result("kuehlen", cfg["temp"], "cool", RULE_TODAY, f"Heute anders: {name}", until=override.until)
        if override.kind == "leer":
            return Result("aus", None, "off", RULE_TODAY, f"Heute anders: {name}", until=override.until)
        if override.kind in FORCE_KINDS:
            modes = replace(modes, force_dtype=FORCE_KINDS[override.kind], force_until=override.until)
    if room.get("party_room") and modes.party_until and now < modes.party_until:
        return Result("kuehlen", cfg["temp"], "cool", RULE_PARTY, "Ereignis Party (Party-Raum)", until=modes.party_until)
    if rule and rule["if"]["mode"] != "vacation" and (res := apply_rule()):
        return res
    today = today or now.date()
    level, temp, rule, why = _cool_level(room, modes, now, today)
    until = nxt = None
    if with_until:
        t = now.replace(second=0, microsecond=0)
        t = t + timedelta(minutes=15 - t.minute % 15)
        for _ in range(4 * 48):
            lvl, tmp, _r, _w = _cool_level(room, modes, t, today)
            if (lvl, tmp) != (level, temp):
                until, nxt = t, lvl
                break
            t += timedelta(minutes=15)
    return Result(level, temp, "cool" if temp is not None else "off", rule, why, until=until, next_level=nxt)


# ---------------------------------------------------------------------------
# Stufen konfigurierbar: Namen ändern, eigene Stufen einschalten, "Raum genutzt" (für das Kühlen)

DEFAULT_LEVEL_DEFS = {
    "komfort": {"name": "Komfort", "temp": 21.0, "use": True, "enabled": True},
    "absenkung": {"name": "Absenkung", "temp": 18.0, "use": False, "enabled": True},
    "nacht": {"name": "Nacht", "temp": 17.0, "use": False, "enabled": True},
    "bad": {"name": "Booster", "temp": 23.0, "use": True, "enabled": True},
    "extra1": {"name": "Stufe 5", "temp": 20.0, "use": True, "enabled": False},
    "extra2": {"name": "Stufe 6", "temp": 20.0, "use": True, "enabled": False},
    "extra3": {"name": "Stufe 7", "temp": 20.0, "use": True, "enabled": False},
    "extra4": {"name": "Stufe 8", "temp": 20.0, "use": True, "enabled": False},
}


def normalize_level_defs(defs: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    names: set[str] = set()
    for key in PLAN_LEVELS:
        d = {**DEFAULT_LEVEL_DEFS[key], **((defs or {}).get(key) or {})}
        name = str(d.get("name") or DEFAULT_LEVEL_DEFS[key]["name"]).strip()[:24]
        temp = float(d.get("temp", DEFAULT_LEVEL_DEFS[key]["temp"]))
        if not 5 <= temp <= 30:
            raise ValueError(f"{name}: {temp:g} °C liegt außerhalb 5…30 °C")
        enabled = True if key in BASE_LEVELS else bool(d.get("enabled"))
        if enabled and name.casefold() in names:
            raise ValueError(f"Der Name „{name}“ ist doppelt")
        if enabled:
            names.add(name.casefold())
        out[key] = {"name": name, "temp": temp, "use": bool(d.get("use")), "enabled": enabled}
    return out


def apply_level_defs(defs: dict[str, dict[str, Any]]) -> None:
    """Namen, Standardtemperaturen und "genutzt" global übernehmen."""
    for key, d in defs.items():
        LEVEL_NAMES[key] = d["name"]
        RULE_ACTIONS[key] = d["name"]
        DEFAULT_LEVEL_TEMPS[key] = d["temp"]
    COOL_USE.clear()
    COOL_USE.update(k for k, d in defs.items() if d["use"])
    ENABLED_LEVELS[:] = [k for k in PLAN_LEVELS if defs[k]["enabled"]]


def levels_in_use(room: dict[str, Any]) -> set[str]:
    used = {room.get("default_level", "absenkung")}
    for blocks in (room.get("schedule") or {}).values():
        used.update(b[2] for b in blocks)
    used.update(r["then"] for r in room.get("rules") or [] if r["then"] in PLAN_LEVELS)
    return used
