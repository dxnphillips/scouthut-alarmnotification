"""Binary sensor platform for Texecom Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TexecomConfigEntry
from .entity import TexecomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TexecomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data.coordinator
    entities: list[TexecomEntity] = [
        TexecomAnyArmed(coordinator, entry),
        TexecomBridge(coordinator, entry),
        TexecomDataHealthy(coordinator, entry),
        TexecomPanelReachable(coordinator, entry),
        TexecomZoneProblem(coordinator, entry),
    ]
    if coordinator.gateway_host:
        entities.append(TexecomSiteReachable(coordinator, entry))
    async_add_entities(entities)


class TexecomAnyArmed(TexecomEntity, BinarySensorEntity):
    """True when any area is armed in any form."""

    _attr_name = "Any area armed"
    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "any_armed")

    @property
    def is_on(self) -> bool:
        """Return whether anything is armed."""
        return self.coordinator.any_area_armed


class TexecomBridge(TexecomEntity, BinarySensorEntity):
    """The bridge Last Will and Testament.

    Where the bridge and the broker sit together this rarely fires, so treat
    it as meaning the bridge process itself has stopped rather than that the
    panel link has failed.
    """

    _attr_name = "Bridge"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "bridge")

    @property
    def is_on(self) -> bool | None:
        """Return whether the bridge is connected to the broker."""
        return self.coordinator.bridge_online


class TexecomDataHealthy(TexecomEntity, BinarySensorEntity):
    """Problem sensor for a bridge that is up but silent.

    The primary failure detector on any topology where the bridge reconnects
    rather than exiting.
    """

    _attr_name = "Data stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "data_stale")

    @property
    def is_on(self) -> bool:
        """Return True when the data has gone stale."""
        return not self.coordinator.data_healthy

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return when the last panel message arrived."""
        return {"last_message": self.coordinator.last_message}


class TexecomSiteReachable(TexecomEntity, BinarySensorEntity):
    """TCP reachability of the site gateway."""

    _attr_name = "Site reachable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "site_reachable")

    @property
    def is_on(self) -> bool | None:
        """Return whether the site answers."""
        return self.coordinator.site_reachable


class TexecomPanelReachable(TexecomEntity, BinarySensorEntity):
    """Whether the panel is in live contact, derived from data freshness.

    Not a TCP probe. The ComIP allows a single connection and the bridge holds
    it, so a probe would always be refused. On instead means data is still
    flowing from the panel through the bridge.
    """

    _attr_name = "Panel reachable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "panel_reachable")

    @property
    def is_on(self) -> bool | None:
        """Return whether the panel is in contact."""
        return self.coordinator.panel_reachable


class TexecomZoneProblem(TexecomEntity, BinarySensorEntity):
    """On while any zone is in a tamper or fault condition.

    Covers zones, such as a permanent tamper zone, whose trouble shows only on
    the zone feed rather than as a panel log event or an area activation.
    """

    _attr_name = "Zone problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "zone_problem")

    @property
    def is_on(self) -> bool:
        """Return whether any zone is tampered or faulted."""
        return self.coordinator.zone_problem

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the zones currently in trouble and their condition."""
        return {"zones": dict(self.coordinator.zone_problems)}
