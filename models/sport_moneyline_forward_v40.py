#!/usr/bin/env python3
"""Four-sport prospective GAME-WINNER market observation, research only.

Leagues: NFL, NBA, NHL, NCAAB. MLB and WNBA are recorded as off-season.
No projected independent win probabilities in candidate boards: NEVER treat
Kalshi bids/asks as independent model confidence or automatically propose
official/shadow picks. Teams MUST match both selections to one unique ESPN
scheduled event; only then can a live Kalshi quote be time-stamped pregame.
ESPN's public site endpoints are unofficial and may change. Missing/mismatched
data is a skip, not an assumed home/away/team assignment.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from multisport_collect_v30 import CONFIG, scoreboard_url
from ncaaf_forward_audit_v33 import get_market, get_orderbook, get_series, fee_spec, simulated_taker, taker_fee, D, stamp

UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")
ACTIVE=("NFL","NBA","NHL","NCAAB")
OFFSEASON=("MLB","WNBA")
MAX_EVENTS_PER_LEAGUE=8
CAPTURE_WINDOW_MINUTES=360
KICKOFF_BUFFER_MINUTES=10

def clean_name(x):
    s=re.sub(r"[^a-z0-9 ]+"," ",str(x or "").lower().replace("&"," and "))
    s=" ".join(s.split())
    # Exact normalization of common school abbreviations, without fuzzy
    # distances, city guesses or ambiguous nickname-only inference.
    words=s.split()
    words=["state" if w=="st" and (len(words)==1 or words[-1]!="louis") else w for w in words]
    return " ".join(words)

def team_aliases(team):
    if not isinstance(team,dict):return set()
    names=[team.get(k) for k in ("location","displayName","shortDisplayName","abbreviation")]
    return {clean_name(n) for n in names if isinstance(n,str) and clean_name(n)}

def scoreboard_events(league, payload):
    out=[]
    for event in payload.get("events",[]):
        if not isinstance(event,dict) or not event.get("id"):continue
        comps=event.get("competitions") or []
        if not comps or not isinstance(comps[0],dict):continue
        comp=comps[0]
        teams=comp.get("competitors") or []
        h=next((x.get("team") for x in teams if x.get("homeAway")=="home"),None)
        a=next((x.get("team") for x in teams if x.get("homeAway")=="away"),None)
        kick=stamp(event.get("date"))
        if not h or not a or kick is None:continue
        state=(comp.get("status") or event.get("status") or {}).get("type") or {}
        out.append({"espn_game_id":str(event["id"]),"kickoff_utc":kick.isoformat(),
            "event_date_et":kick.astimezone(ET).date().isoformat(),
            "home":h,"away":a,"completed":state.get("completed") is True,
            "home_score":next((x.get("score") for x in teams if x.get("homeAway")=="home"),None),
            "away_score":next((x.get("score") for x in teams if x.get("homeAway")=="away"),None),
            "league":league})
    return out

def matched_games(board,schedules,now,window=CAPTURE_WINDOW_MINUTES):
    if not isinstance(board.get("markets"),list):return [],{"INVALID BOARD":1}
    byevent=collections.defaultdict(list)
    for m in board["markets"]:
        if m.get("market_category")=="game" and m.get("ticker") and m.get("event_ticker"):
            byevent[m["event_ticker"]].append(m)
    result=[];rejected=collections.Counter()
    used=set()
    for event_ticker,markets in sorted(byevent.items()):
        # Require both potential winners, distinct tickers, same event + day.
        if len(markets)!=2 or len({x.get("ticker") for x in markets})!=2:
            rejected["MISSING EXACT TWO WINNER TICKERS"]+=1;continue
        selections={clean_name(x.get("yes_selection")) for x in markets}
        days={x.get("event_date") for x in markets}
        if len(selections)!=2 or "" in selections or len(days)!=1:
            rejected["AMBIGUOUS WINNER SELECTION"]+=1;continue
        date=next(iter(days))
        possible=[]
        for event in schedules:
            if event["event_date_et"]!=date or event["completed"]:continue
            kick=stamp(event["kickoff_utc"])
            left=(kick-now).total_seconds()/60
            if not (KICKOFF_BUFFER_MINUTES<left<=window):continue
            h=team_aliases(event["home"]);a=team_aliases(event["away"])
            if len(selections.intersection(h))==1 and len(selections.intersection(a))==1:
                possible.append(event)
        if len(possible)!=1:
            rejected["NO UNIQUE MATCH OF BOTH TEAMS TO FUTURE ESPN GAME"]+=1;continue
        event=possible[0]
        if event["espn_game_id"] in used:
            rejected["DUPLICATE ESPN GAME MATCH"]+=1;continue
        used.add(event["espn_game_id"])
        home_matches=[m for m in markets if clean_name(m["yes_selection"]) in team_aliases(event["home"])]
        if len(home_matches)!=1:
            rejected["NO SINGLE HOME WINNER CONTRACT"]+=1;continue
        result.append({"espn_game_id":event["espn_game_id"],
            "event_ticker":event_ticker,"event_date_et":date,
            "kickoff_utc":event["kickoff_utc"],
            "home_team":event["home"].get("displayName"),
            "away_team":event["away"].get("displayName"),
            "home_team_id":str(event["home"].get("id")),
            "away_team_id":str(event["away"].get("id")),
            "ticker":home_matches[0]["ticker"],
            "home_selection_label":home_matches[0]["yes_selection"],
            "team_identity_matched_both_sides":True})
    result.sort(key=lambda r:(r["kickoff_utc"],r["espn_game_id"]))
    return result,dict(rejected)

def public_scoreboard(league,day):
    url=scoreboard_url(league,day)
    req=urllib.request.Request(url,headers={"User-Agent":"SportsPregameResearch/4.0"})
    try:
        with urllib.request.urlopen(req,timeout=22) as resp:
            payload=json.load(resp)
        if not isinstance(payload.get("events"),list):
            raise ValueError("missing scoreboard event list")
        return payload
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        raise ValueError("unofficial ESPN scoreboard unavailable") from None

def capture_one(row,now,market_fn=get_market,book_fn=get_orderbook,series_fn=get_series,clock=None):
    ticker=row["ticker"]
    try:
        market=market_fn(ticker)
        if market.get("ticker")!=ticker or str(market.get("status","")).lower() not in ("active","open"):
            raise ValueError("not open or identity mismatch")
        book=book_fn(ticker)
        yes=simulated_taker(book,"YES",D("1"))
        no=simulated_taker(book,"NO",D("1"))
        if not (yes and no and yes.get("depth_available") and no.get("depth_available")):
            raise ValueError("both sides lack one-contract depth")
        series=series_fn(str(market.get("series_ticker") or ticker.split("-")[0]))
        multiplier,error=fee_spec(series,market)
        fee=taker_fee(D("1"),D(str(yes["vwap_ask"])),multiplier) if multiplier is not None else None
        at=(clock or (lambda:dt.datetime.now(UTC)))()
        kick=stamp(row["kickoff_utc"])
        if not (now<=at<kick-dt.timedelta(minutes=1)):
            raise ValueError("not before kickoff")
        # Midpoint of YES ask vs (1-NO ask), neither implies execution.
        midpoint=(yes["vwap_ask"]+1-no["vwap_ask"])/2
        if not 0<midpoint<1:
            raise ValueError("invalid book midpoint")
        return {**row,"quote_observed_utc":at.isoformat(),
            "home_yes_ask":round(yes["vwap_ask"],6),
            "home_no_ask":round(no["vwap_ask"],6),
            "home_bidask_midpoint":round(midpoint,6),
            "yes_contracts_available":yes.get("available_contracts"),
            "no_contracts_available":no.get("available_contracts"),
            "taker_fee_estimate_one_yes_contract":float(fee) if fee is not None else None,
            "fee_metadata_verified":multiplier is not None,
            "independent_model_probability":None,
            "lineup_or_starter_verified":False,
            "model_edge_evaluated":False,
            "official_eligible":False,"shadow_eligible":False,
            "research_only":True},None
    except (ValueError,KeyError,TypeError) as err:
        return None,str(err)[:110]

def scan(league,board,schedules,now,capture=capture_one,max_events=MAX_EVENTS_PER_LEAGUE):
    if league not in ACTIVE:raise ValueError("league not active")
    if board.get("sport_key")!=league.lower():raise ValueError("board sport identity mismatch")
    board_day=dt.date.fromisoformat(board["board_date_et"])
    today=now.astimezone(ET).date()
    if abs((today-board_day).days)>1:
        return {"sport":league,"status":"BOARD DATE STALE — NO CAPTURE",
            "observations":[],"candidate_events":0,"matched_events":0,
            "exclusions":{"BOARD DATE STALE":1},
            "official_eligible":False,"production_eligible":False}
    matches,exclusions=matched_games(board,schedules,now)
    results=[];errors=collections.Counter(exclusions)
    for m in matches[:max_events]:
        row,error=capture(m,now)
        if row:results.append(row)
        else:errors[error or "UNAVAILABLE QUOTE"]+=1
    return {"sport":league,"status":"PROSPECTIVE INDEPENDENT GAME-WINNER PRICE SAMPLING ONLY",
        "board_date_et":board_day.isoformat(),
        "candidate_events":len({x.get("event_ticker") for x in board.get("markets",[])
                                if x.get("market_category")=="game"}),
        "matched_events":len(matches),"attempted_events":min(len(matches),max_events),
        "observations":results,"exclusions":dict(errors),
        "official_eligible":False,"shadow_eligible":False,"production_eligible":False,
        "note":"No independent sportsbook model probabilities exist here. Public sampled book asks are NOT user fills. No market-derived model edge or official pick."}

def read_schedules(league,now,scoreboard_fn=public_scoreboard):
    # Date in ET, plus adjacent tomorrow for late-evening forward coverage.
    today=now.astimezone(ET).date()
    out=[];missing=[]
    for day in (today,today+dt.timedelta(days=1)):
        try:out.extend(scoreboard_events(league,scoreboard_fn(league,day)))
        except ValueError:missing.append(day.isoformat())
    return out,missing

def merge(archive,observations):
    base=dict(archive)
    existing=list(base.get("observations",[]))
    keys={(str(x.get("espn_game_id")),str(x.get("ticker")),str(x.get("quote_observed_utc")))
          for x in existing}
    for row in observations:
        key=(str(row["espn_game_id"]),row["ticker"],row["quote_observed_utc"])
        if key not in keys:
            existing.append(row);keys.add(key)
    base["observations"]=existing
    return base

def run(root,boards_dir,now,scoreboard_fn=public_scoreboard,capture_fn=capture_one):
    diagnostics={};root=pathlib.Path(root)
    for league in ACTIVE:
        board_path=pathlib.Path(boards_dir)/f"{league.lower()}-candidates.json"
        try:
            board=json.loads(board_path.read_text())
            schedules,missing=read_schedules(league,now,scoreboard_fn)
            if missing:raise ValueError("missing dates from independent schedule")
            report=scan(league,board,schedules,now,capture_fn)
            bydate=collections.defaultdict(list)
            for item in report.get("observations",[]):bydate[item["event_date_et"]].append(item)
            for day,items in bydate.items():
                path=root/league/(day+".json")
                path.parent.mkdir(parents=True,exist_ok=True)
                prior=json.loads(path.read_text()) if path.exists() else {"schemaVersion":1,
                    "sport":league,"event_date_et":day,"observations":[],"verified_outcomes":{}}
                merged=merge(prior,items)
                path.write_text(json.dumps(merged,indent=2)+"\n")
            diagnostics[league]={k:v for k,v in report.items() if k!="observations"}
            diagnostics[league]["new_observations"]=len(report.get("observations",[]))
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as e:
            diagnostics[league]={"sport":league,"status":"SOURCE/BOARD COVERAGE UNAVAILABLE",
                "error":str(e)[:180],"new_observations":0,
                "official_eligible":False,"production_eligible":False}
    for league in OFFSEASON:
        diagnostics[league]={"sport":league,"status":"OFFSEASON — NO GAME-WINNER CAPTURE",
            "new_observations":0,"official_eligible":False,"production_eligible":False}
    return {"schemaVersion":1,"generatedAtUTC":now.isoformat(),
        "status":"CROSS-SPORT MONEYLINE FORWARD COLLECTION — RESEARCH ONLY",
        "leagues":diagnostics,"official_eligible":False,"shadow_eligible":False,
        "production_eligible":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive-dir",default="research/sports-forward")
    p.add_argument("--boards-dir",default="kalshi")
    p.add_argument("--output",default="dashboard/sports-v40-capture-health.json")
    a=p.parse_args()
    now=dt.datetime.now(UTC)
    out=run(a.archive_dir,a.boards_dir,now)
    path=pathlib.Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:{"status":v["status"],"new":v.get("new_observations",0)} for k,v in out["leagues"].items()}))
if __name__=="__main__":main()
