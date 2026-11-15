"""0.9.9: Taster je Zeitplan, HA-Schalter, Hand-Bedienung mit „nach X wieder aus“ – in Home Assistant."""
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.home_rhythm.const import DOMAIN

SIG = "event:event.taster_flur_action:single"


@pytest.fixture
async def setup(hass: HomeAssistant, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"lampe1": {}, "lampe2": {}}})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    # Taster als Gerät mit Ereignis-Entität
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "taster")}, name="Taster Flur")
    er.async_get(hass).async_get_or_create("event", "test", "taster1", suggested_object_id="taster_flur_action", device_id=dev.id)
    hass.states.async_set("event.taster_flur_action", "unknown", {"event_type": None})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    return ctrl, dev.id


async def press(hass, n):
    hass.states.async_set("event.taster_flur_action", f"2026-11-14T18:00:0{n}+00:00", {"event_type": "single"})
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def save(ctrl, dev_id, **kw):
    flow = {"type": "plan", "kind": "switch", "name": "Weihnachtsbeleuchtung", "devices": ["input_boolean.lampe1", "input_boolean.lampe2"], "mode": "simple",
            "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "time", "time": "16:00"}}, "sa": {"like": "mf"}, "so": {"like": "mf"}, "hol": {"like": "mf"}}, "close": {"ref": "time", "time": "23:00"}},
            "button": {"device_id": dev_id, "map": {SIG: "toggle"}, **kw.pop("button", {})}, **kw}
    return await ctrl.runner.async_save_flow(flow, sync=False)


async def test_button_toggles_all_together(hass, setup):
    ctrl, dev_id = setup
    fid = await save(ctrl, dev_id)
    hass.states.async_set("input_boolean.lampe1", "on")  # gemischt: eins an
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.lampe1"}, blocking=True)
    await press(hass, 1)
    assert hass.states.get("input_boolean.lampe1").state == "off"
    assert hass.states.get("input_boolean.lampe2").state == "off"
    assert ctrl.runner.hand[fid]["action"] == "off"
    await press(hass, 2)
    assert hass.states.get("input_boolean.lampe1").state == "on"
    assert hass.states.get("input_boolean.lampe2").state == "on"
    assert "Taster Flur" in ctrl.runner.hand[fid]["src"]


