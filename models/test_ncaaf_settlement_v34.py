#!/usr/bin/env python3
"""Offline CFBD independent-final-score validation tests. No remote calls."""
import datetime as dt
import unittest
from ncaaf_settlement_verify_v34 import reconcile, scoreboard_side
from ncaaf_cfbd_model_v32 import alias_index

UTC=dt.timezone.utc
KICK="2026-11-07T20:30:00+00:00"
ENTRY="2026-11-07T19:05:00+00:00"
HOME="Middle Tennessee"
AWAY="Western Kentucky"
TICK="KXNCAAFGAME-26NOV07WKUMTU-MTU"

def archive():
    return {"sport":"NCAAF","game_date_et":"2026-11-07",
      "observations":[{
        "ticker":TICK,"cfbdGameId":"401","eventTicker":"KXNCAAFGAME-26NOV07WKUMTU",
        "kickoffUTC":KICK,"quote_observed_utc":ENTRY,
        "homeTeam":HOME,"awayTeam":AWAY,"selectionLabel":HOME,
        "side":"YES","model_probability":.65,
        "research_only":True,"official_eligible":False,"shadow_eligible":False,
      }],"settlements":{}}

def game(completed=True,home=HOME,away=AWAY,home_score=28,away_score=21):
    return {"id":401,"homeTeam":home,"awayTeam":away,
      "startDate":KICK,"completed":completed,
      "homePoints":home_score if completed else None,
      "awayPoints":away_score if completed else None}

TEAMS=[{"school":HOME},{"school":AWAY}]+[{"school":"Team "+str(i)} for i in range(90)]
NOW=dt.datetime(2026,11,8,10,tzinfo=UTC)

class TestSettlement(unittest.TestCase):
 def test_verified_independent_market_result(self):
    archives={"2026-11-07":archive()}
    result=reconcile(archives,[game()],TEAMS,NOW,
      market_fn=lambda ticker:{"ticker":TICK,"status":"settled","result":"yes"})
    self.assertEqual(result["independently_verified_tickers"],1)
    self.assertEqual(result["unique_game_winner_samples"],1)
    self.assertAlmostEqual(result["forward_unique_game_brier"],(.65-1)**2,6)
    self.assertFalse(result["official_eligible"])
    self.assertFalse(archives["2026-11-07"]["verified_outcomes"][TICK]["official_eligible"])
 def test_second_reconcile_does_not_reverify_or_change_timestamp(self):
    archives={"2026-11-07":archive()}
    get=lambda ticker:{"ticker":TICK,"status":"settled","result":"yes"}
    first=reconcile(archives,[game()],TEAMS,NOW,market_fn=get)
    self.assertEqual(first["newly_verified_tickers_this_run"],1)
    original=archives["2026-11-07"]["verified_outcomes"][TICK]["verified_at_utc"]
    later=NOW+dt.timedelta(hours=6)
    second=reconcile(archives,[game()],TEAMS,later,market_fn=get)
    self.assertEqual(second["newly_verified_tickers_this_run"],0)
    self.assertEqual(second["independently_verified_tickers"],1)
    self.assertEqual(archives["2026-11-07"]["verified_outcomes"][TICK]["verified_at_utc"],original)
 def test_conflicting_refinal_removes_prior_verification(self):
    archives={"2026-11-07":archive()}
    get=lambda ticker:{"ticker":TICK,"status":"settled","result":"yes"}
    reconcile(archives,[game()],TEAMS,NOW,market_fn=get)
    changed=game(home_score=18,away_score=23)
    later=reconcile(archives,[changed],TEAMS,NOW+dt.timedelta(hours=1),market_fn=get)
    self.assertEqual(later["independently_verified_tickers"],0)
    self.assertGreater(later["unverified_reasons"].get("SOURCE RESULT CONFLICT",0),0)
 def test_market_vs_cfbd_conflict_fails_closed(self):
    x={"2026-11-07":archive()}
    out=reconcile(x,[game()],TEAMS,NOW,
      market_fn=lambda ticker:{"ticker":TICK,"status":"settled","result":"no"})
    self.assertEqual(out["independently_verified_tickers"],0)
    self.assertEqual(out["unverified_reasons"]["SOURCE RESULT CONFLICT"],1)
    self.assertFalse(x["2026-11-07"].get("verified_outcomes"))
 def test_while_game_not_finished_no_validation(self):
    x={"2026-11-07":archive()}
    out=reconcile(x,[game(completed=False)],TEAMS,NOW,
      market_fn=lambda ticker:{"ticker":TICK,"status":"settled","result":"yes"})
    self.assertEqual(out["independently_verified_tickers"],0)
    self.assertEqual(out["unverified_reasons"]["GAME NOT FINAL"],1)
 def test_wrong_game_identity_blocks_verification(self):
    x={"2026-11-07":archive()}
    out=reconcile(x,[game(home="Different")],TEAMS,NOW,
      market_fn=lambda ticker:{"ticker":TICK,"status":"settled","result":"yes"})
    self.assertEqual(out["independently_verified_tickers"],0)
    self.assertEqual(out["unverified_reasons"]["CFBD TEAM IDENTITY CONFLICT"],1)
 def test_kalshi_not_settled_no_validation(self):
    x={"2026-11-07":archive()}
    out=reconcile(x,[game()],TEAMS,NOW,
      market_fn=lambda ticker:{"ticker":TICK,"status":"closed","result":"yes"})
    self.assertEqual(out["independently_verified_tickers"],0)
    self.assertEqual(out["unverified_reasons"]["KALSHI NOT SETTLED"],1)
 def test_game_not_yet_started(self):
    x={"2026-11-07":archive()}
    t=dt.datetime(2026,11,7,20,tzinfo=UTC)
    out=reconcile(x,[game(completed=True)],TEAMS,t,
      market_fn=lambda ticker:{"ticker":TICK,"status":"settled","result":"yes"})
    self.assertEqual(out["independently_verified_tickers"],0)
    self.assertIn("GAME NOT YET ELIGIBLE FOR SETTLEMENT",out["unverified_reasons"])
if __name__=="__main__":unittest.main()
