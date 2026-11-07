#!/usr/bin/env python3
"""NCAAF kickoff weather provenance, stadium checked via CFBD /venues.

Forecasts are supplemental research context, never an automatic model adjustment.
Unverified stadium, indoor roof status, insufficient forecast coverage, or stale
kickoff timing fail closed. This file never authorizes an official/shadow pick.
"""
import argparse
import datetime as dt
import json
import math
import os
import pathlib
import urllib.parse
import urllib.request
from ncaaf_cfbd_ingest_v31 import fetch, instant, finite, DataError

UTC=dt.timezone.utc

def open_meteo(latitude,longitude,kickoff,now):
    if not(-90<=latitude<=90 and -180<=longitude<=180):
        return None,"invalid stadium coordinates"
    params={
      "latitude":round(latitude,5),"longitude":round(longitude,5),
      "hourly":"temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability,precipitation",
      "timezone":"UTC","forecast_days":7,
      "temperature_unit":"fahrenheit","wind_speed_unit":"mph"}
    url="https://api.open-meteo.com/v1/forecast?"+urllib.parse.urlencode(params)
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"NCAAFResearchWeather/3.2"})
        with urllib.request.urlopen(req,timeout=20) as response:
            payload=json.load(response)
    except (OSError,ValueError,TimeoutError):
        return None,"weather service unavailable"
    hourly=payload.get("hourly",{}) if isinstance(payload,dict) else {}
    times=hourly.get("time",[])
    closest=None
    for i,when in enumerate(times):
        t=instant(when+"Z" if isinstance(when,str) and not when.endswith("Z") else when)
        if t is None:continue
        gap=abs((t-kickoff).total_seconds())
        if gap<=3600 and (closest is None or gap<closest[0]):
            closest=(gap,i,t)
    if closest is None:
        return None,"kickoff not covered by hourly forecast"
    gap,i,t=closest
    fields={"temperature_f": "temperature_2m",
      "wind_mph":"wind_speed_10m","gust_mph":"wind_gusts_10m",
      "precipitation_probability_pct":"precipitation_probability",
      "precipitation_mm":"precipitation"}
    values={}
    for alias,k in fields.items():
        v=hourly.get(k,[])
        n=finite(v[i]) if i<len(v) else None
        if n is None:return None,"incomplete forecast weather fields"
        values[alias]=round(n,2)
    return {
      "model_source":"Open-Meteo hourly forecast",
      "forecast_retrieved_at_utc":now.isoformat(),
      "forecast_valid_hour_utc":t.isoformat(),
      "kickoff_utc":kickoff.isoformat(),
      "forecast_lead_hours":round((kickoff-now).total_seconds()/3600,2),
      **values,
      "historical_kickoff_weather_verified":False,
      "weather_effect_on_probability_calibrated":False,
    },None

def enrich(research,games,venues,now,forecast_fn=open_meteo):
    events=research["market_research"]
    ids={r["cfbd_game_id"] for r in events.get("research_comparisons",[])}
    selected={str(g.get("id")):g for g in games if str(g.get("id")) in ids}
    sites={str(v.get("id")):v for v in venues if v.get("id") is not None}
    weather={};counts={"matched_events":len(ids),"forecast_available":0,
                        "indoor_venue":0,"unverified_venue":0,"forecast_unavailable":0,
                        "game_already_started":0}
    cache={}
    for gid in sorted(ids):
        g=selected.get(gid)
        if not g:
            counts["unverified_venue"]+=1
            weather[gid]={"status":"MISSING CFBD GAME"};continue
        kickoff=instant(g.get("startDate"))
        if kickoff is None or kickoff<=now or g.get("completed") is True:
            counts["game_already_started"]+=1
            weather[gid]={"status":"NOT PREGAME"};continue
        v=sites.get(str(g.get("venueId")))
        if not v:
            counts["unverified_venue"]+=1
            weather[gid]={"status":"VENUE NOT VERIFIED"};continue
        if v.get("dome") is True:
            counts["indoor_venue"]+=1
            weather[gid]={"status":"INDOOR VENUE","stadium":v.get("name"),
                          "source":"CFBD /venues","weather_probability_adjustment":None};continue
        if v.get("dome") is not False:
            counts["unverified_venue"]+=1
            weather[gid]={"status":"ROOF STATUS UNKNOWN"};continue
        lat=finite(v.get("latitude"));lon=finite(v.get("longitude"))
        if lat is None or lon is None:
            counts["unverified_venue"]+=1
            weather[gid]={"status":"STADIUM COORDINATES UNKNOWN"};continue
        key=(str(g.get("venueId")),kickoff.replace(minute=0,second=0,microsecond=0).isoformat())
        if key not in cache:
            cache[key]=forecast_fn(lat,lon,kickoff,now)
        fcst,error=cache[key]
        if fcst is None:
            counts["forecast_unavailable"]+=1
            weather[gid]={"status":"FORECAST UNAVAILABLE","reason":error};continue
        counts["forecast_available"]+=1
        weather[gid]={"status":"WEATHER FORECAST SOURCED",
                      "stadium":v.get("name"),"stadium_source":"CFBD /venues",
                      "stadium_id":g.get("venueId"),"forecast":fcst,
                      "weather_probability_adjustment":None}
    return {"schemaVersion":1,"capturedAtUTC":now.isoformat(),
      "sport":"NCAAF","status":"WEATHER RESEARCH ONLY",
      "weather_for_cfbd_game_id":weather,"counts":counts,
      "qb_verified":False,"injuries_verified":False,
      "official_eligible":False,"production_eligible":False,
      "note":"Forecasts are sourced when venue/roof confirmed, but no untested weather adjustment is applied."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",default="ncaaf-cfbd-v32-research.json")
    p.add_argument("--output",default="ncaaf-weather-v32-research.json")
    p.add_argument("--health",default="dashboard/ncaaf-v32-weather-health.json")
    a=p.parse_args()
    token=os.environ.get("CFBD_API_KEY","").strip()
    if not token:raise DataError("Missing CFBD_API_KEY")
    now=dt.datetime.now(UTC)
    research=json.loads(pathlib.Path(a.research).read_text())
    games=fetch("/games",{"year":now.year,"classification":"fbs"},token)
    venues=fetch("/venues",{},token)
    result=enrich(research,games,venues,now)
    pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    out={k:result[k] for k in ("schemaVersion","sport","capturedAtUTC",
       "status","counts","qb_verified","injuries_verified",
       "official_eligible","production_eligible","note")}
    path=pathlib.Path(a.health);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out))

if __name__=="__main__":
    main()
