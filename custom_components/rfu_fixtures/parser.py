"""Parse an englandrugby.com fixtures-and-results 'search-results' page.

Pure functions only (no Home Assistant imports) so the parser can be unit
tested against a saved copy of the page.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.englandrugby.com"
SEARCH_PATH = "/fixtures-and-results/search-results"

_SCORE_RE = re.compile(r"(\d+)\s*[-–:]\s*(\d+)|(\d+)\D+?(\d+)")


@dataclass
class TableRow:
    position: int
    team: str
    team_id: int | None
    played: int
    won: int
    drawn: int
    lost: int
    points_for: int
    points_against: int
    difference: int
    try_bonus: int
    losing_bonus: int
    points: int


@dataclass
class Match:
    match_id: int | None
    date: str  # ISO yyyy-mm-dd
    competition: str
    home: str
    home_id: int | None
    away: str
    away_id: int | None
    home_score: int | None = None
    away_score: int | None = None
    played: bool = False
    raw_score: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class Page:
    team: str | None
    team_id: int | None
    division: str | None
    table: list[TableRow]
    fixtures: list[Match]
    results: list[Match]

    def as_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "team_id": self.team_id,
            "division": self.division,
            "table": [asdict(r) for r in self.table],
            "fixtures": [asdict(m) for m in self.fixtures],
            "results": [asdict(m) for m in self.results],
        }


def build_url(team: int, competition: int, division: int, season: str) -> str:
    return (
        f"{BASE_URL}{SEARCH_PATH}?team={team}&competition={competition}"
        f"&division={division}&season={season}"
    )


def parse_search_url(url: str) -> dict[str, Any]:
    """Pull team/competition/division/season out of a pasted page URL."""
    q = parse_qs(urlparse(url.strip()).query)
    try:
        return {
            "team": int(q["team"][0]),
            "competition": int(q["competition"][0]),
            "division": int(q["division"][0]),
            "season": q["season"][0],
        }
    except (KeyError, ValueError, IndexError) as err:
        raise ValueError(
            "URL needs team, competition, division and season parameters"
        ) from err


def _team_id(a: Tag | None) -> int | None:
    if a is None or not a.get("href"):
        return None
    q = parse_qs(urlparse(a["href"]).query)
    try:
        return int(q["team"][0])
    except (KeyError, ValueError, IndexError):
        return None


def _int(text: str) -> int:
    text = text.strip().replace("+", "")
    try:
        return int(text)
    except ValueError:
        return 0


def _parse_date(text: str) -> str:
    text = " ".join(text.split())
    for fmt in ("%A, %d %b %Y", "%A, %d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def parse_table(soup: BeautifulSoup) -> tuple[str | None, list[TableRow]]:
    table = soup.select_one("table.league-table")
    if table is None:
        return None, []
    name_el = soup.select_one("#league-table .league-name")
    rows: list[TableRow] = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 12:
            continue
        a = tds[1].find("a")
        cells = [td.get_text(" ", strip=True) for td in tds]
        rows.append(
            TableRow(
                position=_int(cells[0]),
                team=(a.get_text(strip=True) if a else cells[1]),
                team_id=_team_id(a),
                played=_int(cells[2]),
                won=_int(cells[3]),
                drawn=_int(cells[4]),
                lost=_int(cells[5]),
                points_for=_int(cells[6]),
                points_against=_int(cells[7]),
                difference=_int(cells[8]),
                try_bonus=_int(cells[9]),
                losing_bonus=_int(cells[10]),
                points=_int(cells[11]),
            )
        )
    return (name_el.get_text(strip=True) if name_el else None), rows


def _parse_score(fnr: Tag | None) -> tuple[int | None, int | None, str]:
    """Return (home, away, raw). 'V'/'VS' with no digits means no score yet."""
    if fnr is None:
        return None, None, ""
    raw = " ".join(fnr.get_text(" ", strip=True).split())
    m = _SCORE_RE.search(raw)
    if not m:
        return None, None, raw
    nums = [g for g in m.groups() if g is not None]
    return int(nums[0]), int(nums[1]), raw


def parse_cards(section: Tag | None) -> list[Match]:
    if section is None:
        return []
    out: list[Match] = []
    for card in section.select(".coh-style-card-body"):
        date_el = card.find_previous(class_="coh-style-card-left-date")
        comp_el = card.find_previous(class_="coh-style-sub-header-right")
        teams = card.select("a.coh-style-right-comp-name")
        if len(teams) < 2:
            continue
        mid_el = card.select_one("[data-match-id]")
        hs, as_, raw = _parse_score(card.select_one(".fnr-scores"))
        out.append(
            Match(
                match_id=int(mid_el["data-match-id"]) if mid_el else None,
                date=_parse_date(date_el.get_text(strip=True)) if date_el else "",
                competition=comp_el.get_text(strip=True) if comp_el else "",
                home=teams[0].get_text(strip=True),
                home_id=_team_id(teams[0]),
                away=teams[1].get_text(strip=True),
                away_id=_team_id(teams[1]),
                home_score=hs,
                away_score=as_,
                played=hs is not None,
                raw_score=raw,
            )
        )
    return out


def parse_page(html: str, team_id: int | None = None) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    division, table = parse_table(soup)
    fixtures = parse_cards(soup.find(attrs={"data-field-selection": "upcoming_fixtures"}))
    results = parse_cards(soup.find(attrs={"data-field-selection": "recent_results"}))
    team = None
    sel = soup.select_one("#selectedOpt[data-selected-option]")
    if sel is not None:
        team = sel["data-selected-option"]
    _flag_clashes(fixtures)
    return Page(team, team_id, division, table, fixtures, results)


def _flag_clashes(fixtures: list[Match]) -> None:
    """Two fixtures for one team on one day: keep the newest match id as
    the likely current one and flag the older as probably stale."""
    by_day: dict[str, list[Match]] = {}
    for m in fixtures:
        by_day.setdefault(m.date, []).append(m)
    for day in by_day.values():
        if len(day) < 2:
            continue
        newest = max(day, key=lambda m: m.match_id or 0)
        for m in day:
            m.flags.append("clash")
            if m is not newest:
                m.flags.append("probably_stale")


def is_ours(m: Match | dict, team_id: int) -> str:
    """'home', 'away' or '' for whether team_id plays in match m."""
    h = m.home_id if isinstance(m, Match) else m.get("home_id")
    a = m.away_id if isinstance(m, Match) else m.get("away_id")
    if h == team_id:
        return "home"
    if a == team_id:
        return "away"
    return ""


def today_iso() -> str:
    return date.today().isoformat()
