"""Auswahl-Entitäten: Ereignis (keins/Party/Gäste) und „Heute anders“ je Raum."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import engine as E
from .const import DOMAIN, SIGNAL_UPDATED
from .controller import HomeRhythmController
from .entity import HomeRhythmEntity as _Base

EVENT_KEYS = {"keins": "keins", "party": "Party", "gaeste": "Gäste"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller: HomeRhythmController = hass.data[DOMAIN]["controller"]
    async_add_entities([EventSelect(controller)] + [TodaySelect(controller, rid) for rid in controller.rooms])

    @callback
    def _new_room(room_id: str) -> None:
        async_add_entities([TodaySelect(controller, room_id)])

    entry.async_on_unload(async_dispatcher_connect(hass, f"{SIGNAL_UPDATED}_new", _new_room))


class EventSelect(_Base, SelectEntity):
    _attr_translation_key = "event"
    _attr_icon = "mdi:party-popper"
    _attr_options = list(EVENT_KEYS)

    def __init__(self, controller: HomeRhythmController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_event"

    @property
    def current_option(self) -> str:
        return next((k for k, v in EVENT_KEYS.items() if v == self.controller.event), "keins")

    @property
    def extra_state_attributes(self):
        pu = self.controller.party_until
        return {"party_until": pu.isoformat() if pu and self.controller.event == "Party" else None}

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_set_event(EVENT_KEYS[option])


class TodaySelect(_Base, SelectEntity):
    """Heute anders: normal / wie Sonntag / Party bis 1 Uhr / Komfort den ganzen Tag / niemand im Raum."""

    _attr_icon = "mdi:calendar-today"
    _attr_options = list(E.TODAY_KINDS.values())

    def __init__(self, controller: HomeRhythmController, room_id: str) -> None:
        super().__init__(controller)
        self.room_id = room_id
        self._attr_unique_id = f"{controller.entry.entry_id}_{room_id}_today"
        self._attr_name = f"{controller.rooms[room_id]['name']} heute"

    @property
    def name(self) -> str:
        room = self.controller.rooms.get(self.room_id)
        return f"{room['name']} heute" if room else self._attr_name

    @property
    def available(self) -> bool:
        return self.room_id in self.controller.rooms

    @property
    def current_option(self) -> str | None:
        kind = self.controller.today_kind(self.room_id)
        return E.TODAY_KINDS.get(kind)  # Ausnahme „Stufe“ hat keine Option → None, Details in den Attributen

    @property
    def extra_state_attributes(self):
        info = self.controller.today_info(self.room_id)
        return {"ausnahme": info["label"], "beginn": info["start"], "ende": info["until"], "geplant": info["planned"]} if info else {}

    async def async_select_option(self, option: str) -> None:
        kind = next(k for k, v in E.TODAY_KINDS.items() if v == option)
        await self.controller.async_set_today(self.room_id, kind)
