"""0.9.11: Übersicht mit Zeitregler (Stand zu einem Zeitpunkt, „angenommen“), Gerätenutzung."""
from datetime import date, timedelta

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN

SCHED = {"wd": [["07:00", "18:00", "komfort"]], "sa": [], "so": [["08:00", "20:00", "komfort"]]}


@pytest.fixture
async def setup(hass, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"lampe": {}}})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "trv")}, name="Heizung Arbeitszimmer OG")
    reg.async_get_or_create("climate", "test", "trv", suggested_object_id="heizung_arbeitszimmer_og", device_id=dev.id)
    sens = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "s")}, name="Sensor Arbeitszimmer OG")
    reg.async_get_or_create("sensor", "test", "s", suggested_object_id="arbeitszimmer_og_temp", device_id=sens.id, original_device_class="temperature")
    hass.states.async_set("climate.heizung_arbeitszimmer_og", "heat", {"temperature": 18, "current_temperature": 19})
    hass.states.async_set("sensor.arbeitszimmer_og_temp", "19.5", {"device_class": "temperature"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    await ctrl.async_save_room({"name": "Arbeitszimmer OG", "climate_entities": ["climate.heizung_arbeitszimmer_og"], "schedule": SCHED,
                                "temp_source": "sensors", "temp_sensors": ["sensor.arbeitszimmer_og_temp"]})
    await hass.async_block_till_done()
    return ctrl


def next_weekday(wd: int) -> date:
    d = dt_util.now().date() + timedelta(days=1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


async def test_at_room_levels_and_assume(hass, setup):
    ctrl = setup
    mon = next_weekday(0)
    rid = next(iter(ctrl.rooms))
    r = ctrl.runner.at(mon, 9 * 60)["rooms"]
    room = next(x for x in r if x["id"] == rid)
    assert room["level"] == "komfort" and room["next_at"].startswith(mon.isoformat() + "T18:00")
    assert next(x for x in ctrl.runner.at(mon, 20 * 60)["rooms"] if x["id"] == rid)["level"] == "absenkung"
    # Urlaub zu Hause → Sonntagsplan (Standard), also 08–20 Komfort auch am Montag um 19:00
    vac_home = ctrl.options.get("home_value") or "Urlaub zu Hause"
    res = ctrl.runner.at(mon, 19 * 60, {"vacation": vac_home})
    assert next(x for x in res["rooms"] if x["id"] == rid)["level"] in ("komfort", "absenkung")
    # Sommer → Heizung aus
    res = ctrl.runner.at(mon, 9 * 60, {"season": "Sommer"})
    assert next(x for x in res["rooms"] if x["id"] == rid)["hvac"] == "off"
    # Feiertag angenommen → wie Sonntag: 07:30 noch Absenkung, 08:30 Komfort
    res = ctrl.runner.at(mon, 7 * 60 + 30, {"holiday": "1"})
    assert next(x for x in res["rooms"] if x["id"] == rid)["level"] == "absenkung"
    assert res["holiday"]


async def test_at_flows_and_inactive(hass, setup):
    ctrl = setup
    flow = {"type": "plan", "kind": "switch", "name": "Abendlicht", "devices": ["input_boolean.lampe"], "mode": "simple",
            "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "time", "time": "17:00"}}, "sa": {"like": "mf"}, "so": {"like": "mf"}, "hol": {"like": "mf"}},
                       "close": {"ref": "time", "time": "22:00"}}}
    fid = await ctrl.runner.async_save_flow(flow, sync=False)
    d = next_weekday(2)
    res = ctrl.runner.at(d, 18 * 60)
    f = next(x for x in res["flows"] if x["id"] == fid)
    assert f["state"] == "on" and f["next"]["minute"] == 22 * 60
    assert next(x for x in ctrl.runner.at(d, 23 * 60)["flows"] if x["id"] == fid)["state"] == "off"
    await ctrl.runner.async_set_enabled(fid, False)
    f = next(x for x in ctrl.runner.at(d, 18 * 60)["flows"] if x["id"] == fid)
    assert f["enabled"] is False and f["state"] is None


async def test_timeline_with_assume(hass, setup):
    ctrl = setup
    mon = next_weekday(0)
    normal = ctrl.runner.timeline(mon)
    assert any(e["cat"] == "heat" and e["minute"] == 7 * 60 for e in normal["events"])
    summer = ctrl.runner.timeline(mon, {"season": "Sommer"})
    assert summer["events"][0]["text"].startswith("aus")
    hol = ctrl.runner.timeline(mon, {"holiday": "1"})
    assert any(e["cat"] == "heat" and e["minute"] == 8 * 60 for e in hol["events"])


async def test_ws_at_validation(hass, hass_ws_client, setup):
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "home_rhythm/at", "date": dt_util.now().date().isoformat(), "minute": 600, "assume": {"season": "Winter"}})
    res = await client.receive_json()
    assert res["success"] and "rooms" in res["result"]
    await client.send_json({"id": 2, "type": "home_rhythm/at", "date": "2000-01-01", "minute": 600})
    assert not (await client.receive_json())["success"]
    await client.send_json({"id": 3, "type": "home_rhythm/at", "date": dt_util.now().date().isoformat(), "minute": 9999})
    assert not (await client.receive_json())["success"]
    await client.send_json({"id": 4, "type": "home_rhythm/timeline", "date": dt_util.now().date().isoformat(), "assume": {"evil": "x"}})
    assert not (await client.receive_json())["success"]


async def test_device_uses(hass, setup):
    ctrl = setup
    room = next(iter(ctrl.rooms.values()))
    devs = ctrl.devices_of(room)
    by = {d["name"]: d for d in devs}
    assert any(u["text"] == "Heizung Arbeitszimmer OG: Thermostat" for u in by["Heizung Arbeitszimmer OG"]["uses"])
    assert any("Raumsensor" in u["text"] for u in by["Sensor Arbeitszimmer OG"]["uses"])
    # Gerät in einem Zeitplan
    fid = await ctrl.runner.async_save_flow({"type": "plan", "kind": "switch", "name": "Test", "devices": ["climate.heizung_arbeitszimmer_og"] and ["input_boolean.lampe"],
                                             "points": [{"days": "daily", "ref": "time", "time": "17:00", "action": "on"}]}, sync=False)
    fl = ctrl.runner.devices()
    assert any(u.get("flow") == fid for d in fl for u in d["uses"])


async def test_day_states_matches_at(hass, setup):
    ctrl = setup
    mon = next_weekday(0)
    ds = ctrl.runner.day_states(mon)
    assert len(ds["slots"]) == 96
    rid = next(iter(ctrl.rooms))
    i = next(k for k, r in enumerate(ds["rooms"]) if r["id"] == rid)
    for minute in (6 * 60 + 45, 9 * 60, 18 * 60 + 15):
        a = next(x for x in ctrl.runner.at(mon, minute)["rooms"] if x["id"] == rid)
        slot = ds["slots"][minute // 15]["r"][i]
        assert slot[0] == a["level"] and slot[1] == a["temperature"]
    summer = ctrl.runner.day_states(mon, {"season": "Sommer"})
    assert all(s["r"][i][2] == "off" for s in summer["slots"])
