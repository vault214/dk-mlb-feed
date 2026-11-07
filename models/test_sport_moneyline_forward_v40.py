#!/usr/bin/env python3
"""Safety regression tests for four-sport forward moneyline observation."""
import datetime as dt
import copy
import unittest
from sport_moneyline_forward_v40 import (
   clean_name,scoreboard_events,matched_games,scan,capture_one,merge,UTC)

NOW=dt.datetime(2026,11,7,17,0,tzinfo=UTC)
KICK="2026-11-07T20:30:00+00:00"
def event():
  return {"id":"401","date":KICK,
    "competitions":[{"status":{"type":{"completed":False}},
    "competitors":[{"homeAway":"home","team":{"id":"h","location":"Phoenix","abbreviation":"PHX","displayName":"Phoenix Suns","shortDisplayName":"Suns"}},
                   {"homeAway":"away","team":{"id":"a","location":"Houston","abbreviation":"HOU","displayName":"Houston Rockets","shortDisplayName":"Rockets"}}]}]}
def board():
  return {"sport_key":"nba","board_date_et":"2026-11-07","markets":[
     {"event_ticker":"KXNBAGAME-26NOV07HOUPHX","ticker":"KXNBAGAME-26NOV07HOUPHX-PHX","event_date":"2026-11-07","market_category":"game","yes_selection":"Phoenix"},
     {"event_ticker":"KXNBAGAME-26NOV07HOUPHX","ticker":"KXNBAGAME-26NOV07HOUPHX-HOU","event_date":"2026-11-07","market_category":"game","yes_selection":"Houston"}]}
def sched():return scoreboard_events("NBA",{"events":[event()]})

class LiveCaptureTests(unittest.TestCase):
 def test_exact_game_and_pair_match(self):
    x,why=matched_games(board(),sched(),NOW)
    self.assertEqual(len(x),1)
    self.assertEqual(x[0]["home_team_id"],"h")
    self.assertTrue(x[0]["team_identity_matched_both_sides"])
 def test_not_invent_opponent_from_one_ticker(self):
    b=board();b["markets"]=b["markets"][:1]
    x,why=matched_games(b,sched(),NOW)
    self.assertEqual(x,[])
    self.assertIn("MISSING EXACT TWO WINNER TICKERS",why)
 def test_wrong_market_selection_is_not_mapped(self):
    b=board();b["markets"][1]["yes_selection"]="New York"
    x,why=matched_games(b,sched(),NOW)
    self.assertEqual(len(x),0)
 def test_ambiguous_matching_two_identical_events_rejected(self):
    x,why=matched_games(board(),sched()+sched(),NOW)
    self.assertEqual(x,[])
    self.assertIn("NO UNIQUE MATCH OF BOTH TEAMS TO FUTURE ESPN GAME",why)
 def test_final_or_past_game_not_captured(self):
    past=copy.deepcopy(event());past["date"]="2026-11-07T16:00:00+00:00"
    x,_=matched_games(board(),scoreboard_events("NBA",{"events":[past]}),NOW)
    self.assertEqual(x,[])
 def test_requires_fresh_live_book_before_kickoff(self):
    match=matched_games(board(),sched(),NOW)[0]
    market=lambda ticker:{"ticker":ticker,"status":"active","series_ticker":"KXNBAGAME"}
    book=lambda ticker:{"no_dollars":[["0.60","10"]],"yes_dollars":[["0.60","10"]]}
    series=lambda ticker:{"ticker":ticker,"fee_type":"quadratic","fee_multiplier":1}
    good,err=capture_one(match,NOW,market,book,series,clock=lambda:NOW+dt.timedelta(seconds=1))
    self.assertIsNone(err)
    self.assertAlmostEqual(good["home_bidask_midpoint"],.5)
    self.assertIsNone(good["independent_model_probability"])
    self.assertFalse(good["official_eligible"])
    late,reason=capture_one(match,NOW,market,book,series,clock=lambda:dt.datetime(2026,11,7,21,tzinfo=UTC))
    self.assertIsNone(late)
    self.assertIn("not before kickoff",reason)
 def test_missing_depth_is_not_model_probability(self):
    match=matched_games(board(),sched(),NOW)[0]
    x,e=capture_one(match,NOW,lambda t:{"ticker":t,"status":"active"},
         lambda t:{"no_dollars":[["0.60","10"]],"yes_dollars":[]},
         lambda t:{"fee_type":"quadratic","fee_multiplier":1},
         clock=lambda:NOW)
    self.assertIsNone(x)
    self.assertIn("both sides lack",e)
 def test_board_date_stale_fail_closed(self):
    b=board();b["board_date_et"]="2026-11-02"
    x=scan("NBA",b,sched(),NOW,lambda r,now:(None,"should not run"))
    self.assertEqual(x["matched_events"],0)
    self.assertFalse(x["official_eligible"])
 def test_different_league_board_refused(self):
    with self.assertRaises(ValueError):scan("NBA",{**board(),"sport_key":"nfl"},sched(),NOW)
 def test_dedupe_same_observation(self):
    x={"observations":[{"espn_game_id":"401","ticker":"TEST","quote_observed_utc":KICK}]}
    d=merge(x,x["observations"])
    self.assertEqual(len(d["observations"]),1)
 def test_school_abbreviation_normalization(self):
    self.assertEqual(clean_name("Utah St."),"utah state")
    self.assertEqual(clean_name("St. Louis"),"st louis")
if __name__=="__main__":unittest.main()
