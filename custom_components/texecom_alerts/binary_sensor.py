"""Binary sensor platform for Texecom Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TexecomConfigEntry
from .const import SIGNAL_UPDATE
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
        TexecomCoverForceClose(coordinator, entry),
        TexecomCoverForceOpen(coordinator, entry),
        TexecomDataHealthy(coordinator, entry),
        TexecomFire(coordinator, entry),
        TexecomPanelReachable(coordinator, entry),
        TexecomZoneProblem(coordinator, entry),
    ]
    if coordinator.gateway_host:
        entities.append(TexecomSiteReachable(coordinator, entry))
    async_add_entities(entities)

    # Per area cover force helpers, added as each area is discovered, for a
    # cover control automation on a site that part arms its areas separately.
    # Off by default, like the site wide pair, since they are only wanted where
    # blinds follow the alarm.
    added_areas: set[str] = set()

    @callback
    def _add_area_covers() -> None:
        new = [area_id for area_id in coordinator.areas if area_id not in added_areas]
        if not new:
            return
        added_areas.update(new)
        extra: list[TexecomEntity] = []
        for area_id in sorted(new):
            extra.append(TexecomAreaCoverForceClose(coordinator, entry, area_id))
            extra.append(TexecomAreaCoverForceOpen(coordinator, entry, area_id))
        async_add_entities(extra)

    _add_area_covers()
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_UPDATE.format(entry.entry_id), _add_area_covers
        )
    )


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


class TexecomCoverForceClose(TexecomEntity, BinarySensorEntity):
    """Ready made cover force close: on when armed, and never during a fire.

    A convenience for a cover control automation, so blinds can close on arming
    without a template. Point the blueprint's auto_down_force at this. Off by
    default, since it is only wanted where blinds follow the alarm. Uses this
    integration's own armed state, so no arm boolean needs maintaining.
    """

    _attr_name = "Cover force close"
    _attr_icon = "mdi:window-shutter"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "cover_force_close")

    @property
    def is_on(self) -> bool:
        """Return whether covers should be forced closed."""
        return self.coordinator.any_area_armed and not self.coordinator.fire_active


class TexecomCoverForceOpen(TexecomEntity, BinarySensorEntity):
    """Ready made cover force open: on when disarmed, or whenever there is a fire.

    For a cover that should stay open while the site is unarmed, and always open
    on a fire. Point the blueprint's auto_up_force at this. A cover that instead
    follows a schedule when unarmed should point auto_up_force at the Fire sensor
    alone. Off by default; uses this integration's own armed state.
    """

    _attr_name = "Cover force open"
    _attr_icon = "mdi:window-shutter-open"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "cover_force_open")

    @property
    def is_on(self) -> bool:
        """Return whether covers should be forced open."""
        return not self.coordinator.any_area_armed or self.coordinator.fire_active


class TexecomAreaCoverForceClose(TexecomEntity, BinarySensorEntity):
    """Per area cover force close: on when this area is set, never during a fire.

    For a part armed site, so a blind closes when its own area is armed rather
    than when any area is. On through an armed state, an entry or exit, and an
    intruder activation, and off during a fire. Off by default.
    """

    _attr_icon = "mdi:window-shutter"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: Any, entry: Any, area_id: str) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, f"area_{area_id}_cover_force_close")
        self._area_id = area_id
        area = coordinator.areas.get(area_id)
        self._attr_name = f"{area.name if area else area_id} cover force close"

    @property
    def is_on(self) -> bool:
        """Return whether this area's covers should be forced closed."""
        return (
            self.coordinator.area_armed(self._area_id)
            and not self.coordinator.fire_active
        )


class TexecomAreaCoverForceOpen(TexecomEntity, BinarySensorEntity):
    """Per area cover force open: on when this area is disarmed, or during a fire.

    For a blind that stays open while its own area is unarmed, on a part armed
    site, and always open on a fire. Off by default.
    """

    _attr_icon = "mdi:window-shutter-open"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: Any, entry: Any, area_id: str) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, f"area_{area_id}_cover_force_open")
        self._area_id = area_id
        area = coordinator.areas.get(area_id)
        self._attr_name = f"{area.name if area else area_id} cover force open"

    @property
    def is_on(self) -> bool:
        """Return whether this area's covers should be forced open."""
        return (
            not self.coordinator.area_armed(self._area_id)
            or self.coordinator.fire_active
        )


class TexecomFire(TexecomEntity, BinarySensorEntity):
    """On while a real fire is active, and deliberately off during a test.

    The single, test aware source of truth for fire, for automations, the
    blinds and the heating hold to gate on. It follows the fire link and clears
    on an alerting reset, and a fire test never turns it on, so a weekly check
    leaves the blinds alone.
    """

    _attr_name = "Fire"
    _attr_device_class = BinarySensorDeviceClass.SMOKE

    def __init__(self, coordinator: Any, entry: Any) -> None:
        """Initialise."""
        super().__init__(coordinator, entry, "fire")

    @property
    def is_on(self) -> bool:
        """Return whether a real fire is currently active."""
        return self.coordinator.fire_active


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
