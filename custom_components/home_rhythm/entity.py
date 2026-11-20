"""Gemeinsame Basis aller Home-Rhythm-Entitäten (ein Gerät „Home Rhythm“ – Gerätename bleibt, sonst ändern sich die Anzeigenamen aller Entitäten, Aktualisierung per Signal)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATED, VERSION


class HomeRhythmEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller) -> None:
        self.controller = controller
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name="Home Rhythm",
            manufacturer="Home Rhythm",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self.async_write_ha_state))
