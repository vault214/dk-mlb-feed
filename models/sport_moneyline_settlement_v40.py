#!/usr/bin/env python3
"""Independently verify four-sport public Kalshi settlements vs ESPN final scores.

This does not manufacture historical performance or model probabilities.
One home winner market per uniquely matched ESPN game, settled yes/no
and completed final score both required. NHL shootout final accepted as
reported; any equal/tied score is unscorable pending market rules review.
"""
import argparse
import collections
import datetime as dt
import json
import math
import pathlib
from zoneinfo import ZoneInfo
from ncaaf_forward_audit_v33 import stamp,get_market,UTC,ET
from sport_moneyline_forward_v40 import ACTIVE,OFFSEASON,read_schedules

MAX_AGE_DAYS=45

def num(x):
    if isinstance(x,bool):return None
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def reconcile_archive(archive,schedules,now,market_fn=get_market):
    sport=archive.get("sport")
    if sport not in ACTIVE:raise ValueError("invalid sport")
    originals=archive.setdefault("verified_outcomes",{})
    byid=collections.defaultdict(list)
    for game in schedules:
        byid[str(game.get("espn_game_id"))].append(game)
    reason=collections.Counter()
    new=0
    grouped=collections.defaultdict(list)
    for x in archive.get("observations",[]):
        if x.get("research_only") is True and x.get("official_eligible") is False:
            grouped[(str(x.get("espn_game_id")),str(x.get("ticker")))].append(x)
    cache={}
    for (gid,ticker),obs in grouped.items():
        if not ticker or len(byid[gid])!=1:
            reason["SCHEDULE GAME ID NOT UNIQUE"]+=1;continue
        g=byid[gid][0]
        first=obs[0]
        start=stamp(g["kickoff_utc"])
        recorded=stamp(first.get("kickoff_utc"))
        if not start or not recorded or abs((start-recorded).total_seconds())>900:
            reason["KICKOFF IDENTITY CONFLICT"]+=1;originals.pop(ticker,None);continue
        if (str(g["home"].get("id"))!=first.get("home_team_id") or
            str(g["away"].get("id"))!=first.get("away_team_id") or
            g["home"].get("displayName")!=first.get("home_team") or
            g["away"].get("displayName")!=first.get("away_team")):
            reason["TEAM IDENTITY CONFLICT"]+=1;originals.pop(ticker,None);continue
        if not g["completed"] or now<start+dt.timedelta(minutes=15):
            reason["GAME NOT FINAL"]+=1;continue
        home,away=num(g.get("home_score")),num(g.get("away_score"))
        if home is None or away is None or home<0 or away<0 or home==away:
            reason["NO UNTIED OFFICIAL SCORE"]+=1;continue
        expected="YES" if home>away else "NO"
        if ticker not in cache:
            try:cache[ticker]=market_fn(ticker)
            except (ValueError,TypeError,KeyError):cache[ticker]=None
        m=cache[ticker]
        if not m or m.get("ticker")!=ticker or str(m.get("status","")).lower()!="settled":
            reason["PUBLIC MARKET NOT SETTLED"]+=1;continue
        result=str(m.get("result","")).upper()
        if result not in ("YES","NO"):
            reason["NONBINARY MARKET SETTLEMENT"]+=1;continue
        if result!=expected:
            reason["CFBD/ESPN VS KALSHI RESULT CONFLICT"]+=1
            originals.pop(ticker,None);continue
        outcome={"espn_game_id":gid,"ticker":ticker,"market_result":result,
            "home_won":home>away,"home_final_score":home,"away_final_score":away,
            "home_team_id":first["home_team_id"],"away_team_id":first["away_team_id"],
            "kickoff_utc":g["kickoff_utc"],"research_only":True,
            "official_eligible":False,"sources":["ESPN completed final game","Kalshi public settled market"]}
        old=originals.get(ticker)
        if old:
            fields=("espn_game_id","market_result","home_final_score","away_final_score")
            if any(old.get(k)!=outcome.get(k) for k in fields):
                originals.pop(ticker,None)
                reason["ARCHIVED RESULT RECONCILIATION CONFLICT"]+=1
            continue
        originals[ticker]={**outcome,"first_verified_at_utc":now.isoformat()}
        new+=1
    return {"newly_verified_tickers":new,"total_verified_tickers":len(originals),
        "reasons":dict(reason)}

