"""Button platform for Texecom Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TexecomConfigEntry
from .entity import TexecomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TexecomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons."""
    data = entry.runtime_data
    async_add_entities(
        [
            TexecomTestButton(data.coordinator, entry, data.alerting),
            TexecomAcknowledgeButton(data.coordinator, entry, data.alerting),
        ]
    )


class TexecomTestButton(TexecomEntity, ButtonEntity):
    """Runs the full escalation ladder with a marked test alert.

    A silently broken call path is worse than no call path, so this exists to
    be pressed regularly rather than as a novelty.
    """

    _attr_name = "Test alerts"
    _attr_icon = "mdi:phone-alert"

    def __init__(self, coordinator: Any, entry: Any, alerting: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "test_alerts")
        self._alerting = alerting

    async def async_press(self) -> None:
        """Start the test."""
        await self._alerting.async_test()


class TexecomAcknowledgeButton(TexecomEntity, ButtonEntity):
    """Stops a running ladder from the dashboard."""

    _attr_name = "Acknowledge"
    _attr_icon = "mdi:check-decagram"

    def __init__(self, coordinator: Any, entry: Any, alerting: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "acknowledge")
        self._alerting = alerting

    async def async_press(self) -> None:
        """Acknowledge."""
        self._alerting.acknowledge(by="the dashboard")
