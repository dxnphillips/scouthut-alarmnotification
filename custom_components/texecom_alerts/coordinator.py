"""MQTT subscription, state model and event classification."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVITY_EVENTS,
    ARM_ACTIVITY_EVENTS,
    ARMED_STATES,
    CONF_AREAS,
    CONF_ESCALATE_TAMPERS,
    CONF_GATEWAY_HOST,
    CONF_GATEWAY_PORT,
    CONF_NOTIFY_ACTIVITY,
    CONF_PREFIX,
    CONF_PROBE_SECONDS,
    CONF_STALE_MINUTES,
    CRITICAL_EVENTS,
    DEFAULT_ESCALATE_TAMPERS,
    DEFAULT_GATEWAY_PORT,
    DEFAULT_NOTIFY_ACTIVITY,
    DEFAULT_PREFIX,
    DEFAULT_PROBE_SECONDS,
    DEFAULT_STALE_MINUTES,
    EVENT_TEXECOM,
    FAULT_EVENTS,
    PROBE_TIMEOUT,
    SEVERITY_ACTIVITY,
    SEVERITY_CRITICAL,
    SEVERITY_FAULT,
    SIGNAL_UPDATE,
    SILENT_EVENTS,
    SMS_FAULTS,
    STATUS_TRIGGERED,
    TAMPER_EVENTS,
)
from .models import AreaState, LogEvent
from .probes import async_tcp_probe

_LOGGER = logging.getLogger(__name__)

_HUMAN_STATUS: dict[str, str] = {
    "full_armed": "armed away",
    "part_armed_1": "part armed 1",
    "part_armed_2": "part armed 2",
    "part_armed_3": "part armed 3",
}


def _human_status(status: str) -> str:
    """Render an area status in words for a notification headline."""
    return _HUMAN_STATUS.get(status, status.replace("_", " "))


def _zone_condition(status: Any) -> str:
    """Map a raw zone status to normal, active, tamper or fault.

    The bridge zone status is one of the project's untested assumptions, so this
    is deliberately forgiving: it matches the words tamper, short, mask and
    fault wherever they appear, and also the classic Texecom numeric encoding
    where 0 is secure, 1 active, 2 tamper and 3 short. Anything unrecognised is
    treated as normal so a surprise value never invents a fault.
    """
    text = str(status).strip().lower()
    if "tamper" in text or text == "2":
        return "tamper"
    if text == "3" or any(word in text for word in ("short", "mask", "fault")):
        return "fault"
    if text in ("1", "active", "open", "true", "on"):
        return "active"
    return "normal"


class TexecomCoordinator:
    """Owns the panel state model and everything that feeds it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        self.hass = hass
        self.entry = entry
        self._unsubs: list[Any] = []

        opts = {**entry.data, **entry.options}
        self.prefix: str = opts.get(CONF_PREFIX, DEFAULT_PREFIX)
        self.gateway_host: str | None = opts.get(CONF_GATEWAY_HOST) or None
        self.gateway_port: int = opts.get(CONF_GATEWAY_PORT, DEFAULT_GATEWAY_PORT)
        self.stale_after = timedelta(
            minutes=opts.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
        )
        self.probe_interval = timedelta(
            seconds=opts.get(CONF_PROBE_SECONDS, DEFAULT_PROBE_SECONDS)
        )
        self.escalate_tampers: bool = bool(
            opts.get(CONF_ESCALATE_TAMPERS, DEFAULT_ESCALATE_TAMPERS)
        )
        self.notify_activity: bool = bool(
            opts.get(CONF_NOTIFY_ACTIVITY, DEFAULT_NOTIFY_ACTIVITY)
        )
        # Only the areas chosen at setup count towards the combined state.
        # Without this, an unused area the panel still publishes would keep the
        # system reading part armed when every area you monitor is armed.
        self.monitored: set[str] = {str(a) for a in (opts.get(CONF_AREAS) or [])}

        # State
        self.areas: dict[str, AreaState] = {}
        # Zones currently in a tamper or fault condition, name to condition.
        self.zone_problems: dict[str, str] = {}
        self.power: dict[str, float] = {}
        self.bridge_online: bool | None = None
        self.site_reachable: bool | None = None
        self.last_message: Any = None
        # Previous derived panel contact, to alert only on the drop.
        self._panel_ok_prev: bool | None = None
        self.last_log: LogEvent | None = None
        self.last_activation: AreaState | None = None

        # Callbacks registered by the alerting engine
        self._alert_listeners: list[Any] = []
        self._disarm_listeners: list[Any] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Subscribe to MQTT and start the reachability probes."""
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise ConfigEntryNotReady("MQTT integration is not available")

        p = self.prefix
        for topic, handler in (
            (f"{p}/area/+", self._handle_area),
            (f"{p}/log", self._handle_log),
            (f"{p}/power", self._handle_power),
            (f"{p}/status", self._handle_status),
            (f"{p}/zone/+", self._handle_zone),
        ):
            self._unsubs.append(
                await mqtt.async_subscribe(self.hass, topic, handler, qos=0)
            )

        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_probe, self.probe_interval)
        )
        await self._async_probe(None)

    async def async_shutdown(self) -> None:
        """Tear everything down."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def add_alert_listener(self, listener: Any) -> None:
        """Register a coroutine called with each Alert worth raising."""
        self._alert_listeners.append(listener)

    def add_disarm_listener(self, listener: Any) -> None:
        """Register a callback fired when a monitored area is disarmed."""
        self._disarm_listeners.append(listener)

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

    @property
    def any_area_armed(self) -> bool:
        """True if any monitored area is armed in any form."""
        return any(a.status in ARMED_STATES for a in self.areas.values())

    @property
    def system_state(self) -> str:
        """Combined state across every monitored area."""
        if not self.areas:
            return "unknown"
        statuses = [a.status for a in self.areas.values()]
        if STATUS_TRIGGERED in statuses:
            return "triggered"
        armed = sum(1 for s in statuses if s in ARMED_STATES)
        if armed and armed == len(statuses):
            return "fully armed"
        if armed:
            return "partly armed"
        if "in_entry" in statuses:
            return "in entry"
        if "in_exit" in statuses:
            return "in exit"
        return "disarmed"

    @property
    def data_healthy(self) -> bool:
        """False when the bridge is up but the panel has gone quiet.

        This is the primary failure detector. The bridge reconnects on error
        rather than exiting, so a dead panel link leaves it reporting itself
        online with nothing flowing.
        """
        if self.last_message is None:
            return False
        return (dt_util.utcnow() - self.last_message) < self.stale_after

    @property
    def panel_reachable(self) -> bool | None:
        """Whether the panel is in live contact, derived from data freshness.

        Deliberately not a TCP probe. The ComIP allows a single connection and
        the bridge holds it, so a probe from here would always be refused. When
        the bridge is up and data is still flowing the panel is reachable; when
        the bridge falls silent past the staleness window, or its Last Will says
        offline, it is not.
        """
        if self.last_message is None and self.bridge_online is None:
            return None
        if self.bridge_online is False:
            return False
        return self.data_healthy

    # ------------------------------------------------------------------
    # MQTT handlers
    # ------------------------------------------------------------------

    @callback
    def _touch(self) -> None:
        self.last_message = dt_util.utcnow()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))

    @staticmethod
    def _decode(payload: Any) -> dict[str, Any] | None:
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @callback
    def _handle_zone(self, msg: mqtt.ReceiveMessage) -> None:
        """Refresh liveness and watch each zone for a tamper or a fault.

        Active and secure are left alone: an activation reaches us through the
        area topic, and normal movement while disarmed is not worth a word. A
        tamper or a fault, though, such as a permanent tamper zone being cut,
        may only ever show here, so those are raised with the zone named.
        """
        self._touch()
        data = self._decode(msg.payload)
        if data is not None:
            self._evaluate_zone(data)
        self._notify()

    def _evaluate_zone(self, data: dict[str, Any]) -> None:
        name = str(data.get("name") or data.get("number") or "")
        if not name:
            return
        condition = _zone_condition(data.get("status"))
        _LOGGER.debug("Zone %s status %r -> %s", name, data.get("status"), condition)
        previous = self.zone_problems.get(name)
        if condition in ("tamper", "fault"):
            if previous != condition:
                self.zone_problems[name] = condition
                self.hass.async_create_task(self._zone_problem(name, condition))
        elif previous is not None:
            del self.zone_problems[name]

    async def _zone_problem(self, name: str, condition: str) -> None:
        if condition == "tamper":
            critical = self.escalate_tampers
            await self._raise(
                SEVERITY_CRITICAL if critical else SEVERITY_FAULT,
                f"ZONE TAMPER at {self.entry.title}"
                if critical
                else f"Zone tamper: {name}",
                f"{name} has been tampered with.",
                sms_worthy=True,
            )
            return
        await self._raise(
            SEVERITY_FAULT,
            f"Zone fault: {name}",
            f"{name} is reporting a fault, such as a short or a mask.",
        )

    @property
    def zone_problem(self) -> bool:
        """True while any zone is in a tamper or fault condition."""
        return bool(self.zone_problems)

    @callback
    def _handle_power(self, msg: mqtt.ReceiveMessage) -> None:
        data = self._decode(msg.payload)
        if data is None:
            return
        for key in (
            "panel_voltage",
            "battery_voltage",
            "panel_current",
            "battery_charging_current",
        ):
            if key in data:
                try:
                    self.power[key] = float(data[key])
                except (TypeError, ValueError):
                    continue
        self._touch()
        self._notify()

    @callback
    def _handle_status(self, msg: mqtt.ReceiveMessage) -> None:
        """Last Will and Testament from the bridge.

        On a topology where the bridge and broker sit together this rarely
        fires, so treat it as meaning the bridge process itself has stopped.
        """
        online = str(msg.payload).strip().lower() == "online"
        changed = online != self.bridge_online
        self.bridge_online = online
        self._notify()
        if changed and not online:
            self.hass.async_create_task(
                self._raise(
                    SEVERITY_FAULT,
                    "Alarm bridge stopped",
                    "The texecom2mqtt bridge went offline. It has stopped or "
                    "crashed rather than lost its link. Check the add on log.",
                )
            )

    @callback
    def _handle_area(self, msg: mqtt.ReceiveMessage) -> None:
        data = self._decode(msg.payload)
        if data is None:
            return
        area_id = str(data.get("id") or data.get("number") or "")
        if not area_id:
            return
        # Ignore areas the user did not choose to monitor.
        if self.monitored and area_id not in self.monitored:
            return

        zone = data.get("last_active_zone") or {}
        state = AreaState(
            area_id=area_id,
            name=str(data.get("name") or area_id),
            number=data.get("number"),
            status=str(data.get("status") or "unknown"),
            last_active_zone=zone.get("name"),
            last_active_zone_number=zone.get("number"),
        )
        previous = self.areas.get(area_id)
        state.last_triggered = previous.last_triggered if previous else None

        self.areas[area_id] = state
        self._touch()

        if state.status == STATUS_TRIGGERED and (
            previous is None or previous.status != STATUS_TRIGGERED
        ):
            state.last_triggered = dt_util.utcnow()
            self.last_activation = state
            self.hass.async_create_task(self._area_triggered(state))
        else:
            self._maybe_area_activity(previous, state)

        # Disarming is the human "I have got this" signal, so it stops the
        # running escalation, but only once no monitored area is still in alarm.
        # Otherwise disarming one area would silence an activation in another.
        if (
            previous is not None
            and previous.status != "disarmed"
            and state.status == "disarmed"
            and not any(a.status == STATUS_TRIGGERED for a in self.areas.values())
        ):
            for listener in self._disarm_listeners:
                listener(state.name)

        self._notify()

    def _maybe_area_activity(
        self, previous: AreaState | None, state: AreaState
    ) -> None:
        """Notify when a monitored area arms or disarms, if enabled.

        Driven from the area topic rather than the log, so it fires even when
        the bridge does not emit an open or close log line, and only once the
        area settles rather than while it counts through entry and exit.
        """
        if not self.notify_activity:
            return
        prev_status = previous.status if previous else "unknown"
        if state.status == prev_status:
            return
        was_armed = prev_status in ARMED_STATES
        now_armed = state.status in ARMED_STATES
        if now_armed and not was_armed:
            human = _human_status(state.status)
            self.hass.async_create_task(
                self._raise(
                    SEVERITY_ACTIVITY,
                    f"{state.name} {human}",
                    f"{state.name} at {self.entry.title} is now {human}.",
                )
            )
        elif state.status == "disarmed" and prev_status != "disarmed":
            self.hass.async_create_task(
                self._raise(
                    SEVERITY_ACTIVITY,
                    f"{state.name} disarmed",
                    f"{state.name} at {self.entry.title} was disarmed.",
                )
            )

    @callback
    def _handle_log(self, msg: mqtt.ReceiveMessage) -> None:
        data = self._decode(msg.payload)
        if data is None:
            return

        event_type = str(data.get("type") or "")
        if not event_type:
            return

        severity = self._classify(event_type)
        entity = data.get("entity") or {}
        event = LogEvent(
            event_type=event_type,
            description=str(data.get("description") or event_type),
            severity=severity,
            silent=event_type in SILENT_EVENTS,
            sms_worthy=event_type in SMS_FAULTS,
            areas=[str(a) for a in (data.get("areas") or [])],
            zone_name=entity.get("zone_name"),
            zone_id=entity.get("zone_id"),
            user_id=entity.get("user_id"),
            parameter=data.get("parameter"),
            panel_time=data.get("timestamp"),
            received=dt_util.utcnow(),
        )

        self.last_log = event
        self._touch()
        self._notify()

        # Always publish to the bus, whatever the severity, so a user can
        # build their own automations without forking this integration.
        self.hass.bus.async_fire(EVENT_TEXECOM, event.as_event_data())

        # Critical and fault always alert. Activity alerts only when the user
        # asked for it, and arm and disarm log lines are left to the area topic
        # so the same arming is not announced twice.
        notify_activity_event = (
            self.notify_activity
            and severity == SEVERITY_ACTIVITY
            and event_type not in ARM_ACTIVITY_EVENTS
        )
        if severity in (SEVERITY_CRITICAL, SEVERITY_FAULT) or notify_activity_event:
            self.hass.async_create_task(self._log_alert(event))

    def _classify(self, event_type: str) -> str:
        if event_type in CRITICAL_EVENTS:
            return SEVERITY_CRITICAL
        if event_type in FAULT_EVENTS:
            # A tamper is a fault until the user opts to treat it as an attack.
            if self.escalate_tampers and event_type in TAMPER_EVENTS:
                return SEVERITY_CRITICAL
            return SEVERITY_FAULT
        if event_type in ACTIVITY_EVENTS:
            return SEVERITY_ACTIVITY
        return SEVERITY_ACTIVITY

    # ------------------------------------------------------------------
    # Reachability
    # ------------------------------------------------------------------

    async def _async_probe(self, _now: Any) -> None:
        """Probe the site gateway and re-evaluate panel contact."""
        if self.gateway_host:
            reachable = await async_tcp_probe(
                self.gateway_host, self.gateway_port, PROBE_TIMEOUT
            )
            if reachable is not self.site_reachable and self.site_reachable is not None:
                await self._site_changed(reachable)
            self.site_reachable = reachable

        # Panel contact is derived from data freshness, not a probe. Alert on
        # the drop while the bridge is still up and the site is not down, the
        # bridge online but panel silent case that staleness exists to catch.
        panel_ok = self.panel_reachable
        if (
            panel_ok is False
            and self._panel_ok_prev is True
            and self.bridge_online is not False
            and self.site_reachable is not False
        ):
            await self._raise(
                SEVERITY_FAULT,
                "Panel link lost",
                "The bridge is up but the panel has gone quiet. No data has "
                "arrived within the staleness window, which usually means the "
                "link between the bridge and the panel has dropped even though "
                "the bridge is still running.",
                sms_worthy=True,
            )
        self._panel_ok_prev = panel_ok

        self._notify()

    async def _site_changed(self, reachable: bool) -> None:
        """Site went up or down.

        Losing the site while armed is critical, because Home Assistant is
        not in the building and this is the only thing that can tell anyone.
        """
        if reachable:
            await self._raise(
                SEVERITY_ACTIVITY,
                "Site back online",
                f"The link to {self.entry.title} came back up. "
                f"System state {self.system_state}.",
            )
            return

        armed = self.any_area_armed
        detail = (
            f"The link to {self.entry.title} dropped. Last known state was "
            f"{self.system_state}. Likely a power cut or a line fault. "
            "No alarm visibility until it returns."
        )
        await self._raise(
            SEVERITY_CRITICAL if armed else SEVERITY_FAULT,
            "Site offline",
            detail,
            sms_worthy=True,
        )

    # ------------------------------------------------------------------
    # Alert raising
    # ------------------------------------------------------------------

    async def _area_triggered(self, area: AreaState) -> None:
        zone = area.last_active_zone or "not reported"
        number = (
            f" (zone {area.last_active_zone_number})"
            if area.last_active_zone_number is not None
            else ""
        )
        await self._raise(
            SEVERITY_CRITICAL,
            f"ALARM ACTIVATION at {self.entry.title}",
            f"{area.name} triggered by {zone}{number}.",
        )

    async def _log_alert(self, event: LogEvent) -> None:
        where = f" on {event.zone_name}" if event.zone_name else ""
        area = f" in {', '.join(event.areas)}" if event.areas else ""
        if event.severity == SEVERITY_CRITICAL:
            headline = f"{event.description.upper()} at {self.entry.title}"
        elif event.severity == SEVERITY_FAULT:
            headline = f"Alarm fault: {event.description}"
        else:
            headline = f"{event.description} at {self.entry.title}"
        await self._raise(
            event.severity,
            headline,
            f"{event.description}{where}{area}.",
            silent=event.silent,
            sms_worthy=event.sms_worthy,
        )

    async def _raise(
        self,
        severity: str,
        headline: str,
        detail: str,
        *,
        silent: bool = False,
        sms_worthy: bool = False,
    ) -> None:
        from .models import Alert

        alert = Alert(
            severity=severity,
            headline=headline,
            detail=detail,
            silent=silent,
            sms_worthy=sms_worthy,
        )
        for listener in self._alert_listeners:
            await listener(alert)
