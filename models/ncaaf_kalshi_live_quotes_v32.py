#!/usr/bin/env python3
"""Fetch live Kalshi public per-ticker quotes for already-verified NCAAF FBS games.

Read-only, unauthenticated public market data. No order placement or modification.
Records quote observation times, not historical executable prices. Even when the
latest ask is valid, exact depth/liquidity, fees, QB and injuries remain unverified.
All model comparisons are RESEARCH ONLY; NEVER create official/shadow picks.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UTC=dt.timezone.utc
BASE="https://external-api.kalshi.com/trade-api/v2/markets/"

def price(x):
    # Kalshi may expose explicit dollar strings and legacy cent integers.
    if x is None or isinstance(x,bool):return None
    try:n=float(x)
    except (TypeError,ValueError):return None
    if not math.isfinite(n) or n<=0:return None
    return n if n<1 else n/100 if n<=100 else None

def dollar_ask(x):
    if x is None or isinstance(x,bool):return None
    try:n=float(x)
    except (TypeError,ValueError):return None
    return n if math.isfinite(n) and 0<n<1 else None

def extract(m,now):
    if not isinstance(m,dict):return {"status":"BAD MARKET RESPONSE"}
    ticker=m.get("ticker")
    if not ticker:return {"status":"MISSING TICKER"}
    yes=dollar_ask(m.get("yes_ask_dollars"))
    no=dollar_ask(m.get("no_ask_dollars"))
    if yes is None:yes=price(m.get("yes_ask"))
    if no is None:no=price(m.get("no_ask"))
    close=m.get("close_time")
    future=None
    if isinstance(close,str):
        try:
            t=dt.datetime.fromisoformat(close.replace("Z","+00:00"))
            future=t.tzinfo is not None and t>now
        except ValueError:future=None
    state=str(m.get("status","")).lower()
    open_now=state in ("active","open")
    valid=yes is not None and no is not None and yes<1 and no<1
    return {"ticker":ticker,"status":"CURRENT QUOTE OBSERVED" if valid and open_now and future else "NOT A VALID OPEN OFFER",
       "market_status":state,"market_close_utc":close,"yes_ask":yes,"no_ask":no,
       "open_and_preclose":bool(open_now and future),
       "observed_at_utc":now.isoformat(),
       "exact_orderbook_depth_verified":False,
       "market_fees_verified":False,"production_eligible":False}

def fetch_market(ticker):
    if not re.fullmatch(r"[A-Z0-9-]{4,200}",str(ticker)):
        raise ValueError("invalid ticker format")
    url=BASE+urllib.parse.quote(ticker,safe="-")
    req=urllib.request.Request(url,headers={"Accept":"application/json",
       "User-Agent":"NCAAFResearchQuoteCapture/3.2"})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            value=json.load(response)
        if not isinstance(value,dict) or not isinstance(value.get("market"),dict):
            raise ValueError("unexpected market response")
        return value["market"]
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        raise ValueError("public market endpoint unavailable") from None

def review(research, fetch_fn=fetch_market):
    m=research.get("market_research",{})
    rows=m.get("research_comparisons",[])
    tickers=sorted({x.get("ticker") for x in rows if x.get("ticker")})
    captured={}
    for ticker in tickers:
        try:
            request_started=dt.datetime.now(UTC)
            market=fetch_fn(ticker)
            if market.get("ticker") != ticker:
                raise ValueError("ticker mismatch")
            captured[ticker]=extract(market,dt.datetime.now(UTC))
            captured[ticker]["request_started_utc"]=request_started.isoformat()
        except ValueError:
            captured[ticker]={"ticker":ticker,"status":"FETCH FAILED",
                "production_eligible":False}
        time.sleep(.04)
    reviewed=[]
    for x in rows:
        current=captured.get(x["ticker"],{})
        ask=current.get("yes_ask") if x["side"]=="YES" else current.get("no_ask")
        good=current.get("status")=="CURRENT QUOTE OBSERVED"
        rec={"ticker":x["ticker"],"side":x["side"],
             "cfbd_game_id":x["cfbd_game_id"],
             "model_probability":x["model_probability"],
             "board_ask":x["ask"],"latest_observed_ask":ask,
             "observed_at_utc":current.get("observed_at_utc"),
             "quote_status":current.get("status","NOT AVAILABLE"),
             "board_to_latest_ask_change_pp":round((ask-x["ask"])*100,2) if ask is not None else None,
             "gross_model_minus_latest_ask_pp":round((x["model_probability"]-ask)*100,2) if good and ask is not None else None,
             "exact_orderbook_depth_verified":False,
             "fee_and_slippage_verified":False,
             "qb_verified":False,"injuries_verified":False,
             "production_eligible":False,"not_a_pick":True}
        reviewed.append(rec)
    counts=collections.Counter(v["status"] for v in captured.values())
    return {"schemaVersion":1,"sport":"NCAAF","status":"LIVE PRICE RESEARCH ONLY",
       "capturedAtUTC":dt.datetime.now(UTC).isoformat(),
       "unique_tickers_checked":len(tickers),
       "market_request_results":dict(counts),
       "contract_sides_reviewed":len(reviewed),
       "research_only_comparisons":reviewed,
       "no_assumption_of_execution_depth_or_fees":True,
       "official":None,"shadow":[],"official_eligible":False,
       "production_eligible":False,
       "note":"This captures current public market best asks only when the exchange returns an open preclose market. It does NOT prove available orderbook size, historical fillability or calibrated betting edge."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",default="ncaaf-cfbd-v32-research.json")
    p.add_argument("--output",default="ncaaf-kalshi-live-v32-research.json")
    p.add_argument("--health",default="dashboard/ncaaf-v32-quote-health.json")
    a=p.parse_args()
    research=json.loads(pathlib.Path(a.research).read_text())
    result=review(research)
    pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    public={k:result[k] for k in ("schemaVersion","sport","status","capturedAtUTC",
       "unique_tickers_checked","market_request_results",
       "contract_sides_reviewed","no_assumption_of_execution_depth_or_fees",
       "official_eligible","production_eligible","note")}
    path=pathlib.Path(a.health);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(public,indent=2)+"\n")
    print(json.dumps(public))

if __name__=="__main__":
    main()
