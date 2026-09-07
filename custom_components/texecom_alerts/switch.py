"""Switch platform for Texecom Alerts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import TexecomConfigEntry
from .const import CONF_MAINTENANCE_HOURS, DEFAULT_MAINTENANCE_HOURS
from .entity import TexecomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TexecomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the maintenance mode and fire test switches."""
    data = entry.runtime_data
    async_add_entities(
        [
            TexecomMaintenanceSwitch(data.coordinator, entry, data.alerting),
            TexecomFireTestSwitch(data.coordinator, entry),
        ]
    )


class TexecomMaintenanceSwitch(TexecomEntity, SwitchEntity):
    """Suppresses fault and connectivity alerts during engineer visits.

    Deliberately does not suppress critical alarm events, and expires on its
    own, because maintenance mode left on after a visit is exactly what gets
    forgotten until the night it matters.
    """

    _attr_name = "Maintenance mode"
    _attr_icon = "mdi:wrench"

    def __init__(self, coordinator: Any, entry: Any, alerting: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "maintenance_mode")
        self._alerting = alerting
        self._cancel_expiry: Any = None

    @property
    def is_on(self) -> bool:
        """Return whether maintenance mode is active."""
        return self._alerting.maintenance_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable maintenance mode with an automatic expiry."""
        self._alerting.maintenance_mode = True
        hours = {**self.entry.data, **self.entry.options}.get(
            CONF_MAINTENANCE_HOURS, DEFAULT_MAINTENANCE_HOURS
        )
        if self._cancel_expiry:
            self._cancel_expiry()
        self._cancel_expiry = async_call_later(
            self.hass, timedelta(hours=hours).total_seconds(), self._expire
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable maintenance mode."""
        self._alerting.maintenance_mode = False
        if self._cancel_expiry:
            self._cancel_expiry()
            self._cancel_expiry = None
        self.async_write_ha_state()

    @callback
    def _expire(self, _now: Any) -> None:
        """Clear maintenance mode and say so."""
        self._alerting.maintenance_mode = False
        self._cancel_expiry = None
        self.async_write_ha_state()
        self.hass.async_create_task(
            self._alerting.async_handle(_expiry_alert(self.entry.title, self.hass))
        )


class TexecomFireTestSwitch(TexecomEntity, SwitchEntity):
    """Suppresses the fire alert for a weekly fire alarm check.

    Deliberately the opposite of maintenance mode, which never touches critical:
    this quiets fire on purpose, so it is ringed with safety. It fails back on,
    the coordinator ending it when the fire link goes quiet after a test or the
    backstop window elapses, and a restart clears it. While on, the fire
    indicator stays off, so the blinds are left alone through the test.
    """

    _attr_name = "Fire test mode"
    _attr_icon = "mdi:fire-alert"

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "fire_test_mode")

    @property
    def is_on(self) -> bool:
        """Return whether fire test mode is active."""
        return self.coordinator.fire_test_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enter fire test mode."""
        self.coordinator.set_fire_test(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Leave fire test mode."""
        self.coordinator.set_fire_test(False)


def _expiry_alert(title: str, _hass: Any) -> Any:
    """Build the maintenance expiry notice."""
    from .const import SEVERITY_FAULT
    from .models import Alert

    return Alert(
        severity=SEVERITY_FAULT,
        headline="Maintenance mode cleared",
        detail=(
            f"Maintenance mode at {title} expired automatically. "
            "Fault and connectivity alerting is live again."
        ),
    )
