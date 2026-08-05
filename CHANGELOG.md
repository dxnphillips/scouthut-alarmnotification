# Changelog

All notable changes to Texecom Alerts are recorded here. This project follows
[semantic versioning](https://semver.org).

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
