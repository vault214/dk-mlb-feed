#!/usr/bin/env python3
import unittest
from football_pregame_features_v21 import build
from ncaaf_calibration_v21 import validate
class Tests(unittest.TestCase):
 def test_no_same_day_leakage(self):
  g=[]
  for d in range(1,8):
   g.append({"id":str(d),"date":"2026-09-%02d"%d,"home_id":"1","away_id":"2","home_points":20+d,"away_points":10})
  rows=build(g,"NFL",min_games=4)
  self.assertEqual(len(rows),3)
  self.assertEqual(rows[0]["date"],"2026-09-05")
  self.assertFalse(rows[0]["production_eligible"])
 def test_calibration_gate(self):
  self.assertEqual(validate([])["status"],"NOT CALIBRATED")
if __name__=="__main__":unittest.main()
