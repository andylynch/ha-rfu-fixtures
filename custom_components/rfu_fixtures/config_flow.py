"""Config flow: paste the England Rugby fixtures page URL for your team."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_COMPETITION,
    CONF_DIVISION,
    CONF_FETCH_GROUP,
    CONF_SEASON,
    CONF_TEAM,
    CONF_URL,
    DOMAIN,
)
from .coordinator import fetch_html
from .parser import build_url, parse_page, parse_search_url


class RfuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                ids = parse_search_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "bad_url"
            else:
                await self.async_set_unique_id(f"{ids['team']}_{ids['division']}_{ids['season']}")
                self._abort_if_unique_id_configured()
                url = build_url(ids["team"], ids["competition"], ids["division"], ids["season"])
                try:
                    html = await fetch_html(async_get_clientsession(self.hass), url)
                    page = await self.hass.async_add_executor_job(parse_page, html, ids["team"])
                except (aiohttp.ClientError, asyncio.TimeoutError, UpdateFailed):
                    errors["base"] = "cannot_connect"
                else:
                    if not page.table and not page.fixtures:
                        errors["base"] = "no_data"
                    else:
                        title = f"{page.team or ids['team']} · {page.division or ids['division']}"
                        return self.async_create_entry(
                            title=title,
                            data={
                                CONF_TEAM: ids["team"],
                                CONF_COMPETITION: ids["competition"],
                                CONF_DIVISION: ids["division"],
                                CONF_SEASON: ids["season"],
                                CONF_FETCH_GROUP: user_input.get(CONF_FETCH_GROUP, True),
                            },
                        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): str,
                    vol.Optional(CONF_FETCH_GROUP, default=True): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return RfuOptionsFlow()


class RfuOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            CONF_FETCH_GROUP, self.config_entry.data.get(CONF_FETCH_GROUP, True)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Optional(CONF_FETCH_GROUP, default=current): bool}),
        )
