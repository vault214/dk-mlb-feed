#!/usr/bin/env python3
"""NCAAF v3.4 independent result corroboration: CFBD final vs Kalshi settlement.

Read-only to outside services; upgrades archived research outcomes only after
both independent CFBD completed final scores and public Kalshi settlement agree.
Does not settle anything in the user's canonical Model Picks ledger, place any
orders, or turn a research hypothesis into an official/shadow paper pick.
"""
import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import sys

from ncaaf_cfbd_ingest_v31 import fetch, finite, DataError
from ncaaf_cfbd_model_v32 import alias_index, norm
from ncaaf_forward_audit_v33 import get_market, stamp, UTC, ET

def games_by_id(games):
    out={}
    for g in games:
        if not isinstance(g,dict) or g.get("id") is None:continue
        out[str(g["id"])]=g
    return out

def scoreboard_side(g,observations,alias):
    if not isinstance(g,dict) or g.get("completed") is not True:
        return None,"GAME NOT FINAL"
    hp,ap=finite(g.get("homePoints")),finite(g.get("awayPoints"))
    if hp is None or ap is None or hp<0 or ap<0 or hp==ap:
        return None,"MISSING SCORE OR TIED"
    if not observations:return None,"NO ARCHIVED OBSERVATION"
    base=observations[0]
    # No fuzzy guessing: saved CFBD names must match the independently fetched game.
    if base["homeTeam"]!=g.get("homeTeam") or base["awayTeam"]!=g.get("awayTeam"):
        return None,"CFBD TEAM IDENTITY CONFLICT"
    kickoff=stamp(base.get("kickoffUTC"))
    date=stamp(g.get("startDate"))
    if kickoff is None or date is None or abs((date-kickoff).total_seconds())>3600:
        return None,"KICKOFF TIME CONFLICT"
    selection=base.get("selectionLabel")
    matched=alias.get(norm(selection),set())
    if len(matched)!=1:
        return None,"WINNER LABEL UNVERIFIED"
    team=next(iter(matched))
    if team not in (g.get("homeTeam"),g.get("awayTeam")):
        return None,"WINNER LABEL NOT IN GAME"
    won=g["homeTeam"] if hp>ap else g["awayTeam"]
    expected="YES" if team==won else "NO"
    return {"expected_market_result":expected,"home_points":int(hp),
            "away_points":int(ap),"winner_team":won,
            "home_team":g["homeTeam"],"away_team":g["awayTeam"],
            "cfbd_game_id":str(g["id"])} ,None

