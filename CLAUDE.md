# CLAUDE.md

Context for Claude Code working on this repository.

## What this is

A Home Assistant custom integration, distributed via HACS, that turns a
Texecom Premier Elite panel into useful alerting. It consumes MQTT published
by the separate `texecom2mqtt` bridge. It does not talk to the panel itself.

Everything is in the integration: state model, classification, escalation
ladder, reachability probes, maintenance mode. There is deliberately no
required YAML.

## Architecture

```
texecom2mqtt (separate add on)
    |  MQTT
    v
coordinator.py     subscribes, parses, classifies, holds state
    |  Alert objects            |  bus events
    v                           v
alerting.py                   texecom_alerts_event
escalation ladder             for user automations
    |
    v
notify services (push, SMS, voice)
```

`coordinator.py` owns state and classification. `alerting.py` owns policy.
Keep that boundary. Anything about *what happened* goes in the coordinator,
anything about *who gets told and how* goes in the alerting engine.

## Module map

| File | Responsibility |
| --- | --- |
| `const.py` | Config keys, defaults, and the event classification sets |
| `models.py` | `AreaState`, `LogEvent`, `Alert` dataclasses |
| `coordinator.py` | MQTT subscription, state model, classification, probes |
| `alerting.py` | Escalation ladder, notification formatting, acknowledgement |
| `probes.py` | TCP reachability, deliberately not ICMP |
| `config_flow.py` | Setup wizard with MQTT area discovery, plus options flow |
| `entity.py` | Base entity, dispatcher subscription, device registry |
| `sensor.py` / `binary_sensor.py` / `switch.py` / `button.py` | Platforms |
| `diagnostics.py` | Redacted state dump |

## Upstream contract

Topics published by texecom2mqtt, all under the configured prefix:

| Topic | Payload |
| --- | --- |
| `<prefix>/area/<name>` | JSON with `id`, `name`, `number`, `status`, and `last_active_zone` when triggered |
| `<prefix>/zone/<name>` | JSON with zone status |
| `<prefix>/log` | JSON with `type`, `description`, `areas`, `entity`, `timestamp` |
| `<prefix>/power` | JSON with `panel_voltage`, `battery_voltage`, `panel_current`, `battery_charging_current` |
| `<prefix>/status` | `online` or `offline`, the Last Will and Testament |

Area status values: `disarmed`, `full_armed`, `part_armed_1`, `part_armed_2`,
`part_armed_3`, `triggered`, `in_entry`, `in_exit`.

Zone entities themselves come from the bridge's own MQTT discovery. Do not
duplicate them here.

## Design decisions, and why

Read these before changing behaviour. Each one exists for a reason that is
not obvious from the code.

**Silent events must stay silent.** `SILENT_EVENTS` covers silent panic and
duress. Those get a bland title, `visibility: private`, and no critical
tone. If somebody is being coerced into disarming, a phone lying face up
that lights up saying "duress code entered" tells the person standing over
them that the alarm knows. Never make these louder.

**Maintenance mode never suppresses critical.** Check `alerting.async_handle`.
Faults and connectivity are suppressed, alarms are not.

**Staleness is the primary failure detector, not the LWT.** The bridge
reconnects on error rather than exiting, so a dead panel link leaves it
reporting itself online with nothing flowing. Where the bridge and broker sit
together the LWT means only that the bridge process stopped.

**TCP probes, not ICMP.** A connect to the ComIP port tests the service
actually depended on, and needs no raw socket privileges in a container.

**Second activation does not start a second ladder.** It sends a
supplementary push under its own tag. Two ladders means everyone's phone
ringing twice over.

**Every provider call is wrapped.** A provider outage in round two must not
stop the voice calls in round three. See `AlertingEngine._call`.

**No arming or disarming, ever.** This integration is read only against the
panel. Publishing to `<prefix>/area/<name>/command` would disarm a building.
Do not add it. If somebody asks, the answer is that the broker ACL should
deny that topic outright.

**Not a signalling path.** This is supplementary awareness and an audit
trail. It does not replace the panel's own monitored route to an ARC. Keep
that framing in user facing text.

## Conventions

- British English in comments, docstrings and user facing strings.
- No hyphens or dashes in prose. Code identifiers are exempt.
- Ruff for lint and format. Run `ruff check` and `ruff format` before
  committing.
- Type hints everywhere. `from __future__ import annotations` at the top.
- Home Assistant minimum 2024.6.0, which is what `entry.runtime_data` needs.

## Testing

`pytest-homeassistant-custom-component` is in `requirements-dev.txt`.

Priority order for tests, highest value first:

1. Classification. Every event type lands in exactly one bucket, and every
   member of `SILENT_EVENTS` is also in `CRITICAL_EVENTS`.
2. The ladder. Acknowledgement stops it, exhaustion terminates cleanly, a
   failing notify service does not abort remaining rounds.
3. Maintenance mode gating, specifically that critical passes through.
4. Coordinator parsing against captured real payloads.

## Known unknowns

These need checking against a live panel. Do not assume the code is right.

- Whether `<prefix>/power` republishes on a timer or only on change. The
  staleness default of 60 minutes assumes periodic. If it only publishes on
  change, an empty building overnight will look stale.
- Exact `id` values in area payloads. Assumed to be letters. Discovery
  handles it either way but the assumption is untested.
- Whether every event type name in `const.py` matches what the bridge
  actually emits. The lists were assembled from documentation, not from
  observed traffic. Capture a real log stream and diff against them.
- Behaviour when two config entries point at the same prefix.
