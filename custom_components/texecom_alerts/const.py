"""Constants for the Texecom Alerts integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "texecom_alerts"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Configuration keys
CONF_SITE_NAME: Final = "site_name"
CONF_PREFIX: Final = "prefix"
CONF_AREAS: Final = "areas"
CONF_PANEL_HOST: Final = "panel_host"
CONF_PANEL_PORT: Final = "panel_port"
CONF_GATEWAY_HOST: Final = "gateway_host"
CONF_GATEWAY_PORT: Final = "gateway_port"

CONF_PUSH_SERVICE: Final = "push_service"
CONF_SMS_SERVICE: Final = "sms_service"
CONF_VOICE_SERVICE: Final = "voice_service"
CONF_RECIPIENTS: Final = "recipients"

CONF_STALE_MINUTES: Final = "stale_minutes"
CONF_BATTERY_LOW_VOLTS: Final = "battery_low_volts"
CONF_LADDER_ROUNDS: Final = "ladder_rounds"
CONF_ROUND_SECONDS: Final = "round_seconds"
CONF_PROBE_SECONDS: Final = "probe_seconds"
CONF_MAINTENANCE_HOURS: Final = "maintenance_hours"

# Defaults
DEFAULT_SITE_NAME: Final = "Scout HQ"
DEFAULT_PREFIX: Final = "texecom2mqtt"
DEFAULT_PANEL_PORT: Final = 10001
DEFAULT_GATEWAY_PORT: Final = 443
DEFAULT_STALE_MINUTES: Final = 60
DEFAULT_BATTERY_LOW_VOLTS: Final = 12.4
DEFAULT_LADDER_ROUNDS: Final = 5
DEFAULT_ROUND_SECONDS: Final = 90
DEFAULT_PROBE_SECONDS: Final = 60
DEFAULT_MAINTENANCE_HOURS: Final = 4

DISCOVERY_SECONDS: Final = 6
PROBE_TIMEOUT: Final = 5

# Dispatcher signal, formatted with the config entry id
SIGNAL_UPDATE: Final = "texecom_alerts_update_{}"

# Bus event fired for every classified panel event, so a user can bolt on
# their own automations without forking the integration.
EVENT_TEXECOM: Final = "texecom_alerts_event"

# Notification action identifiers
ACTION_ACK: Final = "TEXECOM_ACK"
ACTION_ATTEND: Final = "TEXECOM_ATTEND"

# Severity
SEVERITY_CRITICAL: Final = "critical"
SEVERITY_FAULT: Final = "fault"
SEVERITY_ACTIVITY: Final = "activity"

# Escalation engine states
ESCALATION_IDLE: Final = "idle"
ESCALATION_RUNNING: Final = "escalating"
ESCALATION_ACKNOWLEDGED: Final = "acknowledged"
ESCALATION_EXHAUSTED: Final = "exhausted"

# Area status values published by texecom2mqtt
STATUS_TRIGGERED: Final = "triggered"

ARMED_STATES: Final = frozenset(
    {"full_armed", "part_armed_1", "part_armed_2", "part_armed_3"}
)

# ---------------------------------------------------------------------------
# Panel log event classification
#
# These lists are the heart of the integration. Getting an event into the
# wrong bucket is the difference between a phone call at 3am and a silent
# logbook entry, so treat changes here as behaviour changes and test them.
# ---------------------------------------------------------------------------

CRITICAL_EVENTS: Final = frozenset(
    {
        "AlarmActive",
        "ConfirmedAlarm",
        "ConfirmedIntruder",
        "VerifiedCrossZoneAlarm",
        "MonitoredAlarm",
        "BellActive",
        "PAAudible",
        "PASilent",
        "ConfirmedPA",
        "ConfirmedPAAudible",
        "ConfirmedPASilent",
        "PAFromRemoteFOB",
        "KeypadAudiblePA",
        "KeypadSilentPA",
        "DuressCodeAlarm",
        "Fire",
        "KeypadFire",
        "FireZoneTamper",
        "Medical",
        "KeypadMedical",
        "TwentyFourHourAudible",
        "TwentyFourHourSilent",
        "TwentyFourHourGas",
    }
)

# Events that must never produce an audible alert or a lock screen preview.
# If somebody is being coerced into disarming, a phone lying face up that
# lights up saying "duress code entered" tells the person standing over them
# that the alarm knows.
SILENT_EVENTS: Final = frozenset(
    {
        "PASilent",
        "ConfirmedPASilent",
        "KeypadSilentPA",
        "DuressCodeAlarm",
        "TwentyFourHourSilent",
    }
)

FAULT_EVENTS: Final = frozenset(
    {
        "Tamper",
        "ZoneTamper",
        "PanelBoxTamper",
        "BellTamper",
        "AuxiliaryTamper",
        "ExpanderTamper",
        "KeypadTamper",
        "GSMTamper",
        "PSUTamper",
        "CodeTamperAlarm",
        "KeypadLockout",
        "ArmFailed",
        "ExitError",
        "ArmedWithLineFault",
        "ACFail",
        "PSUACFail",
        "MainsOverVoltage",
        "PowerOPFault",
        "LowBattery",
        "PSUBatteryFail",
        "BatteryChargerFault",
        "PowerUnitFailure",
        "PSULowOutputFail",
        "ExpanderLowVoltage",
        "RFDeviceLowBattery",
        "TAGSystemExitBatteryLow",
        "TAGSystemEntryBatteryLow",
        "TelephoneLineFault",
        "FailToCommunicate",
        "TestCallFailed",
        "RadioJamming",
        "RadioConfigFailure",
        "SupervisionFault",
        "ExpanderTrouble",
        "RemoteKeypadTrouble",
        "ZoneFault",
        "ZoneMasked",
        "FaultsOverridden",
        "InstallerProgrammingStart",
        "NVMDefaultsLoaded",
        "LogCleared",
        "SiteDataChanged",
        "LogCapacityAlert",
    }
)

# Faults that also warrant an SMS, because these are what an intruder causes
# shortly before an activation.
SMS_FAULTS: Final = frozenset(
    {
        "PanelBoxTamper",
        "BellTamper",
        "ExpanderTamper",
        "KeypadTamper",
        "GSMTamper",
        "CodeTamperAlarm",
        "FailToCommunicate",
        "TelephoneLineFault",
        "RadioJamming",
        "SupervisionFault",
    }
)

ACTIVITY_EVENTS: Final = frozenset(
    {
        "OpenClose",
        "PartArmed",
        "PartArm1",
        "PartArm2",
        "PartArm3",
        "AutoOpenClose",
        "RemoteOpenClose",
        "QuickArm",
        "RecentClosing",
        "AutoArmingStarted",
        "AutoArmDeferred",
        "OpenAfterAlarm",
        "ResetAfterAlarm",
        "Rearm",
        "DoorAccess",
        "DoorAccess2",
        "UserCode",
        "ProxTag",
        "UserAdded",
        "UserDeleted",
        "AccessCodeChangedDeleted",
        "UserWalkTestStartEnd",
        "ManualTestTransmission",
        "TestCallPassed",
    }
)
