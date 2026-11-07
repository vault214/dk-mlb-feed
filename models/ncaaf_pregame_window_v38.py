#!/usr/bin/env python3
"""2026 NCAA conference-only reporting clock and pre-kickoff sampling window.

Read-only diagnostics, never a substitute for a GAME-SPECIFIC report.
Run at 15-minute intervals, while limiting expensive report/market queries to
matched games within 180 minutes of verified kickoff. Does not certify QBs.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")
CONF={
 "sec":("SEC",90,"https://www.secsports.com/reports"),
 "big 12":("BIG12",90,"https://admin.big12sports.com/news/2025/8/13/general-big-12-conference-to-begin-player-availability-reporting-for-football-womens-and-mens-basketball.aspx"),
 "big ten":("BIGTEN",120,"https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx"),
 "acc":("ACC",120,"https://admin.theacc.com/sports/2025/8/28/availability-reporting.aspx"),
}
ALIASES={
 "sec":"sec","southeastern":"sec","southeastern conference":"sec",
 "big 12":"big 12","big 12 conference":"big 12",
 "big ten":"big ten","big ten conference":"big ten",
 "acc":"acc","atlantic coast":"acc","atlantic coast conference":"acc",
}
WINDOW_MINUTES=180
def parse_utc(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except ValueError:return None

def policy_for(row):
    if row.get("conference_game") is not True:
        return None
    h=ALIASES.get(str(row.get("home_conference") or "").strip().lower())
    a=ALIASES.get(str(row.get("away_conference") or "").strip().lower())
    return CONF.get(h) if h and h==a else None

def report_clock(row,now):
    kick=parse_utc(row.get("kickoff_utc"))
    if kick is None:
        return {"status":"INVALID KICKOFF — FAIL CLOSED","capture_window":False}
    minutes=(kick-now).total_seconds()/60
    pol=policy_for(row)
    due=kick-dt.timedelta(minutes=pol[1]) if pol else None
    if minutes<=0:stage="KICKOFF PASSED"
    elif minutes>WINDOW_MINUTES:stage="OUTSIDE ACTIVE REPORT WINDOW"
    elif pol is None:stage="PREGAME — NO APPLICABLE VERIFIED CONFERENCE POLICY"
    elif now<due:stage="FINAL REPORT NOT YET DUE"
    else:stage="FINAL REPORT DUE — ACTUAL DOCUMENT MUST BE VERIFIED"
    return {
       "cfbd_game_id":str(row.get("cfbd_game_id")),
       "home_team":row.get("home_team"),"away_team":row.get("away_team"),
       "kickoff_utc":kick.isoformat(),
       "minutes_to_kickoff":round(minutes,1),
       "capture_window":0<minutes<=WINDOW_MINUTES,
       "official_policy_applicable":pol is not None,
       "conference":pol[0] if pol else None,
       "final_report_due_utc":due.isoformat() if due else None,
       "final_report_due_minutes_before_kickoff":pol[1] if pol else None,
       "official_policy_url":pol[2] if pol else None,
       "unlisted_player_policy_if_verified_complete_report":
          ("AVAILABLE BY REPORTING POLICY — ONLY IF PLAYER IS COVERED AND A COMPLETE FINAL GAME REPORT IS VERIFIED"
           if pol and pol[0] in ("SEC","BIGTEN")
           else "NO VERIFIED SAFE OMISSION INFERENCE"),
       "actual_unlisted_player_status_assessed":False,
       "stage":stage,
       "actual_final_report_verified":False,
       "both_starting_qbs_verified":False,
       "available_if_omitted_policy_applied":False,
       "official_eligible":False}

def plan(queue,research,now,manual=False):
    policy={str(r.get("cfbd_game_id")):r for r in queue.get("game_review_queue",[])}
    rows=research.get("rows",[])
    seen=set();clocks=[]
    for r in rows:
        gid=str(r.get("cfbdGameId") or "")
        if not gid or gid in seen:continue
        seen.add(gid)
        q=policy.get(gid)
        if q is None:continue
        if q.get("home_team")!=r.get("homeTeam") or q.get("away_team")!=r.get("awayTeam"):
            continue
        when=parse_utc(r.get("kickoffUTC"))
        if when!=parse_utc(q.get("kickoff_utc")):
            continue
        clocks.append(report_clock(q,now))
    selected=[g for g in clocks if g["capture_window"]]
    ids={g["cfbd_game_id"] for g in selected}
    filtered_rows=[r for r in rows if str(r.get("cfbdGameId")) in ids]
    selected_queue=[g for g in queue.get("game_review_queue",[]) if str(g.get("cfbd_game_id")) in ids]
    out={"schemaVersion":1,"sport":"NCAAF","generatedAtUTC":now.isoformat(),
      "status":"PREGAME WINDOW SELECTION — RESEARCH ONLY",
      "capture_interval_minutes":15,"window_minutes_before_kickoff":WINDOW_MINUTES,
      "matched_games":len(clocks),"active_window_games":len(selected),
      "conference_final_reports_due":sum(x["official_policy_applicable"] and x["stage"].startswith("FINAL REPORT DUE") for x in selected),
      "games":clocks,"capture_now":bool(selected),
      "official_eligible":False,"production_eligible":False,
      "note":"Only actual primary matchup documents can validate statuses. Conference policy timing and website links cannot."}
    filtered=dict(research);filtered["rows"]=filtered_rows;filtered["rowCount"]=len(filtered_rows)
    scoped=dict(queue);scoped["game_review_queue"]=selected_queue;scoped["matched_games"]=len(selected_queue)
    return out,filtered,scoped

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="dashboard/ncaaf-v34-availability-health.json")
    p.add_argument("--research",default="dashboard/ncaaf-v32-research.json")
    p.add_argument("--output",default="dashboard/ncaaf-v38-window.json")
    p.add_argument("--filtered-research",default="ncaaf-v38-filtered-research.json")
    p.add_argument("--scoped-queue",default="ncaaf-v38-scoped-queue.json")
    p.add_argument("--manual",action="store_true")
    a=p.parse_args()
    q=json.loads(pathlib.Path(a.queue).read_text())
    r=json.loads(pathlib.Path(a.research).read_text())
    now=dt.datetime.now(UTC)
    report,filtered,scoped=plan(q,r,now,a.manual)
    for path,value in ((a.output,report),(a.filtered_research,filtered),(a.scoped_queue,scoped)):
        target=pathlib.Path(path);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,indent=2)+"\n")
    output=os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output,"a") as f:
            f.write("capture="+("true" if report["capture_now"] else "false")+"\n")
    print(json.dumps({"capture":report["capture_now"],
        "active_window_games":report["active_window_games"],
        "conference_final_reports_due":report["conference_final_reports_due"],
        "official_eligible":False}))
if __name__=="__main__":main()
