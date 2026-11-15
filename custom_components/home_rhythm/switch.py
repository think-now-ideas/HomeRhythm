"""Schalter: „Jahreszeit automatisch“ (aus = festhalten) und je Zeitplan ein Schalter für seine Geräte (ab 0.9.9).

Der Zeitplan-Schalter schaltet – wie der Taster – alle Geräte des Zeitplans gemeinsam, wie von Hand: Der Plan
läuft danach normal weiter. Er ist an, wenn mindestens ein Gerät an bzw. offen ist. So lässt sich ein Zeitplan
aus jeder HA-Automation, per Sprache oder über einen Dashboard-Knopf bedienen.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import flows as F
from .const import DOMAIN, SIGNAL_FLOWS, SIGNAL_UPDATED
from .controller import HomeRhythmController
from .entity import HomeRhythmEntity as _Base

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller: HomeRhythmController = hass.data[DOMAIN]["controller"]
    async_add_entities([SeasonAutoSwitch(controller)])
    plan_switches: dict[str, FlowSwitch] = {}

    def _wanted() -> set[str]:
        runner = controller.runner
        return {fid for fid, f in (runner.flows if runner else {}).items() if f.get("type") == "plan" and f.get("switch")} if runner else set()

    @callback
    def _sync() -> None:
        wanted = _wanted()
        new = [FlowSwitch(controller, fid) for fid in wanted - set(plan_switches)]
        for ent in new:
            plan_switches[ent.flow_id] = ent
        if new:
            async_add_entities(new)
        reg = er.async_get(hass)
        for fid in set(plan_switches) - wanted:  # Häkchen entfernt oder Zeitplan gelöscht → Entität entfernen
            ent = plan_switches.pop(fid)
            if ent.entity_id and reg.async_get(ent.entity_id):
                reg.async_remove(ent.entity_id)
            elif ent.hass is not None:
                hass.async_create_task(ent.async_remove(force_remove=True))
        # verwaiste Einträge aus früheren Läufen (z. B. Zeitplan gelöscht, während HA aus war)
        prefix = f"{entry.entry_id}_flow_"
        for e in er.async_entries_for_config_entry(reg, entry.entry_id):
            if e.domain == "switch" and e.unique_id.startswith(prefix) and e.unique_id[len(prefix):] not in wanted:
                reg.async_remove(e.entity_id)

    _sync()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_FLOWS, _sync))


class SeasonAutoSwitch(_Base, SwitchEntity):
    _attr_translation_key = "season_auto"
    _attr_icon = "mdi:weather-partly-snowy-rainy"

    def __init__(self, controller: HomeRhythmController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_season_auto"

    @property
    def is_on(self) -> bool:
        return self.controller.season_auto

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        avg, days = self.controller.season_average()
        return {"average_3_days": avg, "days_measured": days, "suggestion": self.controller.season_suggestion()}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_set_season_auto(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_set_season_auto(False)


class FlowSwitch(_Base, SwitchEntity):
    """Alle Geräte eines Zeitplans gemeinsam schalten (wie der Taster)."""

    def __init__(self, controller: HomeRhythmController, flow_id: str) -> None:
        super().__init__(controller)
        self.flow_id = flow_id
        self._attr_unique_id = f"{controller.entry.entry_id}_flow_{flow_id}"
        self._attr_name = self._flow["name"] if self._flow else flow_id
        self._devices: list[str] = []
        self._unsub_devices = None

    @property
    def _flow(self) -> dict[str, Any] | None:
        runner = self.controller.runner
        return runner.flows.get(self.flow_id) if runner else None

    @property
    def name(self) -> str:
        f = self._flow
        return f["name"] if f else self._attr_name

    @property
    def icon(self) -> str:
        f = self._flow
        return "mdi:window-shutter" if f and f["kind"] == F.KIND_COVER else "mdi:lightbulb-group"

    @property
    def available(self) -> bool:
        return self._flow is not None and bool(self._devices)

    @property
    def is_on(self) -> bool:
        f = self._flow
        return bool(f) and self.controller.runner.any_on(f)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        h = self.controller.runner.hand.get(self.flow_id) if self.controller.runner else None
        return {"geraete": len(self._devices), "von_hand": bool(h), "von_hand_bis": (h or {}).get("until"), "quelle": (h or {}).get("src")}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh))
        self.async_on_remove(self._untrack)
        self._refresh()

    @callback
    def _untrack(self) -> None:
        if self._unsub_devices:
            self._unsub_devices()
            self._unsub_devices = None

    @callback
    def _refresh(self) -> None:
        """Geräte neu auflösen (Bereich/Label können sich ändern) und deren Zustände beobachten."""
        f = self._flow
        devices = self.controller.runner.resolve(f) if f else []
        if devices != self._devices:
            self._untrack()
            self._devices = devices
            if devices:
                self._unsub_devices = async_track_state_change_event(self.hass, devices, self._on_device)
        self.async_write_ha_state()

    @callback
    def _on_device(self, _event: Event) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.runner.async_button(self.flow_id, "on", "HA-Schalter")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.runner.async_button(self.flow_id, "off", "HA-Schalter")
