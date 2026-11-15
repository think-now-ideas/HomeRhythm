"""Daten für die Kartenprüfung (render/data.json) – kein eigentlicher Test."""
import json
import os

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN

OUT = os.environ.get("HR_DUMP")


async def test_dump(hass, hass_ws_client, enable_custom_integrations):
    if not OUT:
        return
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"lichterkette": {}, "stern": {}}})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    for name in ("Taster Flur", "Hue Dimmer Wohnzimmer"):
        dev = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", name)}, name=name)
        reg.async_get_or_create("event", "test", name, suggested_object_id=name.lower().replace(" ", "_") + "_action", device_id=dev.id)
    fl = __import__("homeassistant.helpers.floor_registry", fromlist=["x"]).async_get(hass)
    ar_ = __import__("homeassistant.helpers.area_registry", fromlist=["x"]).async_get(hass)
    og = fl.async_create("Obergeschoss", level=1)
    eg = fl.async_create("Erdgeschoss", level=0)
    a_arbeitszimmer_og = ar_.async_create("Arbeitszimmer OG", floor_id=og.floor_id)
    a_wz = ar_.async_create("Wohnzimmer", floor_id=eg.floor_id)
    for nm, area in (("Heizung Arbeitszimmer OG", a_arbeitszimmer_og), ("Wohnzimmer Heizung", a_wz)):
        dv = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", nm)}, name=nm, model="SONOFF TRVZB")
        dr.async_get(hass).async_update_device(dv.id, area_id=area.id)
        oid = nm.lower().replace(" ", "_")
        reg.async_get_or_create("climate", "test", nm, suggested_object_id=oid, device_id=dv.id)
        reg.async_get_or_create("sensor", "test", nm + "b", suggested_object_id=oid + "_battery", device_id=dv.id, original_device_class="battery")
        hass.states.async_set(f"climate.{oid}", "heat", {"temperature": 18, "current_temperature": 19.4})
        hass.states.async_set(f"sensor.{oid}_battery", "15" if "Arbeitszimmer OG" in nm else "80", {"device_class": "battery"})
    sdv = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "s1")}, name="Arbeitszimmer OG Temperatur Sonoff 1", model="SNZB-02D")
    dr.async_get(hass).async_update_device(sdv.id, area_id=a_arbeitszimmer_og.id)
    reg.async_get_or_create("sensor", "test", "s1", suggested_object_id="arbeitszimmer_og_temp_1", device_id=sdv.id, original_device_class="temperature")
    hass.states.async_set("sensor.arbeitszimmer_og_temp_1", "unavailable", {"device_class": "temperature"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    await ctrl.async_save_room({"name": "Arbeitszimmer OG", "area_id": a_arbeitszimmer_og.id, "climate_entities": ["climate.heizung_arbeitszimmer_og"],
                                "schedule": {"wd": [["07:00", "18:00", "komfort"]], "sa": [], "so": []}})
    await ctrl.async_save_room({"name": "Wohnzimmer", "area_id": a_wz.id, "climate_entities": ["climate.wohnzimmer_heizung"],
                                "schedule": {"wd": [["00:00", "07:00", "nacht"], ["17:00", "23:00", "komfort"]], "sa": [["07:30", "23:00", "komfort"]], "so": [["07:30", "23:00", "komfort"]]}})
    await hass.async_block_till_done()
    dev_id = dr.async_get(hass).async_get_device({("test", "Taster Flur")}).id
    flow = {"type": "plan", "kind": "switch", "name": "Weihnachtsbeleuchtung", "icon": "🎄", "devices": ["input_boolean.lichterkette", "input_boolean.stern"],
            "mode": "simple", "switch": True,
            "conds": {"op": "and", "items": [{"key": "date", "op": "is", "from": "11-01", "to": "01-06"}]},
            "button": {"device_id": dev_id, "map": {"event:event.taster_flur_action:single": "toggle"}, "auto_off": 120},
            "simple": {"rows": {"mf": {"like": "own", "open": {"ref": "sunset", "offset": -30}}, "sa": {"like": "mf"}, "so": {"like": "mf"}},
                       "close": {"ref": "time", "time": "23:00"},
                       "days": [{"date": "12-24", "name": "Heiligabend", "open": {"ref": "time", "time": "15:00"}, "close": {"ref": "time", "time": "02:00"}},
                                {"date": "12-31", "name": "Silvester", "open": {"ref": "normal"}, "close": {"ref": "time", "time": "03:00"}}]}}
    fid = await ctrl.runner.async_save_flow(flow, sync=False)
    await ctrl.runner.async_button(fid, "on", "Taster Flur")
    f2 = {**flow, "name": "Abendlicht", "icon": "💡", "switch": False, "button": None, "conds": {"op": "and", "items": []}}
    f2id = await ctrl.runner.async_save_flow(f2, sync=False)
    f3id = await ctrl.runner.async_save_flow({**f2, "name": "Urlaubssimulation", "icon": "🏖️"}, sync=False)
    await ctrl.runner.async_set_enabled(f3id, False)
    client = await hass_ws_client(hass)
    out = {}
    await client.send_json({"id": 1, "type": "home_rhythm/state"})
    out["state"] = (await client.receive_json())["result"]
    item = next(i for i in out["state"]["flows"]["items"] if i["id"] == fid)
    await client.send_json({"id": 2, "type": "home_rhythm/flow/preview", "flow": {k: item[k] for k in flow} | {"id": fid}})
    res = await client.receive_json()
    out["preview"] = res.get("result") or res
    out["fid"] = fid
    from homeassistant.util import dt as dt_util
    today = dt_util.now().date().isoformat()
    await client.send_json({"id": 3, "type": "home_rhythm/state"})
    out["state"] = (await client.receive_json())["result"]
    await client.send_json({"id": 4, "type": "home_rhythm/at", "date": today, "minute": 19 * 60})
    out["at"] = (await client.receive_json())["result"]
    await client.send_json({"id": 5, "type": "home_rhythm/day_states", "date": today})
    out["day_states"] = (await client.receive_json())["result"]
    await client.send_json({"id": 6, "type": "home_rhythm/timeline", "date": today})
    out["timeline"] = (await client.receive_json())["result"]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
