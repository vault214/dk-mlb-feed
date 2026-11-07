#!/usr/bin/env python3
"""Strict season-separated seven-league research backtest (NO market wagers).

Only winner research; real spread/total/player prop accuracy requires timestamped
historical market strikes, settlement rules and real pregame player/team inputs.
Never use this as an official probability eligibility flag.
"""
import argparse
import datetime as dt
import json
import math
import pathlib
import statistics

TRAIN_END = {
    "NCAAF": "2025-08-01", "NFL": "2025-08-01",
    "NBA": "2025-07-01", "NHL": "2025-07-01",
    "NCAAB": "2025-07-01", "MLB": "2025-01-01",
    "WNBA": "2025-01-01",
}

def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def report(features_payload, min_train=80, min_test=30):
    league = features_payload["league"]
    boundary = TRAIN_END[league]
    records = sorted(features_payload["features"], key=lambda g: (g["date"], g["id"]))
    if any(g.get("feature_cutoff_exclusive") != g["date"] or g.get("production_eligible") for g in records):
        raise ValueError("feature chronology or research-only flag invalid")
    train = [r for r in records if r["date"] < boundary]
    test = [r for r in records if r["date"] > boundary]
    base = {
        "schema_version": 3, "league": league,
        "status": "INSUFFICIENT RESEARCH COVERAGE",
        "source_games": features_payload.get("source_games"),
        "feature_rows": len(records), "training_games": len(train),
        "holdout_games": len(test), "train_end_exclusive": boundary,
        "test_start_exclusive": boundary,
        "last_train_date": max((x["date"] for x in train), default=None),
        "first_test_date": min((x["date"] for x in test), default=None),
        "failed_source_dates": len(features_payload.get("failed_dates", [])),
        "missing_verified_inputs": features_payload["missing_verified_inputs"],
        "production_eligible": False, "official_eligible": False,
        "market_price_backtest": "NOT AVAILABLE - no timestamped Kalshi historical asks",
        "non_winner_markets": "NOT TESTED - real market line/prop archive absent",
    }
    if len(train) < min_train or len(test) < min_test or base["failed_source_dates"]:
        base["reason"] = "minimum train/test games not met or source date fetch failed"
        return base
    if base["last_train_date"] >= base["first_test_date"]:
        raise ValueError("overlapping training and testing dates")
    resid = [(float(r["home_points"]) - float(r["away_points"])) -
             (r["projected_home_points"] - r["projected_away_points"]) for r in train]
    margin_sd = statistics.stdev(resid)
    if margin_sd <= 0 or not math.isfinite(margin_sd):
        base["reason"] = "invalid training residual variance"
        return base
    # Ties excluded from winner statistics: settlement needs sport/market-specific handling.
    non_ties_train = [r for r in train if r["home_points"] != r["away_points"]]
    non_ties_test = [r for r in test if r["home_points"] != r["away_points"]]
    if len(non_ties_train) < min_train or len(non_ties_test) < min_test:
        base["reason"] = "insufficient non-tied winner outcomes"
        return base
    home_win_base = sum(int(r["home_points"] > r["away_points"]) for r in non_ties_train) / len(non_ties_train)
    outcomes = []
    for r in non_ties_test:
        margin = r["projected_home_points"] - r["projected_away_points"]
        p = max(1e-6, min(1 - 1e-6, normal_cdf(margin / margin_sd)))
        y = int(r["home_points"] > r["away_points"])
        outcomes.append((p, y))
    n = len(outcomes)
    brier = sum((p-y)**2 for p,y in outcomes) / n
    logloss = -sum(y*math.log(p) + (1-y)*math.log(1-p) for p,y in outcomes) / n
    brier_prior = sum((home_win_base-y)**2 for _,y in outcomes) / n
    brier_half = sum((.5-y)**2 for _,y in outcomes) / n
    bins = []
    for j in range(5):
        rows = [(p,y) for p,y in outcomes if j/5 <= p < (j+1)/5 or j == 4 and p == 1]
        if rows:
            bins.append({"band": "%d-%d%%" % (j*20, (j+1)*20),
                         "n": len(rows), "mean_predicted": round(sum(p for p,y in rows)/len(rows),4),
                         "actual_win_rate": round(sum(y for p,y in rows)/len(rows),4)})
    base.update({
        "status": "RESEARCH HOLDOUT ONLY",
        "winner_sample": n,
        "winner_brier": round(brier, 6), "winner_log_loss": round(logloss, 6),
        "baseline_empirical_home_brier": round(brier_prior, 6),
        "baseline_50_50_brier": round(brier_half, 6),
        "winner_brier_improvement_vs_home_baseline": round(brier_prior-brier,6),
        "train_margin_sd": round(margin_sd,4),
        "calibration_bins": bins,
        "warnings": [
            "Score-based rolling proxies are NOT adjusted efficiency or verified starters/injuries.",
            "No historical executable asks, timestamped market odds or profit simulation.",
            "One chronological season-separated holdout is not enough for production.",
            "Brier score improvement alone does not prove betting edge or profitability.",
        ],
    })
    return base

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--features",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    input_data=json.loads(pathlib.Path(a.features).read_text())
    res=report(input_data)
    pathlib.Path(a.output).write_text(json.dumps(res, indent=2)+"\n")
    print(json.dumps({k:res.get(k) for k in
        ("league","status","training_games","holdout_games","winner_brier",
         "baseline_empirical_home_brier","winner_brier_improvement_vs_home_baseline",
         "production_eligible")}))
if __name__=="__main__":
    main()
