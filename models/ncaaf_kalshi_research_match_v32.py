#!/usr/bin/env python3
"""Strict research-only NCAAF Kalshi moneyline mapping and coverage check.

Maps a winner contract only when its selection matches one and only one
same-day FBS game/team. Never treats board asks as fresh without independent
quote capture, and never declares official/shadow eligibility.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import unicodedata
from zoneinfo import ZoneInfo

ET=ZoneInfo("America/New_York")
ALIASES={"oklahoma st.":"oklahoma state",
"oklahoma st":"oklahoma state","kansas st.":"kansas state",
"kansas st":"kansas state","penn st.":"penn state","penn st":"penn state",
"michigan st.":"michigan state","michigan st":"michigan state",
"ohio st.":"ohio state","ohio st":"ohio state",
"miami (fl)":"miami","ole miss":"mississippi",
"smu":"southern methodist","usc":"southern california",
"ucf":"central florida","byu":"brigham young",
"lsu":"louisiana state","utsa":"texas san antonio"}
def canonical(x):
    text=unicodedata.normalize("NFKD",str(x or "")).encode("ascii","ignore").decode().lower().strip()
    text=ALIASES.get(text,text)
    return re.sub(r"[^a-z0-9]","",text)

def inspect(board,proj):
    from collections import Counter
    report={"status":"RESEARCH MATCHING ONLY","board_date_et":board.get("board_date_et"),
        "board_markets":len(board.get("markets",[])),
        "projected_games":len(proj.get("projections",[])),
        "verified_mapping_count":0,"unmapped_markets":0,"ambiguous_markets":0,
        "moneyline_mapped":[],"official":None,"shadow":[],
        "reasons":Counter(),"production_eligible":False}
    if not board.get("board_date_et") or board.get("candidate_market_count",0)==0:
        report["status"]="DATA PASS";report["reasons"]["empty board"]+=1
        report["reasons"]=dict(report["reasons"])
        return report
    asof=dt.datetime.fromisoformat(proj["asof_utc"])
    if asof.tzinfo is None:raise ValueError("missing projection timezone")
    date=asof.astimezone(ET).date().isoformat()
    if board["board_date_et"]!=date:
        report["status"]="STALE BOARD"
        report["reasons"]["board and projection ET date do not match"]+=1
        report["reasons"]=dict(report["reasons"])
        return report
    by_day=collections.defaultdict(list)
    for g in proj.get("projections",[]):
        if not g.get("fbs_verified") or not g.get("research_only") or g.get("production_eligible"):
            raise ValueError("model provenance/eligibility inconsistent")
        when=dt.datetime.fromisoformat(g["kickoff_utc"])
        if when.tzinfo is None:raise ValueError("missing kickoff timezone")
        if when>asof:
            by_day[g["date_et"]].append(g)
    for m in board.get("markets",[]):
        if m.get("event_date")!=date or m.get("market_category")!="game":
            continue
        if m.get("status")!="active":
            report["reasons"]["inactive moneyline"]+=1;continue
        selection=canonical(m.get("yes_selection"))
        if not selection:
            report["unmapped_markets"]+=1;continue
        valid=[]
        for g in by_day[date]:
            hc=canonical(g["home_team"]); ac=canonical(g["away_team"])
            if selection==hc and hc!=ac:
                valid.append((g,"home"))
            elif selection==ac and hc!=ac:
                valid.append((g,"away"))
        if len(valid)!=1:
            report["unmapped_markets" if len(valid)==0 else "ambiguous_markets"]+=1
            report["reasons"]["missing or ambiguous exact team mapping"]+=1
            continue
        game,side=valid[0]
        p=float(game["prob_home_win_research"])
        q=p if side=="home" else 1-p
        ask=m.get("yes_ask")
        no_ask=m.get("no_ask")
        known_price=all(isinstance(x,(int,float)) and 0<x<1 for x in (ask,no_ask))
        report["verified_mapping_count"]+=1
        report["moneyline_mapped"].append({
            "ticker":m.get("ticker"),"event_ticker":m.get("event_ticker"),
            "game_id":game["cfbd_game_id"],"selection":m.get("yes_selection"),
            "home_team":game["home_team"],"away_team":game["away_team"],
            "kickoff_utc":game["kickoff_utc"],
            "model_probability_yes_research":round(q,5),
            "yes_ask_board_snapshot":ask if known_price else None,
            "no_ask_board_snapshot":no_ask if known_price else None,
            "board_price_timestamp_verified":False,
            "injuries_verified":False,"qb_verified":False,"weather_verified":False,
            "confidence":"RESEARCH ONLY — no official/shadow eligibility"})
    report["reasons"]["market quote freshness unavailable"]+=1
    report["reasons"]["injuries/QB/weather unavailable"]+=1
    report["reasons"]["historical market-profit holdout unavailable"]+=1
    report["reasons"]=dict(report["reasons"])
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--board",required=True);p.add_argument("--projections",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    board=json.loads(pathlib.Path(a.board).read_text())
    proj=json.loads(pathlib.Path(a.projections).read_text())
    result=inspect(board,proj)
    pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("status","board_markets","projected_games",
        "verified_mapping_count","unmapped_markets","ambiguous_markets","production_eligible")}))
if __name__=="__main__":main()
