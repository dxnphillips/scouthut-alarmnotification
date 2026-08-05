"""Sensor platform for Texecom Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TexecomConfigEntry
from .const import SIGNAL_UPDATE
from .entity import TexecomEntity

POWER_KEYS: dict[str, tuple[str, str, SensorDeviceClass]] = {
    "panel_voltage": (
        "Panel voltage",
        UnitOfElectricPotential.VOLT,
        SensorDeviceClass.VOLTAGE,
    ),
    "battery_voltage": (
        "Battery voltage",
        UnitOfElectricPotential.VOLT,
        SensorDeviceClass.VOLTAGE,
    ),
    "panel_current": (
        "Panel current",
        UnitOfElectricCurrent.MILLIAMPERE,
        SensorDeviceClass.CURRENT,
    ),
    "battery_charging_current": (
        "Battery charging current",
        UnitOfElectricCurrent.MILLIAMPERE,
        SensorDeviceClass.CURRENT,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TexecomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    data = entry.runtime_data
    coordinator = data.coordinator

    entities: list[TexecomEntity] = [
        TexecomSystemStateSensor(coordinator, entry),
        TexecomLastActivationSensor(coordinator, entry),
        TexecomLastLogSensor(coordinator, entry),
        TexecomEscalationSensor(coordinator, entry, data.alerting),
    ]
    entities.extend(TexecomPowerSensor(coordinator, entry, key) for key in POWER_KEYS)
    async_add_entities(entities)

    # Areas arrive asynchronously over MQTT, so add a sensor per area as each is
    # discovered rather than only for those present at setup. Otherwise an area
    # whose retained message lands a moment after setup never gets an entity,
    # and any remembered from a previous run sits there unavailable.
    added: set[str] = set()

    @callback
    def _add_areas() -> None:
        new = [area_id for area_id in coordinator.areas if area_id not in added]
        if not new:
            return
        added.update(new)
        async_add_entities(
            TexecomAreaSensor(coordinator, entry, area_id) for area_id in sorted(new)
        )

    _add_areas()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_UPDATE.format(entry.entry_id), _add_areas)
    )


class TexecomAreaSensor(TexecomEntity, SensorEntity):
    """State of one panel area."""

    _attr_icon = "mdi:shield-home"

    def __init__(self, coordinator: Any, entry: Any, area_id: str) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, f"area_{area_id}")
        self._area_id = area_id
        area = coordinator.areas.get(area_id)
        self._attr_name = area.name if area else f"Area {area_id}"

    @property
    def native_value(self) -> str | None:
        """Return the area status."""
        area = self.coordinator.areas.get(self._area_id)
        return area.status if area else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the detail carried alongside the status."""
        area = self.coordinator.areas.get(self._area_id)
        if not area:
            return {}
        return {
            "area_id": area.area_id,
            "area_number": area.number,
            "last_active_zone": area.last_active_zone,
            "last_active_zone_number": area.last_active_zone_number,
            "last_triggered": area.last_triggered,
        }


class TexecomSystemStateSensor(TexecomEntity, SensorEntity):
    """Combined state across every area."""

    _attr_name = "System state"
    _attr_icon = "mdi:shield-half-full"

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "system_state")

    @property
    def native_value(self) -> str:
        """Return the combined state."""
        return self.coordinator.system_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return each area separately."""
        return {a.name: a.status for a in self.coordinator.areas.values()}


class TexecomLastActivationSensor(TexecomEntity, SensorEntity):
    """The zone that caused the most recent activation.

    Held separately from the area sensor because the area moves on to
    in_entry and then disarmed within seconds of somebody walking in, taking
    the zone information with it.
    """

    _attr_name = "Last activation zone"
    _attr_icon = "mdi:alarm-light"

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "last_activation")

    @property
    def native_value(self) -> str | None:
        """Return the zone name."""
        area = self.coordinator.last_activation
        if not area:
            return None
        return area.last_active_zone or "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return where and when."""
        area = self.coordinator.last_activation
        if not area:
            return {}
        return {
            "area_name": area.name,
            "area_id": area.area_id,
            "zone_number": area.last_active_zone_number,
            "activated_at": area.last_triggered,
        }


class TexecomLastLogSensor(TexecomEntity, SensorEntity):
    """The most recent panel log event."""

    _attr_name = "Last log event"
    _attr_icon = "mdi:script-text"

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "last_log")

    @property
    def native_value(self) -> str | None:
        """Return a readable label for the most recent event."""
        event = self.coordinator.last_log
        return event.label if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full event detail, raw event type included."""
        event = self.coordinator.last_log
        return event.as_event_data() if event else {}


class TexecomEscalationSensor(TexecomEntity, SensorEntity):
    """Where the escalation ladder has got to."""

    _attr_name = "Escalation state"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator: Any, entry: Any, alerting: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "escalation")
        self._alerting = alerting

    @property
    def native_value(self) -> str:
        """Return the ladder state."""
        return self._alerting.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return what is being escalated and who responded."""
        current = self._alerting.current
        return {
            "headline": current.headline if current else None,
            "detail": current.detail if current else None,
            "acknowledged_by": self._alerting.acknowledged_by,
        }


class TexecomPowerSensor(TexecomEntity, SensorEntity):
    """One value from the panel power topic."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: Any, entry: Any, key: str) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, key)
        name, unit, device_class = POWER_KEYS[key]
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._power_key = key

    @property
    def native_value(self) -> float | None:
        """Return the reading."""
        return self.coordinator.power.get(self._power_key)

    @property
    def available(self) -> bool:
        """Unavailable rather than stale when the bridge is down."""
        return bool(self.coordinator.bridge_online)
