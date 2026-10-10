"""Fetch, parse and combine RFU pages for one team."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import elo
from .const import (
    CONF_COMPETITION,
    CONF_DIVISION,
    CONF_FETCH_GROUP,
    CONF_SEASON,
    CONF_TEAM,
    DOMAIN,
    EVENT_NEW_RESULT,
    INTERVAL_MATCHDAY,
    INTERVAL_NORMAL,
    MATCHDAY_HOURS,
    MATCHDAY_WEEKDAY,
    REQUEST_GAP_SECONDS,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from .parser import build_url, is_ours, parse_page

_LOGGER = logging.getLogger(__name__)


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
    ) as resp:
        if resp.status != 200:
            raise UpdateFailed(f"englandrugby.com returned HTTP {resp.status} for {url}")
        return await resp.text()


class RfuCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One coordinator per configured team."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_{entry.data[CONF_TEAM]}", update_interval=INTERVAL_NORMAL
        )
        self.entry = entry
        self.team_id: int = entry.data[CONF_TEAM]
        self.competition: int = entry.data[CONF_COMPETITION]
        self.division: int = entry.data[CONF_DIVISION]
        self.season: str = entry.data[CONF_SEASON]
        self._session = async_get_clientsession(hass)
        self._seen_results: set[int] | None = None

    def _url(self, team: int) -> str:
        return build_url(team, self.competition, self.division, self.season)

    def _next_interval(self) -> timedelta:
        now = dt_util.now()
        if now.weekday() == MATCHDAY_WEEKDAY and now.hour in MATCHDAY_HOURS:
            return INTERVAL_MATCHDAY
        return INTERVAL_NORMAL

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            html = await fetch_html(self._session, self._url(self.team_id))
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"Could not reach englandrugby.com: {err}") from err

        page = await self.hass.async_add_executor_job(parse_page, html, self.team_id)
        if not page.table and not page.fixtures and not page.results:
            raise UpdateFailed("Page loaded but no table, fixtures or results were found (layout changed?)")
        data = page.as_dict()

        # Results from every team in the group, for Elo. Merged by match id.
        results: dict[Any, dict[str, Any]] = {}
        for r in data["results"]:
            results[r["match_id"] or (r["date"], r["home"], r["away"])] = r
        group_ok = True
        if self.entry.options.get(CONF_FETCH_GROUP, self.entry.data.get(CONF_FETCH_GROUP, True)):
            for row in data["table"]:
                tid = row["team_id"]
                if not tid or tid == self.team_id:
                    continue
                await asyncio.sleep(REQUEST_GAP_SECONDS)
                try:
                    other_html = await fetch_html(self._session, self._url(tid))
                    other = await self.hass.async_add_executor_job(parse_page, other_html, tid)
                except (aiohttp.ClientError, asyncio.TimeoutError, UpdateFailed) as err:
                    _LOGGER.debug("Skipping group team %s: %s", tid, err)
                    group_ok = False
                    continue
                for r in other.as_dict()["results"]:
                    if r["competition"] and data["division"] and r["competition"] != data["division"]:
                        continue
                    results.setdefault(r["match_id"] or (r["date"], r["home"], r["away"]), r)

        all_results = sorted(results.values(), key=lambda r: (r["date"], r["match_id"] or 0))
        for r in all_results:
            if r["raw_score"] and not r["played"] and r["raw_score"].upper() not in ("V", "VS"):
                _LOGGER.warning("Unrecognised score format %r (match %s) - please report", r["raw_score"], r["match_id"])

        table_teams = [row["team"] for row in data["table"]]
        # Only rate games between teams still in the table (withdrawn teams'
        # games are dropped from the official table too).
        rated = [r for r in all_results if r["home"] in table_teams and r["away"] in table_teams]
        rating = elo.compute(rated, table_teams)
        data["group_results"] = all_results
        data["group_results_complete"] = group_ok
        data["elo"] = rating

        our = data["team"] or next((t["team"] for t in data["table"] if t["team_id"] == self.team_id), None)
        today = dt_util.now().date().isoformat()
        upcoming = [
            f for f in data["fixtures"] if f["date"] >= today and "probably_stale" not in f["flags"]
        ]
        nxt = upcoming[0] if upcoming else None
        if nxt and our:
            opp = nxt["away"] if is_ours(nxt, self.team_id) == "home" else nxt["home"]
            nxt = {
                **nxt,
                "opponent": opp,
                "venue": is_ours(nxt, self.team_id),
                "win_probability": elo.win_probability(rating["ratings"], our, opp),
            }
        data["next_fixture"] = nxt
        ours = [r for r in all_results if is_ours(r, self.team_id)]
        data["our_results"] = ours
        data["last_result"] = next((r for r in reversed(ours) if r["played"]), None)

        self._announce_new_results(ours)
        self.update_interval = self._next_interval()
        return data

    def _announce_new_results(self, ours: list[dict[str, Any]]) -> None:
        played = {r["match_id"]: r for r in ours if r["played"] and r["match_id"]}
        if self._seen_results is None:  # first refresh after start: don't replay history
            self._seen_results = set(played)
            return
        for mid, r in played.items():
            if mid not in self._seen_results:
                self.hass.bus.async_fire(EVENT_NEW_RESULT, {"team_id": self.team_id, **r})
        self._seen_results |= set(played)
