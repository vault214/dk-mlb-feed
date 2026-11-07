#!/usr/bin/env python3
"""NCAAF v3.2 independent efficiency model + season-separated calibration + safe Kalshi mapping.

Production eligible: NEVER. Trains on 2024 CFBD advanced game statistics, calibrates
on 2025, tests once on 2026 results, projects only future FBS games from prior-day
statistics. Screens exact paired Kalshi moneyline contracts only as RESEARCH. No
official/shadow entries, trades, sheet writes, bank details, or assumed quotes.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import unicodedata
from zoneinfo import ZoneInfo
from ncaaf_cfbd_ingest_v31 import fetch, instant, finite, DataError

UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")
FEATURES=["ppa_net_diff","success_net_diff","offense_ppa_diff","defense_ppa_diff",
          "offense_success_diff","defense_success_diff","offensive_plays_diff",
          "elo_diff","rest_diff","home_field"]
TRAIN_YEAR=2024
CALIBRATE_YEAR=2025
TEST_YEAR=2026

def sigmoid(x):
    if x>=0:
        z=math.exp(-min(x,700));return 1/(1+z)
    z=math.exp(max(x,-700));return z/(1+z)

def summary(entries):
    recent=entries[-8:]
    if len(recent)<3:return None
    return {key:sum(x[key] for x in recent)/len(recent) for key in
            ("off_ppa","def_ppa","off_sr","def_sr","off_plays","def_plays")}

def features(h,a,elo_h,elo_a,neutral,rest_h,rest_a):
    return [
        (h["off_ppa"]-h["def_ppa"])-(a["off_ppa"]-a["def_ppa"]),
        (h["off_sr"]-h["def_sr"])-(a["off_sr"]-a["def_sr"]),
        h["off_ppa"]-a["off_ppa"],
        h["def_ppa"]-a["def_ppa"],
        h["off_sr"]-a["off_sr"],
        h["def_sr"]-a["def_sr"],
        h["off_plays"]-a["off_plays"],
        (elo_h-elo_a)/400.0,
        max(-14,min(14,rest_h-rest_a))/7.0,
        0 if neutral else 1,
    ]

def stats_by_game(stats):
    out=collections.defaultdict(dict)
    for entry in stats:
        gid=entry.get("gameId");team=entry.get("team")
        if gid is None or not team:continue
        offense=entry.get("offense") or {}
        defense=entry.get("defense") or {}
        raw={"off_ppa":finite(offense.get("ppa")),
             "def_ppa":finite(defense.get("ppa")),
             "off_sr":finite(offense.get("successRate")),
             "def_sr":finite(defense.get("successRate")),
             "off_plays":finite(offense.get("plays")),
             "def_plays":finite(defense.get("plays"))}
        if (all(x is not None for x in raw.values())
                and 0<=raw["off_sr"]<=1 and 0<=raw["def_sr"]<=1
                and raw["off_plays"]>0 and raw["def_plays"]>0):
            out[str(gid)][team]=raw
    return out

def build_season(year,games,stats,teams,asof):
    schools={t.get("school") for t in teams if t.get("school")}
    if len(schools)<80:raise DataError("CFBD FBS coverage too low for year "+str(year))
    adv=stats_by_game(stats)
    fixtures=[]
    for g in games:
        if not isinstance(g,dict):continue
        kickoff=instant(g.get("startDate"))
        if not kickoff or g.get("id") is None:continue
        home,away=g.get("homeTeam"),g.get("awayTeam")
        if home not in schools or away not in schools or home==away:continue
        fixtures.append({"id":str(g["id"]),"home":home,"away":away,
             "kickoff":kickoff,"date_et":kickoff.astimezone(ET).date().isoformat(),
             "completed":g.get("completed") is True,
             "start_time_tbd":g.get("startTimeTBD") is True,
             "neutral":g.get("neutralSite") is True,
             "home_points":finite(g.get("homePoints")),
             "away_points":finite(g.get("awayPoints"))})
    fixtures.sort(key=lambda x:(x["date_et"],x["kickoff"],x["id"]))
    hist=collections.defaultdict(list);last_played={}
    elo=collections.defaultdict(lambda:1500.0)
    labeled=[];upcoming=[];excluded=collections.Counter()
    i=0
    while i<len(fixtures):
        day=fixtures[i]["date_et"];batch=[]
        while i<len(fixtures) and fixtures[i]["date_et"]==day:
            batch.append(fixtures[i]);i+=1
        # Model EVERYTHING on this date before adding any completed game
        for g in batch:
            if g["start_time_tbd"]:
                excluded["kickoff not confirmed"]+=1;continue
            h=summary(hist[g["home"]]);a=summary(hist[g["away"]])
            if not h or not a:
                excluded["fewer than 3 previous advanced-stat games"]+=1
                continue
            kickoff_day=dt.date.fromisoformat(day)
            rh=(kickoff_day-last_played[g["home"]]).days-1
            ra=(kickoff_day-last_played[g["away"]]).days-1
            row={"cfbd_game_id":g["id"],"year":year,"date_et":day,
                 "home_team":g["home"],"away_team":g["away"],
                 "kickoff_utc":g["kickoff"].isoformat(),"neutral_site":g["neutral"],
                 "home_prior_advanced_games":len(hist[g["home"]]),
                 "away_prior_advanced_games":len(hist[g["away"]]),
                 "features":features(h,a,elo[g["home"]],elo[g["away"]],g["neutral"],rh,ra),
                 "feature_cutoff_exclusive_et":day,
                 "advanced_source":"CFBD game advanced statistics from prior ET dates only",
                 "qb_verified":False,"injuries_verified":False,
                 "weather_verified":False,"quote_freshness_verified":False,
                 "production_eligible":False}
            if (g["completed"] and g["kickoff"]<=asof
                    and g["home_points"] is not None and g["away_points"] is not None):
                if g["home_points"]!=g["away_points"]:
                    row["winner_home"]=int(g["home_points"]>g["away_points"])
                    labeled.append(row)
            elif not g["completed"] and g["kickoff"]>asof and year==asof.astimezone(ET).year:
                upcoming.append(row)
        # Completed games from earlier days only affect future dates; Elo never uses quotes.
        for g in batch:
            if not g["completed"] or g["kickoff"]>asof:
                continue
            if g["home_points"] is None or g["away_points"] is None:continue
            hteam,ateam=g["home"],g["away"]
            for team in (hteam,ateam):last_played[team]=dt.date.fromisoformat(day)
            h_adv=adv.get(g["id"],{}).get(hteam)
            a_adv=adv.get(g["id"],{}).get(ateam)
            if h_adv:hist[hteam].append(h_adv)
            if a_adv:hist[ateam].append(a_adv)
            margin=0 if g["neutral"] else 55
            expected=sigmoid((elo[hteam]-elo[ateam]+margin)*math.log(10)/400)
            actual=1 if g["home_points"]>g["away_points"] else 0 if g["home_points"]<g["away_points"] else .5
            change=22*(actual-expected)
            elo[hteam]+=change;elo[ateam]-=change
    return {"year":year,"FBS_count":len(schools),"game_count":len(fixtures),
        "advanced_game_count":len(adv),"labeled":labeled,"upcoming":upcoming,
        "excluded":dict(excluded)}

def fit_scaler(train):
    result=[]
    for j in range(len(FEATURES)):
        vals=[r["features"][j] for r in train]
        m=sum(vals)/len(vals)
        std=math.sqrt(sum((v-m)**2 for v in vals)/len(vals))
        result.append((m,max(std,1e-6)))
    return result

def vector(row,scaler):
    return [1.0]+[(x-m)/s for x,(m,s) in zip(row["features"],scaler)]

def fit_logistic(rows,scaler,iterations=1500,learning=.10,ridge=.025):
    coeff=[0.0]*(len(FEATURES)+1)
    vectors=[vector(row,scaler) for row in rows]
    n=len(rows)
    for i in range(iterations):
        gradients=[0.0]*len(coeff)
        for v,row in zip(vectors,rows):
            p=sigmoid(sum(a*b for a,b in zip(coeff,v)))
            e=p-row["winner_home"]
            for k,x in enumerate(v):gradients[k]+=e*x
        lr=learning/(1+i/800)
        for k in range(len(coeff)):
            gradients[k]/=n
            if k:gradients[k]+=ridge*coeff[k]
            coeff[k]-=lr*gradients[k]
    return coeff

def raw_logit(row,scaler,coeff):
    return sum(a*b for a,b in zip(vector(row,scaler),coeff))

def fit_platt(calib,scaler,coeff,iterations=1200):
    # Fit only on 2025 labels, NEVER use 2026 holdout outcomes.
    a,b=1.0,0.0
    xs=[raw_logit(r,scaler,coeff) for r in calib]
    n=len(calib)
    for i in range(iterations):
        ga,gb=0.0,0.0
        for x,row in zip(xs,calib):
            e=sigmoid(a*x+b)-row["winner_home"]
            ga+=e*x;gb+=e
        lr=.06/(1+i/600)
        a-=lr*(ga/n+.002*(a-1))
        b-=lr*(gb/n+.002*b)
        a=max(0.0,min(4.0,a))
        b=max(-3.0,min(3.0,b))
    return [a,b]

def probability(row,scaler,coeff,platt):
    return sigmoid(platt[0]*raw_logit(row,scaler,coeff)+platt[1])

def score(rows,scaler,coeff,platt,prior):
    samples=[(probability(r,scaler,coeff,platt),r["winner_home"]) for r in rows]
    n=len(samples)
    if not n:return None
    brier=sum((p-y)**2 for p,y in samples)/n
    homeprior=sum((prior-y)**2 for p,y in samples)/n
    logloss=-sum(y*math.log(max(1e-8,p))+(1-y)*math.log(max(1e-8,1-p)) for p,y in samples)/n
    bins=[]
    for j in range(10):
        selection=[(p,y) for p,y in samples if j/10<=p<(j+1)/10 or (j==9 and p==1)]
        if selection:
            bins.append({"range":"%02d-%02d"%(j*10,(j+1)*10),
                "n":len(selection),
                "mean_prediction":round(sum(p for p,y in selection)/len(selection),4),
                "observed_win_rate":round(sum(y for p,y in selection)/len(selection),4)})
    ece=sum(x["n"]*abs(x["mean_prediction"]-x["observed_win_rate"]) for x in bins)/n
    return {"n":n,"brier":round(brier,6),"home_win_prior_brier":round(homeprior,6),
        "improvement_vs_home_prior":round(homeprior-brier,6),
        "log_loss":round(logloss,6),"ece_10_bins":round(ece,6),"reliability":bins}

def train_and_evaluate(seasons):
    tr=seasons[TRAIN_YEAR]["labeled"];ca=seasons[CALIBRATE_YEAR]["labeled"]
    te=seasons[TEST_YEAR]["labeled"]
    if len(tr)<150 or len(ca)<150 or len(te)<100:
        raise DataError("Insufficient season-separated game samples for calibrated research")
    if not (max(x["year"] for x in tr)<min(x["year"] for x in ca)
            and max(x["year"] for x in ca)<min(x["year"] for x in te)):
        raise DataError("Season split overlap")
    scaler=fit_scaler(tr)
    coeff=fit_logistic(tr,scaler)
    platt=fit_platt(ca,scaler,coeff)
    prior=sum(x["winner_home"] for x in tr)/len(tr)
    result={"status":"SEASON-SEPARATED RESEARCH HOLDOUT","train_year":TRAIN_YEAR,
            "calibration_year":CALIBRATE_YEAR,"blind_test_year":TEST_YEAR,
            "feature_names":FEATURES,
            "training_games":len(tr),"calibration_games":len(ca),
            "holdout_games":len(te),
            "training":score(tr,scaler,coeff,platt,prior),
            "calibration":score(ca,scaler,coeff,platt,prior),
            "holdout":score(te,scaler,coeff,platt,prior),
            "calibration_method":"Platt scaling on distinct 2025 games; 2026 outcomes never fitted",
            "feature_method":"3+ previous same-season games of CFBD PPA, success, plays; Elo/venue/rest",
            "limitations":["PPA/success baseline is not opponent-adjusted efficiency",
                "2026 blind test outcomes must remain unseen during parameter selection",
                "no verified QB/injuries/weather","no pregame historical Kalshi ask archive",
                "one blind season not proof of profitability"],
            "model_training_data_source":"CollegeFootballData; not Kalshi",
            "production_eligible":False,"official_eligible":False}
    return result,scaler,coeff,platt

def norm(s):
    s=unicodedata.normalize("NFKD",str(s).lower())
    s="".join(c for c in s if not unicodedata.combining(c))
    s=s.replace("&"," and ")
    s=s.replace("st.","state").replace(" st "," state ")
    s=re.sub(r"[^a-z0-9]+"," ",s).strip()
    return re.sub(r"\s+"," ",s)

SPECIAL={
    "oklahoma st":"Oklahoma State","kansas st":"Kansas State",
    "ohio st":"Ohio State","iowa st":"Iowa State",
    "boise st":"Boise State","fresno st":"Fresno State",
    "washington st":"Washington State","florida st":"Florida State",
    "mississippi st":"Mississippi State","arkansas st":"Arkansas State",
    "michigan st":"Michigan State","app st":"Appalachian State",
    "miami fl":"Miami","ole miss":"Ole Miss",
    "uconn":"UConn","unc":"North Carolina","u of a":"Arizona",
    "southern miss":"Southern Mississippi",
    "colorado st":"Colorado State","utah st":"Utah State",
    "san jose st":"San José State",
}

def alias_index(teams):
    mapping=collections.defaultdict(set)
    for t in teams:
        school=t.get("school")
        if not school:continue
        for candidate in (school,t.get("abbreviation"),t.get("altName1"),
                          t.get("altName2"),t.get("altName3")):
            if candidate:mapping[norm(candidate)].add(school)
    for short,canonical in SPECIAL.items():
        if canonical in {t.get("school") for t in teams}:
            mapping[norm(short)].add(canonical)
    return mapping

def match_markets(board,teams,upcoming,asof,scaler,coeff,platt,cost_pp=1.5,uncertainty_pp=4.0):
    today=asof.astimezone(ET).date().isoformat()
    if board.get("board_date_et")!=today:
        return {"status":"BOARD DATE STALE","board_date":board.get("board_date_et"),
                "date_et":today,"matched_events":0,"research_comparisons":[],
                "official":None,"shadow":[],"production_eligible":False}
    aliases=alias_index(teams)
    bymatch=collections.defaultdict(list)
    for g in upcoming:
        if g["date_et"]==today:
            bymatch[(frozenset([g["home_team"],g["away_team"]]),today)].append(g)
    grouped=collections.defaultdict(list)
    for m in board.get("markets",[]):
        if (m.get("market_category")=="game" and m.get("event_date")==today
            and m.get("status")=="active" and isinstance(m.get("event_ticker"),str)):
            grouped[m["event_ticker"]].append(m)
    comparisons=[];exclusions=collections.Counter()
    matched=0
    for event, markets in grouped.items():
        labels={str(m.get("yes_selection","")) for m in markets if m.get("yes_selection")}
        if len(labels)!=2:
            exclusions["event lacks exactly two distinct winner labels"]+=1
            continue
        mapped=[]
        for label in labels:
            candidates=aliases.get(norm(label),set())
            if len(candidates)!=1:
                mapped=[];break
            mapped.append(next(iter(candidates)))
        if len(mapped)!=2 or mapped[0]==mapped[1]:
            exclusions["unverified or ambiguous team alias"]+=1;continue
        pair=bymatch.get((frozenset(mapped),today),[])
        if len(pair)!=1:
            exclusions["matchup not uniquely verified as pregame FBS"]+=1;continue
        g=pair[0]
        # All CFBD sourced research game probabilities are home-side, never derived from Kalshi.
        p_home=probability(g,scaler,coeff,platt)
        matched+=1
        for m in markets:
            teamset=aliases.get(norm(m.get("yes_selection")),set())
            if len(teamset)!=1:continue
            winner=next(iter(teamset))
            if winner not in (g["home_team"],g["away_team"]):continue
            p_yes=p_home if winner==g["home_team"] else 1-p_home
            for side,askkey in (("YES","yes_ask"),("NO","no_ask")):
                ask=finite(m.get(askkey))
                if ask is None or not 0<ask<1:
                    exclusions["invalid executable ask"]+=1;continue
                model=p_yes if side=="YES" else 1-p_yes
                comparisons.append({
                    "ticker":m["ticker"],"event_ticker":event,
                    "home_team":g["home_team"],"away_team":g["away_team"],
                    "cfbd_game_id":g["cfbd_game_id"],"kickoff_utc":g["kickoff_utc"],
                    "side":side,"winner_contract_label":m["yes_selection"],
                    "ask":ask,"model_probability":round(model,5),
                    "gross_research_difference_pp":round(100*(model-ask),2),
                    "net_if_assumed_costs_pp":round(100*(model-ask)-cost_pp-uncertainty_pp,2),
                    "qb_verified":False,"injuries_verified":False,"weather_verified":False,
                    "quote_timestamp_verified":False,
                    "not_an_official_or_shadow_pick":True})
    comparisons.sort(key=lambda r:r["net_if_assumed_costs_pp"],reverse=True)
    return {"status":"RESEARCH COMPARISON ONLY","date_et":today,
      "board_date_et":board.get("board_date_et"),"moneyline_events":len(grouped),
      "matched_events":matched,"compared_contract_sides":len(comparisons),
      "excluded_events":dict(exclusions),"research_comparisons":comparisons,
      "ask_capture_time":"UNVERIFIED — board has no per-contract quote capture timestamp",
      "fee_pp_assumption":cost_pp,"uncertainty_pp_assumption":uncertainty_pp,
      "note":"NOT betting recommendations. Match pair and pregame time verified, but quotes, QB, injuries, and weather unverified.",
      "official":None,"shadow":[],"production_eligible":False,"official_eligible":False}

def run(board_path,output,health_path):
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:raise DataError("CFBD_API_KEY unavailable")
    now=dt.datetime.now(UTC)
    seasons={}; teamlist=None
    for year in (TRAIN_YEAR,CALIBRATE_YEAR,TEST_YEAR):
        teams=fetch("/teams/fbs",{"year":year},token)
        games=fetch("/games",{"year":year,"classification":"fbs"},token)
        stats=fetch("/stats/game/advanced",{"year":year},token)
        seasons[year]=build_season(year,games,stats,teams,now)
        if year==TEST_YEAR:teamlist=teams
    report,scaler,coeff,platt=train_and_evaluate(seasons)
    board=json.loads(pathlib.Path(board_path).read_text())
    matched=match_markets(board,teamlist,seasons[TEST_YEAR]["upcoming"],now,scaler,coeff,platt)
    body={"schemaVersion":1,"capturedAtUTC":now.isoformat(),"sport":"NCAAF",
         "calibration":report,
         "years":{str(y):{k:v for k,v in s.items() if k not in ("labeled","upcoming")} for y,s in seasons.items()},
         "upcoming_fbs_games_with_advanced_inputs":len(seasons[TEST_YEAR]["upcoming"]),
         "market_research":matched,"status":"RESEARCH ONLY","production_eligible":False,
         "official":None,"shadow":[]}
    pathlib.Path(output).write_text(json.dumps(body,indent=2)+"\n")
    health={"schemaVersion":1,"capturedAtUTC":now.isoformat(),"sport":"NCAAF",
        "status":"RESEARCH ONLY","production_eligible":False,"official_eligible":False,
        "calibration":{"training_games":report["training_games"],
           "calibration_games":report["calibration_games"],
           "holdout_games":report["holdout_games"],
           "holdout_brier":report["holdout"]["brier"],
           "home_prior_brier":report["holdout"]["home_win_prior_brier"],
           "improvement":report["holdout"]["improvement_vs_home_prior"],
           "ece":report["holdout"]["ece_10_bins"]},
        "market_matching":{"status":matched["status"],"board_date":matched.get("board_date_et"),
            "moneyline_events":matched.get("moneyline_events",0),
            "matched_events":matched.get("matched_events",0),
            "compared_contract_sides":matched.get("compared_contract_sides",0),
            "excluded_events":matched.get("excluded_events",{})},
        "unverified_requirements":["quarterback availability","injuries","weather",
             "fresh executable ask timestamp","market fees/liquidity","independent forward validation"],
        "note":"Independent calibrated pregame winner research. NOT eligible to issue official or shadow picks."}
    dest=pathlib.Path(health_path);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(health,indent=2)+"\n")
    print(json.dumps(health))
    return body

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--board",default="kalshi/ncaafb-candidates.json")
    p.add_argument("--output",default="ncaaf-cfbd-v32-research.json")
    p.add_argument("--health",default="dashboard/ncaaf-v32-health.json")
    a=p.parse_args()
    try:run(a.board,a.output,a.health)
    except (DataError,OSError,ValueError,KeyError) as exc:
        # No tokens/URLs in error messages (DataError is sanitized by upstream fetch).
        print("NCAAF v3.2 research failed: "+str(exc)[:300],file=sys.stderr)
        sys.exit(1)

if __name__=="__main__":
    main()
