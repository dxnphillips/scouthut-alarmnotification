"""Inbound acknowledgement webhook for keyholders without Home Assistant.

A keyholder who only has a phone can stop the escalation ladder by pressing a
key on the Twilio voice call or replying to the alert SMS. Twilio posts to a
webhook this module registers, which resolves the site and acknowledges it.

Home Assistant must be reachable by Twilio over the public internet with a
certificate Twilio trusts. Twilio refuses a self signed certificate, so a real
certificate or a trusted tunnel is required for any of this to arrive.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError

from .const import CONF_PHONE_ACK, CONF_WEBHOOK_ID, DOMAIN

if TYPE_CHECKING:
    from . import TexecomConfigEntry

_LOGGER = logging.getLogger(__name__)

# Words accepted in an SMS reply. STOP is deliberately not here, because Twilio
# treats it as a carrier level opt out and never delivers it to the webhook.
_ACK_WORDS = frozenset({"ACK", "ACKNOWLEDGE", "ACKNOWLEDGED", "OK", "YES", "1"})


def async_register_webhook(hass: HomeAssistant, entry: TexecomConfigEntry) -> None:
    """Register the acknowledgement webhook for a config entry."""
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        return
    webhook.async_register(
        hass,
        DOMAIN,
        f"Texecom Alerts {entry.title}",
        webhook_id,
        _handle,
        allowed_methods=["GET", "POST"],
        local_only=False,
    )

    # Log the address once so it can be pasted into the Twilio number for SMS
    # replies. Only when the option is on, since it is otherwise unused.
    if entry.options.get(CONF_PHONE_ACK, entry.data.get(CONF_PHONE_ACK, False)):
        try:
            url = webhook.async_generate_url(hass, webhook_id)
        except NoURLAvailableError:
            url = f"/api/webhook/{webhook_id}"
        _LOGGER.info(
            "Phone acknowledgement webhook for %s: %s. Twilio needs a "
            "certificate it trusts to reach this, a self signed one is refused",
            entry.title,
            url,
        )


def async_unregister_webhook(hass: HomeAssistant, entry: TexecomConfigEntry) -> None:
    """Remove the acknowledgement webhook for a config entry."""
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if webhook_id:
        webhook.async_unregister(hass, webhook_id)


def _twiml(body: str) -> web.Response:
    """Wrap a TwiML fragment in a response Twilio will accept."""
    return web.Response(
        text=f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
        content_type="text/xml",
    )


def _entry_for(hass: HomeAssistant, webhook_id: str) -> TexecomConfigEntry | None:
    """Find the loaded config entry that owns this webhook."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            getattr(entry, "runtime_data", None)
            and entry.data.get(CONF_WEBHOOK_ID) == webhook_id
        ):
            return entry
    return None


async def _handle(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    """Acknowledge from a Twilio voice keypress or SMS reply."""
    entry = _entry_for(hass, webhook_id)
    if entry is None:
        return web.Response(status=404)
    alerting = entry.runtime_data.alerting

    try:
        form = await request.post()
    except (ValueError, TypeError):
        form = {}

    body = str(form.get("Body") or "").strip()
    digits = str(form.get("Digits") or "").strip()
    caller = str(form.get("From") or "a keyholder")

    # An SMS reply.
    if body:
        if body.upper() in _ACK_WORDS:
            alerting.acknowledge(by=f"{caller} by SMS")
            return _twiml("<Message>Alarm acknowledged. Thank you.</Message>")
        return _twiml("<Message>Reply ACK to acknowledge the alarm.</Message>")

    # A key pressed during the voice call.
    if digits:
        if digits == "1":
            alerting.acknowledge(by=f"{caller} by phone")
            return _twiml("<Say>Acknowledged. Goodbye.</Say><Hangup/>")
        return _twiml("<Say>Not acknowledged. Goodbye.</Say><Hangup/>")

    # The initial fetch when Twilio places the call: speak the alert and wait
    # for a single digit. Gather with no action reposts to this same URL.
    spoken = escape(alerting.spoken_alert())
    return _twiml(
        f'<Gather numDigits="1"><Say>{spoken} Press 1 to acknowledge.</Say>'
        "</Gather><Say>No key pressed. Goodbye.</Say>"
    )
