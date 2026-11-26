"""0.9.17: Funk-Zuverlässigkeit je Thermostat (Zählung, gelbes ⚠, Lücken aus 0.9.16 geschlossen).

Das Thermostat ist nur ein Zustand in Home Assistant; `climate.set_temperature` tut – wie ein schlecht
erreichbares Zigbee-Gerät – nichts. „Übernommen“ wird durch Setzen des Zustands nachgebildet.
"""
from datetime import timedelta

import pytest
from homeassistant.core import Context
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN, STARTUP_GRACE_SECONDS, STUCK_SECONDS
from custom_components.home_rhythm.radio import RadioLog

SCHED = {"wd": [["00:00", "24:00", "nacht"]], "sa": [["00:00", "24:00", "nacht"]], "so": [["00:00", "24:00", "nacht"]]}
EID = "climate.heizung_wohnzimmer"
ATTRS = {"current_temperature": 20.7, "hvac_action": "heating", "hvac_modes": ["off", "heat", "auto"], "target_temp_step": 0.5,
         "min_temp": 5, "max_temp": 30}


@pytest.fixture
async def setup(hass, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    calls = []

    async def ignore(call):
        calls.append(call)

    for svc in ("set_temperature", "set_hvac_mode", "set_preset_mode"):
        hass.services.async_register("climate", svc, ignore)
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Wohnzimmer")
    er.async_get(hass).async_get_or_create("climate", "test", "wz", suggested_object_id="heizung_wohnzimmer")
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 21})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    await ctrl.async_save_room({"name": "Wohnzimmer", "area_id": area.id, "climate_entities": [EID], "schedule": SCHED})
    await hass.async_block_till_done()
    ctrl._started_at = dt_util.utcnow() - timedelta(seconds=STARTUP_GRACE_SECONDS + 1)  # Startphase vorbei
    rid = next(iter(ctrl.rooms))
    return ctrl, rid, calls


def _radio(ctrl, rid):
    room = next(r for r in ctrl.snapshot()["rooms"] if r["id"] == rid)
    return room["climates"][0]["radio"]


async def _take(hass, ctrl, temp):
    """Gerät meldet den gesendeten Wert (mit unserem Kontext, wie ein Echo)."""
    ctx = next(iter(ctrl._own_contexts))
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": temp}, context=Context(id=ctx))
    await hass.async_block_till_done()


async def test_taken_quickly_counts_ok(hass, setup, freezer):
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=20))
    await _take(hass, ctrl, 17.0)
    freezer.tick(timedelta(seconds=40))
    await ctrl.async_update(apply=True)
    r = _radio(ctrl, rid)
    assert (r["cmd_ok"], r["cmd_total"], r["level"]) == (1, 1, "")
    assert r["delay_max"] <= 25 and r["events"] == []
    assert len(r["days"]) == 7 and r["days"][-1]["share"] == 100


async def test_taken_late_is_yellow(hass, setup, freezer):
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 60))
    await ctrl.async_update(apply=True)
    assert _radio(ctrl, rid)["level"] == "r"  # hängt gerade → rot (wie 0.9.16)
    await _take(hass, ctrl, 17.0)
    await ctrl.async_update(apply=True)
    r = _radio(ctrl, rid)
    assert r["level"] == "y" and (r["cmd_ok"], r["cmd_total"]) == (0, 1)
    assert "nicht rechtzeitig" in r["why"][0] and r["delay_max"] >= STUCK_SECONDS
    assert r["events"][0]["k"] == "late" and r["events"][0]["want"] == "17,0 °C"
    assert next(x for x in ctrl.rooms_light() if x["id"] == rid)["radio_warn"] is True


async def test_hanging_is_red_and_counted(hass, setup, freezer):
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 5))
    await ctrl.async_update(apply=True)
    r = _radio(ctrl, rid)
    assert r["level"] == "r" and r["cmd_total"] == 1 and r["cmd_ok"] == 0
    assert r["events"][0]["k"] == "hang" and r["events"][0]["e"] is None
    assert r["days"][-1]["share"] == 0  # zählt heute schon als nicht angekommen


async def test_offline_three_times_yellow_not_in_startup(hass, setup, freezer):
    ctrl, rid, _ = setup
    ctrl._started_at = dt_util.utcnow()  # Startphase: zählt nicht
    hass.states.async_set(EID, "unavailable", {})
    await hass.async_block_till_done()
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 17.0})
    await hass.async_block_till_done()
    assert _radio(ctrl, rid)["off_count"] == 0
    ctrl._started_at = dt_util.utcnow() - timedelta(seconds=STARTUP_GRACE_SECONDS + 1)
    for _ in range(3):
        hass.states.async_set(EID, "unavailable", {})
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=4))
        hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 17.0})
        await hass.async_block_till_done()
    r = _radio(ctrl, rid)
    assert r["off_count"] == 3 and r["off_seconds"] == 720 and r["level"] == "y"
    assert [e["k"] for e in r["events"]].count("off") == 3


