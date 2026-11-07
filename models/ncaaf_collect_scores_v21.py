#!/usr/bin/env python3
"""ESPN FBS historical score collector. Does NOT produce pregame efficiency/pace."""
import argparse,datetime as dt,json,urllib.request
def collect(start,end):
 d=dt.date.fromisoformat(start);last=dt.date.fromisoformat(end);records={}
 while d<=last:
  url="https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates="+d.strftime("%Y%m%d")+"&limit=500&groups=80"
  with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"NCAAF research v2.1"}),timeout=20) as f:data=json.load(f)
  for e in data.get("events",[]):
   c=e.get("competitions",[{}])[0];teams=c.get("competitors",[])
   if not c.get("status",{}).get("type",{}).get("completed") or len(teams)!=2:continue
   h=next((x for x in teams if x.get("homeAway")=="home"),None);a=next((x for x in teams if x.get("homeAway")=="away"),None)
   if not h or not a:continue
   try:hp=int(h["score"]);ap=int(a["score"])
   except (KeyError,ValueError,TypeError):continue
   records[e["id"]]={"date":d.isoformat(),"home_team":h["team"]["displayName"],"away_team":a["team"]["displayName"],"home_points":hp,"away_points":ap,"home_id":h["team"]["id"],"away_id":a["team"]["id"],"source":url}
  d+=dt.timedelta(days=1)
 return list(records.values())
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--start",required=True);p.add_argument("--end",required=True);p.add_argument("--output",required=True);a=p.parse_args()
 games=collect(a.start,a.end)
 with open(a.output,"w") as f:json.dump(games,f,indent=2)
 print(json.dumps({"games":len(games),"note":"Scores only; not a calibrated pregame dataset"}))
