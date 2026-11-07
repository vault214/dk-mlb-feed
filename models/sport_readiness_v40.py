#!/usr/bin/env python3
"""One transparent readiness board for seven independent sports models.

Never turn holdout Brier or a stale Kalshi ask into an eligible pick.
MLB and WNBA remain offseason; NCAAF uses its own independent forward source.
"""
import argparse
import datetime as dt
import json
import pathlib

ACTIVE=("NFL","NBA","NHL","NCAAB")
ALL=("NCAAF","NFL","NBA","NHL","NCAAB","MLB","WNBA")
GATES={
  "NFL":"EPA/success, starting QB, injury, weather and an independent per-game live model forecast",
  "NBA":"adjusted possessions, confirmed starters/minutes, injuries and an independent live game forecast",
  "NHL":"expected goals and verified starting goalie; first improve winner model versus baseline",
  "NCAAB":"Division I team/roster verification, adjusted efficiency, starters and prospective model",
  "MLB":"confirmed starter, lineup, bullpen, park/weather and season restart",
  "WNBA":"adjusted efficiency, confirmed starters/minutes and season restart",
  "NCAAF":"official game-specific availability and independently settled forward games"
}
def summarize(model,capture,settlement,ncaaf,now):
    h={x.get("league"):x for x in model.get("leagues",[])}
    out=[]
    for league in ALL:
        m=h.get(league,{})
        c=capture.get("leagues",{}).get(league,{})
        s=settlement.get("leagues",{}).get(league,{})
        is_ncaaf=league=="NCAAF"
        archived=ncaaf.get("research_unique_games_with_pregame_quotes",0) if is_ncaaf else s.get("observed_unique_games",0)
        settled=ncaaf.get("independently_verified_game_probability_samples",0) if is_ncaaf else s.get("independently_settled_games",0)
        missing=m.get("missing_verified_inputs",[])
        season_state="OFFSEASON" if league in ("MLB","WNBA") else "RESEARCH ACTIVE"
        if league=="NFL" and c.get("status","").startswith("BOARD DATE STALE"):
            season_state="CANDIDATE BOARD STALE"
        if league in ACTIVE and c.get("status","").startswith("SOURCE/BOARD"):
            season_state="SOURCE CHECK REQUIRED"
        reasons=[]
        if missing:reasons.append("Verified model inputs missing: "+", ".join(missing))
        if m.get("improvement_vs_home_baseline") is not None and m["improvement_vs_home_baseline"]<=0:
            reasons.append("Historical winner baseline NOT beaten; retrain/revalidate")
        if league in ACTIVE:
            if not c.get("new_observations"):reasons.append("No new valid independent game-matched market observations in last capture")
            reasons.append("No paired independent forward model probability for exact timestamped game winner contract")
        if settled<40:reasons.append("Insufficient distinct independently settled forward games for research review")
        if league in ("MLB","WNBA"):reasons.append("Offseason: live market validation deferred")
        if is_ncaaf:reasons.append("Primary game-specific player evidence and impact still unverified")
        out.append({
          "sport":league,"state":season_state,
          "historical_holdout_games":m.get("holdout_games"),
          "historical_winner_brier":m.get("winner_brier"),
          "historical_improvement_vs_home_baseline":m.get("improvement_vs_home_baseline"),
          "last_board_date_et":(m.get("market_board") or {}).get("date_et"),
          "capture_status":"NCAAF SEPARATE WORKFLOW" if is_ncaaf else c.get("status"),
          "last_capture_new_moneyline_quotes":None if is_ncaaf else c.get("new_observations",0),
          "unique_games_with_market_snapshots":archived,
          "independent_settled_game_samples":settled,
          "market_midpoint_brier":None if is_ncaaf else s.get("market_midpoint_brier"),
          "new_prospective_games_pending":ncaaf.get("precommitted_candidate_games_awaiting_independent_settlement") if is_ncaaf else s.get("games_awaiting_settlement"),
          "next_model_evidence":GATES[league],
          "blockers":reasons,
          "official_eligible":False,"shadow_eligible":False,"production_eligible":False
        })
    return {"schemaVersion":1,"generatedAtUTC":now.isoformat(),
      "status":"SEVEN-SPORT READINESS / FORWARD COVERAGE — RESEARCH ONLY",
      "active_capture_sports":list(ACTIVE),
      "separate_primary_sport":"NCAAF",
      "offseason_sports":["MLB","WNBA"],
      "sports":out,"official_eligible":False,
      "shadow_eligible":False,"production_eligible":False,
      "note":"Positive historical holdout metrics and future public odds are insufficient to claim calibrated betting profitability. No official/shadow picks, trades, or canonical betting ledger changes."}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model-health",default="dashboard/model-health.json")
    p.add_argument("--capture-health",default="dashboard/sports-v40-capture-health.json")
    p.add_argument("--result-health",default="dashboard/sports-v40-result-health.json")
    p.add_argument("--ncaaf",default="dashboard/ncaaf-v39-forward-scorecard.json")
    p.add_argument("--output",default="dashboard/sports-v40-readiness.json")
    a=p.parse_args()
    def read(file):
        try:return json.loads(pathlib.Path(file).read_text())
        except (ValueError,OSError):return {}
    out=summarize(read(a.model_health),read(a.capture_health),read(a.result_health),read(a.ncaaf),dt.datetime.now(dt.timezone.utc))
    path=pathlib.Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({r["sport"]:{"state":r["state"],"games":r["unique_games_with_market_snapshots"],"settled":r["independent_settled_game_samples"]} for r in out["sports"]}))
if __name__=="__main__":main()