async def test_offline_keeps_incident(hass, setup, freezer):
    """Lücke aus 0.9.16: kurz „nicht erreichbar“ setzte die Zählung zurück – jetzt bleibt es derselbe Vorfall."""
    ctrl, rid, calls = setup
    await ctrl.async_update(apply=True)
    since = ctrl._last_sent[f"{rid}|{EID}"]["since"]
    freezer.tick(timedelta(minutes=3))
    hass.states.async_set(EID, "unavailable", {})
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 21})
    await hass.async_block_till_done()
    n = len(calls)
    await ctrl.async_update(apply=True)
    assert len(calls) > n  # sofort erneut gesendet
    last = ctrl._last_sent[f"{rid}|{EID}"]
    assert last["since"] == since and last["tries"] == 2
    freezer.tick(timedelta(minutes=2))
    await ctrl.async_update(apply=True)
    assert ctrl.stuck_info(rid, EID) is not None  # nach insgesamt > 5 Min. rot
    assert ctrl.manual.get(rid) is None


async def test_late_own_value_is_not_hand_change(hass, setup, freezer):
    """Lücke aus 0.9.16: ein überholter eigener Befehl kommt verspätet an → keine Hand-Änderung."""
    ctrl, rid, _ = setup
    room = dict(ctrl.rooms[rid])
    two = [["00:00", "23:00", "nacht"], ["23:00", "24:00", "absenkung"]]
    room["schedule"] = {"wd": two, "sa": two, "so": two}
    await ctrl.async_save_room(room)
    await hass.async_block_till_done()
    freezer.move_to(dt_util.now().replace(hour=22, minute=58, second=0))
    await ctrl.async_update(apply=True)  # 17 °C gesendet, Gerät reagiert nicht
    freezer.tick(timedelta(minutes=3))
    await ctrl.async_update(apply=True)  # 23:01 – 18 °C gesendet
    assert ctrl._last_sent[f"{rid}|{EID}"]["want"]["temp"] == 18.0
    freezer.tick(timedelta(minutes=20))
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 17.0})  # alter Befehl kommt spät an, ohne Kontext
    await hass.async_block_till_done()
    assert ctrl.manual.get(rid) is None
    assert any(e["k"] == "old" for e in _radio(ctrl, rid)["events"])


async def test_real_hand_change_still_hand_change(hass, setup, freezer):
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 5))
    await ctrl.async_update(apply=True)
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 19.5})  # nie gesendeter Wert → am Gerät gedreht
    await hass.async_block_till_done()
    assert ctrl.manual.get(rid) is not None
    r = _radio(ctrl, rid)
    assert r["cmd_total"] == 1 and r["cmd_ok"] == 0 and r["events"][0]["k"] == "lost"


async def test_reset_and_persist(hass, setup, freezer):
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 60))
    await _take(hass, ctrl, 17.0)
    await ctrl.async_update(apply=True)
    assert _radio(ctrl, rid)["level"] == "y"
    dumped = ctrl.radio.dump()
    other = RadioLog()
    other.load(dumped)
    assert other.summary(EID, dt_util.utcnow(), STUCK_SECONDS)["cmd_total"] == 1  # übersteht einen Neustart
    freezer.tick(timedelta(hours=1))
    await ctrl.async_radio_reset(True)
    r = _radio(ctrl, rid)
    assert r["cmd_total"] == 0 and r["level"] == "" and ctrl.snapshot()["radio_reset"]
    await ctrl.async_radio_reset(False)
    assert _radio(ctrl, rid)["cmd_total"] == 1 and ctrl.snapshot()["radio_reset"] is None


def test_room_value_counting():
    log, t0 = RadioLog(), dt_util.utcnow()
    for i in range(6):  # 6 Raumwerte, 4 kommen an
        log.rv_sent("climate.x", "number.x", 20.0 + i / 10, t0 + timedelta(minutes=10 * i))
        if i < 4:
            log.rv_check("climate.x", 20.0 + i / 10, t0 + timedelta(minutes=10 * i, seconds=30))
        else:
            log.rv_check("climate.x", 19.0, t0 + timedelta(minutes=10 * i + 6))
    s = log.summary("climate.x", t0 + timedelta(hours=1), STUCK_SECONDS)
    assert (s["rv_ok"], s["rv_total"]) == (4, 6) and s["level"] == "y" and "67 %" in s["why"][0]
    assert [e["k"] for e in s["events"]] == ["rv"] and s["events"][0]["n"] == 2  # zusammengefasst
    log.prune(t0 + timedelta(days=9))
    assert log.summary("climate.x", t0 + timedelta(days=9), STUCK_SECONDS)["rv_total"] == 0
