#!/usr/bin/env python3
"""No backfilled picks, duplicate game samples, unverified results, or future leaks."""
import datetime as dt
import copy
import unittest
from ncaaf_forward_scorecard_v39 import analyze,valid_observation,UTC
NOW=dt.datetime(2026,11,8,15,tzinfo=UTC)
KICK="2026-11-07T20:30:00+00:00"
M="2026-11-07T18:00:00+00:00"
ENTRY="2026-11-07T19:05:00+00:00"
NENTRY="2026-11-07T19:05:30+00:00"
LATE="2026-11-07T20:00:00+00:00"
TICK="KXNCAAFGAME-26NOV07ABC-ABC"
def obs(side="YES",p=.65,ask=.42,at=ENTRY,model=M):
    return {
        "ticker":TICK,"side":side,"cfbdGameId":"401",
        "eventTicker":"KXNCAAFGAME-26NOV07ABC",
        "homeTeam":"Auburn","awayTeam":"Georgia",
        "selectionLabel":"Auburn","kickoffUTC":KICK,
        "quote_observed_utc":at,"model_captured_utc":model,
        "model_probability":p,"book_vwap_ask":ask,
        "taker_fee_estimate_dollars":.02,"sample_contracts":1,
        "research_only":True,"official_eligible":False}
def sample(verified=True):
    yes=obs();no=obs("NO",.35,.61,NENTRY)
    later=obs(at=LATE,ask=.50)
    d={"sport":"NCAAF","observations":[yes,no,later]}
    if verified:
        d["verified_outcomes"]={TICK:{
            "cfbd_game_id":"401","home_team":"Auburn",
            "away_team":"Georgia","winner_team":"Auburn","market_result":"YES",
            "sources":["CollegeFootballData completed final score","Kalshi settled public market"],
            "official_eligible":False,"research_only":True}}
    return {"2026-11-07":d}

class TestScorecard(unittest.TestCase):
 def test_one_game_one_brier_one_research_candidate(self):
    dataset=sample()
    x=analyze(dataset,NOW)
    self.assertEqual(x["independently_verified_game_probability_samples"],1)
    self.assertEqual(x["research_edge_strategy_distinct_games"],1)
    self.assertAlmostEqual(x["model_home_probability_brier"],(.65-1)**2)
    self.assertAlmostEqual(x["market_bidask_midpoint_brier"],((.42+1-.61)/2-1)**2)
    self.assertEqual(x["matched_independent_close_proxy_games"],1)
    self.assertAlmostEqual(x["mean_later_pregame_quote_movement_pp"],8.0)
    self.assertAlmostEqual(x["theoretical_one_contract_net_pnl_sum"],.56)
    self.assertFalse(x["review_sample_target_met"])
    self.assertFalse(x["official_eligible"])
 def test_repeating_same_side_does_not_increase_game_count(self):
    d=sample()
    d["2026-11-07"]["observations"].extend(copy.deepcopy(d["2026-11-07"]["observations"]))
    x=analyze(d,NOW)
    self.assertEqual(x["independently_verified_game_probability_samples"],1)
    self.assertEqual(x["research_edge_strategy_distinct_games"],1)
 def test_unverified_settlement_not_counted(self):
    x=analyze(sample(False),NOW)
    self.assertEqual(x["independently_verified_game_probability_samples"],0)
    self.assertEqual(x["research_edge_strategy_distinct_games"],0)
    self.assertIsNone(x["theoretical_one_contract_net_pnl_sum"])
 def test_future_model_cannot_feed_pregame_prob(self):
    x=obs(model="2026-11-07T22:00:00+00:00")
    self.assertFalse(valid_observation(x))
 def test_after_kickoff_book_not_valid(self):
    x=obs(at="2026-11-07T20:31:00+00:00")
    self.assertFalse(valid_observation(x))
 def test_low_edge_no_hypothetical_strategy(self):
    d=sample()
    for o in d["2026-11-07"]["observations"]:
        o["book_vwap_ask"]=.69 if o["side"]=="YES" else .35
    x=analyze(d,NOW)
    self.assertEqual(x["independently_verified_game_probability_samples"],1)
    self.assertEqual(x["research_edge_strategy_distinct_games"],0)
if __name__=="__main__":unittest.main()
