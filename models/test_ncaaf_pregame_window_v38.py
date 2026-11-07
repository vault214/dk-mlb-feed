#!/usr/bin/env python3
"""Regressions for policy schedule and no nonconference coverage assumptions."""
import datetime as dt
import unittest
from ncaaf_pregame_window_v38 import report_clock,plan,UTC
NOW=dt.datetime(2026,11,7,16,0,tzinfo=UTC)
KICK=dt.datetime(2026,11,7,19,0,tzinfo=UTC)
def g(home="SEC",away="SEC",conference=True,kick=None):
    return {"cfbd_game_id":"123","home_team":"Texas","away_team":"Georgia",
            "home_conference":home,"away_conference":away,
            "conference_game":conference,"kickoff_utc":(kick or KICK).isoformat()}
def resources(item):
    return {"game_review_queue":[item]},{
       "modelCapturedAtUTC":NOW.isoformat(),
       "rows":[{"cfbdGameId":"123","homeTeam":"Texas","awayTeam":"Georgia",
                "kickoffUTC":item["kickoff_utc"],"ticker":"TEST","side":"YES",
                "modelProbability":0.6}]}
class PregameClock(unittest.TestCase):
 def test_sec_and_big12_due_90m(self):
    for conf in ("SEC","Big 12"):
      x=report_clock(g(conf,conf),NOW)
      self.assertEqual(x["final_report_due_minutes_before_kickoff"],90)
      self.assertEqual(x["stage"],"FINAL REPORT NOT YET DUE")
      due=NOW+dt.timedelta(minutes=95)
      self.assertIn("ACTUAL DOCUMENT",report_clock(g(conf,conf),due)["stage"])
 def test_bigten_and_acc_due_120m(self):
    for conf in ("Big Ten","ACC"):
      x=report_clock(g(conf,conf),NOW)
      self.assertEqual(x["final_report_due_minutes_before_kickoff"],120)
      x=report_clock(g(conf,conf),NOW+dt.timedelta(minutes=61))
      self.assertIn("ACTUAL DOCUMENT",x["stage"])
 def test_policy_omission_never_assumes_healthy_without_actual_game_report(self):
    for conf in ("SEC","Big Ten"):
      x=report_clock(g(conf,conf),KICK-dt.timedelta(minutes=5))
      self.assertIn("ONLY IF",x["unlisted_player_policy_if_verified_complete_report"])
      self.assertFalse(x["actual_unlisted_player_status_assessed"])
      self.assertFalse(x["both_starting_qbs_verified"])
    for conf in ("ACC","Big 12"):
      x=report_clock(g(conf,conf),KICK-dt.timedelta(minutes=5))
      self.assertEqual(x["unlisted_player_policy_if_verified_complete_report"],
                        "NO VERIFIED SAFE OMISSION INFERENCE")
 def test_nonconference_not_eligible_even_sec_school(self):
    for item in (g("SEC","SEC",False),g("SEC","Big Ten",False),g("SEC","ACC",True)):
      x=report_clock(item,NOW)
      self.assertFalse(x["official_policy_applicable"])
      self.assertIsNone(x["final_report_due_utc"])
      self.assertFalse(x["official_eligible"])
 def test_window_180_minutes_exact_and_postkickoff(self):
    self.assertTrue(report_clock(g(),NOW)["capture_window"])
    self.assertFalse(report_clock(g(),NOW-dt.timedelta(seconds=1))["capture_window"])
    self.assertFalse(report_clock(g(),KICK)["capture_window"])
 def test_only_exact_game_identity_is_selected(self):
    item=g()
    q,r=resources(item)
    r["rows"].append({"cfbdGameId":"123","homeTeam":"Texas","awayTeam":"Georgia",
       "kickoffUTC":KICK.isoformat(),"ticker":"TEST2"})
    r["rows"].append({"cfbdGameId":"124","homeTeam":"Texas","awayTeam":"Georgia",
       "kickoffUTC":KICK.isoformat(),"ticker":"OTHER"})
    info,filtered,scoped=plan(q,r,NOW)
    self.assertTrue(info["capture_now"])
    self.assertEqual(info["active_window_games"],1)
    self.assertEqual(len(filtered["rows"]),2)
    self.assertEqual(len(scoped["game_review_queue"]),1)
    self.assertFalse(info["official_eligible"])
 def test_never_certify_player_from_reporting_clock(self):
    x=report_clock(g(),KICK-dt.timedelta(minutes=5))
    self.assertFalse(x["actual_final_report_verified"])
    self.assertFalse(x["both_starting_qbs_verified"])
    self.assertFalse(x["available_if_omitted_policy_applied"])
 def test_bad_start_date_fails_closed(self):
    item=g();item["kickoff_utc"]="2026-not-a-date"
    self.assertFalse(report_clock(item,NOW)["capture_window"])
if __name__=="__main__":unittest.main()
