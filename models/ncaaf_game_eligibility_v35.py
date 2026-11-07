#!/usr/bin/env python3
"""NCAAF game-by-game eligibility diagnostics v3.5, ALWAYS research-only.

Outputs blockers per matchup and strongest side-specific *research* net differences.
No automatic official/shadow promotion, trades, Model Picks or bank access.
Market summaries and old quotes do not prove executable conditions. Requires
separately verified primary game reports, independent forward outcomes and fees.
"""
import argparse
import collections
import datetime as dt
import json
import math
import pathlib
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")
QUOTE_MAX_AGE_SECONDS=120
MIN_INDEPENDENT_SETTLED_GAMES=40
MIN_ROBUST_NET_EDGE_PP=5.0
UNCERTAINTY_RESERVE_PP=4.0
MIN_HOLDOUT_GAMES=250

def timestamp(value):
    try:
        t=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except (ValueError, TypeError):return None

def valid_number(value):
    try:
        f=float(value)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None

def weather_check(row):
    status=row.get("weatherForecastStatus")
    if status=="INDOOR VENUE":
        return {"status":"INDOOR — NO OUTDOOR WEATHER ADJUSTMENT","clear":True}
    if status!="WEATHER FORECAST SOURCED":
        return {"status":"KICKOFF FORECAST NOT VERIFIED","clear":False}
    # Game-specific conditions must be present. Having a weather STATUS alone
    # cannot establish that the weather is mild.
    w=row.get("weatherSnapshot") or {}
    gust=valid_number(w.get("gust_mph"))
    precip=valid_number(w.get("precipitation_probability_pct"))
    temp=valid_number(w.get("temperature_f"))
    if None in (gust,precip,temp):
        return {"status":"WEATHER DETAIL MISSING — NOT SCREENED","clear":False}
    if gust>=25 or precip>=65 or temp<=25 or temp>=100:
        return {"status":"SEVERE WEATHER UNCERTAINTY — CONSERVATIVE PASS","clear":False,
                "gust_mph":gust,"precipitation_probability_pct":precip,"temperature_f":temp}
    return {"status":"LOW WEATHER RISK BY CONSERVATIVE HEURISTIC","clear":True,
            "gust_mph":gust,"precipitation_probability_pct":precip,"temperature_f":temp,
            "note":"Weather heuristic is not a calibrated change to win probability."}

def best_archive_observations(datasets,now):
    # Only true pregame observations; unique per contract side / CFBD game.
    bykey={}
    for data in datasets.values():
        for r in data.get("observations",[]):
            at=timestamp(r.get("quote_observed_utc"));kick=timestamp(r.get("kickoffUTC"))
            if at is None or kick is None or not (at<kick and at<=now):continue
            key=(str(r.get("cfbdGameId")),str(r.get("ticker")),str(r.get("side")))
            if key not in bykey or at>timestamp(bykey[key]["quote_observed_utc"]):
                bykey[key]=r
    return bykey

