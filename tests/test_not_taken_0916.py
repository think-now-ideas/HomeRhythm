"""0.9.16: Thermostat übernimmt einen gesendeten Sollwert nicht (z. B. Funkproblem) → Hinweis für die Karte.

Das Thermostat ist hier nur ein Zustand in Home Assistant; der Dienst `climate.set_temperature` wird nachgebildet
und tut – wie ein nicht erreichbares Zigbee-Gerät – nichts.
"""
import logging
from datetime import timedelta

import pytest
from homeassistant.core import Context
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_rhythm.const import DOMAIN, STUCK_SECONDS, STUCK_SECONDS_SLOW

SCHED = {"wd": [["00:00", "24:00", "nacht"]], "sa": [["00:00", "24:00", "nacht"]], "so": [["00:00", "24:00", "nacht"]]}
EID = "climate.heizung_wohnzimmer"
ATTRS = {"current_temperature": 20.7, "hvac_action": "heating", "hvac_modes": ["off", "heat", "auto"], "target_temp_step": 0.5,
         "min_temp": 5, "max_temp": 30}


@pytest.fixture
async def setup(hass, enable_custom_integrations):
    await async_setup_component(hass, "homeassistant", {})
    calls = []

    async def ignore(call):  # Gerät antwortet nicht – der Zustand bleibt, wie er ist
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
    rid = next(iter(ctrl.rooms))
    return ctrl, rid, calls


def _dev(ctrl, rid):
    room = next(r for r in ctrl.snapshot()["rooms"] if r["id"] == rid)
    return room["climates"][0]


async def test_not_taken_after_limit(hass, setup, freezer, caplog):
    ctrl, rid, calls = setup
    await ctrl.async_update(apply=True)
    assert any(c.service == "set_temperature" and c.data["temperature"] == 17.0 for c in calls)
    assert _dev(ctrl, rid)["not_taken"] is None  # noch keine Warnung – Funkgeräte brauchen etwas

    freezer.tick(timedelta(seconds=STUCK_SECONDS + 5))
    caplog.set_level(logging.WARNING)
    await ctrl.async_update(apply=True)
    info = _dev(ctrl, rid)["not_taken"]
    assert info and info["tries"] == 1 and info["want_temp"] == 17.0 and info["temp"] == 21
    assert next(r for r in ctrl.rooms_light() if r["id"] == rid)["not_taken"] is True
    warns = [r for r in caplog.records if "übernimmt den Sollwert nicht" in r.getMessage()]
    assert len(warns) == 1

    # nach 10 Minuten erneut gesendet → Versuche zählen weiter, keine zweite Warnung
    freezer.tick(timedelta(seconds=600))
    await ctrl.async_update(apply=True)
    info2 = _dev(ctrl, rid)["not_taken"]
    assert info2["tries"] == 2 and info2["since"] == info["since"]
    assert len([r for r in caplog.records if "übernimmt den Sollwert nicht" in r.getMessage()]) == 1

    # Gerät übernimmt den Wert → Hinweis weg
    ctx = next(iter(ctrl._own_contexts))
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 17.0}, context=Context(id=ctx))
    await hass.async_block_till_done()
    await ctrl.async_update(apply=True)
    assert _dev(ctrl, rid)["not_taken"] is None
    assert next(r for r in ctrl.rooms_light() if r["id"] == rid)["not_taken"] is False


async def test_plan_change_keeps_counting(hass, setup, freezer):
    """Wechselt der Plan, während das Gerät nicht reagiert, bleibt „seit“ – es ist dasselbe Problem."""
    ctrl, rid, _ = setup
    room = dict(ctrl.rooms[rid])
    two = [["00:00", "23:00", "nacht"], ["23:00", "24:00", "absenkung"]]
    room["schedule"] = {"wd": two, "sa": two, "so": two}
    await ctrl.async_save_room(room)
    await hass.async_block_till_done()
    freezer.move_to(dt_util.now().replace(hour=22, minute=58, second=0))
    await ctrl.async_update(apply=True)
    first = ctrl._last_sent[f"{rid}|{EID}"]["since"]
    assert ctrl._last_sent[f"{rid}|{EID}"]["want"]["temp"] == 17.0
    freezer.tick(timedelta(minutes=3))  # 23:01 – Absenkung
    await ctrl.async_update(apply=True)
    last = ctrl._last_sent[f"{rid}|{EID}"]
    assert last["want"]["temp"] == 18.0 and last["since"] == first and last["tries"] >= 2


async def test_fritz_gets_more_time(hass, setup, freezer):
    ctrl, rid, _ = setup
    room = dict(ctrl.rooms[rid])
    room["kind"] = "fritz"
    await ctrl.async_save_room(room)
    await hass.async_block_till_done()
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 5))
    await ctrl.async_update(apply=True)
    assert _dev(ctrl, rid)["not_taken"] is None  # FRITZ!DECT wacht nur alle paar Minuten auf
    freezer.tick(timedelta(seconds=STUCK_SECONDS_SLOW))
    await ctrl.async_update(apply=True)
    assert _dev(ctrl, rid)["not_taken"] is not None


async def test_unavailable_is_not_not_taken(hass, setup, freezer):
    """Nicht erreichbar zeigt die Karte schon anders – kein zweites Warnzeichen."""
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 5))
    hass.states.async_set(EID, "unavailable", {})
    await hass.async_block_till_done()
    assert _dev(ctrl, rid)["not_taken"] is None


async def test_hand_change_at_device_clears(hass, setup, freezer):
    """Ändert jemand am Gerät, ist es erreichbar – der Hinweis verschwindet (Hand-Änderung wie bisher)."""
    ctrl, rid, _ = setup
    await ctrl.async_update(apply=True)
    freezer.tick(timedelta(seconds=STUCK_SECONDS + 5))
    await ctrl.async_update(apply=True)
    assert _dev(ctrl, rid)["not_taken"] is not None
    hass.states.async_set(EID, "heat", {**ATTRS, "temperature": 19.5})
    await hass.async_block_till_done()
    assert ctrl.manual.get(rid) is not None
    assert _dev(ctrl, rid)["not_taken"] is None
