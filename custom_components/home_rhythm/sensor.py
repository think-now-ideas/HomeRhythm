"""Ein Sensor pro Raum: Sollzustand mit Begründung – nutzbar in Verlauf, Logbuch und eigenen Karten."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import engine as E
from .const import DOMAIN, SIGNAL_UPDATED
from .controller import HomeRhythmController
from .entity import HomeRhythmEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller: HomeRhythmController = hass.data[DOMAIN]["controller"]
    async_add_entities([HomeRhythmStatusSensor(controller)] + [HomeRhythmRoomSensor(controller, rid) for rid in controller.rooms])

    @callback
    def _new_room(room_id: str) -> None:
        async_add_entities([HomeRhythmRoomSensor(controller, room_id)])

    entry.async_on_unload(async_dispatcher_connect(hass, f"{SIGNAL_UPDATED}_new", _new_room))


class _Base(HomeRhythmEntity, SensorEntity):
    """Sensor mit gemeinsamer Home-Rhythm-Basis."""


class HomeRhythmRoomSensor(_Base):
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, controller: HomeRhythmController, room_id: str) -> None:
        super().__init__(controller)
        self.room_id = room_id
        self._attr_unique_id = f"{controller.entry.entry_id}_{room_id}"
        self._attr_name = controller.rooms[room_id]["name"]

    @property
    def available(self) -> bool:
        return self.room_id in self.controller.rooms

    @property
    def native_value(self) -> str | None:
        r = self.controller.results.get(self.room_id)
        return E.LEVEL_NAMES.get(r.level, r.level) if r else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        room = self.controller.rooms.get(self.room_id, {})
        r = self.controller.results.get(self.room_id)
        attrs: dict[str, Any] = {
            "room_id": self.room_id,
            "climate_entities": room.get("climate_entities", []),
            "area_id": room.get("area_id"),
            "enabled": room.get("enabled", True),
        }
        if r:
            attrs.update(
                {
                    "level": r.level,
                    "target_temperature": r.temperature,
                    "hvac_mode": r.hvac_mode,
                    "rule": r.rule,
                    "reason": r.reason,
                    "until": r.until.isoformat() if r.until else None,
                    "next_level": E.LEVEL_NAMES.get(r.next_level) if r.next_level else None,
                }
            )
        if energy := self.controller.room_energy.get(self.room_id):
            attrs.update(
                {
                    "heat_source": "Klimaanlage" if energy["source"] == "ac" else "Heizkörper",
                    "heat_source_reason": energy["reason"],
                    "outdoor_temperature": energy["outdoor"],
                    "ac_threshold": energy["threshold"],
                    "cop_now": energy["cop_now"],
                    "cost_gas_ct_per_kwh": energy["cost_gas"],
                    "cost_ac_ct_per_kwh": energy["cost_ac"],
                }
            )
        attrs["ac_entities"] = room.get("ac_entities", [])
        attrs["thermostats"] = {
            eid: {"target_temperature": d.temperature, "hvac_mode": d.hvac_mode, "rule": d.rule, "reason": d.reason}
            for eid in room.get("climate_entities", []) + room.get("ac_entities", [])
            if (d := self.controller.dev_results.get(f"{self.room_id}|{eid}"))
        }
        return attrs


class HomeRhythmStatusSensor(_Base):
    _attr_icon = "mdi:home-clock-outline"

    def __init__(self, controller: HomeRhythmController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_status"
        self._attr_name = "Status"

    @property
    def native_value(self) -> str:
        m = self.controller.modes()
        if m.cooling_season:
            return "Kühlen aus (niemand zu Hause)" if m.nobody_home else f"Kühlen ({m.season})"
        if not m.heating_season:
            return f"Heizung aus ({m.season})"
        if m.away:
            return m.vacation_label or "Urlaub unterwegs"
        if m.event == "Party":
            return "Party"
        if m.home_vacation:
            return "Urlaub zu Hause"
        if m.holiday_today:
            return "Feiertag"
        return "Wochenplan"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "rooms": len(self.controller.rooms),
            "manual_rooms": sorted(
                {self.controller.rooms[k.split("|")[0]]["name"] for k in self.controller.manual if k.split("|")[0] in self.controller.rooms}
            ),
            "season": self.controller.modes().season,
            "outdoor_temperature": self.controller.outdoor(),
            "break_even_cop": round(self.controller.prices().break_even_cop, 2),
            "heat_cost_gas_ct_per_kwh": round(self.controller.prices().heat_cost_gas, 1),
        }
