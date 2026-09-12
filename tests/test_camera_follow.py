"""Camera analytics following the armed state.

The one place the integration drives another integration's switches, so the
tests pin the two things that would be dangerous to get wrong: the overnight
window maths, and that the feature touches nothing at all until a site opts in.
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.texecom_alerts.camera_follow import (
    CameraFollowController,
    _in_window,
)
from custom_components.texecom_alerts.const import DOMAIN


def _controller(hass, options: dict, armed: bool, fire: bool = False):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Scout HQ",
        data={"areas": ["A"]},
        options=options,
    )
    entry.add_to_hass(hass)
    coordinator = SimpleNamespace(any_area_armed=armed, fire_active=fire)
    return CameraFollowController(hass, entry, coordinator)


def test_night_window_wraps_midnight() -> None:
    """The default 22:00 to 08:00 window is on across midnight, off by day."""
    start, end = time(22, 0), time(8, 0)
    assert _in_window(time(23, 30), start, end) is True
    assert _in_window(time(2, 0), start, end) is True
    assert _in_window(time(7, 59), start, end) is True
    assert _in_window(time(8, 0), start, end) is False
    assert _in_window(time(12, 0), start, end) is False
    assert _in_window(time(21, 59), start, end) is False


def test_daytime_window_does_not_wrap() -> None:
    """A start before the end is a plain within the day window."""
    start, end = time(8, 0), time(22, 0)
    assert _in_window(time(12, 0), start, end) is True
    assert _in_window(time(7, 59), start, end) is False
    assert _in_window(time(22, 0), start, end) is False


def test_equal_bounds_are_an_empty_window() -> None:
    """Equal bounds must never pin detection on around the clock."""
    assert _in_window(time(12, 0), time(9, 0), time(9, 0)) is False


async def test_targets_follow_the_armed_state(hass):
    """Armed forces detection on and the inverted buzzer off, and the reverse."""
    # Night window cleared, so only the armed state decides, deterministically.
    armed = _controller(hass, {"camera_follow": True}, armed=True)
    armed._night_start = None
    armed._night_end = None
    assert armed._targets() == (True, False)

    disarmed = _controller(hass, {"camera_follow": True}, armed=False)
    disarmed._night_start = None
    disarmed._night_end = None
    assert disarmed._targets() == (False, True)


async def test_fire_forces_detection_on(hass):
    """A real fire forces detection on even while disarmed and out of hours."""
    controller = _controller(hass, {"camera_follow": True}, armed=False, fire=True)
    controller._night_start = None
    controller._night_end = None
    detection_on, inverted_on = controller._targets()
    assert detection_on is True
    # A fire does not touch the inverted group, which still follows arm only.
    assert inverted_on is True


async def test_fire_force_can_be_turned_off(hass):
    """With fire forcing disabled, a fire does not turn detection on."""
    controller = _controller(
        hass,
        {"camera_follow": True, "camera_fire_force": False},
        armed=False,
        fire=True,
    )
    controller._night_start = None
    controller._night_end = None
    assert controller._targets() == (False, True)


async def test_disabled_feature_touches_nothing(hass):
    """With the feature off, setup registers no listeners and drives no switch."""
    controller = _controller(
        hass,
        {"camera_follow": False, "camera_detection_switches": ["switch.analytics"]},
        armed=True,
    )
    await controller.async_setup()
    assert controller._unsubs == []


async def test_enabled_without_switches_touches_nothing(hass):
    """Enabled but with no switches named is inert, so nothing is driven."""
    controller = _controller(hass, {"camera_follow": True}, armed=True)
    await controller.async_setup()
    assert controller._unsubs == []
