"""0.9.13: leichte Raumabfrage `home_rhythm/rooms`, Abo `home_rhythm/subscribe` (auch ohne Admin)."""
import pytest
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN, EVENT_UPDATED

SCHED = {"wd": [["00:00", "24:00", "komfort"]], "sa": [["00:00", "24:00", "komfort"]], "so": [["00:00", "24:00", "komfort"]]}


@pytest.fixture
async def setup(hass, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    areas = ar.async_get(hass)
    kueche = areas.async_create("Küche")
    bad = areas.async_create("Bad")
    reg = er.async_get(hass)
    for oid in ("kueche", "bad", "bad2"):
        reg.async_get_or_create("climate", "test", oid, suggested_object_id=f"heizung_{oid}")
    reg.async_get_or_create("sensor", "test", "kt", suggested_object_id="kueche_temp", original_device_class="temperature")
    hass.states.async_set("climate.heizung_kueche", "heat", {"temperature": 21, "current_temperature": 19.4, "hvac_action": "heating"})
    hass.states.async_set("climate.heizung_bad", "heat", {"temperature": 21, "current_temperature": 22})
    hass.states.async_set("climate.heizung_bad2", "unavailable", {})
    hass.states.async_set("sensor.kueche_temp", "20.3", {"device_class": "temperature"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN]["controller"]
    await ctrl.async_save_room({"name": "Küche", "area_id": kueche.id, "climate_entities": ["climate.heizung_kueche"], "schedule": SCHED,
                                "temp_source": "sensors", "temp_sensors": ["sensor.kueche_temp"]})
    await ctrl.async_save_room({"name": "Bad", "area_id": bad.id, "climate_entities": ["climate.heizung_bad", "climate.heizung_bad2"], "schedule": SCHED})
    await hass.async_block_till_done()
    return ctrl, kueche.id, bad.id


async def test_rooms_light_fields(hass, setup):
    ctrl, kueche, bad = setup
    rooms = {r["area_id"]: r for r in ctrl.rooms_light()}
    k = rooms[kueche]
    assert k["name"] == "Küche" and k["enabled"] is True
    assert k["climate_entities"] == ["climate.heizung_kueche"]
    assert k["room_temp_entities"] == ["sensor.kueche_temp"] and k["room_temp_source"] == "sensors"
    assert k["ist"] == 20.3  # Raumfühler statt Fühler am Thermostat
    assert k["unavailable"] is False and k["manual_until"] is None
    assert set(k) >= {"id", "name", "area_id", "enabled", "climate_entities", "room_temp_entities", "ist", "soll",
                      "hvac_mode", "level", "level_name", "manual_until", "unavailable"}
    b = rooms[bad]
    assert b["unavailable"] is True  # ein Thermostat nicht erreichbar …
    assert b["ist"] == 22.0  # … Ist trotzdem vom erreichbaren
    assert b["room_temp_entities"] == [] and b["room_temp_source"] == "device"


async def test_rooms_light_manual(hass, setup):
    ctrl, kueche, _ = setup
    rid = next(r["id"] for r in ctrl.rooms_light() if r["area_id"] == kueche)
    await ctrl.async_card_manual(rid, temperature=23.5, minutes=60)
    await hass.async_block_till_done()
    k = next(r for r in ctrl.rooms_light() if r["id"] == rid)
    assert k["manual_until"] and k["level"] == "hand" and k["soll"] == 23.5 and k["hvac_mode"] == "heat"


async def test_ws_rooms_non_admin(hass, setup, hass_ws_client, hass_read_only_access_token):
    ctrl, kueche, _ = setup
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json({"id": 1, "type": "home_rhythm/rooms"})
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert any(r["area_id"] == kueche for r in msg["result"]["rooms"])
    # Admin-Befehle bleiben gesperrt
    await ws.send_json({"id": 2, "type": "home_rhythm/export"})
    msg = await ws.receive_json()
    assert not msg["success"]


async def test_ws_subscribe_non_admin(hass, setup, hass_ws_client, hass_read_only_access_token):
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json({"id": 1, "type": "home_rhythm/subscribe"})
    msg = await ws.receive_json()
    assert msg["success"], msg
    hass.bus.async_fire(EVENT_UPDATED, {})
    await hass.async_block_till_done()
    msg = await ws.receive_json()
    assert msg["id"] == 1 and msg["type"] == "event" and msg["event"] == {"updated": True}
    await ws.send_json({"id": 2, "type": "unsubscribe_events", "subscription": 1})
    msg = await ws.receive_json()
    assert msg["success"]
