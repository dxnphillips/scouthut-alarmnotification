# Changelog

All notable changes to Texecom Alerts are recorded here. This project follows
[semantic versioning](https://semver.org).

## 1.3.3

- Area sensors no longer sit unavailable. They are now added as each area is
  discovered over MQTT, rather than only for the areas present at the instant
  the platform set up. An area whose retained message landed a moment later, or
  one remembered from a previous run, was left showing unavailable even though
  the combined system state read it fine.

## 1.3.1

- Split activity notifications in two. Arm and disarm now has its own option,
  on by default, while the noisier door access, user code and remote command
  notifications are a separate option, off by default. So the useful arm and
  disarm notices can stay on without the rest of the chatter.

## 1.3.0

- Zone monitoring. Each zone is now watched for a tamper or a fault, so a
  permanent tamper zone, or any trouble that shows only on the zone feed rather
  than as a panel log event, raises an alert with the zone named. A zone tamper
  follows the escalate tampers choice, and a new zone problem binary sensor
  lists any zones currently in trouble. Active and secure zones are left alone,
  since an activation reaches the ladder through the area topic and normal
  movement while disarmed is not worth a word.

## 1.2.3

- Disarming one area no longer silences an activation in another. The
  escalation only stops once no monitored area is still triggered, so a disarm
  elsewhere leaves a live alarm running.
- Fault and activity notifications no longer overwrite each other. Each event
  now carries its own tag, so a new one sits alongside the last rather than
  replacing it, which had looked like the system wiping earlier notifications,
  including ones for other areas. Critical alerts still share one tag so the
  ladder updates in place and clears cleanly on acknowledgement.

## 1.2.2

- Panel reachability is now derived from whether data is flowing, not a TCP
  probe. The Texecom ComIP allows a single connection and the bridge holds it,
  so a probe from Home Assistant was always refused and the panel read as
  unreachable even when healthy. The panel address is no longer asked for, and
  the panel reachable sensor now means the panel is in live contact.
- The panel link going quiet while the bridge stays up now raises a fault, the
  bridge online but panel silent case, rather than only showing on a sensor.

## 1.2.1

- The alarm SMS now tells the keyholder to reply ACK to acknowledge, so a phone
  only keyholder is not left guessing how to stop the alerts. It is added only
  on a real alarm with phone acknowledgement on, since a fault SMS has no
  running ladder for a reply to stop. The voice call already says to press a key.

## 1.2.0

Emergency delivery, car screens, automatic phones and phone acknowledgement,
from testing on real phones.

- Choose phones automatically. With automatic phones on, the default, every
  Home Assistant Companion phone is discovered and used, and iOS and Android are
  told apart on their own, so nothing needs picking or keeping in step.
- Acknowledge from a phone through a relay. An Acknowledgement relay URL option
  lets Twilio talk to a trusted relay, such as a Twilio Function, that forwards
  to Home Assistant, so a Home Assistant on a self signed certificate can still
  take a press of a key or a reply to the SMS. A full Twilio walkthrough is in
  docs/twilio-setup.md.
- Android phones also receive a spoken siren at maximum alarm volume, forcing
  the alarm volume up so a quiet phone is still loud. It is sent only to Android,
  never to an iPhone that would show it as text.
- Emergency pushes are now genuinely loud on Android. They use the documented
  alarm_stream channel, which plays through the ringer switch and Do Not
  Disturb, rather than a value that only applies to text to speech and left
  them as a quiet buzz.
- Emergency alerts show on the car. On CarPlay a critical alert appears on the
  built in display, and on Android Auto the alert carries `car_ui`. Faults,
  activity and silent duress are kept off the car screen.
- Acknowledging, disarming or resetting clears the loud alarm notification from
  every phone. Without this an iOS critical alert, which cannot be replaced by
  tag, sat on the phone after the alarm was dealt with.
- Disarming the panel stops a running escalation on its own.
- A custom emergency sound can be set, so the critical alert uses a siren
  imported into the Companion app on iOS rather than the default tone.
- The last log event sensor shows a readable label. RemoteCommand reads as
  Remote command, with acronyms such as AC Fail kept intact. The raw event type
  stays available as an attribute.
- HACS validation in CI ignores the topics, description and brands checks, which
  only gate the default store and not a custom repository install.

## 1.1.0

First public release.

### Alerting

- Classify every panel event into critical, fault or activity, escalate
  confirmed alarms, panic, duress, fire and medical, and keep silent panic and
  duress discreet.
- Escalation ladder of push, then SMS, then repeating voice calls, stopping the
  moment anybody acknowledges.
- Emergency pushes now override a silent phone properly. Android plays on the
  alarm audio stream at full volume so it bypasses the ringer and Do Not
  Disturb, and iOS sends a correctly formed critical alert. Faults stay time
  sensitive and activity stays passive, so only a real emergency is loud.
- Optional escalation of tamper alarms, so an attack on the bell, box, keypad
  or comms path can ring keyholders rather than notify quietly.
- Optional activity notifications, including a tidy notice when a monitored
  area arms or disarms, driven from the area topic so it fires even when the
  bridge emits no log line.

### Acknowledgement

- Acknowledge from the Companion app, the dashboard button or a service call.
- Optional acknowledgement by phone for keyholders without Home Assistant,
  pressing a key on the Twilio voice call or replying to the SMS.
- Disarming the panel stops a running escalation on its own.
- Escalation start, acknowledgement, disarm stop and exhaustion are written to
  the logbook, naming who responded.

### Liveness

- Staleness detection tells a bridge that is up but silent apart from a healthy
  one.
- TCP reachability probes to the site gateway and the panel tell a dead site
  apart from a dead panel.

### Configuration

- Guided setup with area discovery from retained MQTT, and an options flow that
  changes notifications and thresholds live with no restart.
- Push can target several phones chosen from the UI, with no notify group YAML.
- Only the areas chosen at setup count towards the combined system state.

### Fixes

- The combined system state no longer sticks at part armed when an unused area
  the panel still publishes is left disarmed.
