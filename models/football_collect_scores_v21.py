#!/usr/bin/env python3
"""Collect historical ESPN football scores, NFL or FBS college.
Unofficial ESPN endpoints; validate completeness before model use.
"""
import argparse,datetime as dt,json,time,urllib.parse,urllib.request
def collect(league,start,end):
 d=dt.date.fromisoformat(start);last=dt.date.fromisoformat(end);out={};failures=[]
 while d<=last:
  params={"dates":d.strftime("%Y%m%d"),"limit":"500"}
  if league=="NCAAF":params["groups"]="80"
  slug="college-football" if league=="NCAAF" else "nfl"
  url="https://site.api.espn.com/apis/site/v2/sports/football/"+slug+"/scoreboard?"+urllib.parse.urlencode(params)
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"FootballResearch/2.1"}),timeout=25) as f:data=json.load(f)
  except Exception as exc:failures.append({"date":d.isoformat(),"error":str(exc)});d+=dt.timedelta(days=1);continue
  for e in data.get("events",[]):
   c=e.get("competitions",[{}])[0];teams=c.get("competitors",[])
   if not c.get("status",{}).get("type",{}).get("completed") or len(teams)!=2:continue
   h=next((x for x in teams if x.get("homeAway")=="home"),None)
   a=next((x for x in teams if x.get("homeAway")=="away"),None)
   if not h or not a:continue
   try:hp=int(h["score"]);ap=int(a["score"])
   except (KeyError,ValueError,TypeError):continue
   out[str(e["id"])]={"id":str(e["id"]),"date":d.isoformat(),
    "home_team":h["team"]["displayName"],"away_team":a["team"]["displayName"],
    "home_points":hp,"away_points":ap,"home_id":str(h["team"]["id"]),
    "away_id":str(a["team"]["id"]),"source":url}
  d+=dt.timedelta(days=1)
 return list(out.values()),failures
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--league",choices=["NCAAF","NFL"],required=True)
 p.add_argument("--start",required=True);p.add_argument("--end",required=True);p.add_argument("--output",required=True);a=p.parse_args()
 games,failures=collect(a.league,a.start,a.end)
 with open(a.output,"w") as f:json.dump(games,f,indent=2)
 print(json.dumps({"games":len(games),"failed_dates":failures,"status":"INCOMPLETE" if failures else "SCORES COLLECTED","note":"No independent pregame efficiency, injury, weather, or calibrated probabilities yet"}))
