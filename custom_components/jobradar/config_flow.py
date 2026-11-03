"""Einrichtung und Optionen für Jobradar."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_EXCLUDED_EMPLOYERS,
    CONF_EXCLUDED_WORDS,
    CONF_INTERVAL,
    CONF_LOCATION,
    CONF_MIN_SCORE,
    CONF_NO_TEMP_AGENCIES,
    CONF_NOTIFY,
    CONF_RADIUS,
    CONF_REMOTE,
    CONF_SEARCH_TERMS,
    CONF_SKILLS,
    CONF_UNWANTED,
    DEFAULT_EXCLUDED_WORDS,
    DEFAULT_INTERVAL,
    DEFAULT_MIN_SCORE,
    DEFAULT_RADIUS,
    DEFAULT_SEARCH_TERMS,
    DEFAULT_SKILLS,
    DEFAULT_UNWANTED,
    DOMAIN,
    MIN_INTERVAL,
)
from .scoring import parse_list

NO_NOTIFY = "persistent_notification"


def _notify_options(hass: HomeAssistant) -> list[SelectOptionDict]:
    options = [SelectOptionDict(value=NO_NOTIFY, label="Nur Benachrichtigung in Home Assistant")]
    for name in sorted(hass.services.async_services_for_domain("notify")):
        if name in ("send_message", "persistent_notification"):
            continue
        options.append(SelectOptionDict(value=f"notify.{name}", label=f"notify.{name}"))
    return options


def _default_notify(hass: HomeAssistant) -> str:
    phones = [
        o["value"] for o in _notify_options(hass) if o["value"].startswith("notify.mobile_app_")
    ]
    return phones[0] if phones else NO_NOTIFY


def _multiline() -> TextSelector:
    return TextSelector(TextSelectorConfig(multiline=True))


def _number(minimum: int, maximum: int, step: int = 1, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _schema(hass: HomeAssistant, values: dict[str, Any], *, advanced: bool) -> vol.Schema:
    def default(key: str, fallback: Any) -> dict[str, Any]:
        return {"default": values.get(key, fallback)}

    fields: dict[Any, Any] = {
        vol.Required(CONF_LOCATION, **default(CONF_LOCATION, "")): str,
        vol.Required(CONF_RADIUS, **default(CONF_RADIUS, DEFAULT_RADIUS)): _number(0, 200, 5, "km"),
        vol.Required(CONF_REMOTE, **default(CONF_REMOTE, True)): BooleanSelector(),
        vol.Required(
            CONF_SEARCH_TERMS, **default(CONF_SEARCH_TERMS, DEFAULT_SEARCH_TERMS)
        ): _multiline(),
        vol.Required(CONF_SKILLS, **default(CONF_SKILLS, DEFAULT_SKILLS)): _multiline(),
        vol.Optional(CONF_EXCLUDED_EMPLOYERS, **default(CONF_EXCLUDED_EMPLOYERS, "")): _multiline(),
        vol.Required(CONF_MIN_SCORE, **default(CONF_MIN_SCORE, DEFAULT_MIN_SCORE)): _number(
            0, 100, 5
        ),
        vol.Required(CONF_NOTIFY, **default(CONF_NOTIFY, _default_notify(hass))): SelectSelector(
            SelectSelectorConfig(options=_notify_options(hass), mode=SelectSelectorMode.DROPDOWN)
        ),
    }
    if advanced:
        fields.update(
            {
                vol.Optional(
                    CONF_UNWANTED, **default(CONF_UNWANTED, DEFAULT_UNWANTED)
                ): _multiline(),
                vol.Optional(
                    CONF_EXCLUDED_WORDS, **default(CONF_EXCLUDED_WORDS, DEFAULT_EXCLUDED_WORDS)
                ): _multiline(),
                vol.Required(
                    CONF_NO_TEMP_AGENCIES, **default(CONF_NO_TEMP_AGENCIES, True)
                ): BooleanSelector(),
                vol.Required(CONF_INTERVAL, **default(CONF_INTERVAL, DEFAULT_INTERVAL)): _number(
                    MIN_INTERVAL, 360, 5, "min"
                ),
            }
        )
    return vol.Schema(fields)


def _validate(values: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not parse_list(values.get(CONF_SEARCH_TERMS)):
        errors[CONF_SEARCH_TERMS] = "no_terms"
    if not str(values.get(CONF_LOCATION, "")).strip() and not values.get(CONF_REMOTE):
        errors[CONF_LOCATION] = "no_location"
    return errors


def _clean(values: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(values)
    cleaned[CONF_LOCATION] = str(values.get(CONF_LOCATION, "")).strip()
    for key in (CONF_RADIUS, CONF_MIN_SCORE, CONF_INTERVAL):
        if key in cleaned:
            cleaned[key] = int(cleaned[key])
    if cleaned.get(CONF_NOTIFY) == NO_NOTIFY:
        cleaned[CONF_NOTIFY] = ""
    return cleaned


def _title(values: dict[str, Any]) -> str:
    location = values.get(CONF_LOCATION)
    return f"Jobradar {location}" if location else "Jobradar Homeoffice"


class JobradarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Suchprofil anlegen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        values = user_input or {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                data = _clean(user_input)
                return self.async_create_entry(title=_title(data), data=data)
        return self.async_show_form(
            step_id="user", data_schema=_schema(self.hass, values, advanced=False), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return JobradarOptionsFlow()


class JobradarOptionsFlow(OptionsFlow):
    """Suchprofil ändern."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if current.get(CONF_NOTIFY) == "":
            current[CONF_NOTIFY] = NO_NOTIFY
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(data=_clean(user_input))
            current.update(user_input)
        return self.async_show_form(
            step_id="init", data_schema=_schema(self.hass, current, advanced=True), errors=errors
        )
