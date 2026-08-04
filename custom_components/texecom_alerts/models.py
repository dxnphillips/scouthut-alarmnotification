"""Data models for the Texecom Alerts integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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

    def as_event_data(self) -> dict[str, Any]:
        """Render for the Home Assistant event bus."""
        return {
            "event_type": self.event_type,
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
