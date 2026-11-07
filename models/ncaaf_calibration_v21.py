#!/usr/bin/env python3
"""Chronological holdout diagnostics; independent pregame feature JSON required."""
import argparse,json,math,statistics
def cdf(z):return (1+math.erf(z/math.sqrt(2)))/2
def project(g):
 required=["home_pregame_offense_ppg","home_pregame_defense_ppg","away_pregame_offense_ppg","away_pregame_defense_ppg","home_pregame_pace","away_pregame_pace"]
 if any(k not in g for k in required):raise ValueError("missing independent pregame features")
 pace=(g["home_pregame_pace"]+g["away_pregame_pace"])/140
 if not .5<=pace<=1.5:raise ValueError("invalid pace")
 h=(g["home_pregame_offense_ppg"]+g["away_pregame_defense_ppg"])*pace/2
 a=(g["away_pregame_offense_ppg"]+g["home_pregame_defense_ppg"])*pace/2
 home=g.get("home_field_points",2)
 return max(0,h+home/2+g.get("injury_home_points",0)+g.get("weather_total_points",0)/2),max(0,a-home/2+g.get("injury_away_points",0)+g.get("weather_total_points",0)/2)
def validate(games):
 records=[]
 for g in sorted(games,key=lambda x:x["date"]):
  try:
   h,a=project(g);records.append((g,h,a,float(g["home_points"]),float(g["away_points"])))
  except (KeyError,ValueError,TypeError):pass
 if len(records)<140:return {"status":"NOT CALIBRATED","usable_games":len(records),"required":140}
 split=max(100,int(len(records)*.8));train,test=records[:split],records[split:]
 if len(test)<40:return {"status":"NOT CALIBRATED","reason":"insufficient holdout"}
 def sd(fn):return statistics.stdev([fn(r) for r in train])
 ms=sd(lambda r:(r[3]-r[4])-(r[1]-r[2]))
 ts=sd(lambda r:(r[3]+r[4])-(r[1]+r[2]))
 hs=sd(lambda r:r[3]-r[1])
 if min(ms,ts,hs)<=0:return {"status":"NOT CALIBRATED","reason":"invalid residual variance"}
 markets={"moneyline":[],"spread":[],"total":[],"team_total":[]}
 for g,h,a,actual_h,actual_a in test:
  margin=h-a;spread=math.floor(margin)+.5;total=math.floor(h+a)+.5;team=math.floor(h)+.5
  markets["moneyline"].append((cdf(margin/ms),int(actual_h>actual_a)))
  markets["spread"].append((cdf((margin-spread)/ms),int(actual_h-actual_a>spread)))
  markets["total"].append((cdf((h+a-total)/ts),int(actual_h+actual_a>total)))
  markets["team_total"].append((cdf((h-team)/hs),int(actual_h>team)))
 def score(rows):
  n=len(rows);return {"n":n,"brier":sum((p-y)**2 for p,y in rows)/n,"log_loss":-sum(y*math.log(max(1e-9,p))+(1-y)*math.log(max(1e-9,1-p)) for p,y in rows)/n,"reliability":[{"bin":i,"n":len(z),"predicted":sum(p for p,y in z)/len(z) if z else None,"observed":sum(y for p,y in z)/len(z) if z else None} for i in range(5) for z in [[(p,y) for p,y in rows if i/5<=p<(i+1)/5 or i==4 and p==1]]]}
 return {"status":"RESEARCH HOLDOUT ONLY","train":len(train),"test":len(test),"train_end":train[-1][0]["date"],"test_start":test[0][0]["date"],"margin_sd":ms,"total_sd":ts,"team_sd":hs,"diagnostics":{k:score(v) for k,v in markets.items()},"warning":"Must verify no feature leakage and test across seasons before production."}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--historical",required=True);a=p.parse_args()
 with open(a.historical) as f:print(json.dumps(validate(json.load(f)),indent=2))
