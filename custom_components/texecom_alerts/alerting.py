"""The escalation engine.

Push, then SMS, then voice call, repeating until somebody acknowledges or
the ladder is exhausted. Every provider call is wrapped, because a provider
outage in round two must not stop the voice calls in round three.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import logbook, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.util import slugify

from .const import (
    ACTION_ACK,
    ACTION_ATTEND,
    CONF_ACK_ENDPOINT,
    CONF_AUTO_PHONES,
    CONF_CRITICAL_SOUND,
    CONF_LADDER_ROUNDS,
    CONF_PHONE_ACK,
    CONF_PUSH_SERVICE,
    CONF_PUSH_SERVICES,
    CONF_RECIPIENTS,
    CONF_ROUND_SECONDS,
    CONF_SMS_SERVICE,
    CONF_TTS_SIREN_SERVICES,
    CONF_VOICE_SERVICE,
    CONF_WEBHOOK_ID,
    DEFAULT_AUTO_PHONES,
    DEFAULT_CRITICAL_SOUND,
    DEFAULT_LADDER_ROUNDS,
    DEFAULT_ROUND_SECONDS,
    DOMAIN,
    ESCALATION_ACKNOWLEDGED,
    ESCALATION_EXHAUSTED,
    ESCALATION_IDLE,
    ESCALATION_RUNNING,
    SEVERITY_ACTIVITY,
    SEVERITY_CRITICAL,
    SIGNAL_UPDATE,
    TAG_ACK,
    TAG_CRITICAL,
    TAG_CRITICAL_SECOND,
    TAG_SIREN,
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

    def _mobile_app_phones(self) -> tuple[list[str], list[str]]:
        """Discover every Companion phone, split into all and Android only.

        The mobile_app integration keeps a config entry per phone carrying its
        device name and operating system, so the notify service and the platform
        can both be worked out without anyone choosing anything.
        """
        everyone: list[str] = []
        android: list[str] = []
        for entry in self.hass.config_entries.async_entries("mobile_app"):
            name = entry.data.get("device_name")
            if not name:
                continue
            service = f"notify.mobile_app_{slugify(name)}"
            everyone.append(service)
            os_name = str(entry.data.get("os_name") or "")
            app_id = str(entry.data.get("app_id") or "")
            if "android" in os_name.lower() or "android" in app_id.lower():
                android.append(service)
        return everyone, android

    def _push_services(self) -> list[str]:
        """Return every push service to notify.

        With automatic phones on, that is every Companion phone. Otherwise it is
        the manual list, with the older single value key honoured so an entry
        configured before the list existed keeps working.
        """
        if self._opt(CONF_AUTO_PHONES, DEFAULT_AUTO_PHONES):
            return self._mobile_app_phones()[0]
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
        # Disarming the panel is a human response, so it stops the ladder.
        self.coordinator.add_disarm_listener(self.stop_for_disarm)

    def _logbook(self, message: str) -> None:
        """Record an entry so the who and when survive after the push clears."""
        logbook.async_log_entry(self.hass, self.entry.title, message, DOMAIN)

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

    def _finish(self, by: str) -> None:
        """Move the ladder out of running and record who ended it."""
        self.acknowledged_by = by
        self.state = ESCALATION_ACKNOWLEDGED
        self._ack.set()
        self._notify_entities()
        # Actively remove the loud, sticky alarm push from every phone. iOS
        # will not let a tag replace a critical notification, so clearing it is
        # the only way to stop it lingering after the alarm is dealt with.
        self.hass.async_create_task(self._clear_critical_push())

    def _tts_siren_services(self) -> list[str]:
        """Return the Android services that also get a max volume spoken siren.

        With automatic phones on, the Android phones are found on their own.
        """
        if self._opt(CONF_AUTO_PHONES, DEFAULT_AUTO_PHONES):
            return self._mobile_app_phones()[1]
        raw = self._opt(CONF_TTS_SIREN_SERVICES) or []
        if isinstance(raw, str):
            raw = [raw]
        return [service for service in raw if service]

    async def _clear_critical_push(self) -> None:
        """Clear the loud alarm notifications from every push device."""
        tags = (TAG_CRITICAL, TAG_CRITICAL_SECOND, TAG_SIREN)
        for service in set(self._push_services()) | set(self._tts_siren_services()):
            for tag in tags:
                await self._call(
                    service,
                    {"message": "clear_notification", "data": {"tag": tag}},
                )

    def acknowledge(self, by: str = "a keyholder", attending: bool = False) -> None:
        """Stop the ladder and tell everyone else who responded."""
        if self.state != ESCALATION_RUNNING:
            return
        self._finish(by)
        verb = "is attending" if attending else "acknowledged the alert"
        self._logbook(f"{by} {verb}")
        self.hass.async_create_task(
            self._send_push(
                Alert(
                    severity=SEVERITY_ACTIVITY,
                    headline="Alert acknowledged",
                    detail=f"{by} {verb}.",
                    tag=TAG_ACK,
                )
            )
        )

    def stop_for_disarm(self, area_name: str) -> None:
        """Stop a running ladder because the panel was disarmed."""
        if self.state != ESCALATION_RUNNING:
            return
        self._finish("the panel being disarmed")
        self._logbook(f"Escalation stopped, {area_name} disarmed at the panel")
        self.hass.async_create_task(
            self._send_push(
                Alert(
                    severity=SEVERITY_ACTIVITY,
                    headline="Escalation stopped",
                    detail=(
                        f"{area_name} was disarmed at the panel, "
                        "so alerting has stopped."
                    ),
                    tag=TAG_ACK,
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
                tag=TAG_CRITICAL_SECOND,
            )
            await self._send_push(supplementary)
            return

        self.current = alert
        self.acknowledged_by = None
        self.state = ESCALATION_RUNNING
        self._ack = asyncio.Event()
        self._notify_entities()
        self._logbook(f"Escalation started: {alert.headline}")
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
            self._logbook("Escalation exhausted with no acknowledgement")
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
            TAG_CRITICAL
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
            # Android: the alarm_stream channel plays through the ringer switch
            # and Do Not Disturb, which a normal channel never does, and car_ui
            # surfaces it on Android Auto. The alarm volume needs to be up. iOS:
            # a critical alert, which also shows on CarPlay, and needs Critical
            # Alerts allowed for the app or it quietly downgrades to a soft push.
            data.update(
                {
                    "channel": "alarm_stream",
                    "importance": "high",
                    "car_ui": True,
                    "persistent": True,
                    "sticky": True,
                    "push": {
                        "interruption-level": "critical",
                        "sound": {
                            "name": self._opt(
                                CONF_CRITICAL_SOUND, DEFAULT_CRITICAL_SOUND
                            )
                            or DEFAULT_CRITICAL_SOUND,
                            "critical": 1,
                            "volume": 1.0,
                        },
                    },
                }
            )
            title = alert.headline
            message = alert.detail
        elif critical and alert.silent:
            # Silent panic and duress. Discreet on both platforms: no alarm
            # stream, a quiet importance, a bland title and the body hidden from
            # the lock screen, so a phone in view never announces a duress entry.
            data.update(
                {
                    "importance": "low",
                    "visibility": "private",
                    "push": {"interruption-level": "passive"},
                }
            )
            title = "Site status update"
            message = alert.detail
        else:
            # Faults break through with time sensitive. Activity stays passive.
            level = "passive" if activity else "time-sensitive"
            data.update({"push": {"interruption-level": level}})
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

        if critical and not alert.silent:
            await self._send_tts_siren(alert)

    async def _send_tts_siren(self, alert: Alert) -> None:
        """Speak the alert at maximum alarm volume on the chosen Android phones.

        alarm_stream_max forces the alarm volume to the top, plays, then puts it
        back. This is a text to speech notification, so it only goes to the
        services named as Android, never to an iPhone that would show the word.
        """
        services = self._tts_siren_services()
        if not services:
            return
        payload = {
            "message": "TTS",
            "data": {
                "ttl": 0,
                "priority": "high",
                "media_stream": "alarm_stream_max",
                "tts_text": f"{alert.headline}. {alert.detail}",
                "tag": TAG_SIREN,
            },
        }
        for service in services:
            await self._call(service, payload)

    async def _send_sms(self, alert: Alert) -> None:
        recipients = self._opt(CONF_RECIPIENTS) or []
        payload: dict[str, Any] = {
            "message": f"{alert.headline}. {alert.detail}",
        }
        if recipients:
            payload["target"] = list(recipients)
        await self._call(self._opt(CONF_SMS_SERVICE), payload)

    def spoken_alert(self) -> str:
        """Return the current alert as a spoken sentence for a phone call."""
        alert = self.current
        if alert is None:
            return "There is no active alarm."
        return f"{alert.headline}. {alert.detail}"

    def _voice_ack_url(self) -> str | None:
        """Return the acknowledgement webhook URL, if phone ack is usable.

        The Twilio call notify platform treats a message that is a URL as a
        TwiML source, so pointing it here lets the call speak the alert and
        collect a keypress rather than just playing a fixed sentence.
        """
        if not self._opt(CONF_PHONE_ACK):
            return None
        # A relay endpoint wins, so Twilio can reach a Home Assistant behind a
        # self signed certificate by talking to something it does trust.
        endpoint = self._opt(CONF_ACK_ENDPOINT)
        if endpoint:
            return str(endpoint)
        webhook_id = self.entry.data.get(CONF_WEBHOOK_ID)
        if not webhook_id:
            return None
        try:
            return webhook.async_generate_url(self.hass, webhook_id)
        except NoURLAvailableError:
            _LOGGER.warning(
                "Phone acknowledgement is on but no external URL is set and no "
                "relay endpoint is configured, so the voice call cannot reach "
                "the acknowledgement webhook"
            )
            return None

    async def _send_voice(self, alert: Alert) -> None:
        # The message repeats itself because people answer halfway through
        # the first sentence.
        spoken = (
            f"{alert.headline}. {alert.detail} "
            f"Repeating. {alert.headline}. {alert.detail}"
        )
        recipients = self._opt(CONF_RECIPIENTS) or []
        # With phone acknowledgement on, send the call to the TwiML webhook so
        # the keyholder can press a key, rather than a one way spoken message.
        message = self._voice_ack_url() or spoken
        payload: dict[str, Any] = {"message": message}
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
        self.hass.async_create_task(self._clear_critical_push())
