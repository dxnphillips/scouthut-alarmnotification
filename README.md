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
comms faults notify, and tampers can be promoted to full emergencies with one
tick if you want the bell, box and comms attacks to ring keyholders. Arming and
access are logged quietly, or turned into notifications if you want them.

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

Then choose which areas to monitor. Only the areas you pick count towards the
combined system state, so an unused area the panel still publishes will not
hold the system at part armed.

Then set notifications, all from the dropdowns with no YAML:

- **Push services.** Pick one or more phones. Choosing several here replaces
  the old need for a notify group
- **SMS and voice services.** Optional, used by the escalation ladder
- **Recipients.** The numbers SMS and voice dial, in E.164 format
- **Escalate tamper alarms.** Off by default. Turn it on to run the full voice
  ladder when the bell, box, keypad or comms path is attacked, rather than a
  quiet fault notification
- **Activity notifications.** Off by default. Turn it on to be told when a
  monitored area arms or disarms, and on door access and user changes

Everything except the areas can be changed later, live, from the options.

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

## Emergency notifications, waking somebody

An emergency push is built to override a silent phone, but each platform needs
one thing set that is outside Home Assistant, and without it the alert arrives
as a quiet buzz.

- **iOS.** The push is sent as a critical alert, which bypasses the mute switch
  and Do Not Disturb. That only takes effect once you grant the Companion app
  **Critical Alerts** in iOS Settings, under the app. Test with the phone muted
  and in Do Not Disturb.
- **Android.** The push is sent on the alarm audio stream, which sounds through
  the ringer switch and Do Not Disturb the way an alarm clock does, with no per
  app permission. It plays at the **alarm** volume, so make sure that is up. If
  it is still quiet, check the alarm volume, not the ringer.

These are the strongest alerts an app is allowed to send. They are not the
government emergency alerts, which travel over cell broadcast and are closed to
apps, but they override silent and Do Not Disturb in the same spirit.

**The low maintenance setup.** You do not need a custom sound at all. Leave the
**Emergency sound** option at `default` and the alert is already loud on both
platforms. The only per phone step is the one time permission or channel below,
which each keyholder does once.

- **iOS.** Grant the Companion app **Critical Alerts** once. That is the whole
  job. The default critical tone plays loud and overrides silent and Do Not
  Disturb, and the ladder repeats it each round until somebody acknowledges. A
  custom siren cannot be pushed to iOS remotely, so only bother with one if the
  default tone is not distinctive enough for you.
- **Android.** Set the tone once on the alarm channel. Press **Test alerts**
  first so the channel exists, then go to Companion app, Settings, Companion
  app, Notification channels, open the alarm channel and set its **Sound** to a
  siren of your choice. Because the alert plays on the alarm stream it already
  sounds through silent and Do Not Disturb, so the tone is the only thing to
  pick.

**A custom siren on iOS.** If you do want a bespoke tone on iOS, import a sound
into the Companion app under Settings, Companion app, Notifications, Sounds. It
must be a 32 bit float 48000 Hz wav. Put its filename, extension included, in
the **Emergency sound** option, and restart the phone once so it registers.

**Acknowledging silences it everywhere.** Acknowledging, or disarming the panel,
clears the loud alarm notification from every phone, not just the one that
acted. This matters on iOS, where a critical notification cannot be replaced and
would otherwise sit there until cleared.

**In the car.** Emergency alerts also reach the car screen. On CarPlay a
critical alert shows on the built in display on its own. On Android Auto the
alert carries `car_ui`, so it appears there too. Faults and activity are kept
off the car screen, and silent panic and duress never appear there. The
escalation voice call also comes through the car as an ordinary phone call,
which is the surest way to reach somebody driving.

Faults and activity are deliberately not built this way, so only a real
emergency is loud. Press **Test alerts** and let it run to the voice call to
prove the whole chain on every phone.

## Acknowledging alerts

Acknowledgement stops the ladder for everyone and tells the other keyholders
who responded. Answering a phone call does not by itself acknowledge. From
Home Assistant there are three ways:

- the Companion app notification buttons, Acknowledge and Attending
- the dashboard button, `button.*_acknowledge`
- the service, `texecom_alerts.acknowledge`

**Disarming the panel also stops the ladder.** When a monitored area goes to
disarmed while an escalation is running, the escalation stops on its own, since
disarming is the human "I have got this" response.

Every escalation start, acknowledgement, disarm stop and exhaustion is written
to the Home Assistant logbook, naming who responded, so there is a record after
the notification clears. The acknowledgement push also names who responded.

### Acknowledging by phone, for keyholders without Home Assistant

Turn on **Let keyholders acknowledge by phone** in the options. A keyholder
can then press **1** on the voice call, or reply **ACK** to the SMS, to stop
the escalation. Both arrive at a webhook this integration registers, one per
site. The address is written to the Home Assistant log when the option is on.

Wiring, using the Twilio notify services you already point at:

- **Voice.** Nothing else to do. With the option on, the call is sent to the
  webhook so it can speak the alert and collect the keypress.
- **SMS.** In the Twilio console, set the phone number's Messaging webhook to
  the address from the log, so replies reach the integration.

**Twilio needs a certificate it trusts.** It refuses a self signed
certificate and will silently drop the callback, so phone acknowledgement
needs Home Assistant reachable on a publicly trusted HTTPS URL. A real
certificate through the DuckDNS add on, Nabu Casa Cloud, or a reverse proxy
that terminates a valid certificate all work. A self signed certificate on a
public address does not.

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
- [ ] On each iOS phone, grant the Companion app critical alert permission in
      iOS Settings. It is not a Home Assistant setting. With that granted the
      default tone is already loud, so there is nothing else to set. Test with
      the phone in Do Not Disturb
- [ ] On each Android phone, press Test alerts once, then set the alarm channel
      tone under Companion app, Notification channels. It already plays on the
      alarm stream, so the tone is the only choice to make
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
