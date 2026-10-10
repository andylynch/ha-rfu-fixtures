"""Sensors: table position, next fixture, last result, Elo."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import RfuCoordinator
from .parser import build_url


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    c: RfuCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([PositionSensor(c), NextFixtureSensor(c), LastResultSensor(c), EloSensor(c)])


class _Base(CoordinatorEntity[RfuCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = "Data: englandrugby.com (Game Management System)"
    # Keep the big lists out of the recorder database; they're for dashboards.
    _unrecorded_attributes = frozenset({"table", "fixtures", "results", "group_results", "history"})

    def __init__(self, c: RfuCoordinator, key: str, name: str, icon: str) -> None:
        super().__init__(c)
        self._attr_unique_id = f"{c.entry.unique_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        team = (c.data or {}).get("team") or f"Team {c.team_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, c.entry.unique_id)},
            name=team,
            manufacturer="England Rugby (RFU)",
            model=(c.data or {}).get("division") or "Fixtures & results",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=build_url(c.team_id, c.competition, c.division, c.season),
        )

    @property
    def d(self) -> dict[str, Any]:
        return self.coordinator.data or {}


class PositionSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c: RfuCoordinator) -> None:
        super().__init__(c, "position", "League position", "mdi:format-list-numbered")

    @property
    def native_value(self) -> int | None:
        row = next((r for r in self.d.get("table", []) if r["team_id"] == self.coordinator.team_id), None)
        return row["position"] if row else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        row = next((r for r in self.d.get("table", []) if r["team_id"] == self.coordinator.team_id), {})
        return {
            "division": self.d.get("division"),
            "teams": len(self.d.get("table", [])),
            "played": row.get("played"),
            "points": row.get("points"),
            "table": self.d.get("table", []),
        }


class NextFixtureSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, c: RfuCoordinator) -> None:
        super().__init__(c, "next_fixture", "Next fixture", "mdi:calendar-star")

    @property
    def native_value(self) -> datetime | None:
        nxt = self.d.get("next_fixture")
        if not nxt or not nxt.get("date"):
            return None
        # The RFU page gives a date but no kick-off; use midday local as a placeholder.
        return datetime.combine(
            date.fromisoformat(nxt["date"]), time(12, 0), tzinfo=dt_util.get_default_time_zone()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nxt = self.d.get("next_fixture") or {}
        return {
            "opponent": nxt.get("opponent"),
            "venue": nxt.get("venue"),
            "home": nxt.get("home"),
            "away": nxt.get("away"),
            "match_id": nxt.get("match_id"),
            "win_probability": nxt.get("win_probability"),
            "kickoff_known": False,
            "flags": nxt.get("flags", []),
            "fixtures": self.d.get("fixtures", []),
        }


class LastResultSensor(_Base):
    def __init__(self, c: RfuCoordinator) -> None:
        super().__init__(c, "last_result", "Last result", "mdi:scoreboard")

    @property
    def native_value(self) -> str | None:
        r = self.d.get("last_result")
        if not r:
            return "No results yet"
        home = r["home_id"] == self.coordinator.team_id
        us, them = (r["home_score"], r["away_score"]) if home else (r["away_score"], r["home_score"])
        wdl = "W" if us > them else "L" if us < them else "D"
        return f"{wdl} {us}-{them} v {r['away'] if home else r['home']}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self.d.get("last_result") or {}
        return {
            "date": r.get("date"),
            "match_id": r.get("match_id"),
            "results": self.d.get("our_results", []),
            "group_results": self.d.get("group_results", []),
            "group_results_complete": self.d.get("group_results_complete"),
        }


class EloSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c: RfuCoordinator) -> None:
        super().__init__(c, "elo", "Elo rating", "mdi:chart-line-variant")

    @property
    def native_value(self) -> int | None:
        team = self.d.get("team")
        return (self.d.get("elo") or {}).get("ratings", {}).get(team)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        e = self.d.get("elo") or {}
        return {
            "ratings": e.get("ratings", {}),
            "matches_rated": e.get("matches_rated", 0),
            "history": e.get("history", []),
            "method": "Start 1500, K=32 scaled by ln(margin+1); unofficial",
        }