async def test_auto_off(hass, setup, freezer):
    ctrl, dev_id = setup
    freezer.move_to(dt_util.now().replace(hour=10, minute=0))  # nächster Schaltpunkt 16:00 → „nach 1 Std.“ gilt
    fid = await save(ctrl, dev_id, button={"auto_off": 60})
    await press(hass, 1)
    assert hass.states.get("input_boolean.lampe2").state == "on"
    assert ctrl.runner.hand[fid]["auto"] is True
    freezer.tick(timedelta(minutes=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("input_boolean.lampe2").state == "off"
    assert fid not in ctrl.runner.hand
    assert "nach 1 Std. wieder aus" in ctrl.runner.logs[fid][-1]["text"]


async def test_auto_off_not_when_plan_switches_earlier(hass, setup, freezer):
    ctrl, dev_id = setup
    freezer.move_to(dt_util.now().replace(hour=15, minute=30))  # Plan schaltet um 16:00 → kein eigener Timer
    fid = await save(ctrl, dev_id, button={"auto_off": 60})
    await press(hass, 1)
    assert ctrl.runner.hand[fid]["auto"] is False
    assert ctrl.runner.hand[fid]["until"].startswith(dt_util.now().date().isoformat() + "T16:00")


async def test_point_clears_hand(hass, setup, freezer):
    ctrl, dev_id = setup
    freezer.move_to(dt_util.now().replace(hour=15, minute=58, second=30))
    fid = await save(ctrl, dev_id, button={"auto_off": 120})
    await press(hass, 1)  # an
    await press(hass, 2)  # aus
    assert hass.states.get("input_boolean.lampe1").state == "off"
    assert fid in ctrl.runner.hand
    freezer.tick(timedelta(seconds=90))
    # HA-Zeitgeber laufen nach der echten Uhr – Minutenschritt direkt auslösen
    await ctrl.runner._run_minute(dt_util.now().replace(second=0, microsecond=0))  # noqa: SLF001
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("input_boolean.lampe1").state == "on"  # 16:00 laut Plan
    assert fid not in ctrl.runner.hand


async def test_scope_active_blocks_outside_range(hass, setup):
    ctrl, dev_id = setup
    today = dt_util.now().date()
    far = today + timedelta(days=60)
    rng = {"op": "and", "items": [{"key": "date", "op": "is", "from": far.strftime("%m-%d"), "to": far.strftime("%m-%d")}]}
    fid = await save(ctrl, dev_id, button={"scope": "active"}, conds=rng)
    await press(hass, 1)
    assert hass.states.get("input_boolean.lampe1").state == "off"
    assert "gilt gerade nicht" in ctrl.runner.logs[fid][-1]["text"]
    # „immer“: schaltet trotzdem
    await save(ctrl, dev_id, id=fid, button={"scope": "always"}, conds=rng)
    await press(hass, 2)
    assert hass.states.get("input_boolean.lampe1").state == "on"


async def test_ha_switch_entity(hass, setup):
    ctrl, dev_id = setup
    fid = await save(ctrl, dev_id, switch=True)
    await hass.async_block_till_done()
    eid = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{ctrl.entry.entry_id}_flow_{fid}")
    assert eid == "switch.home_rhythm_weihnachtsbeleuchtung"
    assert hass.states.get(eid).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.lampe1").state == "on"
    assert hass.states.get(eid).state == "on"
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": ["input_boolean.lampe1", "input_boolean.lampe2"]}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"
    # Häkchen weg → Entität verschwindet
    await save(ctrl, dev_id, id=fid, switch=False)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(eid) is None


async def test_detect_any_button(hass, setup):
    ctrl, dev_id = setup
    ctrl.controls.learn_start("*")
    assert "event.taster_flur_action" in ctrl.controls._watch_map  # noqa: SLF001
    await press(hass, 3)
    res = ctrl.controls.learn_result("*")
    assert res["state"] == "done" and res["device_id"] == dev_id and res["signature"] == SIG and res["name"] == "Taster Flur"


async def test_hand_survives_storage(hass, setup):
    ctrl, dev_id = setup
    fid = await save(ctrl, dev_id)
    await press(hass, 1)
    data = ctrl.runner.storage_data()["flows"]
    assert fid in data["hand"]


async def test_after_midnight_on_last_day_runs(hass, setup, freezer):
    ctrl, dev_id = setup
    freezer.move_to(dt_util.now().replace(hour=0, minute=59, second=30))
    yesterday = dt_util.now().date() - timedelta(days=1)
    rng = {"op": "and", "items": [{"key": "date", "op": "is", "from": "01-01", "to": yesterday.strftime("%m-%d")}]}
    flow = {"type": "plan", "kind": "switch", "name": "Lichterkette", "devices": ["input_boolean.lampe1"], "mode": "simple", "conds": rng,
            "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "time", "time": "16:00"}}, "sa": {"like": "mf"}, "so": {"like": "mf"}, "hol": {"like": "mf"}},
                       "close": {"ref": "time", "time": "01:00"}}}
    await ctrl.runner.async_save_flow(flow, sync=False)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.lampe1"}, blocking=True)
    # Zeitgeber von HA laufen nach der echten Uhr – die Minute 01:00 daher direkt ausführen
    await ctrl.runner._run_minute(dt_util.now().replace(hour=1, minute=0, second=0, microsecond=0))  # noqa: SLF001
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.lampe1").state == "off"  # gehört zum letzten Tag des Zeitraums


async def test_snapshot_preview_timeline(hass, setup):
    ctrl, dev_id = setup
    flow = {"type": "plan", "kind": "switch", "name": "Weihnachten", "devices": ["input_boolean.lampe1"], "mode": "simple", "switch": True,
            "conds": {"op": "and", "items": [{"key": "date", "op": "is", "from": "11-01", "to": "01-06"}]},
            "button": {"device_id": dev_id, "map": {SIG: "toggle"}},
            "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "sunset", "offset": -30}}}, "close": {"ref": "time", "time": "23:00"},
                       "days": [{"date": "24.12.", "name": "Heiligabend", "open": {"ref": "time", "time": "15:00"}, "close": {"ref": "time", "time": "02:00"}}]}}
    prev = ctrl.runner.preview(flow)
    assert len(prev["week"]) == 7 and len(prev["week_marks"]) == 7
    fid = await ctrl.runner.async_save_flow(flow, sync=False)
    snap = ctrl.runner.snapshot()
    item = next(i for i in snap["items"] if i["id"] == fid)
    assert item["button"]["device_id"] == dev_id and item["switch"] is True and "hand" in item
    assert snap["meta"]["date_ops"]["is"] == "zwischen"
    ctrl.runner.timeline(dt_util.now().date().replace(month=12, day=24))


async def test_preview_other_week(hass, setup):
    ctrl, _dev = setup
    flow = {"type": "plan", "kind": "switch", "name": "Weihnachten", "devices": ["input_boolean.lampe1"], "mode": "simple",
            "conds": {"op": "and", "items": [{"key": "date", "op": "is", "from": "11-28", "to": "01-06"}]},
            "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "time", "time": "16:00"}}, "sa": {"like": "mf"}, "so": {"like": "mf"}, "hol": {"like": "mf"}},
                       "close": {"ref": "time", "time": "23:00"},
                       "days": [{"date": "12-24", "name": "Heiligabend", "open": {"ref": "time", "time": "15:00"}, "close": {"ref": "time", "time": "02:00"}}]}}
    year = dt_util.now().year
    p = ctrl.runner.preview({**flow, "week": f"{year}-12-24"})
    assert f"{year}-12-24" in p["dates"]
    i = p["dates"].index(f"{year}-12-24")
    assert p["day_labels"][i] == "Heiligabend – bestimmter Tag"
    assert [m["m"] for m in p["week_marks"][i]] == [15 * 60]
    # Unsinn / zu weit weg → aktuelle Woche
    for bad in ("2099-01-01", "kaputt", 5):
        assert dt_util.now().date().isoformat() in ctrl.runner.preview({**flow, "week": bad})["dates"]


async def test_hand_until_only_when_plan_runs(hass, setup):
    ctrl, dev_id = setup
    far = dt_util.now().date() + timedelta(days=60)
    rng = {"op": "and", "items": [{"key": "date", "op": "is", "from": far.strftime("%m-%d"), "to": far.strftime("%m-%d")}]}
    fid = await save(ctrl, dev_id, conds=rng)
    await ctrl.runner.async_switch_all(fid, "off")
    assert ctrl.runner.hand[fid]["until"] is None  # Plan ruht → kein „bis 23:00“