def reconcile(archives,games,teams,now,market_fn=get_market):
    alias=alias_index(teams)
    games=games_by_id(games)
    verified=0
    counters=collections.Counter()
    cfbd_complete=set()
    settled_public=set()
    conflict_details=[]
    cache={}
    # Evidence grouping: settle once per ticker; the same game/ticker may have
    # many snapshots and both YES and NO research sides.
    for day,archive in sorted(archives.items()):
        if archive.get("sport")!="NCAAF":continue
        grouped=collections.defaultdict(list)
        for o in archive.get("observations",[]):
            grouped[(o.get("ticker"),str(o.get("cfbdGameId")))].append(o)
        for (ticker,gid),obs in grouped.items():
            if not ticker or gid not in games:
                counters["GAME RESULT UNAVAILABLE"]+=1
                continue
            kickoff=stamp(obs[0].get("kickoffUTC"))
            if kickoff is None or now<kickoff+dt.timedelta(minutes=15):
                counters["GAME NOT YET ELIGIBLE FOR SETTLEMENT"]+=1
                continue
            evidence,error=scoreboard_side(games[gid],obs,alias)
            if error:
                counters[error]+=1
                if "CONFLICT" in error:conflict_details.append({"ticker":ticker,"reason":error})
                continue
            cfbd_complete.add(gid)
            if ticker not in cache:
                try:cache[ticker]=market_fn(ticker)
                except (ValueError,KeyError,TypeError):cache[ticker]=None
            m=cache[ticker]
            if not isinstance(m,dict) or m.get("ticker")!=ticker:
                counters["KALSHI MARKET UNAVAILABLE"]+=1;continue
            state=str(m.get("status","")).lower()
            result=str(m.get("result","")).upper()
            if state!="settled" or result not in ("YES","NO"):
                counters["KALSHI NOT SETTLED"]+=1;continue
            settled_public.add(ticker)
            if result!=evidence["expected_market_result"]:
                archive.setdefault("verified_outcomes",{}).pop(ticker,None)
                counters["SOURCE RESULT CONFLICT"]+=1
                conflict_details.append({"ticker":ticker,"game_id":gid,
                  "cfbd_winner":evidence["winner_team"],"kalshi_result":result})
                continue
            prior=(archive.get("verified_outcomes") or {}).get(ticker)
            if prior:
                if (prior.get("cfbd_game_id")!=gid or
                    prior.get("market_result")!=result or
                    prior.get("home_points")!=evidence["home_points"] or
                    prior.get("away_points")!=evidence["away_points"]):
                    counters["ARCHIVED RESULT CHANGED — REQUIRES REVIEW"]+=1
                    # Revoke stale verification rather than counting conflicting evidence.
                    archive["verified_outcomes"].pop(ticker,None)
                    conflict_details.append({"ticker":ticker,"game_id":gid,
                      "reason":"archived verified result changed"})
                    continue
                # Preserve initial verification timestamp and avoid rewriting an
                # already corroborated result on every daily validation run.
                continue
            archive.setdefault("verified_outcomes",{})[ticker]={
                **evidence,"market_result":result,
                "verified_at_utc":now.isoformat(),
                "sources":["CollegeFootballData completed final score","Kalshi settled public market"],
                "research_only":True,"official_eligible":False}
            verified+=1
    # Prevent correlation: use exactly one earliest valid home-team YES or NO
    # probability per completed unique CFBD game, not all four contract sides.
    game_first={}
    for archive in archives.values():
        confirmed=archive.get("verified_outcomes",{})
        for o in archive.get("observations",[]):
            ev=confirmed.get(o.get("ticker"))
            if not ev:continue
            if str(o.get("cfbdGameId"))!=ev["cfbd_game_id"]:continue
            if o.get("selectionLabel")!=ev["home_team"]:continue
            if o.get("side")!="YES":continue
            gid=ev["cfbd_game_id"]
            ts=stamp(o.get("quote_observed_utc"));kick=stamp(o.get("kickoffUTC"))
            if ts is None or kick is None or ts>=kick:continue
            p=finite(o.get("model_probability"))
            if p is None or not 0<p<1:continue
            old=game_first.get(gid)
            if old is None or ts<old[0]:
                home_won=int(ev["winner_team"]==ev["home_team"])
                game_first[gid]=(ts,p,home_won)
    scored=[(x[1],x[2]) for x in game_first.values()]
    brier=sum((p-y)**2 for p,y in scored)/len(scored) if scored else None
    return {
        "schemaVersion":1,"sport":"NCAAF",
        "verifiedAtUTC":now.isoformat(),
        "status":"INDEPENDENT RESULT RECONCILIATION — RESEARCH ONLY",
        "independently_completed_game_ids":len(cfbd_complete),
        "public_kalshi_settled_tickers":len(settled_public),
        "independently_verified_tickers":sum(len(a.get("verified_outcomes",{})) for a in archives.values()),
        "newly_verified_tickers_this_run":verified,
        "unique_game_winner_samples":len(scored),
        "forward_unique_game_brier":round(brier,6) if brier is not None else None,
        "unverified_reasons":dict(counters),
        "conflicts":conflict_details[:20],
        "official":None,"shadow":[],
        "production_eligible":False,"official_eligible":False,"shadow_eligible":False,
        "note":"Kalshi contract outcome must match an independent CFBD completed score and unambiguous team identity. Duplicate correlated contract sides are not counted as independent games."
    }

def load_archives(root):
    res={}
    folder=pathlib.Path(root)
    for path in folder.glob("20??-??-??.json") if folder.exists() else []:
        try:
            obj=json.loads(path.read_text())
            if obj.get("sport")=="NCAAF" and isinstance(obj.get("observations"),list):
                res[path.stem]=obj
        except (ValueError,OSError):pass
    return res

def settlement_seasons(archives,now,year_override=None):
    """Include prior season at calendar rollover; no premature archived loss."""
    if year_override is not None:
        return [year_override]
    current=now.astimezone(ET).year
    years={current}
    for archive in archives.values():
        for row in archive.get("observations",[]):
            kickoff=stamp(row.get("kickoffUTC"))
            if kickoff is not None:
                season=kickoff.astimezone(ET).year
                if current-1<=season<=current:
                    years.add(season)
    return sorted(years)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive-dir",default="research/ncaaf-forward")
    p.add_argument("--health",default="dashboard/ncaaf-v34-settlement-health.json")
    p.add_argument("--year",type=int,default=None)
    a=p.parse_args()
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:raise DataError("CFBD_API_KEY unavailable")
    now=dt.datetime.now(UTC)
    archives=load_archives(a.archive_dir)
    # Query at most current and previous season, so December postseason
    # contracts settling in January remain independently verifiable.
    years=settlement_seasons(archives,now,a.year)
    games=[];teams=[]
    for year in years:
        games.extend(fetch("/games",{"year":year,"classification":"fbs"},token))
        teams.extend(fetch("/teams/fbs",{"year":year},token))
    out=reconcile(archives,games,teams,now)
    for day,item in archives.items():
        pathlib.Path(a.archive_dir,day+".json").write_text(json.dumps(item,indent=2)+"\n")
    dest=pathlib.Path(a.health);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in (
        "status","independently_completed_game_ids",
        "public_kalshi_settled_tickers","independently_verified_tickers",
        "newly_verified_tickers_this_run","unique_game_winner_samples",
        "forward_unique_game_brier","production_eligible")}))
if __name__=="__main__":
    try:main()
    except DataError as e:
        print("NCAAF independent settlement validation failed: "+str(e),file=sys.stderr)
        sys.exit(1)
