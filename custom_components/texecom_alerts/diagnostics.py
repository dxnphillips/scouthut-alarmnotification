"""Diagnostics for Texecom Alerts."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import TexecomConfigEntry
from .const import (
    CONF_GATEWAY_HOST,
    CONF_PANEL_HOST,
    CONF_RECIPIENTS,
    CONF_WEBHOOK_ID,
)

REDACT = {CONF_RECIPIENTS, CONF_PANEL_HOST, CONF_GATEWAY_HOST, CONF_WEBHOOK_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TexecomConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics."""
    coordinator = entry.runtime_data.coordinator
    alerting = entry.runtime_data.alerting

    return {
        "config": async_redact_data({**entry.data, **entry.options}, REDACT),
        "state": {
            "system_state": coordinator.system_state,
            "any_area_armed": coordinator.any_area_armed,
            "bridge_online": coordinator.bridge_online,
            "site_reachable": coordinator.site_reachable,
            "panel_reachable": coordinator.panel_reachable,
            "data_healthy": coordinator.data_healthy,
            "last_message": str(coordinator.last_message),
            "areas": {k: asdict(v) for k, v in coordinator.areas.items()},
            "power": coordinator.power,
        },
        "alerting": {
            "state": alerting.state,
            "maintenance_mode": alerting.maintenance_mode,
            "acknowledged_by": alerting.acknowledged_by,
        },
    }
