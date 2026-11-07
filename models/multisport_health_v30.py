#!/usr/bin/env python3
"""Publishable, sanitized health report for all seven independent paper models.
Reads research-only calibration and Kalshi candidate board metadata.
Does not expose trades, bank, accounts or private spreadsheet rows.
"""
import argparse
import datetime as dt
import json
import pathlib

LEAGUES = ("NCAAF", "NFL", "NBA", "NHL", "NCAAB", "MLB", "WNBA")
BOARDS = {
 "NCAAF":"ncaafb-candidates.json", "NFL":"nfl-candidates.json",
 "NBA":"nba-candidates.json", "NHL":"nhl-candidates.json",
 "NCAAB":"ncaab-candidates.json", "MLB":"mlb-candidates.json",
 "WNBA":"wnba-candidates.json",
}
def health(reports, boards):
 out = []
 for league in LEAGUES:
  p = pathlib.Path(reports)/ (league + ".json")
  if p.exists():
   data = json.loads(p.read_text())
   if data.get("league") != league:
    raise ValueError("mismatched league report: " + league)
  else:
   data = {"status": "NO RUN RESULT", "missing_verified_inputs": ["research backtest"]}
  b = pathlib.Path(boards)/BOARDS[league]
  try:
   board = json.loads(b.read_text())
   markets = board.get("markets", [])
   executable = sum(1 for m in markets if m.get("status")=="active" and any(
     isinstance(m.get(x),(int,float)) and 0<m[x]<1 for x in ("yes_ask","no_ask")))
   board_meta = {
    "date_et": board.get("board_date_et"),
    "candidate_market_count": board.get("candidate_market_count"),
    "active_markets_with_at_least_one_executable_ask": executable,
    "quote_timestamp_verification": "UNVERIFIED" if not board.get("fetched_at_utc") else "BOARD FETCH TIME ONLY; NOT PER-CONTRACT ASK FRESHNESS",
   }
  except (OSError,ValueError,TypeError):
   board_meta = {"status":"BOARD MISSING OR INVALID"}
  out.append({
   "league": league,
   "research_status": data.get("status"),
   "historical_games_collected": data.get("source_games"),
   "feature_rows": data.get("feature_rows"),
   "training_games": data.get("training_games"),
   "holdout_games": data.get("holdout_games"),
   "winner_brier": data.get("winner_brier"),
   "home_prior_baseline_brier": data.get("baseline_empirical_home_brier"),
   "improvement_vs_home_baseline": data.get("winner_brier_improvement_vs_home_baseline"),
   "failed_source_dates": data.get("failed_source_dates"),
   "missing_verified_inputs": data.get("missing_verified_inputs", []),
   "market_price_backtest": data.get("market_price_backtest","UNAVAILABLE"),
   "production_eligible": False, "official_eligible": False,
   "market_board": board_meta
  })
 return {
   "schemaVersion": 1, "visibility": "sanitized research model health only",
   "generatedAtUTC": dt.datetime.now(dt.timezone.utc).isoformat(),
   "status": "RESEARCH ONLY — NO PRODUCTION VALIDATION",
   "leagues": out,
   "disclaimer": "A passing workflow is not a calibrated betting model. No market P/L or automatic official bets derive from this report."
 }
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--reports-dir",required=True)
 p.add_argument("--boards-dir",required=True)
 p.add_argument("--output",required=True)
 a=p.parse_args()
 value=health(a.reports_dir,a.boards_dir)
 pathlib.Path(a.output).write_text(json.dumps(value,indent=2)+"\n")
 print(json.dumps({"leagues":len(value["leagues"]),"status":value["status"],
                   "available_reports":sum(x["research_status"]!="NO RUN RESULT" for x in value["leagues"])}))
if __name__=="__main__":main()
