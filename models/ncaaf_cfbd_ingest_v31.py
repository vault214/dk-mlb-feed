#!/usr/bin/env python3
"""CollegeFootballData authenticated FBS pregame research snapshot.

Never publish credentials; only read CFBD_API_KEY from environment.
All advanced stats are linked to completed games with kickoff strictly before
the target game's start AND before snapshot time; no future-season aggregation.
Stats are opponent-unadjusted research features, NOT betting probabilities.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE = "https://api.collegefootballdata.com"
UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")

class DataError(Exception):
    pass

def fetch(path, params, token):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "IndependentNCAAFResearch/3.1"})
    try:
        with urllib.request.urlopen(req, timeout=50) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as exc:
        # NEVER echo request URLs (or headers), response bodies, or token.
        raise DataError("CFBD endpoint " + path + " returned HTTP " + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise DataError("CFBD endpoint " + path + " could not be fetched/decoded") from None
    if not isinstance(result, list):
        raise DataError("CFBD endpoint " + path + " returned unexpected data shape")
    return result

def instant(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        t = dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except ValueError:
        return None

def finite(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):
        return None

def summarize_team(team, past_ids, advanced, min_games=3):
    samples = []
    for gid in past_ids:
        for stat in advanced.get(str(gid), []):
            if stat.get("team") != team:
                continue
            offense = stat.get("offense") or {}
            defense = stat.get("defense") or {}
            vals = {k: finite((side or {}).get(field)) for k,side,field in [
                ("off_ppa",offense,"ppa"),("def_ppa",defense,"ppa"),
                ("off_success",offense,"successRate"),
                ("def_success",defense,"successRate"),
                ("off_plays",offense,"plays"),("def_plays",defense,"plays")]}
            if all(v is not None for v in vals.values()) and vals["off_plays"] > 0 and vals["def_plays"] > 0:
                samples.append(vals)
    # At most last 8 earlier games, but caller must supply sorted IDs.
    samples = samples[-8:]
    if len(samples) < min_games:
        return None
    return {"games":len(samples),
            "offense_ppa_per_play":round(statistics.mean(s["off_ppa"] for s in samples),4),
            "defense_ppa_allowed_per_play":round(statistics.mean(s["def_ppa"] for s in samples),4),
            "offense_success_rate":round(statistics.mean(s["off_success"] for s in samples),4),
            "defense_success_rate_allowed":round(statistics.mean(s["def_success"] for s in samples),4),
            "offense_plays_per_game":round(statistics.mean(s["off_plays"] for s in samples),2),
            "defense_plays_per_game":round(statistics.mean(s["def_plays"] for s in samples),2),
            "source":"CFBD completed-game advanced statistics; not opponent-adjusted"}

def build_snapshot(year, games, stats, teams, now):
    fbs={str(t.get("school")) for t in teams if t.get("school")}
    if len(fbs)<80:
        raise DataError("FBS team list coverage unexpectedly low")
    adv=collections.defaultdict(list)
    for s in stats:
        if isinstance(s,dict) and s.get("gameId") is not None:
            adv[str(s["gameId"])].append(s)
    by_team=collections.defaultdict(list)
    usable=[]
    for g in games:
        if not isinstance(g,dict):
            continue
        when=instant(g.get("startDate"))
        if when is None or g.get("id") is None:
            continue
        home=g.get("homeTeam");away=g.get("awayTeam")
        if home not in fbs or away not in fbs:
            continue
        x={"id":str(g["id"]),"when":when,"home":home,"away":away,
           "completed":g.get("completed") is True}
        usable.append(x)
    usable.sort(key=lambda g:(g["when"],g["id"]))
    # Prevent leakage from games completed earlier on the same ET calendar day.
    asof_date=now.astimezone(ET).date()
    prior=[x for x in usable if x["completed"] and x["when"].astimezone(ET).date()<asof_date]
    for g in prior:
        by_team[g["home"]].append(g["id"])
        by_team[g["away"]].append(g["id"])
    planned=[x for x in usable if x["when"]>now and x["when"]<=now+dt.timedelta(days=7)]
    rows=[]
    for g in planned:
        h=summarize_team(g["home"],by_team[g["home"]],adv)
        a=summarize_team(g["away"],by_team[g["away"]],adv)
        rows.append({
          "cfbd_game_id":g["id"],"home_team":g["home"],"away_team":g["away"],
          "kickoff_utc":g["when"].isoformat(),
          "home":h,"away":a,"available":bool(h and a),
          "features_asof_utc":now.isoformat(),
          "cutoff_policy":"only games before snapshot ET calendar date",
          "injuries_verified":False,"qb_verified":False,
          "weather_verified":False,"independent_projection_validated":False,
          "production_eligible":False})
    return {"schemaVersion":1,"sport":"NCAAF","year":year,
     "capturedAtUTC":now.isoformat(),"source":"CollegeFootballData API",
     "endpoints":["/teams/fbs","/games","/stats/game/advanced"],
     "fbs_team_count":len(fbs),"season_fbs_games":len(usable),
     "completed_fbs_games_before_today":len(prior),
     "advanced_game_ids":len(adv),
     "upcoming_fbs_games":len(planned),
     "upcoming_with_minimum_advanced_data":sum(x["available"] for x in rows),
     "upcoming":rows,
     "gaps":["opponent-adjusted efficiency calibration","quarterback/injury verification",
       "weather verification","historical timestamped Kalshi executable asks",
       "game-to-Kalshi market mapping and current quote verification"],
     "status":"RESEARCH ONLY","production_eligible":False,
     "official_eligible":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",type=int,default=dt.datetime.now(ET).year)
    p.add_argument("--output",default="ncaaf-cfbd-snapshot.json")
    p.add_argument("--health",default="dashboard/ncaaf-cfbd-health.json")
    args=p.parse_args()
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:
        raise DataError("CFBD_API_KEY GitHub Actions secret was not provided")
    now=dt.datetime.now(UTC)
    teams=fetch("/teams/fbs",{"year":args.year},token)
    games=fetch("/games",{"year":args.year,"classification":"fbs"},token)
    stats=fetch("/stats/game/advanced",{"year":args.year},token)
    snapshot=build_snapshot(args.year,games,stats,teams,now)
    pathlib.Path(args.output).write_text(json.dumps(snapshot,indent=2)+"\n")
    health={k:snapshot[k] for k in ("schemaVersion","sport","year",
       "capturedAtUTC","source","fbs_team_count","season_fbs_games",
       "completed_fbs_games_before_today","advanced_game_ids",
       "upcoming_fbs_games","upcoming_with_minimum_advanced_data",
       "gaps","status","production_eligible","official_eligible")}
    # Small sanitized report, no private finance data or API key.
    dest=pathlib.Path(args.health);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(health,indent=2)+"\n")
    print(json.dumps({k:health[k] for k in ("year","fbs_team_count",
       "season_fbs_games","advanced_game_ids","upcoming_fbs_games",
       "upcoming_with_minimum_advanced_data","status")}))
if __name__=="__main__":
    try:main()
    except DataError as exc:
        print("CFBD research ingestion failed: "+str(exc),file=sys.stderr)
        sys.exit(1)
