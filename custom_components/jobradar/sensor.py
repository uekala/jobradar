"""Sensoren: neue und alle passenden Stellen, letzte Suche."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_LISTED
from .coordinator import JobradarConfigEntry, JobradarCoordinator


def device_info(entry: JobradarConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Jobbörse der Bundesagentur für Arbeit",
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JobradarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [NewJobsSensor(coordinator), MatchingJobsSensor(coordinator), LastSearchSensor(coordinator)]
    )


class JobradarEntity(CoordinatorEntity[JobradarCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: JobradarCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device_info(coordinator.config_entry)

    @property
    def available(self) -> bool:
        # Auch wenn eine Suche scheitert, bleiben die gemerkten Stellen gültig
        return self.coordinator.data is not None


def _listing(coordinator: JobradarCoordinator, only_unread: bool) -> list[dict[str, Any]]:
    data = coordinator.data
    jobs = [j for j in data.jobs if not only_unread or j.refnr in data.unread]
    return [
        {
            "titel": j.title,
            "arbeitgeber": j.employer,
            "ort": j.place,
            "entfernung_km": j.distance_km,
            "homeoffice": j.remote,
            "punkte": j.score,
            "treffer": j.matches,
            "veroeffentlicht": j.published,
            "gehalt": j.pay or j.salary or None,
            "gehalt_passt": j.pay_ok,
            "bewerbungsfrist": j.deadline or None,
            "quelle": j.source or "Bundesagentur",
            "neu": j.refnr in data.unread,
            "refnr": j.refnr,
            "url": j.url,
        }
        for j in jobs[:MAX_LISTED]
    ]


class NewJobsSensor(JobradarEntity, SensorEntity):
    """Wie viele passende Stellen noch ungelesen sind."""

    _attr_native_unit_of_measurement = "Stellen"
    _unrecorded_attributes = frozenset({"stellen"})

    def __init__(self, coordinator: JobradarCoordinator) -> None:
        super().__init__(coordinator, "new_jobs")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.unread)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"stellen": _listing(self.coordinator, only_unread=True)}


class MatchingJobsSensor(JobradarEntity, SensorEntity):
    """Alle passenden Stellen der letzten Wochen."""

    _attr_native_unit_of_measurement = "Stellen"
    _unrecorded_attributes = frozenset({"stellen"})

    def __init__(self, coordinator: JobradarCoordinator) -> None:
        super().__init__(coordinator, "matching_jobs")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.jobs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"stellen": _listing(self.coordinator, only_unread=False)}


class LastSearchSensor(JobradarEntity, SensorEntity):
    """Wann zuletzt gesucht wurde und wie es lief."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: JobradarCoordinator) -> None:
        super().__init__(coordinator, "last_search")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_search

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "suchanfragen": data.queries,
            "fehlgeschlagen": data.errors,
            "neue_treffer": data.new_matches,
            "anfragen_gesamt": data.requests,
        }
