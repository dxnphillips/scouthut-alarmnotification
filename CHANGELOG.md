# Changelog

All notable changes to Texecom Alerts are recorded here. This project follows
[semantic versioning](https://semver.org).

## 1.7.0

- Add camera analytics that follow the armed state, configured in the options,
  no automation to maintain. Name the detection switches, such as line crossing
  and intrusion, and they come on while any area is armed and overnight during a
  configurable window even while disarmed, and go off during the day once
  disarmed. A second, inverted group is on only while fully disarmed, off while
  armed, for a camera whose own audible warning should sound while the site is
  open. It reads this integration's own armed state, so no arm helper needs
  keeping in sync, verifies each switch actually followed and retries the
  laggards, and raises a notification if any detection switch will not follow.
  Off by default, and it never touches a switch until a site turns it on and
  names the switches.

## 1.6.8

- Stop a restart alerting that areas have armed when nothing has changed. The
  bridge retains area and log state, so the moment the integration resubscribes
  after a Home Assistant restart the broker replays it, and that replay was read
  as a live arm, disarm or event. A restart with an already armed panel raised a
  fresh armed alert, and a retained fire or Auxiliary log would have re-raised
  the fire and put a stale event back on the bus. A retained message now seeds
  the state quietly, so the entities are right after a restart, and only a live
  change, delivered with the retain flag clear, alerts.

## 1.6.7

- Fix a real fire closing the blinds. The fire link auto rearms, returning to
  normal within seconds while the fire is still going, and the fire indicator
  cleared on that return to normal. With the area still in its silent fire
  alarm, the cover force close then read the area as an intruder and shut the
  blinds mid fire. The fire indicator now latches through the auto rearm and
  clears only on an explicit reset or a backstop that will not drop it while an
  area is still in alarm, so the blinds stay open for the whole event. A disarm
  at the panel silences the ladder but no longer drops the indicator, since a
  keyholder often disarms to quiet the siren while the fire is still going.

## 1.6.6

- Fire test mode now ends reliably a couple of minutes after the last activation
  whatever path the fire arrives by. The auto exit was tied to the zone feed
  reporting the link going quiet, so a fire link that reports only as an
  Auxiliary log event left the test to run to the backstop window. The settle
  now restarts on every fire detection, log or zone feed, so it ends shortly
  after the fire link falls quiet on either.

## 1.6.5

- Fix the fire link raising a spurious intruder alert. The Auxiliary fire link
  trips the area on a silent alarm with no zone named, at the same instant as the
  fire, so the area path read it as a break in and raised ALARM ACTIVATION, which
  was not suppressed by a fire test. An area activation within thirty seconds of a
  fire is now taken to be that fire and routed to the fire path, deduplicated, so
  it raises no separate alarm and stays suppressed in a test. A genuine intruder,
  with no fire, still alarms as before.

## 1.6.4

- Fix a fire test shutting the blinds. The Auxiliary fire link raises a silent
  alarm that sets the area to triggered even while a test suppresses the fire
  indicator, so the cover force close read the test as an intruder and closed
  the blinds. The cover force helpers now treat a fire test like a fire and stay
  off through it, while a real intruder still closes the blinds. Alerts and the
  heating hold remain suppressed during a test as before.

## 1.6.3

- Per area cover force helpers, for a site that part arms its areas separately.
  `binary_sensor.<site>_<area>_cover_force_close` is on when that area is set and
  never during a fire, and `binary_sensor.<site>_<area>_cover_force_open` is on
  when that area is disarmed or during a fire, so each blind can follow its own
  area rather than the whole building. The armed state includes an entry or exit
  and an intruder activation, so an intruder still closes the blind while a fire
  opens it. Added as each area is discovered, and off by default like the site
  wide pair.

## 1.6.2

- Fire test mode now keeps a fire off the event bus entirely, whatever the panel
  calls the event. Previously the generic mirror of every panel event could put
  a Fire event on the bus during a test if the zone was a proper Fire type, so a
  fire consumer such as the heating hold might have reacted to a weekly check. A
  fire during a test is still recorded in recent events and the logbook.

## 1.6.1

- Two ready made cover control helpers, so a cover control automation needs no
  template. `binary_sensor.<site>_cover_force_close` is on when the site is
  armed and never during a fire, for the blueprint's auto_down_force.
  `binary_sensor.<site>_cover_force_open` is on when the site is disarmed or
  whenever there is a fire, for auto_up_force on a cover that stays open when
  unarmed. Both use this integration's own armed state, so no arm boolean needs
  maintaining, and both are off by default since they are only wanted where
  blinds follow the alarm.

## 1.6.0

- A test aware fire indicator, `binary_sensor.<site>_fire`, on while a real fire
  is active and cleared when the fire link returns to normal or the alerting is
  reset. It is the single source of truth for fire, for automations, the blinds
  and the heating hold to gate on, and a fire test deliberately never turns it
  on, so a weekly check leaves the blinds alone.
- Fire test mode, a switch for weekly fire alarm checks. While on, a fire is
  logged for the audit trail but raises no alert, no heating hold and no blind
  movement. It is deliberately the opposite of maintenance mode, which never
  touches critical, so it is ringed with safety: it fails back on when the fire
  link goes quiet after a test, when a backstop window elapses (30 minutes by
  default, hard capped at 60 and configurable), or on a restart, and says so
  when it ends.

## 1.5.1

- Fire conditions now also emit texecom_alerts_event (event_type Fire) on the
  Home Assistant bus, matching the README, so external automations can react. A
  fire was reaching the notification ladder but not the bus, because both fire
  pathways returned before the log handler's own bus emit, and the real
  Auxiliary alarm reached the bus only under its raw event type. The heating
  integration's fire safety hold, which listens for a Fire event, can now fire.

## 1.5.0

- Add an Alarm view to the shared Scout Hut sidebar dashboard, the same one the
  heating integration builds, so heating, fans and the alarm live under one tab.
  A Create dashboard button and a create_dashboard service add it, with the real
  entity ids resolved automatically. The write merges rather than replaces, so
  it never disturbs the heating views. For the heating Create dashboards button
  to leave the Alarm view alone in turn, the heating integration needs the same
  merge, a matching small change there.

## 1.4.2

- Emergency and fire alerts now carry a recognisable icon, a flame for fire and
  an alarm light for an intruder activation, on the phone and on the Android Auto
  car screen, so the two are told apart at a glance while driving. The alerts
  already carried car_ui for Android Auto; the app must stay enabled in the
  Android Auto launcher for it to show.
- Detect a fire link wired as an Auxiliary zone. On a real Premier Elite the
  fire zone fires as an Auxiliary alarm, not a Fire event, and it carries the
  zone number in the log parameter field rather than as a named zone, so the
  first fire test raised no fire alert. An Auxiliary alarm is now treated as
  fire whenever its zone is a configured fire zone, matched by that parameter as
  well as by name and id. A Fire type event is still caught as before, and an
  auxiliary alarm on any other zone is left alone.

## 1.4.1

- A separate fire sound can be set, so a fire is told from an intruder alarm by
  ear on iPhones. It uses a sound imported into the Companion app, the same way
  as the emergency sound, and falls back to the emergency sound when left blank.
  Android tells them apart through the spoken siren, which says the fire
  headline aloud, so no channel tone change is needed there.
- The Android spoken siren now says only the headline, kept short on purpose.
  Android cannot stop a spoken notification part way through, so a long sentence
  kept talking for seconds after a keyholder had already acknowledged. The full
  detail still shows on the notification and is spoken on the voice calls.

## 1.4.0

- Fire zones. A new option names the zones wired to a fire alarm link, by name
  or number, and any of them going active raises a distinct loud fire alert,
  armed or disarmed, separate from an intruder activation. It is caught three
  ways, the zone feed going active, the area triggering off a fire zone, and a
  Fire panel log event, and deduplicated so one fire raises one ladder rather
  than three. This matters for a fire link programmed as an Auxiliary zone,
  which raises only a silent alarm at the panel and emits no Fire log event, so
  watching the zone go active is the only dependable signal. The fire alert runs
  the full escalation ladder and clears from every phone on acknowledgement like
  any other emergency.

## 1.3.7

- Diagnostics now include a short history of recent log events, the last log
  event, the last activation and any zone problems, so a test activation can
  actually be seen in a diagnostics download rather than only in the moment.

## 1.3.6

- Arm and disarm notifications now pop up rather than landing silently in the
  background. They use a banner on iOS and a heads up on Android, on their own
  channel so a phone that had muted the activity channel still shows them, and
  so the other activity notifications stay quietly in the shade.

## 1.3.5

- The site reachability probe is debounced, so a flapping link no longer
  shouts site offline and back online over and over. The site is declared
  offline only after several consecutive failed probes and online again after
  a couple of successes, and the sensor follows that steadied state. A single
  missed probe over the VPN is now ignored.

## 1.3.4

- Notifications now read in words, matching the log sensor. A fault reads
  Alarm fault: Supervision fault rather than the raw SupervisionFault code.
- Notifications name the affected zone or device when the bridge provides one,
  so a supervision fault says which sensor rather than only its area.

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
