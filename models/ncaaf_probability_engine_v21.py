#!/usr/bin/env python3
"""NCAAF independent projection and Kalshi screening engine v2.1.

Inputs:
  --board: Kalshi JSON with markets[] (same shape as kalshi/ncaafb-candidates.json)
  --projections: independent, date-specific matchup projections CSV:
    event_ticker,event_date,away_team,home_team,away_points,home_points,
    margin_sd,total_sd,team_sd,source,updated_at_et,injuries_verified,
    weather_verified
  Optional: --date YYYY-MM-DD; --output file.json.
Projection points MUST come from an independent ratings/efficiency model, not
from Kalshi quotes. Explicit per-game standard deviations must be backtested.
Do not use this engine to imply calibration until holdout validation is complete.
"""
import argparse, csv, datetime as dt, json, math, pathlib
from collections import Counter
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
def normal_cdf(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))
def valid_price(v): return isinstance(v,(int,float)) and 0 < v < 1 and math.isfinite(v)
def probability(m,p,side):
    cat=m.get("market_category")
    floor=m.get("floor_strike")
    title=(m.get("title") or "").lower()
    away=float(p["away_points"]); home=float(p["home_points"])
    if cat=="game":
        # Explicit team mapping is required, not inferred from opaque ticker.
        sel=m.get("yes_selection")
        if sel==p["home_team"]: mean=home-away
        elif sel==p["away_team"]: mean=away-home
        else: return None,"unmatched moneyline team"
        sd=float(p["margin_sd"]); q=normal_cdf(mean/sd)
    elif cat=="spread":
        # Spread strike is encoded in the contract; do not guess side from ticker.
        # Require explicit market mapping in projection CSV for this market.
        key="spread_yes_mean_" + m["ticker"]
        if key not in p: return None,"spread contract mapping missing"
        mean=float(p[key]); sd=float(p["margin_sd"])
        q=normal_cdf(mean/sd)
    elif cat=="total":
        if floor is None: return None,"missing total strike"
        sd=float(p["total_sd"]); q=normal_cdf((away+home-float(floor))/sd)
    elif cat=="team_total":
        if floor is None: return None,"missing team-total strike"
        # Team-total title must match one of the exact team names.
        if title.startswith(p["home_team"].lower()+" over"): mean=home
        elif title.startswith(p["away_team"].lower()+" over"): mean=away
        else: return None,"team-total team mapping missing"
        sd=float(p["team_sd"]); q=normal_cdf((mean-float(floor))/sd)
    else: return None,"unsupported category"
    if sd<=0 or not math.isfinite(sd): return None,"invalid scoring uncertainty"
    return (q if side=="YES" else 1-q),None

def run(board,projections,date,cost_pp=1.5,uncertainty_pp=4.0):
    if board.get("board_date_et")!=date or board.get("candidate_market_count",0)<=0:
        return {"status":"DATA PASS","reason":"stale or empty board"}
    by_event={(r["event_ticker"],r["event_date"]):r for r in projections}
    candidates=[]; exclusions=Counter(); modeled=0
    for m in board["markets"]:
        if m.get("event_date")!=date or m.get("status")!="active":
            exclusions["wrong date or inactive"]+=1;continue
        p=by_event.get((m.get("event_ticker"),date))
        if not p: exclusions["independent projection unavailable"]+=1;continue
        if p.get("injuries_verified")!="true" or p.get("weather_verified")!="true":
            exclusions["injury/weather verification missing"]+=1;continue
        if not p.get("source") or not p.get("updated_at_et"):
            exclusions["projection provenance missing"]+=1;continue
        if p.get("fbs_verified")!="true":
            exclusions["FBS verification missing"]+=1;continue
        # Pregame restriction: explicitly verified start time, no retroactive entries.
        if not p.get("kickoff_et"):
            exclusions["kickoff timestamp missing"]+=1;continue
        kickoff=dt.datetime.fromisoformat(p["kickoff_et"])
        if kickoff.tzinfo is None: exclusions["kickoff timezone missing"]+=1;continue
        if kickoff<=dt.datetime.now(ET):
            exclusions["already kicked off"]+=1;continue
        had_model=False
        for side,field in (("YES","yes_ask"),("NO","no_ask")):
            ask=m.get(field)
            if not valid_price(ask):
                exclusions["invalid executable ask"]+=1;continue
            try: prob,error=probability(m,p,side)
            except (ValueError,TypeError,OverflowError,ZeroDivisionError):
                prob,error=None,"invalid independent projection"
            if error:
                exclusions[error]+=1;continue
            had_model=True
            gross=100*(prob-ask); net=gross-cost_pp-uncertainty_pp
            candidates.append({"ticker":m["ticker"],"event_ticker":m["event_ticker"],
                "category":m["market_category"],"title":m.get("title"),
                "side":side,"ask":ask,"break_even_pct":round(100*ask,2),
                "model_pct":round(100*prob,2),"gross_edge_pp":round(gross,2),
                "net_edge_pp":round(net,2),"source":p["source"],
                "projection_updated_et":p["updated_at_et"],
                "quality":"UNVALIDATED — not official eligible"})
        if had_model: modeled+=1
    candidates.sort(key=lambda x:x["net_edge_pp"],reverse=True)
    return {"status":"SCREENED — RESEARCH ONLY","date_et":date,
      "board_markets":len(board["markets"]),"modeled_markets":modeled,
      "excluded_reasons":dict(exclusions),"top_10":candidates[:10],
      "official":None,"shadow":[],"note":"No official or shadow picks until historical holdout calibration, verified quote freshness, and matchup data checks are implemented. Fees and uncertainty are configurable research assumptions."}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--board",required=True)
    ap.add_argument("--projections",required=True);ap.add_argument("--date")
    ap.add_argument("--output");a=ap.parse_args()
    date=a.date or dt.datetime.now(ET).date().isoformat()
    with open(a.board) as f:board=json.load(f)
    with open(a.projections,newline="") as f:projections=list(csv.DictReader(f))
    result=run(board,projections,date)
    data=json.dumps(result,indent=2)+"\\n"
    if a.output:pathlib.Path(a.output).write_text(data)
    else:print(data)
if __name__=="__main__":main()
