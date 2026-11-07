#!/usr/bin/env python3
"""Prospective NCAA Football v3.9 one-independent-game performance scorecard.

Research only. Neither backfills quotes nor creates paper picks. Market "entry"
is an observed one-contract, pre-kickoff orderbook snapshot (NOT a fill).
Results require independent CFBD+Kalshi corroboration in verified_outcomes.
Each unique game contributes at most ONE home-team probability sample and at
most ONE predeclared-style theoretical edge candidate. No hindsight selection.
"""
import argparse
import collections
import datetime as dt
import json
import math
import pathlib
from ncaaf_forward_audit_v33 import stamp, ET, UTC

EDGE_PP=5.0
RESERVE_PP=4.0
MIN_GAMES=40

def number(value):
    if isinstance(value,bool):return None
    try:
        x=float(value)
        if not math.isfinite(x):return None
        return x
    except (TypeError,ValueError):return None

def brier(rows,field):
    usable=[r for r in rows if number(r.get(field)) is not None]
    if not usable:return None
    return round(sum((r[field]-r["home_won"])**2 for r in usable)/len(usable),6)

def log_loss(rows,field):
    usable=[r for r in rows if number(r.get(field)) is not None]
    if not usable:return None
    return round(-sum(r["home_won"]*math.log(max(1e-9,min(1-1e-9,r[field])))
                     +(1-r["home_won"])*math.log(max(1e-9,min(1-1e-9,1-r[field])))
                     for r in usable)/len(usable),6)

def valid_observation(r):
    at=stamp(r.get("quote_observed_utc"))
    kick=stamp(r.get("kickoffUTC"))
    model=stamp(r.get("model_captured_utc"))
    prob=number(r.get("model_probability"))
    ask=number(r.get("book_vwap_ask"))
    if not (r.get("research_only") is True and
            r.get("official_eligible") is False and
            r.get("side") in ("YES","NO") and at and kick and model and
            model<=at<kick and 0<prob<1 and 0<ask<1):
        return False
    return True

