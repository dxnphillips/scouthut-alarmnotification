"""Fire must reach the event bus, not only the internal escalation ladder.

The heating integration holds all heating, water and fans off on a fire by
listening on the bus for a texecom_alerts_event with event_type Fire. Both fire
pathways return before the log handler's own bus emit, so these guard that a
fire still reaches the bus as a Fire event however it is detected.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.texecom_alerts.const import DOMAIN, EVENT_TEXECOM
from custom_components.texecom_alerts.coordinator import TexecomCoordinator


def _coordinator(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Scout HQ",
        data={"areas": ["A"], "fire_zones": ["3", "Fire"]},
    )
    entry.add_to_hass(hass)
    return TexecomCoordinator(hass, entry)


def _fire_events(hass) -> list[dict]:
    captured: list[dict] = []
    hass.bus.async_listen(
        EVENT_TEXECOM,
        lambda event: captured.append(event.data),
    )
    return captured


async def test_fire_zone_active_fires_bus_event(hass):
    """A configured fire zone going active reaches the bus as a Fire event."""
    coordinator = _coordinator(hass)
    events = _fire_events(hass)

    coordinator._evaluate_zone({"name": "Fire", "number": 3, "status": "active"})
    await hass.async_block_till_done()

    fires = [e for e in events if e.get("event_type") == "Fire"]
    assert fires, "fire zone activation did not emit a Fire event on the bus"
    assert fires[0]["severity"] == "critical"


async def test_auxiliary_alarm_on_fire_zone_fires_bus_event(hass):
    """An Auxiliary alarm on a fire zone reaches the bus as a Fire event.

    This is how the real Premier Elite reports the fire link, with the zone
    number in the parameter field rather than as a Fire event type.
    """
    coordinator = _coordinator(hass)
    events = _fire_events(hass)

    msg = SimpleNamespace(
        payload=json.dumps(
            {"type": "Auxiliary", "description": "Auxiliary Alarm", "parameter": 3}
        )
    )
    coordinator._handle_log(msg)
    await hass.async_block_till_done()

    fires = [e for e in events if e.get("event_type") == "Fire"]
    assert fires, "Auxiliary alarm on a fire zone did not emit a Fire event"


async def test_fire_log_event_fires_bus_event(hass):
    """A proper Fire log event reaches the bus as a Fire event."""
    coordinator = _coordinator(hass)
    events = _fire_events(hass)

    msg = SimpleNamespace(payload=json.dumps({"type": "Fire", "description": "Fire"}))
    coordinator._handle_log(msg)
    await hass.async_block_till_done()

    fires = [e for e in events if e.get("event_type") == "Fire"]
    assert fires, "Fire log event did not emit a Fire event on the bus"
