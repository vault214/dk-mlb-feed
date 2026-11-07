#!/usr/bin/env python3
"""Publish a sanitized NCAAF Kalshi research screen for scheduled-model review.

NO trade/account data and NO official/shadow eligibility. Fresh quotes must be
independently rechecked at decision time; observed price is not an executable
depth/fees guarantee. An explicit short freshness window avoids stale screen use.
"""
import argparse
import datetime as dt
import json
import pathlib

def publish(model, weather, quotes):
    source=model.get("market_research",{}).get("research_comparisons",[])
    qs={(x.get("ticker"),x.get("side"),str(x.get("cfbd_game_id"))):x for x in
        quotes.get("research_only_comparisons",[])}
    wx=weather.get("weather_for_cfbd_game_id",{})
    rows=[]; seen=set()
    for x in source:
        key=(x["ticker"],x["side"],str(x["cfbd_game_id"]))
        if key in seen:raise ValueError("duplicate market research key")
        seen.add(key)
        q=qs.get(key,{})
        w=wx.get(str(x["cfbd_game_id"]),{})
        if x.get("not_an_official_or_shadow_pick") is not True:
            raise ValueError("source row not explicitly research-only")
        row={
          "ticker":x["ticker"],"eventTicker":x["event_ticker"],
          "cfbdGameId":x["cfbd_game_id"],"kickoffUTC":x["kickoff_utc"],
          "homeTeam":x["home_team"],"awayTeam":x["away_team"],
          "selectionLabel":x["winner_contract_label"],"side":x["side"],
          "modelProbability":x["model_probability"],
          "latestObservedAsk":q.get("latest_observed_ask"),
          "quoteObservedUTC":q.get("observed_at_utc"),
          "marketState":q.get("quote_status","QUOTE NOT VERIFIED"),
          "grossDifferencePP":q.get("gross_model_minus_latest_ask_pp"),
          "weatherForecastStatus":w.get("status","NOT VERIFIED"),
          "qbVerified":False,"injuriesVerified":False,
          "feesVerified":False,"askDepthVerified":False,
          "researchOnly":True,"officialEligible":False,"shadowEligible":False,
          "decision":"RESEARCH ONLY — DO NOT BOOK",
          "exclusionReason":"QB/injury availability, calibrated weather effect, fee/quote depth and forward edge validation missing"
        }
        rows.append(row)
    now=quotes.get("capturedAtUTC")
    if not now:raise ValueError("quote capture timestamp missing")
    snapshot=dt.datetime.fromisoformat(now.replace("Z","+00:00"))
    if snapshot.tzinfo is None:raise ValueError("quote capture timezone missing")
    expires=snapshot+dt.timedelta(minutes=2)
    return {
      "schemaVersion":1,"visibility":"public sanitized research, no personal finances",
      "sport":"NCAAF","status":"RESEARCH ONLY — NO OFFICIAL OR SHADOW PICKS",
      "modelCapturedAtUTC":model.get("capturedAtUTC"),
      "quoteCapturedAtUTC":now,"quoteResearchExpiresUTC":expires.isoformat(),
      "rowCount":len(rows),"official":[],"shadow":[],
      "productionEligible":False,"officialEligible":False,"shadowEligible":False,
      "notes":["Model derived from CFBD historical games, not from Kalshi odds.",
        "All quoted asks are read-only API snapshots and may already have changed.",
        "Quote estimates expire after two minutes for research freshness; no depth is verified.",
        "QB/injury statuses are NOT verified. Weather forecasts do not change model probabilities.",
        "Do not convert these research rows to paper picks or alter the canonical Model Picks sheet."],
      "rows":rows
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="ncaaf-cfbd-v32-research.json")
    p.add_argument("--weather",default="ncaaf-weather-v32-research.json")
    p.add_argument("--quotes",default="ncaaf-kalshi-live-v32-research.json")
    p.add_argument("--output",default="dashboard/ncaaf-v32-research.json")
    a=p.parse_args()
    out=publish(*[json.loads(pathlib.Path(x).read_text()) for x in
        (a.model,a.weather,a.quotes)])
    dest=pathlib.Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"status":out["status"],"rowCount":out["rowCount"],
        "quoteCapturedAtUTC":out["quoteCapturedAtUTC"],
        "quoteResearchExpiresUTC":out["quoteResearchExpiresUTC"],
        "officialEligible":out["officialEligible"]}))

if __name__=="__main__":main()
