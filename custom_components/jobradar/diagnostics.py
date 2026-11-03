"""Diagnose ohne Stellendetails und ohne Arbeitgeberliste."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_EXCLUDED_EMPLOYERS
from .coordinator import JobradarConfigEntry, settings
from .scoring import Job


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: JobradarConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    client = coordinator.client
    if client.detail_shape is None and data and data.jobs:
        # Eine Detailansicht zur Probe, damit die Diagnose ihr Format zeigt
        await client.load_details(Job.from_dict(data.jobs[0].as_dict()))
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
        "response_shapes": client.shapes,
        "pay_samples": client.pay_samples,
        "detail_shape": client.detail_shape,
        "bund": {
            "requests": coordinator.bund.requests,
            "hits": coordinator.bund.hits,
            "errors": coordinator.bund.errors,
            "last_error": coordinator.bund.last_error,
            "last_response": coordinator.bund.last_response,
            "place": coordinator.bund.place,
            "nationwide": coordinator.bund.nationwide,
            "probe": coordinator.bund.last_probe,
            "geocoded_places": len(coordinator._geo),
            "geocoded_ok": sum(1 for v in coordinator._geo.values() if v),
            "geo_sample": dict(list(coordinator._geo.items())[:8]),
            "last_geo": coordinator.client.last_geo,
            "nearby": coordinator.bund_nearby,
        },
    }
