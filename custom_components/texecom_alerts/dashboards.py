"""One-press creation of the Scout Hut alarm dashboard view.

Adds an Alarm view to the shared "Scout Hut" sidebar dashboard, the same one
the scout_hut_heating integration builds, so heating, fans and the alarm all
live under one tab. Entity ids are resolved from the entity registry, so
nothing needs hand editing.

The write is deliberately a merge, not a replace: any view this integration
does not own, the heating Home, Heating and Fans views in particular, is kept
untouched, and only the Alarm view is added or refreshed. That way pressing
this button never wipes the heating views, and, once the heating integration
merges in the same way, its own Create dashboards button never wipes this one.

The Lovelace storage API is semi-internal and has been reshaped across Home
Assistant releases, so everything HA facing here is feature detected and fails
soft: the caller surfaces any error as a notification, and the sidebar picks a
newly created dashboard up on the next restart.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

# Shared with scout_hut_heating on purpose, so both write to one dashboard.
DASHBOARD_URL = "scout-hut"
DASHBOARD_TITLE = "Scout Hut"
DASHBOARD_ICON = "mdi:campfire"

# The Alarm view this integration owns. Only this path is replaced on a write;
# every other view is left alone.
VIEW_PATH = "alarm"
VIEW_TITLE = "Alarm"
VIEW_ICON = "mdi:shield-home"

NOTIFY_DASHBOARDS = "texecom_alerts_dashboards"

# Returned when the dashboard was created or updated in storage but the running
# Lovelace could not be told about it live (modern HA keeps its dashboards
# collection private): a restart will surface it.
RESTART_REQUIRED = "__restart_required__"

# (helper key, display name) rows. A row is silently dropped when the helper is
# missing from the registry, so the view is always valid.
_HEALTH = [
    ("panel_reachable", "Panel in contact"),
    ("site_reachable", "Site reachable"),
    ("bridge", "Bridge online"),
    ("data_stale", "Panel data stale"),
    ("zone_problem", "Zone problem"),
]
_POWER = [
    ("panel_voltage", "Panel voltage"),
    ("battery_voltage", "Battery voltage"),
    ("panel_current", "Panel current"),
    ("battery_charging_current", "Battery charging current"),
]
_CONTROLS = [
    ("maintenance_mode", "Maintenance mode"),
    ("acknowledge", "Acknowledge"),
    ("test_alerts", "Test alerts"),
]


def _rows(emap: dict[str, str], spec: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"entity": emap[key], "name": name} for key, name in spec if key in emap]


def _card(title: str, rows: list[dict[str, str]]) -> dict[str, Any] | None:
    return {"type": "entities", "title": title, "entities": rows} if rows else None


def build_view(emap: dict[str, str]) -> dict[str, Any]:
    """Build the Alarm view from resolved entity ids."""
    # Status: the combined state, each monitored area, what set it off, the
    # escalation state and the last event. Area rows carry no explicit name, so
    # each shows its own area name, Main or Office rather than a helper key.
    status: list[dict[str, str]] = []
    if "system_state" in emap:
        status.append({"entity": emap["system_state"], "name": "System state"})
    for key in sorted(k for k in emap if k.startswith("area_")):
        status.append({"entity": emap[key]})
    for key, name in (
        ("any_armed", "Any area armed"),
        ("escalation", "Escalation"),
        ("last_activation", "Last activation zone"),
        ("last_log", "Last log event"),
    ):
        if key in emap:
            status.append({"entity": emap[key], "name": name})

    cards = [
        card
        for card in (
            _card("Alarm", status),
            _card("System health", _rows(emap, _HEALTH)),
            _card("Power", _rows(emap, _POWER)),
            _card("Controls", _rows(emap, _CONTROLS)),
        )
        if card is not None
    ]
    return {
        "title": VIEW_TITLE,
        "path": VIEW_PATH,
        "icon": VIEW_ICON,
        "cards": cards,
    }


def _entity_map(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    """Map each integration helper key to its real entity id."""
    registry = er.async_get(hass)
    prefix = f"{entry_id}_"
    emap: dict[str, str] = {}
    for entry in er.async_entries_for_config_entry(registry, entry_id):
        unique_id = getattr(entry, "unique_id", None) or ""
        if unique_id.startswith(prefix):
            emap[unique_id[len(prefix) :]] = entry.entity_id
    return emap


async def _load_existing(dashboard: Any) -> dict[str, Any] | None:
    """Return the dashboard's current stored config, or None if there is none.

    async_load has taken both a required and an optional force argument across
    versions, and raises when nothing has been saved yet, so both shapes are
    tried and any failure is treated as an empty dashboard.
    """
    for args in ((False,), ()):
        try:
            existing = await dashboard.async_load(*args)
        except TypeError:
            continue
        except Exception:
            return None
        return existing if isinstance(existing, dict) else None
    return None


def _merge(existing: dict[str, Any] | None, view: dict[str, Any]) -> dict[str, Any]:
    """Add or refresh the Alarm view while keeping every other view intact."""
    config = dict(existing) if isinstance(existing, dict) else {}
    kept = [
        v
        for v in config.get("views", [])
        if isinstance(v, dict) and v.get("path") != VIEW_PATH
    ]
    kept.append(view)
    config["views"] = kept
    return config


async def async_create_or_update(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Create or refresh the Alarm view on the Scout Hut dashboard.

    Returns None on success, RESTART_REQUIRED when the dashboard was written but
    could not be registered live, or an error string the caller can surface.
    """
    view = build_view(_entity_map(hass, entry.entry_id))

    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return "the Lovelace integration is not loaded"

    def _get(name: str) -> Any:
        value = getattr(lovelace, name, None)
        if value is None and isinstance(lovelace, dict):
            value = lovelace.get(name)
        return value

    dashboards = _get("dashboards")
    if dashboards is None:
        return "this Home Assistant version does not expose the dashboard store"

    created_offline = False
    item: dict[str, Any] | None = None
    if DASHBOARD_URL not in dashboards:
        collection = _get("dashboards_collection")
        if collection is None:
            # Modern HA (2025.2+) keeps the running collection private. Load our
            # own instance over the same storage: the item persists and the
            # sidebar picks it up on the next restart.
            from homeassistant.components.lovelace import (
                dashboard as lovelace_dashboard,
            )

            collection = lovelace_dashboard.DashboardsCollection(hass)
            await collection.async_load()
            created_offline = True
        existing_item = [
            entry_item
            for entry_item in collection.async_items()
            if entry_item.get("url_path") == DASHBOARD_URL
        ]
        if existing_item:
            item = existing_item[0]
        else:
            item = await collection.async_create_item(
                {
                    "url_path": DASHBOARD_URL,
                    "title": DASHBOARD_TITLE,
                    "icon": DASHBOARD_ICON,
                    "show_in_sidebar": True,
                    "require_admin": False,
                }
            )

    dashboard = dashboards.get(DASHBOARD_URL)
    if dashboard is None and item is not None:
        # Not registered with the running Lovelace: write straight to the
        # dashboard's own store so it is ready when the panel appears.
        from homeassistant.components.lovelace import dashboard as lovelace_dashboard

        dashboard = lovelace_dashboard.LovelaceStorage(hass, item)
    if dashboard is None:
        return "the dashboard was created but did not register"

    existing = await _load_existing(dashboard)
    await dashboard.async_save(_merge(existing, view))
    return RESTART_REQUIRED if created_offline else None


async def async_create_dashboards(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create or refresh the dashboard and tell the user how it went."""
    try:
        error = await async_create_or_update(hass, entry)
    except Exception as err:
        error = str(err)

    if error == RESTART_REQUIRED:
        persistent_notification.async_create(
            hass,
            (
                "The Alarm view has been saved to the 'Scout Hut' dashboard, but "
                "this Home Assistant version cannot add it to the sidebar live. "
                "Restart Home Assistant and it will appear."
            ),
            title="Texecom Alerts: Alarm view saved, restart to see it",
            notification_id=NOTIFY_DASHBOARDS,
        )
    elif error:
        persistent_notification.async_create(
            hass,
            (f"Could not add the Alarm view to the dashboard automatically ({error})."),
            title="Texecom Alerts: dashboard update failed",
            notification_id=NOTIFY_DASHBOARDS,
        )
    else:
        persistent_notification.async_create(
            hass,
            (
                "The Alarm view has been added to the 'Scout Hut' dashboard in "
                "the sidebar, alongside the heating views if they are present."
            ),
            title="Texecom Alerts: Alarm view added",
            notification_id=NOTIFY_DASHBOARDS,
        )
