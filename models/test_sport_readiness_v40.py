#!/usr/bin/env python3
import datetime as dt
import unittest
from sport_readiness_v40 import summarize,ALL
UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,7,22,tzinfo=UTC)
M={"leagues":[{"league":"NHL","holdout_games":631,
   "winner_brier":.251,"improvement_vs_home_baseline":-.002,"missing_verified_inputs":["starting goalie"]},
  {"league":"NBA","improvement_vs_home_baseline":.021,"missing_verified_inputs":["starters"]}]}
C={"leagues":{"NFL":{"status":"BOARD DATE STALE — NO CAPTURE","new_observations":0},
  "NBA":{"status":"PROSPECTIVE INDEPENDENT GAME-WINNER PRICE SAMPLING ONLY","new_observations":6}}}
S={"leagues":{"NBA":{"observed_unique_games":6,"games_awaiting_settlement":6,"independently_settled_games":0},
               "NHL":{"observed_unique_games":8,"independently_settled_games":0}}}
A={"research_unique_games_with_pregame_quotes":13,"independently_verified_game_probability_samples":0,
   "precommitted_candidate_games_awaiting_independent_settlement":3}
class TestReadiness(unittest.TestCase):
 def test_all_seven_and_no_false_approval(self):
    r=summarize(M,C,S,A,NOW)
    self.assertEqual(set(x["sport"] for x in r["sports"]),set(ALL))
    self.assertFalse(r["official_eligible"])
    self.assertTrue(all(not x["production_eligible"] and not x["official_eligible"] for x in r["sports"]))
 def test_stale_board_not_collected(self):
    x={r["sport"]:r for r in summarize(M,C,S,A,NOW)["sports"]}
    self.assertEqual(x["NFL"]["state"],"CANDIDATE BOARD STALE")
    self.assertEqual(x["NBA"]["unique_games_with_market_snapshots"],6)
    self.assertEqual(x["NBA"]["independent_settled_game_samples"],0)
 def test_negative_baseline_explicitly_blocks(self):
    x={r["sport"]:r for r in summarize(M,C,S,A,NOW)["sports"]}
    self.assertTrue(any("NOT beaten" in b for b in x["NHL"]["blockers"]))
    self.assertEqual(x["NCAAF"]["unique_games_with_market_snapshots"],13)
 def test_offseason_never_activated(self):
    x={r["sport"]:r for r in summarize(M,C,S,A,NOW)["sports"]}
    self.assertEqual(x["MLB"]["state"],"OFFSEASON")
    self.assertEqual(x["WNBA"]["state"],"OFFSEASON")
if __name__=="__main__":unittest.main()
