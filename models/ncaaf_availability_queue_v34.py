#!/usr/bin/env python3
"""Game-specific official conference availability research queue, fail closed.

Conference report hubs ARE NOT game-specific evidence. This file does not scrape
or pretend to verify an athlete's availability. A game must have a primary,
date-specific report and player-level source checked independently before any
availability evidence can inform a model. Never assume unlisted == available
unless a confirmed report's published conference policy explicitly says so.
"""
import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import sys

from ncaaf_cfbd_ingest_v31 import fetch, DataError, instant, ET, UTC

HUBS={
    "sec":"https://www.secsports.com/fbreports",
    "big 12":"https://big12sports.com/sports/2025/8/21/availability-reporting.aspx",
    "big ten":"https://bigten.org/",
    "acc":"https://theacc.com/sports/2025/8/28/availability-reporting.aspx"
}
NAMES={
    "southeastern":"sec","sec":"sec",
    "big 12":"big 12","big 12 conference":"big 12",
    "big ten":"big ten","big ten conference":"big ten",
    "acc":"acc","atlantic coast":"acc","atlantic coast conference":"acc"
}

def source_for(g):
    if not g.get("conferenceGame"):
        return None,"NO CONFERENCE REPORT COVERAGE ASSUMED"
    h=str(g.get("homeConference") or "").strip().lower()
    a=str(g.get("awayConference") or "").strip().lower()
    conf=NAMES.get(h)
    if not conf or conf!=NAMES.get(a):
        return None,"NO VERIFIED SAME-CONFERENCE POLICY"
    return HUBS.get(conf),"OFFICIAL POLICY HUB ONLY — MATCHUP REPORT NOT VERIFIED"

def queue(research,games,now):
    index={str(g.get("id")):g for g in games if isinstance(g,dict) and g.get("id") is not None}
    seen=set();items=[]
    for r in research.get("rows",[]):
        gid=str(r.get("cfbdGameId") or "")
        if not gid or gid in seen:continue
        seen.add(gid)
        g=index.get(gid)
        kickoff=instant(r.get("kickoffUTC"))
        if not g or kickoff is None:continue
        if g.get("homeTeam")!=r.get("homeTeam") or g.get("awayTeam")!=r.get("awayTeam"):
            continue
        hub,hint=source_for(g)
        items.append({
            "cfbd_game_id":gid,"event_date_et":kickoff.astimezone(ET).date().isoformat(),
            "kickoff_utc":kickoff.isoformat(),
            "home_team":g.get("homeTeam"),"away_team":g.get("awayTeam"),
            "home_conference":g.get("homeConference"),
            "away_conference":g.get("awayConference"),
            "conference_game":bool(g.get("conferenceGame")),
            "report_discovery_hub":hub,
            "source_status":hint,
            "game_specific_primary_report_url":None,
            "report_published_at_utc":None,
            "two_teams_report_coverage_confirmed":False,
            "starting_qb_names_confirmed":False,
            "starting_qb_statuses_verified":False,
            "material_absences_verified":False,
            "risk_adjustment_backtested":False,
            "model_eligible":False,
            "review_due_before_kickoff":kickoff>now,
        })
    items.sort(key=lambda x:(x["kickoff_utc"],x["cfbd_game_id"]))
    counts=collections.Counter(x["source_status"] for x in items)
    return {
        "schemaVersion":1,"sport":"NCAAF",
        "generatedAtUTC":now.isoformat(),
        "status":"PRIMARY-SOURCE AVAILABILITY REVIEW QUEUE — NONE VERIFIED",
        "matched_games":len(items),
        "official_conference_report_hubs_found":sum(bool(x["report_discovery_hub"]) for x in items),
        "game_specific_reports_verified":0,
        "starting_qbs_verified":0,
        "injury_availability_verified":0,
        "conference_policy_hub_is_not_game_report":True,
        "source_discovery_status":dict(counts),
        "game_review_queue":items,
        "production_eligible":False,"official_eligible":False,"shadow_eligible":False,
        "note":"Official game reports may be missing for nonconference games. Do not treat a policy hub or an aggregator as evidence of player status. No guessed injuries or QB reports."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",default="dashboard/ncaaf-v32-research.json")
    p.add_argument("--output",default="dashboard/ncaaf-v34-availability-health.json")
    p.add_argument("--year",type=int,default=dt.datetime.now(ET).year)
    args=p.parse_args()
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:raise DataError("CFBD_API_KEY unavailable")
    now=dt.datetime.now(UTC)
    research=json.loads(pathlib.Path(args.research).read_text())
    games=fetch("/games",{"year":args.year,"classification":"fbs"},token)
    data=queue(research,games,now)
    target=pathlib.Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps({k:data[k] for k in (
        "status","matched_games","official_conference_report_hubs_found",
        "game_specific_reports_verified","starting_qbs_verified",
        "injury_availability_verified","production_eligible")}))
if __name__=="__main__":
    try:main()
    except DataError as e:
        print("Availability report verification unavailable: "+str(e),file=sys.stderr)
        sys.exit(1)
