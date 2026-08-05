"""Config and options flow for Texecom Alerts."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import voluptuous as vol
from homeassistant.components import mqtt, webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_ACK_ENDPOINT,
    CONF_AREAS,
    CONF_AUTO_PHONES,
    CONF_BATTERY_LOW_VOLTS,
    CONF_CRITICAL_SOUND,
    CONF_ESCALATE_TAMPERS,
    CONF_GATEWAY_HOST,
    CONF_GATEWAY_PORT,
    CONF_LADDER_ROUNDS,
    CONF_MAINTENANCE_HOURS,
    CONF_NOTIFY_ACTIVITY,
    CONF_PHONE_ACK,
    CONF_PREFIX,
    CONF_PROBE_SECONDS,
    CONF_PUSH_SERVICES,
    CONF_RECIPIENTS,
    CONF_ROUND_SECONDS,
    CONF_SITE_NAME,
    CONF_SMS_SERVICE,
    CONF_STALE_MINUTES,
    CONF_TTS_SIREN_SERVICES,
    CONF_VOICE_SERVICE,
    CONF_WEBHOOK_ID,
    DEFAULT_AUTO_PHONES,
    DEFAULT_BATTERY_LOW_VOLTS,
    DEFAULT_CRITICAL_SOUND,
    DEFAULT_ESCALATE_TAMPERS,
    DEFAULT_GATEWAY_PORT,
    DEFAULT_LADDER_ROUNDS,
    DEFAULT_MAINTENANCE_HOURS,
    DEFAULT_NOTIFY_ACTIVITY,
    DEFAULT_PHONE_ACK,
    DEFAULT_PREFIX,
    DEFAULT_PROBE_SECONDS,
    DEFAULT_ROUND_SECONDS,
    DEFAULT_SITE_NAME,
    DEFAULT_STALE_MINUTES,
    DISCOVERY_SECONDS,
    DOMAIN,
)


async def _discover_areas(hass: Any, prefix: str) -> dict[str, str]:
    """Listen for retained area messages and return id to name.

    texecom2mqtt retains area state, so retained messages land almost
    immediately. The wait is generous rather than necessary.
    """
    found: dict[str, str] = {}

    @callback
    def _got(msg: Any) -> None:
        try:
            data = json.loads(msg.payload)
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        area_id = str(data.get("id") or data.get("number") or "")
        if area_id:
            found[area_id] = str(data.get("name") or area_id)

    if not await mqtt.async_wait_for_mqtt_client(hass):
        return found

    unsub = await mqtt.async_subscribe(hass, f"{prefix}/area/+", _got, qos=0)
    try:
        await asyncio.sleep(DISCOVERY_SECONDS)
    finally:
        unsub()
    return found


class TexecomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._data: dict[str, Any] = {}
        self._discovered: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Site and connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            self._discovered = await _discover_areas(self.hass, user_input[CONF_PREFIX])
            if not self._discovered:
                errors["base"] = "no_areas"
            else:
                return await self.async_step_areas()

        schema = vol.Schema(
            {
                vol.Required(CONF_SITE_NAME, default=DEFAULT_SITE_NAME): str,
                vol.Required(CONF_PREFIX, default=DEFAULT_PREFIX): str,
                vol.Optional(CONF_GATEWAY_HOST, default=""): str,
                vol.Optional(CONF_GATEWAY_PORT, default=DEFAULT_GATEWAY_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which discovered areas to monitor."""
        if user_input is not None:
            self._data[CONF_AREAS] = user_input[CONF_AREAS]
            return await self.async_step_notify()

        options = [
            SelectOptionDict(value=area_id, label=f"{name} ({area_id})")
            for area_id, name in sorted(self._discovered.items())
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AREAS, default=list(self._discovered)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="areas", data_schema=schema)

    async def async_step_notify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Notification channels and recipients."""
        if user_input is not None:
            self._data.update(user_input)
            # Mint the acknowledgement webhook id up front so its URL is stable.
            self._data[CONF_WEBHOOK_ID] = webhook.async_generate_id()
            return self.async_create_entry(
                title=self._data[CONF_SITE_NAME], data=self._data
            )

        services = _notify_service_options(self.hass)
        return self.async_show_form(
            step_id="notify", data_schema=_notify_schema({}, services)
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> TexecomOptionsFlow:
        """Return the options flow."""
        return TexecomOptionsFlow()


class TexecomOptionsFlow(OptionsFlow):
    """Change notification settings and thresholds without a restart."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        services = _notify_service_options(self.hass)
        schema = _notify_schema(current, services).extend(
            {
                vol.Optional(
                    CONF_STALE_MINUTES,
                    default=current.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5, max=1440, step=5, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_BATTERY_LOW_VOLTS,
                    default=current.get(
                        CONF_BATTERY_LOW_VOLTS, DEFAULT_BATTERY_LOW_VOLTS
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=10, max=14, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_LADDER_ROUNDS,
                    default=current.get(CONF_LADDER_ROUNDS, DEFAULT_LADDER_ROUNDS),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=10, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_ROUND_SECONDS,
                    default=current.get(CONF_ROUND_SECONDS, DEFAULT_ROUND_SECONDS),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=30, max=600, step=10, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_PROBE_SECONDS,
                    default=current.get(CONF_PROBE_SECONDS, DEFAULT_PROBE_SECONDS),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=30, max=900, step=30, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_MAINTENANCE_HOURS,
                    default=current.get(
                        CONF_MAINTENANCE_HOURS, DEFAULT_MAINTENANCE_HOURS
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=24, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _notify_service_options(hass: Any) -> list[SelectOptionDict]:
    """List the notify services Home Assistant currently knows about.

    Presenting these as pickable options means a keyholder chooses phones from
    a dropdown rather than writing a notify group in YAML. Custom values stay
    allowed so a service not yet loaded can still be typed.
    """
    services = hass.services.async_services().get("notify", {})
    return [
        SelectOptionDict(value=f"notify.{name}", label=f"notify.{name}")
        for name in sorted(services)
    ]


def _notify_schema(
    current: dict[str, Any], services: list[SelectOptionDict]
) -> vol.Schema:
    """Build the notification part of the schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_AUTO_PHONES,
                default=current.get(CONF_AUTO_PHONES, DEFAULT_AUTO_PHONES),
            ): BooleanSelector(),
            vol.Optional(
                CONF_PUSH_SERVICES,
                default=current.get(CONF_PUSH_SERVICES, []),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=services,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_SMS_SERVICE, default=current.get(CONF_SMS_SERVICE, "")
            ): SelectSelector(
                SelectSelectorConfig(
                    options=services,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_VOICE_SERVICE, default=current.get(CONF_VOICE_SERVICE, "")
            ): SelectSelector(
                SelectSelectorConfig(
                    options=services,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_RECIPIENTS, default=current.get(CONF_RECIPIENTS, [])
            ): TextSelector(TextSelectorConfig(multiple=True)),
            vol.Optional(
                CONF_ESCALATE_TAMPERS,
                default=current.get(CONF_ESCALATE_TAMPERS, DEFAULT_ESCALATE_TAMPERS),
            ): BooleanSelector(),
            vol.Optional(
                CONF_NOTIFY_ACTIVITY,
                default=current.get(CONF_NOTIFY_ACTIVITY, DEFAULT_NOTIFY_ACTIVITY),
            ): BooleanSelector(),
            vol.Optional(
                CONF_PHONE_ACK,
                default=current.get(CONF_PHONE_ACK, DEFAULT_PHONE_ACK),
            ): BooleanSelector(),
            vol.Optional(
                CONF_ACK_ENDPOINT,
                default=current.get(CONF_ACK_ENDPOINT, ""),
            ): str,
            vol.Optional(
                CONF_CRITICAL_SOUND,
                default=current.get(CONF_CRITICAL_SOUND, DEFAULT_CRITICAL_SOUND),
            ): str,
            vol.Optional(
                CONF_TTS_SIREN_SERVICES,
                default=current.get(CONF_TTS_SIREN_SERVICES, []),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=services,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )
