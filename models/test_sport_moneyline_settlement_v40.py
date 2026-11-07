#!/usr/bin/env python3
"""Four-league independent settled-game scores never imply model edge."""
import datetime as dt
import copy
import unittest
from sport_moneyline_settlement_v40 import reconcile_archive,score,UTC
NOW=dt.datetime(2026,11,8,16,tzinfo=UTC)
KICK="2026-11-07T20:30:00+00:00"
OBS="2026-11-07T19:30:00+00:00"
TICK="KXNBAGAME-26NOV07HOUPHX-PHX"
def archive():
 return {"sport":"NBA","schemaVersion":1,"observations":[{
   "espn_game_id":"401","ticker":TICK,
   "home_team_id":"h","away_team_id":"a",
   "home_team":"Phoenix Suns","away_team":"Houston Rockets",
   "kickoff_utc":KICK,"quote_observed_utc":OBS,
   "home_bidask_midpoint":.6,"home_yes_ask":.61,
   "independent_model_probability":None,"research_only":True,
   "official_eligible":False}],"verified_outcomes":{}}
def game(done=True,home_score="108",away_score="99"):
 return {"espn_game_id":"401","kickoff_utc":KICK,"completed":done,
         "home":{"id":"h","displayName":"Phoenix Suns"},
         "away":{"id":"a","displayName":"Houston Rockets"},
         "home_score":home_score,"away_score":away_score}
def market(val="yes",state="settled"):
 return lambda t:{"ticker":t,"result":val,"status":state}
class IndependentSettlements(unittest.TestCase):
 def test_actual_score_and_settlement_verified_once(self):
    a=archive()
    x=reconcile_archive(a,[game()],NOW,market("yes"))
    self.assertEqual(x["newly_verified_tickers"],1)
    b=score("NBA",[a],NOW)
    self.assertEqual(b["independently_settled_games"],1)
    self.assertAlmostEqual(b["market_midpoint_brier"],(.6-1)**2)
    self.assertIsNone(b["independent_model_brier"])
    self.assertIsNone(b["hypothetical_profit"])
    self.assertFalse(b["official_eligible"])
    initial=a["verified_outcomes"][TICK]["first_verified_at_utc"]
    y=reconcile_archive(a,[game()],NOW+dt.timedelta(days=1),market("yes"))
    self.assertEqual(y["newly_verified_tickers"],0)
    self.assertEqual(a["verified_outcomes"][TICK]["first_verified_at_utc"],initial)
 def test_unsettled_market_never_counts(self):
    a=archive()
    x=reconcile_archive(a,[game()],NOW,market("yes","closed"))
    self.assertEqual(x["total_verified_tickers"],0)
    self.assertEqual(score("NBA",[a],NOW)["independently_settled_games"],0)
 def test_wrong_score_rejected_and_past_verification_revoked(self):
    a=archive();reconcile_archive(a,[game()],NOW,market("yes"))
    x=reconcile_archive(a,[game(home_score="88",away_score="105")],NOW,market("yes"))
    self.assertEqual(x["total_verified_tickers"],0)
    self.assertIn("CFBD/ESPN VS KALSHI RESULT CONFLICT",x["reasons"])
 def test_ambiguous_schedule_game_id_rejected(self):
    a=archive()
    x=reconcile_archive(a,[game(),game()],NOW,market("yes"))
    self.assertEqual(x["total_verified_tickers"],0)
 def test_wrong_team_id_rejected(self):
    a=archive();g=game();g["home"]["id"]="different"
    x=reconcile_archive(a,[g],NOW,market("yes"))
    self.assertEqual(x["total_verified_tickers"],0)
 def test_score_ties_not_scored(self):
    a=archive();g=game(home_score="101",away_score="101")
    x=reconcile_archive(a,[g],NOW,market("yes"))
    self.assertEqual(x["total_verified_tickers"],0)
 def test_game_unfinished_not_verified(self):
    a=archive()
    x=reconcile_archive(a,[game(done=False)],NOW,market("yes"))
    self.assertEqual(x["total_verified_tickers"],0)
 def test_duplicate_observed_quotes_one_game_one_brier(self):
    a=archive();reconcile_archive(a,[game()],NOW,market("yes"))
    r=copy.deepcopy(a["observations"][0]);r["quote_observed_utc"]="2026-11-07T20:10:00+00:00"
    a["observations"].append(r)
    self.assertEqual(score("NBA",[a],NOW)["independently_settled_games"],1)
 def test_future_quote_excluded(self):
    a=archive();reconcile_archive(a,[game()],NOW,market("yes"))
    a["observations"][0]["quote_observed_utc"]="2026-11-07T21:00:00+00:00"
    self.assertEqual(score("NBA",[a],NOW)["independently_settled_games"],0)
if __name__=="__main__":unittest.main()
