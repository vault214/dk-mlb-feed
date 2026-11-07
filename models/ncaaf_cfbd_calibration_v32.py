#!/usr/bin/env python3
"""CFBD independent advanced-stat model, season holdout, and current game projections.

Research ONLY: 2024 training / 2025 holdout; then refit on 2024+2025 for
unseen 2026 games. Uses PPA, success rate, offensive play counts; NOT
opponent-adjusted and missing injuries, QB and weather. No market odds used
to train or tune this model. Never enables paper official/shadow selections.
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

from ncaaf_cfbd_ingest_v31 import fetch, instant, summarize_team, finite, ET, UTC, DataError

SEASONS = (2024,2025)
FEATURES = ("intercept","home_advantage","ppa_matchup","ppa_defense","success_matchup","success_defense","pace_diff")
MIN_GAMES=3
RIDGE=15.0

def solve(matrix,vector):
    """Tiny pivoting solver; avoids heavy dependencies."""
    n=len(vector)
    a=[list(map(float,row))+[float(vector[i])] for i,row in enumerate(matrix)]
    for k in range(n):
        pivot=max(range(k,n),key=lambda i:abs(a[i][k]))
        if abs(a[pivot][k])<1e-9:raise DataError("singular ridge design")
        a[k],a[pivot]=a[pivot],a[k]
        z=a[k][k]
        a[k]=[x/z for x in a[k]]
        for i in range(n):
            if i==k:continue
            q=a[i][k]
            a[i]=[x-q*y for x,y in zip(a[i],a[k])]
    return [row[-1] for row in a]

def fit(rows,target):
    n=len(FEATURES)
    xs=[x["feature_vector"] for x in rows]
    ys=[x[target] for x in rows]
    if len(xs)<150:raise DataError("insufficient training feature samples")
    gram=[[sum(x[i]*x[j] for x in xs)+(RIDGE if i==j and i!=0 else 0.0)
          for j in range(n)] for i in range(n)]
    rhs=[sum(x[i]*y for x,y in zip(xs,ys)) for i in range(n)]
    return solve(gram,rhs)

def predict(coeff,features):
    return sum(a*b for a,b in zip(coeff,features))

def norm_cdf(z):
    return 0.5*(1+math.erf(z/math.sqrt(2)))

def vector(home,away,neutral):
    return [1.0, 0.0 if neutral else 1.0,
            (home["offense_ppa_per_play"]-away["defense_ppa_allowed_per_play"]),
            (away["offense_ppa_per_play"]-home["defense_ppa_allowed_per_play"]),
            (home["offense_success_rate"]-away["defense_success_rate_allowed"]),
            (away["offense_success_rate"]-home["defense_success_rate_allowed"]),
            (home["offense_plays_per_game"]-away["offense_plays_per_game"])/20.0]

def game_rows(games,advanced,teams,year,cutoff=None,require_completed=True):
    fbs={str(t.get("school")) for t in teams if t.get("school")}
    if len(fbs)<80:raise DataError("invalid FBS school reference")
    stats=collections.defaultdict(list)
    for row in advanced:
        if isinstance(row,dict) and row.get("gameId") is not None:
            stats[str(row["gameId"])].append(row)
    parsed=[]
    for g in games:
        start=instant(g.get("startDate"))
        if start is None or not g.get("id"):continue
        if g.get("homeTeam") not in fbs or g.get("awayTeam") not in fbs:continue
        parsed.append({"id":str(g["id"]),"when":start,"date":start.astimezone(ET).date().isoformat(),
            "home":g["homeTeam"],"away":g["awayTeam"],"completed":g.get("completed") is True,
            "neutral":g.get("neutralSite") is True,"home_points":finite(g.get("homePoints")),
            "away_points":finite(g.get("awayPoints"))})
    parsed.sort(key=lambda x:(x["when"],x["id"]))
    hist=collections.defaultdict(list)
    result=[]
    i=0
    while i<len(parsed):
        today=parsed[i]["date"];batch=[]
        while i<len(parsed) and parsed[i]["date"]==today:
            batch.append(parsed[i]);i+=1
        for g in batch:
            if cutoff and g["when"]>=cutoff:continue
            if require_completed and not g["completed"]:continue
            if not require_completed and (g["completed"] or g["when"]<=cutoff):continue
            h=summarize_team(g["home"],hist[g["home"]],stats,MIN_GAMES)
            a=summarize_team(g["away"],hist[g["away"]],stats,MIN_GAMES)
            if not h or not a:continue
            if require_completed and (g["home_points"] is None or g["away_points"] is None):continue
            result.append({**g,"feature_vector":vector(h,a,g["neutral"]),
                "home_advanced":h,"away_advanced":a,"season":year,
                "feature_date_exclusive":today})
        # Only incorporate completed games from PREVIOUS dates on later iterations.
        for g in batch:
            if g["completed"] and (cutoff is None or g["when"]<cutoff) and g["home_points"] is not None and g["away_points"] is not None:
                hist[g["home"]].append(g["id"])
                hist[g["away"]].append(g["id"])
    return result

def brier(probs, ys):
    return sum((p-y)**2 for p,y in zip(probs,ys))/len(ys)

def calibrate(train,test):
    c_margin=fit(train,"observed_margin")
    c_total=fit(train,"observed_total")
    residual=[x["observed_margin"]-predict(c_margin,x["feature_vector"]) for x in train]
    residual_tot=[x["observed_total"]-predict(c_total,x["feature_vector"]) for x in train]
    margin_sd=statistics.stdev(residual)
    total_sd=statistics.stdev(residual_tot)
    if min(margin_sd,total_sd)<2:raise DataError("implausible scoring variance")
    valid=[x for x in test if x["observed_margin"]!=0]
    if len(valid)<40:raise DataError("insufficient winner holdout")
    probs=[norm_cdf(predict(c_margin,x["feature_vector"])/margin_sd) for x in valid]
    outcomes=[int(x["observed_margin"]>0) for x in valid]
    baseline=sum(int(x["observed_margin"]>0) for x in train if x["observed_margin"]!=0)/sum(int(x["observed_margin"]!=0) for x in train)
    bins=[]
    for i in range(5):
        sub=[(p,y) for p,y in zip(probs,outcomes) if i/5<=p<(i+1)/5 or (i==4 and p==1)]
        if sub:bins.append({"bin":f"{20*i}-{20*(i+1)}","n":len(sub),
            "predicted":round(sum(p for p,y in sub)/len(sub),4),
            "actual":round(sum(y for p,y in sub)/len(sub),4)})
    return {"training_games":len(train),"holdout_games":len(test),
        "winner_holdout_games":len(valid),"training_season":2024,"holdout_season":2025,
        "train_last_date":max(x["date"] for x in train),
        "holdout_first_date":min(x["date"] for x in test),
        "moneyline_brier":round(brier(probs,outcomes),6),
        "home_base_brier":round(brier([baseline]*len(valid),outcomes),6),
        "moneyline_log_loss":round(-sum(y*math.log(max(1e-9,p))+
            (1-y)*math.log(max(1e-9,1-p)) for p,y in zip(probs,outcomes))/len(valid),6),
        "calibration_bins":bins,"training_margin_sd":round(margin_sd,4),
        "training_total_sd":round(total_sd,4),
        "research_only":True,
        "notes":["Independent advanced metrics, no Kalshi price inputs",
                 "No historical executable quote / contract settlement validation",
                 "2024 training and 2025 out-of-season holdout",
                 "Statistics are NOT opponent adjusted; QB injuries/weather unavailable",
                 "Validation limited to moneyline; spread/total not assessed versus market lines"]}

def make_data(token,years):
    out={}
    for year in years:
        games=fetch("/games",{"year":year,"classification":"fbs"},token)
        advanced=fetch("/stats/game/advanced",{"year":year},token)
        teams=fetch("/teams/fbs",{"year":year},token)
        out[year]={"games":games,"stats":advanced,"teams":teams}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--projections",required=True)
    args=p.parse_args()
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:raise DataError("missing CFBD_API_KEY secret")
    datasets=make_data(token,(2024,2025,dt.datetime.now(ET).year))
    samples={}
    for year in (2024,2025):
        d=datasets[year]
        rows=game_rows(d["games"],d["stats"],d["teams"],year)
        samples[year]=[{**r,
            "observed_margin":r["home_points"]-r["away_points"],
            "observed_total":r["home_points"]+r["away_points"]} for r in rows]
    train=samples[2024];test=samples[2025]
    results=calibrate(train,test)
    if results["train_last_date"]>=results["holdout_first_date"]:
        raise DataError("training/holdout chronology failure")
    all_rows=train+test
    margin_coeff=fit(all_rows,"observed_margin")
    total_coeff=fit(all_rows,"observed_total")
    margin_sd=statistics.stdev(x["observed_margin"]-predict(margin_coeff,x["feature_vector"]) for x in all_rows)
    total_sd=statistics.stdev(x["observed_total"]-predict(total_coeff,x["feature_vector"]) for x in all_rows)
    current_year=dt.datetime.now(ET).year
    d=datasets[current_year]
    now=dt.datetime.now(UTC)
    upcoming=game_rows(d["games"],d["stats"],d["teams"],current_year,cutoff=now,require_completed=False)
    upcoming=[g for g in upcoming if g["when"]<=now+dt.timedelta(days=7)]
    projections=[]
    for g in upcoming:
        mar=predict(margin_coeff,g["feature_vector"])
        tot=predict(total_coeff,g["feature_vector"])
        projections.append({"cfbd_game_id":g["id"],"date_et":g["date"],"home_team":g["home"],
           "away_team":g["away"],"kickoff_utc":g["when"].isoformat(),
           "projected_home_points":round(max(0,(tot+mar)/2),2),
           "projected_away_points":round(max(0,(tot-mar)/2),2),
           "projected_margin_home":round(mar,3),"projected_total":round(tot,3),
           "margin_sd_research":round(margin_sd,3),"total_sd_research":round(total_sd,3),
           "prob_home_win_research":round(norm_cdf(mar/margin_sd),5),
           "home_game_count":g["home_advanced"]["games"],
           "away_game_count":g["away_advanced"]["games"],
           "asof_utc":now.isoformat(),
           "fbs_verified":True,"injuries_verified":False,
           "qb_verified":False,"weather_verified":False,
           "research_only":True,"production_eligible":False})
    output={"model":"NCAAF CFBD adjusted-stat prototype v3.2 (NOT opponent adjusted)",
      "generated_utc":now.isoformat(),
      "historical_backtest":results,
      "refit": {"train_seasons":[2024,2025],"margin_features":FEATURES,
          "margin_coefficients":margin_coeff,"total_coefficients":total_coeff,
          "margin_sd":margin_sd,"total_sd":total_sd},
      "current_projection_count":len(projections),
      "production_eligible":False,
      "official_eligible":False,
      "data_gaps":["QB and injury status","venue-level weather",
       "opponent-adjusted rating verification","per-contract quote timestamp",
       "Kalshi market/game identity validation","forward paper calibration"]}
    pathlib.Path(args.output).write_text(json.dumps(output,indent=2)+"\n")
    pathlib.Path(args.projections).write_text(json.dumps({"model":"NCAAF v3.2 research",
      "asof_utc":now.isoformat(),"projections":projections,
      "production_eligible":False},indent=2)+"\n")
    print(json.dumps({"status":"RESEARCH ONLY","train":len(train),"holdout":len(test),
      "moneyline_brier":results["moneyline_brier"],
      "baseline_brier":results["home_base_brier"],
      "current_projections":len(projections),"production_eligible":False}))
if __name__=="__main__":
    try:main()
    except DataError as e:
        print("NCAAF research validation failed: "+str(e),file=sys.stderr)
        sys.exit(1)
