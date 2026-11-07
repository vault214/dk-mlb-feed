#!/usr/bin/env python3
"""Leakage-safe, league-specific rolling-score baselines for seven sports.
This IS NOT a calibrated player/lineup/efficiency model and cannot issue picks.
All predictions for a date are computed before ANY game from that date is learned.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import statistics

REQUIRED_EXTERNAL = {
    "NCAAF": ["FBS membership", "adjusted offense/defense", "true tempo", "quarterback", "injuries", "weather"],
    "NFL": ["EPA/success rate", "true pace", "quarterback", "injuries", "weather", "personnel"],
    "NBA": ["adjusted efficiency", "possessions/pace", "starters", "minutes", "injuries", "player prop distributions"],
    "NCAAB": ["Division I eligibility", "adjusted efficiency", "possessions/pace", "transfers/rosters", "starters", "injuries"],
    "WNBA": ["adjusted efficiency", "possessions/pace", "starters", "minutes", "injuries", "player prop distributions"],
    "NHL": ["expected goals", "goalie confirmation", "starting goalie quality", "injuries", "special teams"],
    "MLB": ["probable/confirmed pitcher", "lineup", "bullpen", "park", "weather", "pitcher props"],
}

def _average(values, default=None):
    return sum(values) / len(values) if values else default

def make_features(payload, min_prior=5, recent=8):
    league = payload["league"]
    if league not in REQUIRED_EXTERNAL:
        raise ValueError("unsupported league")
    rows = sorted(payload["games"], key=lambda x: (x["date"], x.get("start_utc", ""), x["id"]))
    history = collections.defaultdict(list)
    all_scores = []
    output = []
    index = 0
    while index < len(rows):
        date = rows[index]["date"]
        batch = []
        while index < len(rows) and rows[index]["date"] == date:
            batch.append(rows[index]); index += 1
        # Freeze feature universe at the beginning of each ET date.
        league_avg = _average(all_scores[-500:])
        home_margins = []
        for scores in history.values():
            for item in scores[-recent:]:
                if item["venue"] == "home":
                    home_margins.append(item["for"] - item["against"])
        empirical_home_edge = _average(home_margins[-1000:], 0.0)
        for g in batch:
            h = history[str(g["home_id"])]
            a = history[str(g["away_id"])]
            if min(len(h), len(a)) < min_prior or league_avg is None:
                continue
            def shrunk(history_rows, stat):
                v = [row[stat] for row in history_rows[-recent:]]
                return (sum(v) + league_avg * 4) / (len(v) + 4)
            ho = shrunk(h, "for"); hd = shrunk(h, "against")
            ao = shrunk(a, "for"); ad = shrunk(a, "against")
            neutral = g.get("neutral_site", False)
            edge = 0.0 if neutral else empirical_home_edge / 2
            projected_h = max(0.01, (ho + ad) / 2 + edge)
            projected_a = max(0.01, (ao + hd) / 2 - edge)
            cur = dt.date.fromisoformat(date)
            home_rest = (cur - dt.date.fromisoformat(h[-1]["date"])).days - 1
            away_rest = (cur - dt.date.fromisoformat(a[-1]["date"])).days - 1
            output.append({
                "id": g["id"], "league": league, "date": date,
                "start_utc": g.get("start_utc"), "home_id": str(g["home_id"]),
                "away_id": str(g["away_id"]),
                "home_team": g["home_team"], "away_team": g["away_team"],
                "home_points": g["home_points"], "away_points": g["away_points"],
                "neutral_site": neutral,
                "home_prior_games": len(h), "away_prior_games": len(a),
                "projected_home_points": round(projected_h, 5),
                "projected_away_points": round(projected_a, 5),
                "home_rest_days": home_rest, "away_rest_days": away_rest,
                "home_scored_recent": round(ho, 5),
                "home_allowed_recent": round(hd, 5),
                "away_scored_recent": round(ao, 5),
                "away_allowed_recent": round(ad, 5),
                "global_prior_score_mean": round(league_avg, 5),
                "feature_cutoff_exclusive": date,
                "method": "past-score opponent-adjusted rolling baseline, not efficiency",
                "missing_verified_inputs": REQUIRED_EXTERNAL[league],
                "production_eligible": False,
            })
        # Only after predictions: process outcomes from the entire date.
        for g in batch:
            h, a = str(g["home_id"]), str(g["away_id"])
            hp, ap = float(g["home_points"]), float(g["away_points"])
            history[h].append({"date": date, "for": hp, "against": ap, "venue": "home"})
            history[a].append({"date": date, "for": ap, "against": hp, "venue": "away"})
            all_scores.extend((hp, ap))
    return {
        "schema_version": 3, "league": league, "source_games": len(rows),
        "excluded_preseason_or_insufficient_history": len(rows) - len(output),
        "failed_dates": payload.get("failed_dates", []),
        "features": output, "missing_verified_inputs": REQUIRED_EXTERNAL[league],
        "production_eligible": False,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--games", required=True)
    p.add_argument("--league", required=True, choices=REQUIRED_EXTERNAL)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    payload = json.loads(pathlib.Path(a.games).read_text())
    if payload["league"] != a.league:
        raise ValueError("league mismatch")
    result = make_features(payload)
    pathlib.Path(a.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"league": a.league, "usable": len(result["features"]),
        "input_games": result["source_games"], "production_eligible": False}))
if __name__ == "__main__":
    main()
