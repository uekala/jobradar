"""Jobradar: sucht passende Stellen in der Jobbörse der Bundesagentur für Arbeit."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ACTION_HIDE, DOMAIN
from .coordinator import JobradarConfigEntry, JobradarCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEARCH = "search"
SERVICE_HIDE = "hide"
SERVICE_MARK_READ = "mark_read"
SERVICE_RESET = "reset"
ATTR_REFNR = "refnr"


def _coordinators(hass: HomeAssistant) -> list[JobradarCoordinator]:
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if isinstance(getattr(entry, "runtime_data", None), JobradarCoordinator)
    ]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Aktionen und Reaktion auf Benachrichtigungsknöpfe einmalig registrieren."""

    async def search(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_refresh()

    async def hide(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_hide(call.data[ATTR_REFNR])

    async def mark_read(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_mark_read(call.data.get(ATTR_REFNR))

    async def reset(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_reset()

    refnr = vol.Schema({vol.Required(ATTR_REFNR): cv.string})
    hass.services.async_register(DOMAIN, SERVICE_SEARCH, search)
    hass.services.async_register(DOMAIN, SERVICE_HIDE, hide, schema=refnr)
    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_READ,
        mark_read,
        schema=vol.Schema({vol.Optional(ATTR_REFNR): cv.string}),
    )
    hass.services.async_register(DOMAIN, SERVICE_RESET, reset)

    @callback
    def notification_action(event: Event) -> None:
        action = str(event.data.get("action") or "")
        if not action.startswith(ACTION_HIDE):
            return
        job = action.removeprefix(ACTION_HIDE)
        for coordinator in _coordinators(hass):
            if coordinator.has_job(job):
                hass.async_create_task(coordinator.async_hide(job))

    hass.bus.async_listen("mobile_app_notification_action", notification_action)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: JobradarConfigEntry) -> bool:
    coordinator = JobradarCoordinator(hass, entry)
    await coordinator.async_load()
    # Gespeicherte Stellen sofort zeigen; die erste Suche läuft im Hintergrund,
    # damit der Start von Home Assistant nicht auf die Jobbörse wartet
    coordinator.data = coordinator.stored_snapshot()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_create_background_task(hass, coordinator.async_refresh(), f"{DOMAIN}_first_search")
    return True


async def _async_reload(hass: HomeAssistant, entry: JobradarConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: JobradarConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
