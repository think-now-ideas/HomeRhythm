"""Einrichtung von Home Rhythm über die Oberfläche (Schritt 1 Hausmodi, Schritt 2 Energie)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_HOLIDAY_AS,
    CONF_VACATION_AS,
    CONF_AWAY_TEMP,
    CONF_AWAY_VALUE,
    CONF_BOILER_EFF,
    CONF_COOL_VALUES,
    CONF_PRESENCE_ENTITY,
    CONF_GAS_PRICE,
    CONF_GAS_PRICE_ENTITY,
    CONF_HOME_VALUE,
    CONF_HOT_ABOVE,
    CONF_HYSTERESIS,
    CONF_SUMMER_VALUE,
    CONF_WINTER_BELOW,
    CONF_OUTDOOR_AGG,
    CONF_OUTDOOR_ENTITIES,
    CONF_OUTDOOR_MINUTES,
    CONF_POWER_PRICE,
    CONF_POWER_PRICE_ENTITY,
    CONF_SEASON_ENTITY,
    CONF_VACATION_ENTITY,
    CONF_WINTER_VALUES,
    CONF_WORKDAY_ENTITY,
    DEFAULTS,
    DOMAIN,
)

MODE_DOMAINS = ["input_select", "select", "sensor", "input_text"]


def _ent(domains: list[str], multiple: bool = False) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domains, multiple=multiple))


def _num(lo: float, hi: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=lo, max=hi, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX)
    )


def _day_as() -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(options=["wd", "sa", "so"], translation_key="day_as", mode=selector.SelectSelectorMode.DROPDOWN))


def _modes_schema(values: dict[str, Any]) -> vol.Schema:
    v = {**DEFAULTS, **values}
    text = selector.TextSelector()
    return vol.Schema(
        {
            vol.Optional(CONF_SEASON_ENTITY, description={"suggested_value": v[CONF_SEASON_ENTITY]}): _ent(MODE_DOMAINS),
            vol.Required(CONF_WINTER_VALUES, default=v[CONF_WINTER_VALUES]): text,
            vol.Optional(CONF_VACATION_ENTITY, description={"suggested_value": v[CONF_VACATION_ENTITY]}): _ent(MODE_DOMAINS),
            vol.Required(CONF_AWAY_VALUE, default=v[CONF_AWAY_VALUE]): text,
            vol.Required(CONF_HOME_VALUE, default=v[CONF_HOME_VALUE]): text,
            vol.Optional(CONF_WORKDAY_ENTITY, description={"suggested_value": v[CONF_WORKDAY_ENTITY]}): _ent(["binary_sensor"]),
            vol.Required(CONF_AWAY_TEMP, default=float(v[CONF_AWAY_TEMP])): _num(5, 25, 0.5, "°C"),
            vol.Optional(CONF_COOL_VALUES, default=v[CONF_COOL_VALUES]): text,
            vol.Required(CONF_SUMMER_VALUE, default=v[CONF_SUMMER_VALUE]): text,
            vol.Optional(CONF_PRESENCE_ENTITY, description={"suggested_value": v[CONF_PRESENCE_ENTITY]}): _ent(
                ["zone", "group", "person", "binary_sensor", "input_boolean"]
            ),
            vol.Required(CONF_HOLIDAY_AS, default=v[CONF_HOLIDAY_AS]): _day_as(),
            vol.Required(CONF_VACATION_AS, default=v[CONF_VACATION_AS]): _day_as(),
        }
    )


def _energy_schema(values: dict[str, Any]) -> vol.Schema:
    v = {**DEFAULTS, **values}
    return vol.Schema(
        {
            vol.Optional(CONF_OUTDOOR_ENTITIES, description={"suggested_value": v[CONF_OUTDOOR_ENTITIES]}): _ent(["sensor", "weather"], True),
            vol.Required(CONF_OUTDOOR_AGG, default=v[CONF_OUTDOOR_AGG]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["mean", "min"], translation_key="outdoor_aggregate", mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Required(CONF_OUTDOOR_MINUTES, default=int(v[CONF_OUTDOOR_MINUTES])): _num(0, 360, 5, "min"),
            vol.Required(CONF_GAS_PRICE, default=float(v[CONF_GAS_PRICE])): _num(1, 100, 0.01, "ct/kWh"),
            vol.Optional(CONF_GAS_PRICE_ENTITY, description={"suggested_value": v[CONF_GAS_PRICE_ENTITY]}): _ent(["sensor", "input_number", "number"]),
            vol.Required(CONF_BOILER_EFF, default=float(v[CONF_BOILER_EFF])): _num(50, 110, 1, "%"),
            vol.Required(CONF_POWER_PRICE, default=float(v[CONF_POWER_PRICE])): _num(1, 150, 0.01, "ct/kWh"),
            vol.Optional(CONF_POWER_PRICE_ENTITY, description={"suggested_value": v[CONF_POWER_PRICE_ENTITY]}): _ent(["sensor", "input_number", "number"]),
            vol.Required(CONF_HYSTERESIS, default=float(v[CONF_HYSTERESIS])): _num(0, 5, 0.5, "K"),
            vol.Required(CONF_WINTER_BELOW, default=float(v[CONF_WINTER_BELOW])): _num(0, 25, 0.5, "°C"),
            vol.Required(CONF_HOT_ABOVE, default=float(v[CONF_HOT_ABOVE])): _num(15, 40, 0.5, "°C"),
        }
    )


MODE_ENTITY_KEYS = (CONF_SEASON_ENTITY, CONF_VACATION_ENTITY, CONF_WORKDAY_ENTITY, CONF_PRESENCE_ENTITY)
ENERGY_ENTITY_KEYS = (CONF_GAS_PRICE_ENTITY, CONF_POWER_PRICE_ENTITY)


def _clean(user_input: dict[str, Any], entity_keys: tuple[str, ...]) -> dict[str, Any]:
    """Leere Entitätsfelder dieses Schritts als "" speichern – Felder anderer Schritte nicht anfassen."""
    out = dict(user_input)
    for key in entity_keys:
        out.setdefault(key, "")
    for key in (CONF_AWAY_TEMP, CONF_GAS_PRICE, CONF_POWER_PRICE, CONF_HYSTERESIS, CONF_BOILER_EFF, CONF_WINTER_BELOW, CONF_HOT_ABOVE):
        if key in out:
            out[key] = float(out[key])
    if CONF_COOL_VALUES in entity_keys or entity_keys == MODE_ENTITY_KEYS:
        out.setdefault(CONF_COOL_VALUES, "")
    if CONF_OUTDOOR_MINUTES in out:
        out[CONF_OUTDOOR_MINUTES] = int(out[CONF_OUTDOOR_MINUTES])
    if entity_keys == ENERGY_ENTITY_KEYS:
        out.setdefault(CONF_OUTDOOR_ENTITIES, [])
    return out


class HomeRhythmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = _clean(user_input, MODE_ENTITY_KEYS)
            return await self.async_step_energy()
        # Vorschläge aus dem, was es hier wirklich gibt – keine fest eingebauten Entitätsnamen
        from .requirements import suggest  # noqa: PLC0415

        found = suggest(self.hass)
        defaults = {k: v for k, v in DEFAULTS.items() if not isinstance(v, list)}
        defaults.update({CONF_SEASON_ENTITY: found.get("season", ""), CONF_VACATION_ENTITY: found.get("vacation", ""),
                         CONF_WORKDAY_ENTITY: found.get("workday", ""), CONF_PRESENCE_ENTITY: found.get("presence", "")})
        return self.async_show_form(step_id="user", data_schema=_modes_schema(defaults))

    async def async_step_energy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Home Rhythm", data={**self._data, **_clean(user_input, ENERGY_ENTITY_KEYS)})
        return self.async_show_form(step_id="energy", data_schema=_energy_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HomeRhythmOptionsFlow:
        return HomeRhythmOptionsFlow()


class HomeRhythmOptionsFlow(OptionsFlowWithReload):
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["modes", "energy"])

    async def async_step_modes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **_clean(user_input, MODE_ENTITY_KEYS)})
        return self.async_show_form(step_id="modes", data_schema=_modes_schema(self._current))

    async def async_step_energy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = _clean(user_input, ENERGY_ENTITY_KEYS)
            return self.async_create_entry(data={**self.config_entry.options, **data})
        return self.async_show_form(step_id="energy", data_schema=_energy_schema(self._current))
