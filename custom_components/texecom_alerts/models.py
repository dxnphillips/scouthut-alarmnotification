"""Data models for the Texecom Alerts integration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Readable names for the log event types whose plain de-camel-cased form still
# reads awkwardly. Anything not here is spaced out from its camel case, so
# LowBattery becomes Low battery, no entry needed.
_EVENT_LABELS: dict[str, str] = {
    "OpenClose": "Arm or disarm",
    "RemoteOpenClose": "Remote arm or disarm",
    "AutoOpenClose": "Automatic arm or disarm",
    "RemoteCommand": "Remote command",
    "RecentClosing": "Recent closing",
    "QuickArm": "Quick arm",
    "UserCode": "User code entered",
    "ProxTag": "Proximity tag used",
    "DoorAccess": "Door access",
    "PASilent": "Silent panic",
    "PAAudible": "Audible panic",
    "DuressCodeAlarm": "Duress code entered",
}


def humanize_event(event_type: str) -> str:
    """Turn a panel event type into something readable for a keyholder.

    RemoteCommand reads as Remote command rather than the raw code. The area
    and system state sensors carry the actual armed or disarmed state, so this
    is only ever a friendlier label for the event itself.
    """
    if event_type in _EVENT_LABELS:
        return _EVENT_LABELS[event_type]
    # Space out the camel case while keeping acronyms intact, so ACFail reads
    # as AC Fail and GSMTamper as GSM Tamper rather than being lower cased.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", event_type)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    return spaced[:1].upper() + spaced[1:] if spaced else event_type


@dataclass
class AreaState:
    """Current state of one panel area."""

    area_id: str
    name: str
    number: int | None = None
    status: str = "unknown"
    last_active_zone: str | None = None
    last_active_zone_number: int | None = None
    last_triggered: datetime | None = None


@dataclass
class LogEvent:
    """A classified panel log event."""

    event_type: str
    description: str
    severity: str
    silent: bool = False
    sms_worthy: bool = False
    areas: list[str] = field(default_factory=list)
    zone_name: str | None = None
    zone_id: int | None = None
    user_id: int | None = None
    parameter: Any = None
    panel_time: str | None = None
    received: datetime | None = None

    @property
    def label(self) -> str:
        """A readable label for display.

        Prefers a real description from the bridge, and otherwise makes the raw
        event type readable.
        """
        if self.description and self.description != self.event_type:
            return self.description
        return humanize_event(self.event_type)

    def as_event_data(self) -> dict[str, Any]:
        """Render for the Home Assistant event bus."""
        return {
            "event_type": self.event_type,
            "label": self.label,
            "description": self.description,
            "severity": self.severity,
            "silent": self.silent,
            "sms_worthy": self.sms_worthy,
            "areas": self.areas,
            "zone_name": self.zone_name,
            "zone_id": self.zone_id,
            "user_id": self.user_id,
            "parameter": self.parameter,
            "panel_time": self.panel_time,
        }


@dataclass
class Alert:
    """Something worth telling a keyholder about."""

    severity: str
    headline: str
    detail: str
    silent: bool = False
    sms_worthy: bool = False
    source: str = "panel"
    tag: str | None = None
    # Ask for a banner rather than a quiet background notice. Used for arm and
    # disarm, so those pop up while the rest of activity stays in the shade.
    heads_up: bool = False
