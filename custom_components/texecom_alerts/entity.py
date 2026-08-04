"""Base entity for the Texecom Alerts integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import TexecomCoordinator


class TexecomEntity(Entity):
    """Base entity that redraws when the coordinator dispatches."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TexecomCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialise the entity."""
        self.coordinator = coordinator
        self.entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Texecom",
            model="Premier Elite",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(self.entry.entry_id),
                self.async_write_ha_state,
            )
        )
