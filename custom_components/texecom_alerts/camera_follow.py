"""Make camera analytics switches follow the armed state on a schedule.

This is the one place the integration drives another integration's switches
rather than just reporting state, so it is kept deliberately narrow. It owns no
state of its own beyond the last target it applied, reads the armed state from
the coordinator, and only ever turns the switches the site named on or off.

Two groups, both opt in and empty by default:

- Detection switches follow "armed or night": on while any area is armed, and
  on overnight even while disarmed so an empty building is still watched, off
  during the day once disarmed. This is line crossing, intrusion and the like.
- Inverted switches are the mirror, on only while fully disarmed, for a camera
  whose own audible warning buzzer should sound while the site is open and stay
  quiet once armed. The night window does not apply to these.

A command to a camera analytics switch can be dropped, so each change is
verified and the laggards retried a few times, and a notification is raised if
any switch will not follow, exactly as the automation this replaces did.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import time
from typing import Any

from homeassistant.components import logbook, persistent_notification
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CAMERA_FAILURE_NOTIFICATION,
    CAMERA_RETRY_COUNT,
    CAMERA_RETRY_DELAY,
    CONF_CAMERA_DETECTION_SWITCHES,
    CONF_CAMERA_FOLLOW,
    CONF_CAMERA_INVERTED_SWITCHES,
    CONF_CAMERA_NIGHT_END,
    CONF_CAMERA_NIGHT_START,
    DEFAULT_CAMERA_FOLLOW,
    DEFAULT_CAMERA_NIGHT_END,
    DEFAULT_CAMERA_NIGHT_START,
    DOMAIN,
    SIGNAL_UPDATE,
)

_LOGGER = logging.getLogger(__name__)

_SWITCH_DOMAIN = "switch"


def _in_window(now: time, start: time, end: time) -> bool:
    """Return whether a time of day falls in a window that may wrap midnight.

    A start equal to the end is treated as an empty window rather than a whole
    day, so a misconfiguration cannot pin detection on around the clock.
    """
    if start == end:
        return False
    if start < end:
        return start <= now < end
    # Wraps midnight, such as the default 22:00 to 08:00.
    return now >= start or now < end


class CameraFollowController:
    """Drive the configured camera switches from the armed state and clock."""

    def __init__(self, hass: HomeAssistant, entry: Any, coordinator: Any) -> None:
        """Initialise from the config entry, reading options over data."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        opts = {**entry.data, **entry.options}
        self._enabled: bool = bool(opts.get(CONF_CAMERA_FOLLOW, DEFAULT_CAMERA_FOLLOW))
        self._detection: list[str] = list(
            opts.get(CONF_CAMERA_DETECTION_SWITCHES) or []
        )
        self._inverted: list[str] = list(opts.get(CONF_CAMERA_INVERTED_SWITCHES) or [])
        self._night_start = dt_util.parse_time(
            str(opts.get(CONF_CAMERA_NIGHT_START) or "")
        ) or dt_util.parse_time(DEFAULT_CAMERA_NIGHT_START)
        self._night_end = dt_util.parse_time(
            str(opts.get(CONF_CAMERA_NIGHT_END) or "")
        ) or dt_util.parse_time(DEFAULT_CAMERA_NIGHT_END)
        self._unsubs: list[Any] = []
        self._lock = asyncio.Lock()
        # The last target applied, so a burst of coordinator updates that does
        # not change the armed state does not re-drive the switches every time.
        self._last_detection: bool | None = None
        self._last_inverted: bool | None = None

    async def async_setup(self) -> None:
        """Start following, unless the feature is off or names no switches."""
        if not self._enabled or not (self._detection or self._inverted):
            return

        # Any coordinator update may carry an arm or disarm, so re-evaluate on
        # each. The apply is cheap and only drives switches on a real change.
        self._unsubs.append(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(self.entry.entry_id),
                self._handle_update,
            )
        )
        # The night window boundaries are a clock event, not a panel event, so
        # they need their own daily triggers to flip detection at 22:00 and
        # 08:00 even when nothing arms or disarms.
        for moment in (self._night_start, self._night_end):
            if moment is not None:
                self._unsubs.append(
                    async_track_time_change(
                        self.hass,
                        self._handle_time,
                        hour=moment.hour,
                        minute=moment.minute,
                        second=moment.second,
                    )
                )

        # Settle the switches to the right state on start. If Home Assistant is
        # still coming up the switch entities may not exist yet, so wait for the
        # started event; otherwise, on a reload or an options change, do it now.
        if self.hass.state is CoreState.running:
            self.hass.async_create_task(self._apply(force=True))
        else:
            self._unsubs.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._handle_started
                )
            )

    async def async_shutdown(self) -> None:
        """Stop following and release every listener."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _handle_update(self) -> None:
        """React to a coordinator update, applying only on a real change."""
        self.hass.async_create_task(self._apply(force=False))

    @callback
    def _handle_time(self, _now: Any) -> None:
        """React to a night window boundary, forcing the switches to follow."""
        self.hass.async_create_task(self._apply(force=True))

    @callback
    def _handle_started(self, _event: Any) -> None:
        """Settle the switches once Home Assistant has finished starting."""
        self.hass.async_create_task(self._apply(force=True))

    def _targets(self) -> tuple[bool, bool]:
        """Return the desired on state for the detection and inverted groups."""
        armed = self.coordinator.any_area_armed
        night = False
        if self._night_start is not None and self._night_end is not None:
            night = _in_window(dt_util.now().time(), self._night_start, self._night_end)
        detection_on = armed or night
        inverted_on = not armed
        return detection_on, inverted_on

    async def _apply(self, force: bool) -> None:
        """Drive both groups to their target, if the target has moved."""
        async with self._lock:
            detection_on, inverted_on = self._targets()
            if (
                not force
                and detection_on == self._last_detection
                and inverted_on == self._last_inverted
            ):
                return
            self._last_detection = detection_on
            self._last_inverted = inverted_on

            stuck = await self._drive(self._detection, detection_on)
            await self._drive(self._inverted, inverted_on)
            self._report_detection(stuck)

    async def _drive(self, entities: list[str], desired_on: bool) -> list[str]:
        """Turn a group on or off, verifying and retrying the laggards.

        Returns the entities that would not follow, so the caller can raise a
        notification. A switch missing from the state machine counts as stuck,
        rather than aborting the whole group as a batched service call would.
        """
        if not entities:
            return []
        service = SERVICE_TURN_ON if desired_on else SERVICE_TURN_OFF
        desired_state = STATE_ON if desired_on else STATE_OFF

        await self._call(service, [e for e in entities if self.hass.states.get(e)])
        for _ in range(CAMERA_RETRY_COUNT):
            laggards = self._laggards(entities, desired_state)
            if not laggards:
                return []
            await asyncio.sleep(CAMERA_RETRY_DELAY)
            await self._call(service, [e for e in laggards if self.hass.states.get(e)])
        return self._laggards(entities, desired_state)

    def _laggards(self, entities: list[str], desired_state: str) -> list[str]:
        """Return the entities not yet at the desired state, missing ones too."""
        stuck = []
        for entity_id in entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state != desired_state:
                stuck.append(entity_id)
        return stuck

    async def _call(self, service: str, entities: list[str]) -> None:
        """Call a switch service, swallowing errors so one bad entity is not fatal."""
        if not entities:
            return
        try:
            await self.hass.services.async_call(
                _SWITCH_DOMAIN,
                service,
                {"entity_id": entities},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Camera follow could not %s %s: %s", service, entities, err)

    def _report_detection(self, stuck: list[str]) -> None:
        """Raise or clear the notification for detection switches that stuck."""
        if stuck:
            joined = ", ".join(stuck)
            persistent_notification.async_create(
                self.hass,
                f"Detection should have followed the alarm but these switches "
                f"did not: {joined}",
                title="Camera analytics did not follow",
                notification_id=CAMERA_FAILURE_NOTIFICATION,
            )
            logbook.async_log_entry(
                self.hass,
                "Camera analytics",
                f"Failed to set detection on: {joined}",
                DOMAIN,
            )
        else:
            persistent_notification.async_dismiss(
                self.hass, CAMERA_FAILURE_NOTIFICATION
            )
