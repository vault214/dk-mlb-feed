#!/usr/bin/env python3
"""Availability source policy tests: an official hub never verifies a QB."""
import datetime as dt
import unittest
from ncaaf_availability_queue_v34 import queue,source_for
UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,7,17,tzinfo=UTC)

class TestAvailabilityQueue(unittest.TestCase):
 def test_policy_link_is_not_a_game_report(self):
    g={"id":123,"homeTeam":"Texas","awayTeam":"Missouri",
       "homeConference":"SEC","awayConference":"SEC",
       "conferenceGame":True}
    research={"rows":[{"cfbdGameId":"123","homeTeam":"Texas",
       "awayTeam":"Missouri","kickoffUTC":"2026-11-07T22:00:00+00:00"}]}
    result=queue(research,[g],NOW)
    self.assertEqual(result["matched_games"],1)
    self.assertEqual(result["official_conference_report_hubs_found"],1)
    self.assertEqual(result["game_specific_reports_verified"],0)
    self.assertEqual(result["starting_qbs_verified"],0)
    self.assertIsNone(result["game_review_queue"][0]["game_specific_primary_report_url"])
    self.assertFalse(result["game_review_queue"][0]["model_eligible"])
 def test_nonconference_does_not_assume_report_coverage(self):
    g={"homeConference":"ACC","awayConference":"Independent","conferenceGame":False}
    url,status=source_for(g)
    self.assertIsNone(url)
    self.assertEqual(status,"NO CONFERENCE REPORT COVERAGE ASSUMED")
 def test_duplicate_contract_rows_one_review(self):
    g={"id":123,"homeTeam":"Texas","awayTeam":"Missouri",
       "homeConference":"SEC","awayConference":"SEC","conferenceGame":True}
    rows=[{"cfbdGameId":"123","homeTeam":"Texas","awayTeam":"Missouri",
           "kickoffUTC":"2026-11-07T22:00:00+00:00"}]*4
    self.assertEqual(queue({"rows":rows},[g],NOW)["matched_games"],1)
if __name__=="__main__":unittest.main()
