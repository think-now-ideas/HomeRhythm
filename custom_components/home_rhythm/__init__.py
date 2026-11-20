"""HomeRhythm – Hausmodi, Wochenpläne und Begründungen für Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CARD_URL, DOMAIN, VERSION
from .controller import HomeRhythmController
from .runner import FlowRunner
from .websocket_api import async_register_websocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Karte bereitstellen und Websocket-Befehle registrieren (einmalig)."""
    hass.data.setdefault(DOMAIN, {})
    card = Path(__file__).parent / "www" / "home-rhythm-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card), cache_headers=False)]
    )
    # Karte global laden, damit sie ohne manuelle Ressource im Dashboard verfügbar ist.
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    async_register_websocket(hass)
    _register_services(hass)
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Dienste für Automationen, Sprache oder Kalender: Ausnahme setzen / beenden."""
    import voluptuous as vol  # noqa: PLC0415

    from . import engine as E  # noqa: PLC0415

    def ctrl_and_room(call: ServiceCall) -> tuple[HomeRhythmController, str]:
        ctrl: HomeRhythmController | None = hass.data.get(DOMAIN, {}).get("controller")
        if ctrl is None:
            raise ServiceValidationError("HomeRhythm ist nicht eingerichtet")
        want = str(call.data["room"]).strip().casefold()
        room_id = next((rid for rid, r in ctrl.rooms.items() if want in (rid.casefold(), str(r.get("name", "")).casefold())), None)
        if room_id is None:
            raise ServiceValidationError(f"Unbekannter Raum: {call.data['room']}")
        return ctrl, room_id

    async def set_exception(call: ServiceCall) -> None:
        ctrl, room_id = ctrl_and_room(call)
        want = str(call.data["level"]).strip().casefold()
        level = next((k for k, d in ctrl.level_defs.items() if want in (k.casefold(), str(d.get("name", "")).casefold())), None)
        if level is None:
            raise ServiceValidationError(f"Unbekannte Stufe: {call.data['level']}")
        try:
            await ctrl.async_set_today(room_id, "stufe", level=level, start=call.data.get("start"), end=call.data["end"])
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def clear_exception(call: ServiceCall) -> None:
        ctrl, room_id = ctrl_and_room(call)
        await ctrl.async_set_today(room_id, "normal")

    hass.services.async_register(
        DOMAIN, "set_exception", set_exception,
        schema=vol.Schema({vol.Required("room"): cv.string, vol.Required("level"): cv.string,
                           vol.Optional("start"): cv.datetime, vol.Required("end"): cv.datetime}),
    )
    hass.services.async_register(DOMAIN, "clear_exception", clear_exception, schema=vol.Schema({vol.Required("room"): cv.string}))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller = HomeRhythmController(hass, entry)
    await controller.async_load()
    controller.runner = FlowRunner(hass, controller)
    controller.runner.load(controller.stored_flows)
    hass.data[DOMAIN]["controller"] = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.async_start()
    await controller.runner.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller: HomeRhythmController | None = hass.data[DOMAIN].get("controller")
    if controller:
        if controller.runner:
            await controller.runner.async_stop()
        await controller.async_stop()
        controller.stopped = True  # danach nichts mehr speichern (z. B. beim Entfernen)
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop("controller", None)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Integration gelöscht: gespeicherte Daten und angelegte HA-Automationen entfernen (Datenschutz)."""
    from homeassistant.helpers.storage import Store  # noqa: PLC0415

    from . import native  # noqa: PLC0415
    from .const import STORAGE_KEY, STORAGE_VERSION  # noqa: PLC0415

    await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_remove()
    try:
        await native.async_sync(hass, {})
    except Exception as err:  # noqa: BLE001 – Entfernen soll nicht scheitern
        _LOGGER.warning("HomeRhythm: Automationen in automations.yaml nicht entfernt: %s", err)
