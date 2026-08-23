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

**Watches zones for tamper and fault**, naming the zone, so a permanent tamper
zone that only shows on the zone feed still raises an alert rather than passing
unseen. A zone tamper follows the same escalate tampers choice as any other.

**Treats a fire link as fire.** Name the zones wired to a fire alarm and any of
them going active raises a distinct loud fire alert, armed or disarmed, kept
apart from an intruder activation. A fire link is often programmed on the panel
as an Auxiliary zone, which raises only a silent alarm there and emits no Fire
log event, so watching the zone go active is the one dependable signal. It is
caught three ways, the zone going active, the area triggering off a fire zone,
and a Fire panel event, and deduplicated so one fire rings one ladder.

**Escalates until somebody answers.** Push, then SMS, then repeating voice
calls, stopping the moment anybody acknowledges from the notification, the
dashboard or a service call.

**Handles silent alarms properly.** Silent panic and duress arrive with a
bland title and a hidden lock screen preview, because a phone lying face up
that announces a duress entry defeats the point of a duress code.

**Tells the failure states apart:**

| Site | Panel data | Meaning |
| --- | --- | --- |
| Down | none | Building lost power or line |
| Up | none | Bridge up but the panel link is dead |
| Up | flowing | Healthy |

That middle row is the one most setups miss. The bridge reconnects on error
rather than exiting, so it keeps reporting itself online with nothing flowing.
Panel contact is judged from that data, not a probe, because the ComIP takes
one connection and the bridge already has it.

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
- **Site gateway address and port.** Your firewall or router at the site

The gateway fields are optional but recommended. Without them a site that has
lost power or its line cannot be told apart from a panel that has simply gone
quiet. The panel itself is not probed, because the ComIP allows a single
connection and the bridge holds it, so panel contact is judged from whether
data is still flowing.

Then choose which areas to monitor. Only the areas you pick count towards the
combined system state, so an unused area the panel still publishes will not
hold the system at part armed.

Then set notifications, all from the dropdowns with no YAML:

- **Automatic phones.** On by default. Every Home Assistant Companion phone is
  found and used on its own, and iOS and Android are told apart automatically,
  so there is nothing to pick and nothing to keep in step as phones come and go.
  A new keyholder who installs the Companion app is simply included
- **Push services.** Only used when automatic phones is off. Pick the phones by
  hand from the dropdown, no notify group needed
- **SMS and voice services.** Optional, used by the escalation ladder
- **Recipients.** The numbers SMS and voice dial, in E.164 format
- **Escalate tamper alarms.** Off by default. Turn it on to run the full voice
  ladder when the bell, box, keypad or comms path is attacked, rather than a
  quiet fault notification
- **Fire zones.** Empty by default. Name or number the zones wired to a fire
  alarm link, one entry each. Any of them going active raises a distinct loud
  fire alert that runs the full ladder, whether the panel is armed or disarmed.
  A fire link programmed as an Auxiliary zone raises only a silent alarm at the
  panel, so naming it here is what turns it into a loud fire alert on the phones
- **Fire sound.** Optional, iPhones only. A separate sound imported into the
  Companion app so a fire is told from an intruder by ear. Left blank it uses the
  emergency sound. Android tells the two apart through the spoken siren, which
  says the fire headline aloud, so it needs nothing set here
- **Arm and disarm notifications.** On by default. A tidy notice when a
  monitored area is armed or disarmed
- **Other activity notifications.** Off by default. The noisier stuff, door
  access, user codes and remote commands, kept separate so it stays quiet
  unless you want it

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
| `binary_sensor.*_panel_reachable` | Panel in contact, from data still flowing |
| `binary_sensor.*_zone_problem` | Any zone in tamper or fault, a permanent tamper zone included |
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

**A spoken siren at maximum volume on Android.** On top of the alarm push, each
Android phone also receives a spoken alert that forces the alarm volume to the
top, plays, then puts it back, so a phone left quiet is still loud. This happens
on its own when automatic phones is on, since the integration knows which phones
are Android. With automatic phones off, list the Android phones under the
maximum volume siren option instead. It never reaches an iPhone, so nobody hears
a robotic voice reading a notification.

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

For the whole Twilio walkthrough, outbound texts and calls, the relay and the
webhook, see [docs/twilio-setup.md](docs/twilio-setup.md).

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
certificate and will silently drop the callback, so Twilio must talk to
something it trusts. On a Home Assistant Container install, where the DuckDNS
add on is not available, the tidy options are a Cloudflare Tunnel or a reverse
proxy such as Caddy that terminates a real certificate, or Nabu Casa Cloud.

### A relay, if Home Assistant keeps its self signed certificate

If Home Assistant is reachable on a public address but only with a self signed
certificate, put a small trusted relay in front of it and set the
**Acknowledgement relay URL** option to the relay. Twilio talks to the relay,
which forwards to the Home Assistant webhook and tolerates the self signed
certificate that Twilio would reject. Nothing on Home Assistant needs to change.

A Twilio Function makes a good relay, since Twilio already trusts it. Create a
Function with these environment variables, `HA_HOST` set to the public address,
`HA_PORT` to the port, usually `8123`, and `HA_WEBHOOK_ID` to the id from the
Home Assistant log:

```javascript
exports.handler = function (context, event, callback) {
  const https = require("https");
  const body = new URLSearchParams(event).toString();
  const req = https.request(
    {
      hostname: context.HA_HOST,
      port: context.HA_PORT || 8123,
      path: "/api/webhook/" + context.HA_WEBHOOK_ID,
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": Buffer.byteLength(body),
      },
      rejectUnauthorized: false, // tolerate the self signed certificate
    },
    (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        const response = new Twilio.Response();
        response.appendHeader("Content-Type", "text/xml");
        response.setBody(data);
        callback(null, response);
      });
    }
  );
  req.on("error", (e) => callback(e));
  req.write(body);
  req.end();
};
```

Put the Function URL in the **Acknowledgement relay URL** option so the voice
call uses it, and set the Twilio number's Messaging webhook to the same URL for
SMS replies. The relay forwards Twilio's request to Home Assistant unchanged and
returns the reply, so the press a key and reply to the SMS flows both work. The
relay needs to reach the Home Assistant port, so allow that port inbound from
Twilio in the Azure network security group.

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
