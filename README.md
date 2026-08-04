# Texecom Alerts

A Home Assistant integration that turns a Texecom Premier Elite panel into
alerting somebody will actually respond to. Push, SMS and escalating voice
calls, with liveness monitoring that can tell a dead site apart from a dead
panel.

Consumes MQTT published by the separate
[texecom2mqtt](https://github.com/dchesterton/texecom2mqtt) bridge.

## Why this exists

The bridge gives you entities. It does not give you a reason to trust that
silence means nothing is wrong. This integration adds the layer between raw
panel events and a keyholder's phone ringing at three in the morning.

## What it does

**Classifies every panel event** into critical, fault or activity. Confirmed
alarms, panic, duress, fire and medical escalate. Tampers, mains, battery and
comms faults notify. Arming and access are logged quietly.

**Escalates until somebody answers.** Push, then SMS, then repeating voice
calls, stopping the moment anybody acknowledges from the notification, the
dashboard or a service call.

**Handles silent alarms properly.** Silent panic and duress arrive with a
bland title and a hidden lock screen preview, because a phone lying face up
that announces a duress entry defeats the point of a duress code.

**Tells four failure states apart:**

| Site | Panel | Data | Meaning |
| --- | --- | --- | --- |
| Down | Down | No | Building lost power or line |
| Up | Down | No | ComIP or panel power fault |
| Up | Up | No | Bridge up but panel link dead |
| Up | Up | Yes | Healthy |

That third row is the one most setups miss. The bridge reconnects on error
rather than exiting, so it keeps reporting itself online with nothing
flowing.

## Requirements

- Home Assistant 2024.6.0 or later
- The MQTT integration configured
- The `texecom2mqtt` bridge running against your panel
- A push notify service. SMS and voice services optional but recommended

## Installation

### HACS

1. HACS, three dot menu, Custom repositories
2. Add this repository URL with category Integration
3. Download Texecom Alerts, restart Home Assistant
4. Settings, Devices and services, Add integration, Texecom Alerts

### Manual

Copy `custom_components/texecom_alerts` into your `custom_components`
directory and restart.

## Setup

The config flow discovers your areas from retained MQTT messages, so there is
nothing to look up first. Supply:

- **Site name.** Used in every alert headline
- **MQTT prefix.** Defaults to `texecom2mqtt`
- **Panel address and port.** The ComIP or SmartCom, usually port 10001
- **Site gateway address and port.** Your firewall or router at the site

The host fields are optional but strongly recommended. Without them there is
no way to tell a dead site apart from a dead panel.

Then choose areas, then notification services and recipients.

## Entities

| Entity | Purpose |
| --- | --- |
| `sensor.*_system_state` | Combined state across all areas |
| `sensor.<area>` | One per monitored area |
| `sensor.*_last_activation_zone` | What actually set it off, held after the area moves on |
| `sensor.*_last_log_event` | Most recent panel event with full detail |
| `sensor.*_escalation_state` | idle, escalating, acknowledged or exhausted |
| `binary_sensor.*_any_area_armed` | Anything armed in any form |
| `binary_sensor.*_bridge` | Bridge Last Will and Testament |
| `binary_sensor.*_data_stale` | Bridge up but panel silent |
| `binary_sensor.*_site_reachable` | TCP probe to the site gateway |
| `binary_sensor.*_panel_reachable` | TCP probe to the ComIP port |
| `switch.*_maintenance_mode` | Suppresses faults, never suppresses alarms |
| `button.*_test_alerts` | Runs the full ladder with a marked test |
| `button.*_acknowledge` | Stops a running ladder |
| `sensor.*_panel_voltage` and three more | Power supply health |

## Services

`texecom_alerts.test_alerts`, `texecom_alerts.acknowledge`,
`texecom_alerts.reset`.

## Building your own automations

Every classified event is also fired on the bus as `texecom_alerts_event`,
whatever its severity, so you can add behaviour without forking:

```yaml
automation:
  - alias: "Log office access to a spreadsheet"
    trigger:
      - platform: event
        event_type: texecom_alerts_event
        event_data:
          event_type: DoorAccess
    action: ...
```

Event data carries `event_type`, `description`, `severity`, `silent`,
`sms_worthy`, `areas`, `zone_name`, `zone_id`, `user_id`, `parameter` and
`panel_time`.

## Commissioning

Do not skip these. They decide whether any of it works at three in the
morning.

- [ ] Walk test a zone, confirm the area sensor follows
- [ ] Trigger a real activation with the bell isolated, let the ladder run
      all the way into the voice call
- [ ] Press **Test alerts** and let it run to exhaustion
- [ ] Have every keyholder save the outbound number as a contact and set it
      as an emergency bypass on iOS or a priority contact on Android. An
      unrecognised number at three in the morning gets silenced, and this is
      the most common reason these setups fail in practice
- [ ] Grant the Companion app critical alert permission in iOS Settings. It
      is not a Home Assistant setting. Test with the phone in Do Not Disturb
- [ ] Pull the link and confirm the site alert fires

## What it deliberately does not do

**It never arms or disarms anything.** Every subscription is read only.
Publishing to the command topic would disarm a building, so deny that topic
in your broker ACL.

**It is not a signalling path.** Supplementary awareness and an audit trail.
It does not replace the panel's own monitored route to an alarm receiving
centre, and anything touching remote disarm should be checked against your
insurer's terms first.

## Security notes

The UDL connection between bridge and panel is unencrypted, because the
Connect protocol requires panel encryption disabled. Put the panel on its own
VLAN, permit only the bridge host to reach it on its port, and give it no
internet egress.

Recipient numbers and host addresses are redacted from diagnostics output.

## Licence

MIT
