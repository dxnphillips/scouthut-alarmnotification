"""Classification is the highest value thing to test.

An event in the wrong bucket is the difference between a phone call at three
in the morning and a silent logbook entry.
"""

from __future__ import annotations

from custom_components.texecom_alerts.const import (
    ACTIVITY_EVENTS,
    CRITICAL_EVENTS,
    FAULT_EVENTS,
    FIRE_EVENTS,
    SILENT_EVENTS,
    SMS_FAULTS,
    TAMPER_EVENTS,
)


def test_buckets_do_not_overlap() -> None:
    """No event type may appear in two severity buckets."""
    assert not CRITICAL_EVENTS & FAULT_EVENTS
    assert not CRITICAL_EVENTS & ACTIVITY_EVENTS
    assert not FAULT_EVENTS & ACTIVITY_EVENTS


def test_silent_events_are_critical() -> None:
    """A silent event that is not critical would never escalate at all."""
    assert SILENT_EVENTS <= CRITICAL_EVENTS


def test_sms_faults_are_faults() -> None:
    """SMS worthy faults must be classified as faults to reach the check."""
    assert SMS_FAULTS <= FAULT_EVENTS


def test_tampers_are_faults() -> None:
    """Tampers are faults so escalation is opt in, not a reclassification."""
    assert TAMPER_EVENTS <= FAULT_EVENTS
    assert not TAMPER_EVENTS & CRITICAL_EVENTS


def test_fire_events_are_critical() -> None:
    """Fire log events route through the fire alert, which must be critical.

    They are held apart in FIRE_EVENTS so the wording and tag are right, but a
    fire that did not escalate would be worse than useless.
    """
    assert FIRE_EVENTS <= CRITICAL_EVENTS
    assert not FIRE_EVENTS & SILENT_EVENTS


def test_duress_is_silent() -> None:
    """Regression guard. Duress must never produce an audible alert."""
    assert "DuressCodeAlarm" in SILENT_EVENTS
    assert "KeypadSilentPA" in SILENT_EVENTS
    assert "PASilent" in SILENT_EVENTS
