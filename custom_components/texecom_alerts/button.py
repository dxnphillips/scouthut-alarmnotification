"""Button platform for Texecom Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TexecomConfigEntry
from . import dashboards as dashboards_helper
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
            TexecomCreateDashboardButton(data.coordinator, entry),
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


class TexecomCreateDashboardButton(TexecomEntity, ButtonEntity):
    """Adds the Alarm view to the shared Scout Hut sidebar dashboard.

    Opt in, so a user who does not want a sidebar dashboard is never given one.
    The write merges, so pressing it never disturbs the heating views on the
    same dashboard.
    """

    _attr_name = "Create dashboard"
    _attr_icon = "mdi:view-dashboard-outline"

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "create_dashboard")

    async def async_press(self) -> None:
        """Create or refresh the Alarm view."""
        await dashboards_helper.async_create_dashboards(self.hass, self.entry)
