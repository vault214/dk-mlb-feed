#!/usr/bin/env python3
"""Offline regression tests: no network access or gambling picks."""
import json
import tempfile
import unittest
from pathlib import Path
from multisport_collect_v30 import CONFIG, parse_final, scoreboard_url
from multisport_features_v30 import make_features, REQUIRED_EXTERNAL
from multisport_backtest_v30 import report, TRAIN_END
from multisport_health_v30 import health, LEAGUES

def game(day, suffix, hs, as_, league="NBA"):
 return {"id":str(suffix),"league":league,"date":day,
  "home_id":"A","away_id":"B","home_team":"Home","away_team":"Away",
  "home_points":hs,"away_points":as_,"start_utc":day+"T23:00:00+00:00",
  "neutral_site":False}

class MultiSportTests(unittest.TestCase):
 def test_all_seven_leagues_configured(self):
  self.assertEqual(set(CONFIG),set(REQUIRED_EXTERNAL))
  self.assertEqual(set(TRAIN_END),set(REQUIRED_EXTERNAL))
  self.assertEqual(set(LEAGUES),set(REQUIRED_EXTERNAL))
  self.assertIn("groups=50",scoreboard_url("NCAAB",__import__("datetime").date(2025,11,7)))
 def test_scoreboard_final_parsing(self):
  e={"id":"17","date":"2025-06-01T22:00:00Z","season":{"type":2},
   "competitions":[{"status":{"type":{"completed":True}},"competitors":[
    {"homeAway":"home","score":"13","team":{"id":"1","displayName":"A"}},
    {"homeAway":"away","score":"7","team":{"id":"2","displayName":"B"}}]}]}
  x=parse_final(e,"test","NFL")
  self.assertEqual(x["home_points"],13)
  self.assertEqual(x["date"],"2025-06-01")
  e["season"]["type"]=1
  self.assertIsNone(parse_final(e,"test","NFL"))
 def test_no_same_day_data_leakage(self):
  games=[game("2025-06-01",1,80,75),game("2025-06-02",2,91,82),
         game("2025-06-03",3,76,87),game("2025-07-02",4,78,74)]
  two=[game("2025-07-03",5,200,20),game("2025-07-03",6,21,20)]
  result=make_features({"league":"NBA","games":games+two},min_prior=1)
  pair=[x for x in result["features"] if x["date"]=="2025-07-03"]
  self.assertEqual(len(pair),2)
  self.assertEqual(pair[0]["projected_home_points"],pair[1]["projected_home_points"])
  self.assertTrue(all(not x["production_eligible"] for x in pair))
 def test_season_holdout_and_no_market_claim(self):
  games=[game("2025-06-01",1,81,79),game("2025-06-02",2,92,75),
         game("2025-06-03",3,74,80),game("2025-07-02",4,65,62),
         game("2025-07-03",5,78,84)]
  f=make_features({"league":"NBA","games":games},min_prior=1)
  r=report(f,min_train=2,min_test=2)
  self.assertEqual(r["status"],"RESEARCH HOLDOUT ONLY")
  self.assertLess(r["last_train_date"],r["first_test_date"])
  self.assertFalse(r["production_eligible"])
  self.assertEqual(r["non_winner_markets"][:10],"NOT TESTED")
 def test_bad_asof_gate(self):
  f=make_features({"league":"NFL","games":[game("2025-06-01",1,5,1,"NFL"),
     game("2025-06-02",2,10,8,"NFL")]},min_prior=1)
  f["features"][0]["feature_cutoff_exclusive"]="2027-01-01"
  with self.assertRaises(ValueError):
   report(f)
 def test_health_is_sanitized_and_never_eligible(self):
  with tempfile.TemporaryDirectory() as p:
   root=Path(p);(root/"reports").mkdir();(root/"boards").mkdir()
   (root/"reports"/"NHL.json").write_text(json.dumps({"league":"NHL",
      "status":"RESEARCH HOLDOUT ONLY","winner_brier":0.24}))
   value=health(root/"reports",root/"boards")
   self.assertEqual(len(value["leagues"]),7)
   self.assertTrue(all(not x["official_eligible"] for x in value["leagues"]))
   self.assertEqual(value["leagues"][3]["research_status"],"RESEARCH HOLDOUT ONLY")
if __name__=="__main__":
 unittest.main()
