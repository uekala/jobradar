"""Knöpfe: jetzt suchen und alle als gelesen markieren."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import JobradarConfigEntry, JobradarCoordinator
from .sensor import JobradarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JobradarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([MarkReadButton(coordinator), SearchButton(coordinator)])


class MarkReadButton(JobradarEntity, ButtonEntity):
    def __init__(self, coordinator: JobradarCoordinator) -> None:
        super().__init__(coordinator, "mark_read")

    async def async_press(self) -> None:
        await self.coordinator.async_mark_read()


class SearchButton(JobradarEntity, ButtonEntity):
    def __init__(self, coordinator: JobradarCoordinator) -> None:
        super().__init__(coordinator, "search_now")

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
