# RFU Fixtures & Results for Home Assistant

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andylynch&repository=ha-rfu-fixtures&category=integration)
[![Open your Home Assistant instance and start setting up RFU Fixtures & Results.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=rfu_fixtures)

Reads a team's public **England Rugby "fixtures and results" page** (the Game Management System pages on englandrugby.com) and turns it into Home Assistant sensors: league table, next fixture, results and an unofficial Elo rating for every team in the group.

Built for Blackheath U14 (U14 Boys Stage 1 Group 4), but it works for any team page with `team=`, `competition=`, `division=` and `season=` in the URL.

## Install

**Manual:** copy `custom_components/rfu_fixtures` into your Home Assistant `config/custom_components/` folder (Samba, File editor or SSH add-on), then restart Home Assistant.

**HACS (one click):** press the first button above. It opens HACS on your Home Assistant with this repository filled in as a custom *Integration* repository; install **RFU Fixtures & Results**, then restart. The second button then starts setup.

Then **Settings → Devices & services → Add integration → RFU Fixtures & Results** and paste the page URL, e.g.

```
https://www.englandrugby.com/fixtures-and-results/search-results?team=2514&competition=2075&division=79247&season=2026-2027
```

Leave **"Also read the other teams' pages"** on if you want group results and Elo (it reads one page per team in the group).

## Entities (for Blackheath U14)

| Entity | State | Key attributes |
|---|---|---|
| `sensor.blackheath_u14_league_position` | position (e.g. 4) | `table` (all rows: P W D L PF PA +/- TB LB Pts, team ids), `division`, `points` |
| `sensor.blackheath_u14_next_fixture` | date (time is a midday placeholder: the RFU page has no kick-off) | `opponent`, `venue` (home/away), `win_probability`, `flags`, `fixtures` (full list) |
| `sensor.blackheath_u14_last_result` | e.g. `W 24-12 v Ashford U14s` or `No results yet` | `results` (ours), `group_results` (everyone's), `group_results_complete` |
| `sensor.blackheath_u14_elo_rating` | our Elo | `ratings` (all teams), `history` (per match), `matches_rated` |

The big list attributes are kept out of the recorder database.

### Duplicate fixtures

The RFU feed sometimes keeps an old fixture alongside its replacement on the same day. Both get `flags: ["clash"]`; the one with the older match id also gets `"probably_stale"` and is skipped when choosing the next fixture. (On 11 Oct 2026 this correctly picks Ashford over Folkestone.)

### Event

When a new result appears for your team the integration fires `rfu_fixtures_new_result` with the match (date, home/away, scores, match id), e.g. for a phone notification:

```yaml
trigger:
  - trigger: event
    event_type: rfu_fixtures_new_result
action:
  - action: notify.mobile_app_your_phone
    data:
      message: "{{ trigger.event.data.home }} {{ trigger.event.data.home_score }}-{{ trigger.event.data.away_score }} {{ trigger.event.data.away }}"
```

## Polling and fair use

Every 3 hours, and every 30 minutes on Sunday 12:00-21:00 when youth results are usually entered. With group fetching on that's 6 page loads per refresh, spaced 3 seconds apart. The integration identifies itself honestly in its User-Agent. Please keep it gentle and check englandrugby.com's terms of use; if the site blocks it, the sensors go unavailable rather than retrying hard.

## Elo

Unofficial. Every team starts at 1500; after each game `delta = 32 × ln(|margin| + 1) × (result − expected)`, expected = `1 / (1 + 10^((Rb − Ra)/400))`. Games involving teams no longer in the table (e.g. a withdrawn side) aren't rated.

## Known limits

- No kick-off times or venues (not on the page).
- Score format on played matches is matched generically (`24 - 12`, `24–12`, `24:12`). If the site uses something else, a warning appears in the log with the raw text; please report it.
- If the RFU changes its page layout the integration will report "no table, fixtures or results were found".

## Tests

`python -m pytest tests -q` (needs `beautifulsoup4` and `pytest`) runs the parser against a saved copy of the Blackheath U14 page and checks the Elo maths.