def score(league,archives,now):
    first={}
    for item in archives:
        if item.get("sport")!=league:continue
        outcomes=item.get("verified_outcomes",{})
        for x in item.get("observations",[]):
            if not x.get("research_only") or x.get("official_eligible") is not False:continue
            at=stamp(x.get("quote_observed_utc"));kick=stamp(x.get("kickoff_utc"))
            p=num(x.get("home_bidask_midpoint"))
            if at is None or kick is None or at>=kick or p is None or not 0<p<1:continue
            gid=str(x.get("espn_game_id"));ticker=x.get("ticker")
            key=(gid,ticker)
            if key not in first or at<stamp(first[key]["quote_observed_utc"]):
                first[key]=x
    outcomes={}
    for item in archives:
        if item.get("sport")!=league:continue
        for ticker,v in item.get("verified_outcomes",{}).items():
            if not isinstance(v,dict):continue
            if (v.get("official_eligible") is False and v.get("research_only") is True and
                v.get("market_result") in ("YES","NO") and
                "Kalshi public settled market" in (v.get("sources") or []) and
                "ESPN completed final game" in (v.get("sources") or [])):
                outcomes[(str(v.get("espn_game_id")),ticker)]=v
    games={};unsettled=set()
    for (gid,ticker),row in first.items():
        ev=outcomes.get((gid,ticker))
        if not ev:
            unsettled.add(gid);continue
        # Do not count twice if source archive holds correlated observations.
        if gid in games:
            # Ambiguous: two different game-winner tickers; do not pick winner
            # retrospectively, remove the game from the scored sample.
            games[gid]=None
            continue
        if (ev.get("home_team_id")!=row.get("home_team_id") or
            ev.get("away_team_id")!=row.get("away_team_id")):continue
        games[gid]={"id":gid,"home_won":int(ev["home_won"]),
            "p":row["home_bidask_midpoint"],"timestamp":row["quote_observed_utc"]}
    scored=[x for x in games.values() if x is not None]
    brier=sum((x["p"]-x["home_won"])**2 for x in scored)/len(scored) if scored else None
    loss= -sum(x["home_won"]*math.log(x["p"])+(1-x["home_won"])*math.log(1-x["p"]) for x in scored)/len(scored) if scored else None
    return {"sport":league,"observed_unique_games":len({k[0] for k in first}),
        "independently_settled_games":len(scored),
        "games_awaiting_settlement":len(unsettled),
        "market_midpoint_brier":round(brier,6) if brier is not None else None,
        "market_midpoint_log_loss":round(loss,6) if loss is not None else None,
        "independent_model_brier":None,"independent_model_vs_market_edge":None,
        "hypothetical_profit":None,
        "official_eligible":False,"shadow_eligible":False,
        "production_eligible":False,
        "note":"Market midpoint is NOT an independent win model. No precommitted model edges or stakes, so no hypothetical strategy profit is calculated."}

def run(root,now,scoreboards=read_schedules,market_fn=get_market):
    base=pathlib.Path(root);leagues={}
    for league in ACTIVE:
        folder=base/league
        archives=[]
        for path in sorted(folder.glob("20??-??-??.json")) if folder.exists() else []:
            try:
                date=dt.date.fromisoformat(path.stem)
                if abs((now.astimezone(ET).date()-date).days)>MAX_AGE_DAYS:continue
                archives.append((path,json.loads(path.read_text())))
            except (ValueError,OSError,TypeError):continue
        checked=0
        errors=[]
        for path,archive in archives:
            day=dt.date.fromisoformat(path.stem)
            # Use EXACT event date, not today's scoreboards.
            try:
                from sport_moneyline_forward_v40 import public_scoreboard,scoreboard_events
                schedule=scoreboard_events(league,public_scoreboard(league,day))
                result=reconcile_archive(archive,schedule,now,market_fn)
                checked+=1
                # Explicit research-only changes to observed event archives.
                path.write_text(json.dumps(archive,indent=2)+"\n")
            except (ValueError,OSError,KeyError) as ex:
                errors.append({"date":day.isoformat(),"reason":str(ex)[:100]})
        metrics=score(league,[a for path,a in archives],now)
        metrics.update({"checked_archive_days":checked,"unavailable_archive_dates":errors})
        leagues[league]=metrics
    for league in OFFSEASON:
        leagues[league]={"sport":league,"status":"OFFSEASON — NO CURRENT FORWARD SAMPLES",
           "official_eligible":False,"production_eligible":False}
    return {"schemaVersion":1,"generatedAtUTC":now.isoformat(),
        "status":"INDEPENDENT MULTISPORT MONEYLINE RESULT RECONCILIATION — RESEARCH ONLY",
        "leagues":leagues,"official_eligible":False,
        "shadow_eligible":False,"production_eligible":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive-dir",default="research/sports-forward")
    p.add_argument("--output",default="dashboard/sports-v40-result-health.json")
    a=p.parse_args();now=dt.datetime.now(UTC)
    result=run(a.archive_dir,now)
    out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:{"games":v.get("independently_settled_games"),"source_errors":len(v.get("unavailable_archive_dates",[]))} for k,v in result["leagues"].items()}))
if __name__=="__main__":main()
