#!/usr/bin/env python3
"""Prospective-valid historical weather archive for NCAA football, research-only.

Uses Open-Meteo Previous Runs API _previous_day1 (~24h lead-time fixed forecasts),
NOT hindsight reanalysis/current-condition data. Weather is never added to any
NCAAF predicted probability until adequate season-separated calibration succeeds.
Acquires a bounded new batch on each scheduled run to respect service limits.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from ncaaf_cfbd_ingest_v31 import fetch,instant,finite,DataError,UTC

BASE="https://previous-runs-api.open-meteo.com/v1/forecast"
VARS=("wind_speed_10m_previous_day1",
      "precipitation_previous_day1",
      "temperature_2m_previous_day1")

def parse_hourly(payload,kickoff):
    h=payload.get("hourly") if isinstance(payload,dict) else None
    if not isinstance(h,dict) or not isinstance(h.get("time"),list):
        return None,"WEATHER FORECAST HOURS MISSING"
    arr=[]
    for i,raw in enumerate(h["time"]):
        ts=instant(raw+"Z" if isinstance(raw,str) and "Z" not in raw and "+" not in raw else raw)
        if ts is not None:
            arr.append((abs((ts-kickoff).total_seconds()),i,ts))
    if not arr:return None,"UNPARSABLE WEATHER VALID TIMES"
    diff,i,ts=min(arr)
    if diff>3600:return None,"KICKOFF FORECAST HOUR NOT FOUND"
    values={}
    for v in VARS:
        seq=h.get(v)
        if not isinstance(seq,list) or i>=len(seq):
            return None,"FORECAST VARIABLE MISSING: "+v
        n=finite(seq[i])
        if n is None:return None,"FORECAST VALUE UNAVAILABLE: "+v
        values[v.replace("_previous_day1","")]=round(n,3)
    return {"forecast_valid_hour_utc":ts.isoformat(),
            "forecast_lead_hours":24,
            "forecast_origin":"Open-Meteo Previous Runs fixed 24h lead, not a hindsight reanalysis",
            **values},None

def fetch_weather(latitude,longitude,kickoff):
    when=kickoff.date().isoformat()
    params={"latitude":round(latitude,5),"longitude":round(longitude,5),
        "start_date":when,"end_date":when,
        "hourly":",".join(VARS),"timezone":"UTC",
        "wind_speed_unit":"mph","temperature_unit":"fahrenheit"}
    req=urllib.request.Request(BASE+"?"+urllib.parse.urlencode(params),
        headers={"User-Agent":"NCAAFWeatherPrekickoffResearch/3.4"})
    try:
        with urllib.request.urlopen(req,timeout=25) as f:
            response=json.load(f)
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        return None,"PREVIOUS RUNS API ERROR"
    return parse_hourly(response,kickoff)

def fixtures_by_season(datasets,venues):
    site={str(v.get("id")):v for v in venues if v.get("id") is not None}
    out=[]
    for year,games in datasets.items():
        for g in games:
            if not isinstance(g,dict) or g.get("completed") is not True:
                continue
            kickoff=instant(g.get("startDate"))
            if kickoff is None or g.get("id") is None or kickoff.year!=year:
                continue
            venue=site.get(str(g.get("venueId")))
            if not venue or venue.get("dome") is not False:
                continue
            lat,lon=finite(venue.get("latitude")),finite(venue.get("longitude"))
            hp,ap=finite(g.get("homePoints")),finite(g.get("awayPoints"))
            if None in (lat,lon,hp,ap) or hp==ap:
                continue
            out.append({
                "cfbd_game_id":str(g["id"]),"year":year,
                "kickoff_utc":kickoff.isoformat(),
                "home_team":g.get("homeTeam"),"away_team":g.get("awayTeam"),
                "home_points":int(hp),"away_points":int(ap),
                "venue_id":g.get("venueId"),"stadium":venue.get("name"),
                "latitude":lat,"longitude":lon})
    return sorted(out,key=lambda r:(r["year"],r["kickoff_utc"],r["cfbd_game_id"]))

def collect(candidates,previous,now,fetch_fn=fetch_weather,max_new=12):
    if max_new<1 or max_new>50:raise ValueError("batch limit out of bounds")
    rows={str(r["cfbd_game_id"]):r for r in previous if r.get("cfbd_game_id")}
    # deterministically rotate selected seasons, do not sample on outcome.
    buckets=collections.defaultdict(list)
    for g in candidates:
        if g["cfbd_game_id"] not in rows:
            buckets[g["year"]].append(g)
    seasons=sorted(buckets)
    selection=[]
    while len(selection)<max_new and any(buckets.values()):
        for year in seasons:
            if buckets[year] and len(selection)<max_new:
                selection.append(buckets[year].pop(0))
    checks=collections.Counter()
    for g in selection:
        kickoff=instant(g["kickoff_utc"])
        fc,err=fetch_fn(g["latitude"],g["longitude"],kickoff)
        if fc is None:
            checks[err or "UNAVAILABLE"]+=1
            # Do not record permanent failed samples; retry on later run.
            continue
        if fc.get("forecast_lead_hours") != 24:
            checks["NOT PRE-EVENT FORECAST"]+=1;continue
        row={k:v for k,v in g.items() if k not in ("latitude","longitude")}
        row.update({"weather":fc,
            "weather_source":"Open-Meteo Previous Runs fixed 24h forecast",
            "weather_training_valid":True,
            "model_probability_adjusted":False,
            "production_eligible":False})
        rows[g["cfbd_game_id"]]=row
        checks["FORECAST ARCHIVED"]+=1
        time.sleep(.08)
    dataset={"schemaVersion":1,"sport":"NCAAF",
      "source":"CFBD /games + /venues; Open-Meteo Previous Runs fixed prior-day forecast",
      "updatedUTC":now.isoformat(),
      "records":sorted(rows.values(),key=lambda v:(v["year"],v["kickoff_utc"],v["cfbd_game_id"])),
      "production_eligible":False}
    health={"schemaVersion":1,"sport":"NCAAF","generatedAtUTC":now.isoformat(),
      "status":"24-HOUR-AHEAD WEATHER HISTORY RESEARCH ONLY",
      "outdoor_completed_fbs_fixture_candidates":len(candidates),
      "archived_pregame_forecast_games":len(dataset["records"]),
      "new_forecasts_archived":checks["FORECAST ARCHIVED"],
      "new_attempts":len(selection),
      "errors":{k:v for k,v in checks.items() if k!="FORECAST ARCHIVED"},
      "weather_win_probability_adjustment":"NOT CALIBRATED — no automatic probability change",
      "before_kickoff_forecast_provenance":"fixed 24h lead, not retrospective realized conditions",
      "seasons_with_archive":sorted(set(r["year"] for r in dataset["records"])),
      "production_eligible":False,"official_eligible":False}
    return dataset,health

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",default="research/ncaaf-weather/prior-day.json")
    p.add_argument("--health",default="dashboard/ncaaf-v34-weather-history-health.json")
    p.add_argument("--batch",type=int,default=12)
    a=p.parse_args()
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:raise DataError("CFBD_API_KEY unavailable")
    years=(2024,2025,2026)
    datasets={y:fetch("/games",{"year":y,"classification":"fbs"},token) for y in years}
    venues=fetch("/venues",{},token)
    fixtures=fixtures_by_season(datasets,venues)
    archive=pathlib.Path(a.archive);archive.parent.mkdir(parents=True,exist_ok=True)
    old=json.loads(archive.read_text()).get("records",[]) if archive.exists() else []
    now=dt.datetime.now(UTC)
    data,health=collect(fixtures,old,now,max_new=a.batch)
    archive.write_text(json.dumps(data,indent=2)+"\n")
    out=pathlib.Path(a.health);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(health,indent=2)+"\n")
    print(json.dumps({k:health[k] for k in (
      "status","outdoor_completed_fbs_fixture_candidates","archived_pregame_forecast_games",
      "new_forecasts_archived","new_attempts","production_eligible")}))
if __name__=="__main__":
    try:main()
    except DataError as e:
        print("NCAAF weather archive failed: "+str(e))
        raise SystemExit(1)
