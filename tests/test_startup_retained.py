"""A restart must not alert for state that has not actually changed.

The bridge retains area and log state, so on a restart the broker replays it
the moment the coordinator resubscribes. That replay is the state as it stood
before, not a live change, so it must seed the coordinator without raising an
arm or disarm alert or re-raising a fire. Only a live message, delivered with
the retain flag clear, alerts.
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


def _alerts(coordinator) -> list:
    captured: list = []

    async def _listen(alert):
        captured.append(alert)

    coordinator.add_alert_listener(_listen)
    return captured


def _area_msg(status: str, retain: bool):
    return SimpleNamespace(
        payload=json.dumps({"id": "A", "name": "Main", "number": 1, "status": status}),
        retain=retain,
    )


async def test_retained_armed_area_seeds_without_alerting(hass):
    """A retained armed area on restart sets the state but raises no alert."""
    coordinator = _coordinator(hass)
    alerts = _alerts(coordinator)

    coordinator._handle_area(_area_msg("full_armed", retain=True))
    await hass.async_block_till_done()

    assert coordinator.areas["A"].status == "full_armed"
    assert not alerts, "a retained armed state alerted on restart"


async def test_live_arm_still_alerts(hass):
    """A genuine arm, delivered live with retain clear, still alerts."""
    coordinator = _coordinator(hass)
    alerts = _alerts(coordinator)

    # Seed the disarmed state as the broker would on restart.
    coordinator._handle_area(_area_msg("disarmed", retain=True))
    await hass.async_block_till_done()
    assert not alerts

    # Then a live arm arrives.
    coordinator._handle_area(_area_msg("full_armed", retain=False))
    await hass.async_block_till_done()

    assert any("armed" in a.headline for a in alerts), [a.headline for a in alerts]


async def test_retained_fire_log_does_not_re_raise_on_restart(hass):
    """A retained Fire log on restart must not re-raise a fire or hit the bus."""
    coordinator = _coordinator(hass)
    alerts = _alerts(coordinator)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_TEXECOM, lambda event: events.append(event.data))

    msg = SimpleNamespace(
        payload=json.dumps({"type": "Fire", "description": "Fire"}),
        retain=True,
    )
    coordinator._handle_log(msg)
    await hass.async_block_till_done()

    assert coordinator.fire_active is False, "a retained Fire latched the indicator"
    assert not [e for e in events if e.get("event_type") == "Fire"], (
        "a retained Fire reached the bus on restart"
    )
    assert not alerts, "a retained Fire raised an alert on restart"