def screen(research,availability,model,settlement,archives,now,supplemental=None,triage=None):
    if now.tzinfo is None:raise ValueError("now must have timezone")
    model_cap=timestamp(research.get("modelCapturedAtUTC"))
    model_fresh=bool(model_cap and dt.timedelta(0)<=now-model_cap<=dt.timedelta(hours=18))
    mr=model.get("calibration",{})
    model_research_supported=(mr.get("holdout_games",0)>=MIN_HOLDOUT_GAMES
        and (valid_number(mr.get("improvement")) or 0)>0
        and (valid_number(mr.get("ece")) or 1)<0.06)
    unique=settlement.get("unique_game_winner_samples",0)
    forward_supported=bool(unique>=MIN_INDEPENDENT_SETTLED_GAMES
        and settlement.get("forward_unique_game_brier") is not None)
    bygame={str(x.get("cfbd_game_id")):x for x in availability.get("game_review_queue",[])}
    supplemental_by_id={str(x.get("cfbd_game_id")):x
                        for x in (supplemental or {}).get("games",[])}
    triage_by_id={str(x.get("cfbd_game_id")):x
                  for x in (triage or {}).get("games",[])}
    triage_observed=timestamp((triage or {}).get("generatedAtUTC"))
    bybook=best_archive_observations(archives,now)
    grp=collections.defaultdict(list)
    for r in research.get("rows",[]):
        if r.get("cfbdGameId") is not None:
            grp[str(r["cfbdGameId"])].append(r)
    games=[];counts=collections.Counter()
    for gid,rows in sorted(grp.items(),key=lambda kv:kv[1][0].get("kickoffUTC","")):
        first=rows[0]
        kick=timestamp(first.get("kickoffUTC"))
        if kick is None:continue
        pregame=now<kick
        review=bygame.get(gid,{})
        source_observed=timestamp(review.get("report_observed_at_utc"))
        source_published=timestamp(review.get("report_published_at_utc"))
        document_verified=bool(
            review.get("two_teams_report_coverage_confirmed") is True
            and review.get("game_specific_primary_report_url")
            and source_observed and source_observed<kick
            and (source_published is None or source_published<=source_observed))
        qb_verified=bool(document_verified
            and review.get("starting_qb_names_confirmed") is True
            and review.get("starting_qb_statuses_verified") is True)
        impact_verified=bool(document_verified
            and review.get("material_absences_verified") is True
            and review.get("risk_adjustment_backtested") is True)
        availability_verified=bool(qb_verified and impact_verified)
        wx=weather_check(first)
        reasons=[]
        if not pregame:reasons.append("KICKOFF ALREADY PASSED")
        if not model_fresh:reasons.append("MODEL SNAPSHOT EXPIRED")
        if not model_research_supported:reasons.append("MODEL HOLDOUT / CALIBRATION BELOW RESEARCH THRESHOLD")
        if not document_verified:reasons.append("PRIMARY GAME-SPECIFIC AVAILABILITY DOCUMENT UNVERIFIED")
        if not qb_verified:reasons.append("BOTH STARTING QB STATUSES NOT VERIFIED")
        if not impact_verified:reasons.append("MATERIAL PLAYER ABSENCES / IMPACT NOT VALIDATED")
        if not wx["clear"]:reasons.append(wx["status"])
        if not forward_supported:reasons.append("INSUFFICIENT INDEPENDENT FORWARD SETTLEMENT VALIDATION")
        quotes=[];valid_quote_sides=0
        for r in rows:
            key=(gid,str(r.get("ticker")),str(r.get("side")))
            obs=bybook.get(key)
            if not obs:continue
            at=timestamp(obs.get("quote_observed_utc"))
            age=(now-at).total_seconds() if at else float("inf")
            price=valid_number(obs.get("book_vwap_ask"))
            prob=valid_number(r.get("modelProbability"))
            fee=valid_number(obs.get("taker_fee_estimate_dollars"))
            size=valid_number(obs.get("sample_contracts"))
            observed_pre_kickoff=at is not None and at<kick
            fee_known=fee is not None and fee>=0 and size and size>0
            price_known=price is not None and 0<price<1
            model_known=prob is not None and 0<prob<1
            # This is a 1-contract cost and uncertainty RESEARCH screen, not
            # a portfolio position-sizing decision.
            gross=100*(prob-price) if model_known and price_known else None
            robust=(gross-100*(fee/size)-UNCERTAINTY_RESERVE_PP
                    if gross is not None and fee_known else None)
            fresh=bool(pregame and observed_pre_kickoff and 0<=age<=QUOTE_MAX_AGE_SECONDS
                       and obs.get("market_open_at_observation") is True)
            depth=(obs.get("depth_scenarios_contracts") or {}).get("1",{}).get("depth_available") is True
            if fresh and fee_known and depth:valid_quote_sides+=1
            quotes.append({
                "ticker":r["ticker"],"side":r["side"],
                "research_model_probability":prob,
                "last_book_ask":price,
                "last_quote_utc":at.isoformat() if at else None,
                "quote_age_seconds":round(age,1) if math.isfinite(age) else None,
                "one_contract_depth_available":depth,
                "fee_estimate_per_contract":round(fee/size,5) if fee_known else None,
                "net_after_fee_and_4pp_uncertainty_research_pp":round(robust,2) if robust is not None else None,
                "quote_within_120_seconds":fresh,"fee_known":fee_known,
                "research_edge_at_least_5pp":bool(robust is not None and robust>=MIN_ROBUST_NET_EDGE_PP),
                "official_eligible":False,"shadow_eligible":False,
            })
        if valid_quote_sides==0:reasons.append("NO FRESH VERIFIED ORDERBOOK WITH FEE/DEPTH")
        if not any(q["research_edge_at_least_5pp"] and q["quote_within_120_seconds"] and q["one_contract_depth_available"]
                   and q["fee_known"] for q in quotes):
            reasons.append("NO CURRENT ROBUST RESEARCH EDGE PASSING 5PP THRESHOLD")
        if not review:
            reasons.append("NO MATCHED AVAILABILITY REVIEW")
        status="NOT PREGAME" if not pregame else "BLOCKED — EVIDENCE INCOMPLETE"
        counts[status]+=1
        lead=supplemental_by_id.get(gid,{})
        secondary=triage_by_id.get(gid,{})
        secondary_pregame=bool(triage_observed and triage_observed<kick)
        secondary_qb_flags=secondary.get("secondary_qb_risk_flags",[]) if secondary_pregame else []
        games.append({
            "cfbd_game_id":gid,"home_team":first.get("homeTeam"),"away_team":first.get("awayTeam"),
            "kickoff_utc":first["kickoffUTC"],"status":status,"reasons":reasons,
            "model_snapshot_fresh":model_fresh,
            "model_holdout_research_supported":model_research_supported,
            "independent_forward_games":unique,
            "availability_report_hub":review.get("report_discovery_hub"),
            "game_specific_report_verified":document_verified,
            "supplemental_report_lead_url":lead.get("supplemental_url"),
            "supplemental_report_lead_status":lead.get("status","NO SUPPLEMENTAL REPORT LEAD"),
            "supplemental_data_counted_as_verified":False,
            "secondary_qb_risk_flags_unverified":secondary_qb_flags,
            "secondary_qb_source_asof_utc":triage_observed.isoformat() if secondary_pregame else None,
            "secondary_qb_flags_used_for_model":False,
            "qb_and_injury_verified":availability_verified,
            "weather":wx,
            "valid_live_quote_sides":valid_quote_sides,
            "available_contract_side_samples":len(quotes),
            "research_side_comparisons":quotes,
            "official_eligible":False,"shadow_eligible":False,
        })
    return {
        "schemaVersion":1,"sport":"NCAAF",
        "generatedAtUTC":now.isoformat(),
        "status":"GAME-BY-GAME ELIGIBILITY RESEARCH — NEVER AUTO APPROVED",
        "matched_games":len(games),"games_blocked":len(games),
        "status_counts":dict(counts),
        "holdout_support":model_research_supported,
        "forward_independent_verified_games":unique,
        "minimum_distinct_forward_games_research_target":MIN_INDEPENDENT_SETTLED_GAMES,
        "snapshot_fresh":model_fresh,
        "games":games,
        "official":None,"shadow":[],
        "production_eligible":False,"official_eligible":False,"shadow_eligible":False,
        "note":"Each reason is a distinct missing check. Positive research edge is NOT an official pick: QB/injuries, forward validation, quote fees, depth and 1u sizing must all be independently confirmed."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",default="dashboard/ncaaf-v32-research.json")
    p.add_argument("--availability",default="dashboard/ncaaf-v34-availability-health.json")
    p.add_argument("--model",default="dashboard/ncaaf-v32-health.json")
    p.add_argument("--settlement",default="dashboard/ncaaf-v34-settlement-health.json")
    p.add_argument("--archive-dir",default="research/ncaaf-forward")
    p.add_argument("--supplemental",default=None)
    p.add_argument("--triage",default=None)
    p.add_argument("--output",default="dashboard/ncaaf-v35-eligibility.json")
    a=p.parse_args()
    def load(path):return json.loads(pathlib.Path(path).read_text())
    archive={}
    folder=pathlib.Path(a.archive_dir)
    for path in folder.glob("20??-??-??.json") if folder.exists() else []:
        obj=load(path)
        if obj.get("sport")=="NCAAF":archive[path.stem]=obj
    out=screen(load(a.research),load(a.availability),load(a.model),load(a.settlement),
               archive,dt.datetime.now(UTC),load(a.supplemental) if a.supplemental else None,
               load(a.triage) if a.triage else None)
    dest=pathlib.Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in (
        "status","matched_games","games_blocked",
        "forward_independent_verified_games","official_eligible")}))
if __name__=="__main__":main()
