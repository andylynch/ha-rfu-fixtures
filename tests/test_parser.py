"""Run: python -m pytest tests -q   (needs beautifulsoup4, pytest)

Uses a saved copy of the Blackheath U14 page (tests/fixtures/blackheath_u14.html).
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "rfu_fixtures"))

import elo  # noqa: E402
import parser as rfu  # noqa: E402

PAGE = ROOT / "tests" / "fixtures" / "blackheath_u14.html"


@pytest.fixture(scope="module")
def page():
    return rfu.parse_page(PAGE.read_text(encoding="utf-8", errors="replace"), 2514)


def test_division_and_team(page):
    assert page.division == "U14 Boys Stage 1 Group 4"
    assert page.team == "Blackheath U14"


def test_table(page):
    assert len(page.table) == 5
    top = page.table[0]
    assert (top.team, top.team_id, top.played, top.won) == ("Ashford U14s", 889, 1, 1)
    assert (top.points_for, top.points_against, top.difference, top.try_bonus, top.points) == (28, 5, 23, 1, 5)
    assert page.table[1].difference == -23
    assert any(r.team == "Blackheath U14" and r.team_id == 2514 for r in page.table)


def test_fixtures(page):
    assert len(page.fixtures) == 7
    first = page.fixtures[0]
    assert first.date == "2026-10-11"
    assert first.competition == "U14 Boys Stage 1 Group 4"
    assert all(not m.played for m in page.fixtures)
    oct11 = [m for m in page.fixtures if m.date == "2026-10-11"]
    stale = [m.home for m in oct11 if "probably_stale" in m.flags]
    assert stale == ["Folkestone RFC U14M"]  # older match id; Ashford is current
    nov29 = [m for m in page.fixtures if m.date == "2026-11-29"]
    assert all("clash" in m.flags for m in nov29)


def test_results_without_score(page):
    assert len(page.results) == 1
    r = page.results[0]
    assert (r.date, r.home, r.away, r.match_id) == ("2026-09-27", "Blackheath U14", "Old Colfeians U14", 1322119)
    assert r.played is False and r.home_score is None


@pytest.mark.parametrize(
    "raw,expected",
    [("24 - 12", (24, 12)), ("7–31", (7, 31)), ("10 : 10", (10, 10)), ("V", (None, None)), ("VS", (None, None))],
)
def test_score_formats(raw, expected):
    from bs4 import BeautifulSoup

    tag = BeautifulSoup(f"<div class='fnr-scores'><span>{raw}</span></div>", "html.parser").div
    assert rfu._parse_score(tag)[:2] == expected


def test_parse_search_url():
    u = "https://www.englandrugby.com/fixtures-and-results/search-results?team=2514&competition=2075&division=79247&season=2026-2027"
    assert rfu.parse_search_url(u) == {"team": 2514, "competition": 2075, "division": 79247, "season": "2026-2027"}
    assert rfu.build_url(2514, 2075, 79247, "2026-2027") == u


def test_elo_matches_tag_panel():
    """Replays the Tagfastics! round 1-5 results and must reproduce its Elo."""
    A, M, G, F, X, D = "Tagamama", "Mergers", "Goblins", "Flying", "Tagfastics", "Democratic"
    rounds = [
        [(A, 8, G, 2), (X, 10, D, 9), (F, 10, M, 0)],
        [(A, 11, F, 9), (M, 15, X, 5), (G, 10, D, 8)],
        [(M, 9, A, 7), (G, 8, X, 1), (F, 16, D, 7)],
        [(A, 20, X, 6), (M, 12, D, 7), (G, 10, F, 8)],
        [(A, 13, D, 6), (M, 14, G, 5), (X, 11, F, 5)],
    ]
    res = []
    for i, rnd in enumerate(rounds):
        for j, (h, hs, a, as_) in enumerate(rnd):
            res.append({"date": f"2026-09-{10 + i:02d}", "match_id": i * 10 + j, "home": h, "away": a, "home_score": hs, "away_score": as_})
    out = elo.compute(res, [A, M, G, F, X, D])
    assert out["ratings"] == {M: 1583, A: 1581, G: 1502, F: 1491, X: 1446, D: 1397}
