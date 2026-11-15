"""0.9.9: Zeitraum (Datum zwischen), bestimmte Tage, Taster – reine Logik."""
from datetime import date, timedelta

import pytest

from custom_components.home_rhythm import flows as F
from custom_components.home_rhythm import native as N

SUN = F.Sun(480, 990)


def ctx(d: date, **kw) -> F.Ctx:
    return F.Ctx(day=d, daytype=F.raw_daytype(d.weekday(), False, False), prev_daytype=F.raw_daytype((d.weekday() - 1) % 7, False, False), **kw)


def plan(simple=None, conds=None, **kw):
    simple = simple or {"rows": {"mf": {"like": "own", "open": {"ref": "sunset", "offset": -30}}, "sa": {"like": "mf"}, "so": {"like": "mf"}},
                        "close": {"ref": "time", "time": "23:00"}}
    return F.normalize_plan({"kind": "switch", "name": "Weihnachtsbeleuchtung", "devices": ["light.a"], "mode": "simple", "simple": simple,
                             "conds": conds or {"op": "and", "items": []}, **kw})


def events(p, d):
    return [(F.hm(m), x["action"]) for m, _i, x in F.day_events("x", p, d, SUN, ctx(d), ctx(d - timedelta(days=1)), check_plan=True)]


RANGE = {"op": "and", "items": [{"key": "date", "op": "is", "from": "28.11.", "to": "6.1."}]}


@pytest.mark.parametrize("raw,md", [("24.12.", "12-24"), ("24.12", "12-24"), ("12-24", "12-24"), ("1.1.", "01-01"), ("29.2.", "02-29")])
def test_parse_md(raw, md):
    assert F.parse_md(raw) == md


@pytest.mark.parametrize("raw", ["31.11.", "0.1.", "32.1.", "1.13.", "abc", "", "24.12.2026"])
def test_parse_md_bad(raw):
    with pytest.raises(ValueError):
        F.parse_md(raw)


def test_md_between_over_new_year():
    assert F.md_between("12-31", "11-28", "01-06")
    assert F.md_between("01-06", "11-28", "01-06")
    assert F.md_between("11-28", "11-28", "01-06")
    assert not F.md_between("01-07", "11-28", "01-06")
    assert not F.md_between("11-27", "11-28", "01-06")
    assert F.md_between("08-12", "08-12", "09-19") and not F.md_between("09-20", "08-12", "09-19")


def test_date_condition():
    c = F.normalize_cond({"key": "date", "op": "is", "from": "28.11.", "to": "6.1."})
    assert c == {"key": "date", "op": "is", "from": "11-28", "to": "01-06"}
    assert F.cond_true(c, ctx(date(2026, 12, 1)))
    assert not F.cond_true(c, ctx(date(2026, 11, 27)))
    assert not F.cond_true(c, F.Ctx())  # ohne Tag → nicht erfüllt
    assert F.cond_true({**c, "op": "not"}, ctx(date(2026, 7, 1)))
    assert F.cond_text(c) == "Datum zwischen 28.11. und 6.1."
    with pytest.raises(ValueError):
        F.normalize_cond({"key": "date", "op": "above", "from": "1.1.", "to": "2.1."})
    with pytest.raises(ValueError):
        F.normalize_cond({"key": "date", "op": "is", "from": "31.11.", "to": "2.1."})


def test_range_plan_runs_only_inside_and_after_midnight_counts_to_last_day():
    simple = {"rows": {"mf": {"like": "own", "open": {"ref": "sunset", "offset": -30}}, "sa": {"like": "mf"}, "so": {"like": "mf"}},
              "close": {"ref": "time", "time": "01:00"}}
    p = plan(simple, RANGE)
    assert events(p, date(2026, 11, 27)) == []
    assert events(p, date(2026, 11, 28)) == [("16:00", "on")]  # 01:00 gehört zum 27.11. → ruht
    assert events(p, date(2026, 11, 29)) == [("01:00", "off"), ("16:00", "on")]
    assert events(p, date(2027, 1, 7)) == [("01:00", "off")]  # aus um 01:00 nach dem letzten Tag läuft noch
    assert events(p, date(2027, 1, 8)) == []


