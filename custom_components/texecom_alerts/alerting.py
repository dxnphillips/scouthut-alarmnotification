"""The escalation engine.

Push, then SMS, then voice call, repeating until somebody acknowledges or
the ladder is exhausted. Every provider call is wrapped, because a provider
outage in round two must not stop the voice calls in round three.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ACTION_ACK,
    ACTION_ATTEND,
    CONF_LADDER_ROUNDS,
    CONF_PUSH_SERVICE,
    CONF_PUSH_SERVICES,
    CONF_RECIPIENTS,
    CONF_ROUND_SECONDS,
    CONF_SMS_SERVICE,
    CONF_VOICE_SERVICE,
    DEFAULT_LADDER_ROUNDS,
    DEFAULT_ROUND_SECONDS,
    ESCALATION_ACKNOWLEDGED,
    ESCALATION_EXHAUSTED,
    ESCALATION_IDLE,
    ESCALATION_RUNNING,
    SEVERITY_ACTIVITY,
    SEVERITY_CRITICAL,
    SIGNAL_UPDATE,
)
from .models import Alert

_LOGGER = logging.getLogger(__name__)

EVENT_MOBILE_ACTION = "mobile_app_notification_action"


class AlertingEngine:
    """Turns Alerts into notifications, calls and an escalation ladder."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: Any,
    ) -> None:
        """Initialise the engine."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator

        self.state: str = ESCALATION_IDLE
        self.current: Alert | None = None
        self.acknowledged_by: str | None = None
        self.maintenance_mode: bool = False

        self._task: asyncio.Task | None = None
        self._ack = asyncio.Event()
        self._unsubs: list[Any] = []

    # ------------------------------------------------------------------
    # Options, re-read on every send so an options flow change takes effect
    # without a restart
    # ------------------------------------------------------------------

    def _opt(self, key: str, default: Any = None) -> Any:
        return {**self.entry.data, **self.entry.options}.get(key, default)

    def _push_services(self) -> list[str]:
        """Return every push service to notify.

        Several phones can be chosen in the UI, so this is a list. The older
        single value key is honoured so an entry configured before the list
        existed keeps working.
        """
        raw = self._opt(CONF_PUSH_SERVICES)
        if not raw:
            legacy = self._opt(CONF_PUSH_SERVICE)
            raw = [legacy] if legacy else []
        if isinstance(raw, str):
            raw = [raw]
        return [service for service in raw if service]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Listen for acknowledgement actions from the companion app."""
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_MOBILE_ACTION, self._handle_action)
        )
        self.coordinator.add_alert_listener(self.async_handle)

    async def async_shutdown(self) -> None:
        """Cancel any running ladder and stop listening."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._task and not self._task.done():
            self._task.cancel()

    @callback
    def _notify_entities(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    @callback
    def _handle_action(self, event: Event) -> None:
        action = event.data.get("action")
        if action not in (ACTION_ACK, ACTION_ATTEND):
            return
        self.acknowledge(
            by=event.data.get("sourceDeviceName") or "a keyholder",
            attending=action == ACTION_ATTEND,
        )

    def acknowledge(self, by: str = "a keyholder", attending: bool = False) -> None:
        """Stop the ladder and tell everyone else who responded."""
        if self.state != ESCALATION_RUNNING:
            return
        self.acknowledged_by = by
        self.state = ESCALATION_ACKNOWLEDGED
        self._ack.set()
        self._notify_entities()
        verb = "is attending" if attending else "acknowledged the alert"
        self.hass.async_create_task(
            self._send_push(
                Alert(
                    severity=SEVERITY_ACTIVITY,
                    headline="Alert acknowledged",
                    detail=f"{by} {verb}.",
                    tag="texecom_critical",
                )
            )
        )

    async def async_handle(self, alert: Alert) -> None:
        """Route an alert according to severity."""
        if alert.severity == SEVERITY_CRITICAL:
            # Maintenance mode never suppresses a critical alert.
            await self._start_ladder(alert)
            return

        if self.maintenance_mode:
            _LOGGER.debug("Suppressed by maintenance mode: %s", alert.headline)
            return

        await self._send_push(alert)
        if alert.sms_worthy:
            await self._send_sms(alert)

    # ------------------------------------------------------------------
    # The ladder
    # ------------------------------------------------------------------

    async def _start_ladder(self, alert: Alert) -> None:
        """Start escalating, or send a supplementary push if already running.

        A second area triggering while the ladder runs should not start a
        competing ladder that has everyone's phone ringing twice over.
        """
        if self.state == ESCALATION_RUNNING:
            supplementary = Alert(
                severity=SEVERITY_CRITICAL,
                headline="FURTHER ACTIVATION",
                detail=alert.detail,
                silent=alert.silent,
                tag="texecom_critical_second",
            )
            await self._send_push(supplementary)
            return

        self.current = alert
        self.acknowledged_by = None
        self.state = ESCALATION_RUNNING
        self._ack = asyncio.Event()
        self._notify_entities()
        self._task = self.hass.async_create_task(self._run_ladder(alert))

    async def _run_ladder(self, alert: Alert) -> None:
        rounds = int(self._opt(CONF_LADDER_ROUNDS, DEFAULT_LADDER_ROUNDS))
        wait = int(self._opt(CONF_ROUND_SECONDS, DEFAULT_ROUND_SECONDS))

        try:
            for index in range(1, rounds + 1):
                if index == 1:
                    await self._send_push(alert)
                elif index == 2:
                    await self._send_sms(alert)
                else:
                    await self._send_voice(alert)
                    await self._send_push(alert)

                try:
                    async with asyncio.timeout(wait):
                        await self._ack.wait()
                    return
                except TimeoutError:
                    continue

            self.state = ESCALATION_EXHAUSTED
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Escalation ladder failed")
            self.state = ESCALATION_EXHAUSTED
        finally:
            if self.state == ESCALATION_RUNNING:
                self.state = ESCALATION_EXHAUSTED
            self._notify_entities()

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    async def _call(self, service: str | None, data: dict[str, Any]) -> None:
        """Call a notify service, swallowing provider failures."""
        if not service:
            return
        if "." not in service:
            service = f"notify.{service}"
        domain, name = service.split(".", 1)
        try:
            await self.hass.services.async_call(domain, name, data, blocking=True)
        except Exception:
            _LOGGER.exception("Notification via %s failed", service)

    async def _send_push(self, alert: Alert) -> None:
        critical = alert.severity == SEVERITY_CRITICAL
        activity = alert.severity == SEVERITY_ACTIVITY
        tag = alert.tag or (
            "texecom_critical"
            if critical
            else "texecom_info"
            if activity
            else "texecom_fault"
        )
        # A separate Android channel per class so a keyholder can mute activity
        # on their own phone without touching the alarm and fault channels.
        if critical:
            channel = "Alarm"
        elif activity:
            channel = "Alarm Activity"
        else:
            channel = "Alarm Faults"

        data: dict[str, Any] = {
            "tag": tag,
            "channel": channel,
            "ttl": 0,
            "priority": "high",
        }

        if critical and not alert.silent:
            data.update(
                {
                    "importance": "max",
                    "persistent": True,
                    "sticky": True,
                    "push": {
                        "interruption_level": "critical",
                        "sound": {"name": "default", "critical": 1, "volume": 1.0},
                    },
                }
            )
            title = alert.headline
            message = alert.detail
        elif critical and alert.silent:
            # Silent panic and duress. Bland title, body hidden from the lock
            # screen, no audible tone.
            data.update(
                {
                    "importance": "max",
                    "visibility": "private",
                    "push": {"interruption_level": "time-sensitive"},
                }
            )
            title = "Site status update"
            message = alert.detail
        else:
            data.update({"push": {"interruption_level": "time-sensitive"}})
            title = alert.headline
            message = alert.detail

        if critical:
            data["actions"] = [
                {"action": ACTION_ACK, "title": "Acknowledge"},
                {"action": ACTION_ATTEND, "title": "Attending"},
            ]

        payload = {"title": title, "message": message, "data": data}
        for service in self._push_services():
            await self._call(service, payload)

    async def _send_sms(self, alert: Alert) -> None:
        recipients = self._opt(CONF_RECIPIENTS) or []
        payload: dict[str, Any] = {
            "message": f"{alert.headline}. {alert.detail}",
        }
        if recipients:
            payload["target"] = list(recipients)
        await self._call(self._opt(CONF_SMS_SERVICE), payload)

    async def _send_voice(self, alert: Alert) -> None:
        # The message repeats itself because people answer halfway through
        # the first sentence.
        spoken = (
            f"{alert.headline}. {alert.detail} "
            f"Repeating. {alert.headline}. {alert.detail}"
        )
        recipients = self._opt(CONF_RECIPIENTS) or []
        payload: dict[str, Any] = {"message": spoken}
        if recipients:
            payload["target"] = list(recipients)
        await self._call(self._opt(CONF_VOICE_SERVICE), payload)

    # ------------------------------------------------------------------
    # Manual
    # ------------------------------------------------------------------

    async def async_test(self) -> None:
        """Run the full ladder with an unmistakably marked test alert."""
        await self._start_ladder(
            Alert(
                severity=SEVERITY_CRITICAL,
                headline=f"TEST ONLY, {self.entry.title} alarm",
                detail=(
                    "This is a test of the alarm alerting chain. "
                    "No action is required. Acknowledge to stop the test."
                ),
            )
        )

    def reset(self) -> None:
        """Return the engine to idle."""
        if self._task and not self._task.done():
            self._task.cancel()
        self.state = ESCALATION_IDLE
        self.current = None
        self.acknowledged_by = None
        self._notify_entities()
