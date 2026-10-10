"""Margin-weighted Elo, the same method used for the Tagfastics! panel.

All teams start at BASE. For each match in date order:
    E = 1 / (1 + 10 ** ((Rb - Ra) / 400))
    delta = K * ln(|margin| + 1) * (S - E),  S = 1 win / 0.5 draw / 0 loss
A 0-0 draw therefore moves nothing; wider wins move ratings further.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

BASE = 1500.0
K = 32.0


def expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def compute(results: Iterable[dict[str, Any]], teams: Iterable[str] = ()) -> dict[str, Any]:
    ratings: dict[str, float] = {t: BASE for t in teams}
    history: list[dict[str, Any]] = []
    played = sorted(
        (r for r in results if r.get("home_score") is not None and r.get("away_score") is not None),
        key=lambda r: (r.get("date", ""), r.get("match_id") or 0),
    )
    for r in played:
        h, a = r["home"], r["away"]
        ratings.setdefault(h, BASE)
        ratings.setdefault(a, BASE)
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        s = 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5
        e = expected(ratings[h], ratings[a])
        delta = K * math.log(abs(hs - as_) + 1) * (s - e)
        ratings[h] += delta
        ratings[a] -= delta
        history.append(
            {
                "date": r.get("date"),
                "match_id": r.get("match_id"),
                "home": h,
                "away": a,
                "score": f"{hs}-{as_}",
                "delta": round(delta, 1),
                "ratings": {t: round(v) for t, v in ratings.items()},
            }
        )
    return {
        "ratings": {t: round(v) for t, v in sorted(ratings.items(), key=lambda kv: -kv[1])},
        "history": history,
        "matches_rated": len(played),
    }


def win_probability(ratings: dict[str, float], team: str, opponent: str) -> int | None:
    if team not in ratings or opponent not in ratings:
        return None
    return round(100 * expected(ratings[team], ratings[opponent]))