def test_special_days():
    simple = {"rows": {"mf": {"like": "own", "open": {"ref": "sunset", "offset": -30}}, "sa": {"like": "mf"}, "so": {"like": "mf"}},
              "close": {"ref": "time", "time": "23:00"}, "guard": "23:30",
              "days": [{"date": "24.12.", "name": "Heiligabend", "open": {"ref": "time", "time": "15:00"}, "close": {"ref": "time", "time": "02:00"}},
                       {"date": "31.12.", "name": "Silvester", "open": {"ref": "normal"}, "close": {"ref": "time", "time": "03:00"}},
                       {"date": "1.1.", "open": {"ref": "none"}, "close": {"ref": "normal"}}]}
    p = plan(simple, RANGE)
    assert [d["date"] for d in p["simple"]["days"]] == ["01-01", "12-24", "12-31"]
    assert events(p, date(2026, 12, 23)) == [("16:00", "on"), ("23:00", "off"), ("23:30", "off")]
    assert events(p, date(2026, 12, 24)) == [("15:00", "on")]  # kein 23:00, keine Absicherung
    assert events(p, date(2026, 12, 25)) == [("02:00", "off"), ("16:00", "on"), ("23:00", "off"), ("23:30", "off")]
    assert events(p, date(2026, 12, 31)) == [("16:00", "on")]  # Einschalten wie sonst
    assert events(p, date(2027, 1, 1)) == [("03:00", "off"), ("23:00", "off"), ("23:30", "off")]  # nicht einschalten
    assert F.day_label(p, ctx(date(2026, 12, 24)), date(2026, 12, 24)) == "Heiligabend – bestimmter Tag"
    assert F.day_label(p, ctx(date(2027, 1, 1)), date(2027, 1, 1)) == "1.1. – bestimmter Tag"


def test_special_days_validation():
    base = {"rows": {"mf": {"like": "own", "open": {"ref": "time", "time": "07:00"}}}, "close": {"ref": "time", "time": "22:00"}}
    with pytest.raises(ValueError, match="doppelt"):
        plan({**base, "days": [{"date": "24.12."}, {"date": "12-24"}]})
    with pytest.raises(ValueError, match="gibt es nicht"):
        plan({**base, "days": [{"date": "30.2."}]})
    with pytest.raises(ValueError, match="Uhrzeit"):
        plan({**base, "days": [{"date": "24.12.", "open": {"ref": "time", "time": "25:00"}}]})
    with pytest.raises(ValueError):
        plan({**base, "days": [{"date": "1.1."}] * 31})
    p = plan({**base, "days": [{"date": "24.12.", "name": "x" * 99}]})
    assert len(p["simple"]["days"][0]["name"]) == 30


def test_old_plans_unchanged_and_no_except_without_special_days():
    p = plan()
    assert all("except" not in x for x in p["points"])
    assert events(p, date(2026, 12, 24)) == [("16:00", "on"), ("23:00", "off")]


def test_advanced_dates_point():
    p = F.normalize_plan({"kind": "switch", "name": "x", "devices": ["light.a"], "points": [
        {"days": "dates", "dates": "24.12., 31.12.", "ref": "time", "time": "18:00", "action": "on"},
        {"days": "dates", "dates": ["12-24"], "prev": True, "ref": "time", "time": "01:00", "action": "off"},
        {"days": "daily", "ref": "time", "time": "22:00", "action": "off", "except": ["24.12."]}]})
    assert p["points"][0]["dates"] == ["12-24", "12-31"]
    assert events(p, date(2026, 12, 24)) == [("18:00", "on")]
    assert events(p, date(2026, 12, 25)) == [("01:00", "off"), ("22:00", "off")]
    assert "24.12., 31.12." in F.point_text(p["points"][0])
    assert "außer 24.12." in F.point_text(p["points"][2])
    with pytest.raises(ValueError):
        F.normalize_plan({"kind": "switch", "name": "x", "devices": ["light.a"], "points": [{"days": "dates", "dates": "", "ref": "time", "time": "18:00", "action": "on"}]})


def test_button_normalize():
    assert plan()["button"] is None and plan()["switch"] is False
    b = plan(button={"device_id": "abc123", "map": {"event:event.taster:single": "toggle", "event:event.taster:double": ""}, "auto_off": 120, "scope": "active"}, switch=True)
    assert b["button"] == {"device_id": "abc123", "map": {"event:event.taster:single": "toggle"}, "auto_off": 120, "scope": "active"}
    assert b["switch"] is True
    assert plan(button={"device_id": "abc", "auto_off": 99999, "scope": "?"})["button"]["auto_off"] == F.MAX_AUTO_OFF
    for bad in ({"device_id": "a b"}, {"device_id": "x", "map": {"event:event.t:1": "explode"}}, {"device_id": "x", "map": {"evil": "on"}},
                {"device_id": "x", "map": {"event:event.t:1": "on", "event:event.t:2": "on"}}):
        with pytest.raises(ValueError):
            plan(button=bad)


def test_native_templates():
    opts = {}
    c = N._cond({"key": "date", "op": "is", "from": "11-28", "to": "01-06"}, opts)
    assert c["condition"] == "template" and "k >= 1128 or k <= 106" in c["value_template"]
    c2 = N._cond({"key": "date", "op": "not", "from": "08-12", "to": "09-19"}, opts)
    assert c2["condition"] == "not" and "812 <= k <= 919" in c2["conditions"][0]["value_template"]
    p = {"days": "dates", "dates": ["12-24"], "prev": True}
    t = N._days_cond(p, opts)["value_template"]
    assert "timedelta(days=1)" in t and "'12-24'" in t
    p2 = {"days": "daily", "except": ["12-24", "12-31"]}
    assert N._days_cond(p2, opts)["condition"] == "not"
