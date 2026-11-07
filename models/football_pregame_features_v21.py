#!/usr/bin/env python3
"""Leakage-safe historical football features from completed game records.

Supports ESPN score collector output for FBS and NFL. Uses ONLY games with
date strictly before target game's date. Produces independent (score-based)
rolling offense/defense/pace proxy projections; pace proxy is NOT possessions.
Injury and weather adjustments are deliberately missing until verified.
"""
import argparse, collections, datetime as dt, json, math, statistics
def build(games,league,min_games=4):
    games=sorted(games,key=lambda g:(g["date"],str(g.get("id",""))))
    history=collections.defaultdict(list); out=[]; i=0
    while i<len(games):
        date=games[i]["date"];batch=[]
        while i<len(games) and games[i]["date"]==date:
            batch.append(games[i]);i+=1
        for g in batch:
            h=history[str(g["home_id"])];a=history[str(g["away_id"])]
            if min(len(h),len(a))<min_games:continue
            def avg(v,k):return sum(x[k] for x in v[-8:])/len(v[-8:])
            # Shrink small samples toward a league-neutral 23 PPG prior.
            def shrink(x,n):return (x*n+23*4)/(n+4)
            hn=min(8,len(h));an=min(8,len(a))
            ho=shrink(avg(h,"for"),hn);hd=shrink(avg(h,"against"),hn)
            ao=shrink(avg(a,"for"),an);ad=shrink(avg(a,"against"),an)
            hp=(ho+ad)/2+1.0;ap=(ao+hd)/2-1.0
            out.append({**g,"home_pregame_offense_ppg":ho,"home_pregame_defense_ppg":hd,
                "away_pregame_offense_ppg":ao,"away_pregame_defense_ppg":ad,
                "home_pregame_pace":70,"away_pregame_pace":70,
                "home_field_points":2.0,"projected_home_points":hp,
                "projected_away_points":ap,"feature_asof":date,
                "feature_source":"rolling prior-game score stats (not efficiency or true pace)",
                "injuries_verified":False,"weather_verified":False,
                "production_eligible":False})
        for g in batch:
            history[str(g["home_id"])].append({"for":float(g["home_points"]),"against":float(g["away_points"])})
            history[str(g["away_id"])].append({"for":float(g["away_points"]),"against":float(g["home_points"])})
    return out
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--games",required=True);p.add_argument("--league",choices=["NCAAF","NFL"],required=True);p.add_argument("--output",required=True);a=p.parse_args()
 with open(a.games) as f:games=json.load(f)
 out=build(games,a.league)
 with open(a.output,"w") as f:json.dump(out,f,indent=2)
 print(json.dumps({"league":a.league,"input_games":len(games),"feature_rows":len(out),"production_eligible":0,"reason":"injuries/weather and true efficiency/pace not connected"}))
