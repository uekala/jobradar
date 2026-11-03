"""Diagnose ohne Stellendetails und ohne Arbeitgeberliste."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_EXCLUDED_EMPLOYERS
from .coordinator import JobradarConfigEntry, settings


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: JobradarConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    conf = settings(entry)
    conf[CONF_EXCLUDED_EMPLOYERS] = "**REDACTED**" if conf.get(CONF_EXCLUDED_EMPLOYERS) else ""
    return {
        "settings": conf,
        "last_search": data.last_search.isoformat() if data and data.last_search else None,
        "queries": data.queries if data else None,
        "errors": data.errors if data else None,
        "requests": data.requests if data else None,
        "hits": data.found if data else 0,
        "best_new_scores": data.best if data else [],
        "matching_jobs": len(data.jobs) if data else 0,
        "unread": len(data.unread) if data else 0,
        "search_path": coordinator.client._search_path,
        "details_available": coordinator.client._details_available,
        "response_shapes": coordinator.client.shapes,
    }