def analyze(archives,now):
    games=collections.defaultdict(list)
    confirmed=collections.defaultdict(dict)
    for file in archives.values():
        if file.get("sport")!="NCAAF":continue
        for r in file.get("observations",[]):
            if valid_observation(r):
                games[str(r.get("cfbdGameId"))].append(r)
        for ticker,ev in (file.get("verified_outcomes") or {}).items():
            if not isinstance(ev,dict):continue
            gid=str(ev.get("cfbd_game_id"))
            if (ev.get("research_only") is True and ev.get("official_eligible") is False and
                ev.get("market_result") in ("YES","NO") and
                "Kalshi settled public market" in (ev.get("sources") or []) and
                "CollegeFootballData completed final score" in (ev.get("sources") or [])):
                confirmed[gid][ticker]=ev
    primary=[]
    matched=[]
    pending_candidates=[]
    all_precommitted=[]
    close_examples=[]
    unverified=set()
    for gid,obs in sorted(games.items()):
        obs.sort(key=lambda r:(r["quote_observed_utc"],str(r["ticker"]),r["side"]))
        verified=confirmed.get(gid,{})
        if not verified:
            unverified.add(gid)
        # Require same CFBD game and home-team winner evidence, never infer.
        homeobs=[r for r in obs if r.get("side")=="YES" and
                 r.get("selectionLabel")==r.get("homeTeam") and
                 r["ticker"] in verified]
        if homeobs:
            first=min(homeobs,key=lambda r:(r["quote_observed_utc"],r["ticker"]))
            evidence=verified[first["ticker"]]
            if (evidence.get("cfbd_game_id")==gid and
                evidence.get("home_team")==first.get("homeTeam") and
                evidence.get("away_team")==first.get("awayTeam") and
                evidence.get("winner_team") in (first.get("homeTeam"),first.get("awayTeam"))):
                home_win=int(evidence["winner_team"]==first["homeTeam"])
                # Market baseline: (observed YES ask + observed YES bid)/2.
                # YES bid = 1 - NO ask on same exact Kalshi ticker.
                no_sides=[r for r in obs if r.get("side")=="NO" and
                    r.get("ticker")==first["ticker"] and
                    abs((stamp(r["quote_observed_utc"])-stamp(first["quote_observed_utc"])).total_seconds())<=120]
                middle=None
                if no_sides:
                    no=min(no_sides,key=lambda r:abs((stamp(r["quote_observed_utc"])-stamp(first["quote_observed_utc"])).total_seconds()))
                    middle=(first["book_vwap_ask"]+1-no["book_vwap_ask"])/2
                    if middle<=0 or middle>=1:middle=None
                primary.append({
                    "game_id":gid,"game_date_et":stamp(first["kickoffUTC"]).astimezone(ET).date().isoformat(),
                    "home_team":first["homeTeam"],"away_team":first["awayTeam"],
                    "kickoff_utc":first["kickoffUTC"],"home_won":home_win,
                    "home_model_probability":first["model_probability"],
                    "home_market_bid_ask_midpoint":round(middle,6) if middle is not None else None,
                    "model_observed_at_utc":first["model_captured_utc"],
                    "price_observed_at_utc":first["quote_observed_utc"],
                    "verified_outcome":True,"research_only":True})
        # Select only on earliest as-of snapshot, with no hindsight:
        # pick the candidate with the largest ex-ante fee+uncertainty-adjusted
        # estimated edge, but only if >=5pp; one side total per distinct game.
        earliest=stamp(obs[0]["quote_observed_utc"])
        first_batch=[r for r in obs if
            (stamp(r["quote_observed_utc"])-earliest).total_seconds()<=120]
        qualified=[]
        for r in first_batch:
            fee=number(r.get("taker_fee_estimate_dollars"))
            size=number(r.get("sample_contracts"))
            if fee is None or fee<0 or size is None or abs(size-1)>1e-9:continue
            edge=100*(r["model_probability"]-r["book_vwap_ask"]-fee/size)-RESERVE_PP
            if edge>=EDGE_PP:
                qualified.append((edge,r))
        if not qualified:continue
        qualified.sort(key=lambda item:(-item[0],item[1]["ticker"],item[1]["side"]))
        edge,entry=qualified[0]
        all_precommitted.append({"game_id":gid,"ticker":entry["ticker"],
            "side":entry["side"],"asof_utc":entry["quote_observed_utc"],
            "research_score_pp":round(edge,3),"official_eligible":False})
        ev=verified.get(entry["ticker"])
        if not ev or ev.get("cfbd_game_id")!=gid:
            pending_candidates.append(gid)
            continue
        result=ev["market_result"]
        hit=int(entry["side"]==result)
        fee=number(entry["taker_fee_estimate_dollars"])
        pnl=hit-(entry["book_vwap_ask"]+fee)
        later=[r for r in obs if r["ticker"]==entry["ticker"] and r["side"]==entry["side"]
               and (stamp(r["quote_observed_utc"])-stamp(entry["quote_observed_utc"])).total_seconds()>=300
               and 0<=(stamp(entry["kickoffUTC"])-stamp(r["quote_observed_utc"])).total_seconds()<=5400]
        close=max(later,key=lambda r:r["quote_observed_utc"]) if later else None
        close_move=round(100*(close["book_vwap_ask"]-entry["book_vwap_ask"]),4) if close else None
        matched.append({
            "game_id":gid,"ticker":entry["ticker"],"side":entry["side"],
            "selected_at_utc":entry["quote_observed_utc"],
            "score_at_selection_pp":round(edge,3),
            "model_probability":entry["model_probability"],
            "observed_one_contract_vwap_ask":entry["book_vwap_ask"],
            "estimated_taker_fee_dollars":fee,
            "settlement_outcome":result,"correct":bool(hit),
            "hypothetical_one_contract_net_dollars":round(pnl,5),
            "later_pregame_proxy_at_utc":close["quote_observed_utc"] if close else None,
            "later_pregame_proxy_movement_pp":close_move,
            "not_guaranteed_execution":True,"official_eligible":False})
        if close:close_examples.append(close_move)
    primary.sort(key=lambda r:(r["kickoff_utc"],r["game_id"]))
    matched.sort(key=lambda r:(r["selected_at_utc"],r["game_id"]))
    b_model=brier([{"home_model_probability":r["home_model_probability"],"home_won":r["home_won"]} for r in primary],"home_model_probability")
    b_market=brier([{"home_market_bid_ask_midpoint":r["home_market_bid_ask_midpoint"],
                    "home_won":r["home_won"]} for r in primary],"home_market_bid_ask_midpoint")
    market_count=sum(r["home_market_bid_ask_midpoint"] is not None for r in primary)
    win=sum(r["correct"] for r in matched)
    total_pnl=sum(r["hypothetical_one_contract_net_dollars"] for r in matched)
    return {
        "schemaVersion":1,"sport":"NCAAF","generatedAtUTC":now.isoformat(),
        "status":"FORWARD INDEPENDENT GAME PERFORMANCE — RESEARCH ONLY",
        "research_unique_games_with_pregame_quotes":len(games),
        "research_unique_games_unverified":len(unverified),
        "independently_verified_game_probability_samples":len(primary),
        "model_home_probability_brier":b_model,
        "model_home_probability_log_loss":log_loss(primary,"home_model_probability"),
        "market_midpoint_baseline_samples":market_count,
        "market_bidask_midpoint_brier":b_market,
        "market_bidask_midpoint_log_loss":log_loss(primary,"home_market_bid_ask_midpoint"),
        "precommitted_research_candidate_games":len(all_precommitted),
        "precommitted_candidate_games_awaiting_independent_settlement":len(pending_candidates),
        "research_edge_strategy_distinct_games":len(matched),
        "research_edge_strategy_wins":win,
        "research_edge_strategy_win_rate":round(win/len(matched),4) if matched else None,
        "theoretical_one_contract_net_pnl_sum":round(total_pnl,5) if matched else None,
        "theoretical_one_contract_net_pnl_per_game":round(total_pnl/len(matched),5) if matched else None,
        "matched_independent_close_proxy_games":len(close_examples),
        "mean_later_pregame_quote_movement_pp":round(sum(close_examples)/len(close_examples),4) if close_examples else None,
        "minimum_unique_games_before_model_edge_review":MIN_GAMES,
        "review_sample_target_met":len(primary)>=MIN_GAMES and len(matched)>=MIN_GAMES,
        "hypothetical_strategy_rule":"Earliest observed batch within 120 seconds independent of eventual settlement; select max pregame net edge >=5pp after fee + 4pp model reserve; unresolved candidates remain pending and are NOT dropped from the selection denominator.",
        "games":primary,
        "research_candidate_examples":matched[:30],
        "unsettled_precommitted_examples":all_precommitted[:15],
        "official_eligible":False,"shadow_eligible":False,"production_eligible":False,
        "not_an_executed_strategy":True,
        "note":"Contract-side observations are correlated and not actual fills. One independently corroborated game is counted once. Market midpoint is an ask/bid proxy, not exchange closing price. Historical research strategies chosen after seeing data may overfit; reserve future slates for independent evaluation."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive-dir",default="research/ncaaf-forward")
    p.add_argument("--output",default="dashboard/ncaaf-v39-forward-scorecard.json")
    a=p.parse_args()
    archives={}
    folder=pathlib.Path(a.archive_dir)
    for f in folder.glob("20??-??-??.json") if folder.exists() else []:
        try:
            data=json.loads(f.read_text())
            if data.get("sport")=="NCAAF":
                archives[f.stem]=data
        except (ValueError,OSError):continue
    now=dt.datetime.now(dt.timezone.utc)
    summary=analyze(archives,now)
    dest=pathlib.Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({k:summary[k] for k in (
        "status","research_unique_games_with_pregame_quotes",
        "independently_verified_game_probability_samples",
        "market_midpoint_baseline_samples",
        "research_edge_strategy_distinct_games","review_sample_target_met",
        "official_eligible")}))
if __name__=="__main__":main()
