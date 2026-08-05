"""The Texecom Alerts integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .alerting import AlertingEngine
from .const import CONF_WEBHOOK_ID, DOMAIN, PLATFORMS
from .coordinator import TexecomCoordinator
from .webhook_ack import async_register_webhook, async_unregister_webhook

_LOGGER = logging.getLogger(__name__)

SERVICE_TEST = "test_alerts"
SERVICE_ACK = "acknowledge"
SERVICE_RESET = "reset"

SERVICE_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})


@dataclass
class TexecomData:
    """Runtime data for a config entry."""

    coordinator: TexecomCoordinator
    alerting: AlertingEngine


type TexecomConfigEntry = ConfigEntry[TexecomData]


async def async_setup_entry(hass: HomeAssistant, entry: TexecomConfigEntry) -> bool:
    """Set up Texecom Alerts from a config entry."""
    # Give the entry a stable webhook id if it predates phone acknowledgement.
    # Done before the update listener is added, so it does not trigger a reload.
    if not entry.data.get(CONF_WEBHOOK_ID):
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_WEBHOOK_ID: webhook.async_generate_id()},
        )

    coordinator = TexecomCoordinator(hass, entry)
    alerting = AlertingEngine(hass, entry, coordinator)

    await alerting.async_setup()
    await coordinator.async_setup()

    entry.runtime_data = TexecomData(coordinator=coordinator, alerting=alerting)
    async_register_webhook(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TexecomConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_unregister_webhook(hass, entry)
        await entry.runtime_data.coordinator.async_shutdown()
        await entry.runtime_data.alerting.async_shutdown()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: TexecomConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register the integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_TEST):
        return

    def _entries(call: ServiceCall) -> list[TexecomConfigEntry]:
        entry_id = call.data.get("entry_id")
        entries = hass.config_entries.async_entries(DOMAIN)
        if entry_id:
            return [e for e in entries if e.entry_id == entry_id]
        return list(entries)

    async def _test(call: ServiceCall) -> None:
        for entry in _entries(call):
            await entry.runtime_data.alerting.async_test()

    async def _ack(call: ServiceCall) -> None:
        for entry in _entries(call):
            entry.runtime_data.alerting.acknowledge(by="a service call")

    async def _reset(call: ServiceCall) -> None:
        for entry in _entries(call):
            entry.runtime_data.alerting.reset()

    hass.services.async_register(DOMAIN, SERVICE_TEST, _test, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ACK, _ack, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET, _reset, schema=SERVICE_SCHEMA)
