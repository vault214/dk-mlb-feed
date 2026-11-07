#!/usr/bin/env python3
"""Offline verification of exact authoritative matchup reports; no guessing."""
import datetime as dt
import unittest
from ncaaf_primary_report_evidence_v35 import (
    verify,primary_url_ok,qb_excerpt_valid,document_date_present)
UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,7,17,tzinfo=UTC)
DOC="Official College Football Availability Report, November 7, 2026. Texas versus Missouri. "
DOC+="Texas QB Alex Example Out. Missouri QB Jordan Sample Available."
Q={"schemaVersion":1,"sport":"NCAAF","matched_games":1,
   "game_review_queue":[{"cfbd_game_id":"123","event_date_et":"2026-11-07",
      "home_team":"Texas","away_team":"Missouri",
      "kickoff_utc":"2026-11-07T21:00:00+00:00",
      "starting_qb_names_confirmed":False,
      "game_specific_primary_report_url":None,
      "material_absences_verified":False}]}
URL="https://big12sports.com/documents/2026/11/7/texas-missouri-football-availability.aspx"
REPORT={"cfbd_game_id":"123","home_team":"Texas","away_team":"Missouri",
        "direct_official_report_url":URL,
        "qbs":{"home":{"name":"Alex Example","status":"Out",
          "source_excerpt":"Texas QB Alex Example Out"},
          "away":{"name":"Jordan Sample","status":"Available",
          "source_excerpt":"Missouri QB Jordan Sample Available"}}}

class TestReportProof(unittest.TestCase):
 def test_exact_official_document_both_qbs(self):
    d=verify(Q,{"reports":[REPORT]},NOW,fetch_fn=lambda url:DOC)
    self.assertEqual(d["game_specific_reports_verified"],1)
    self.assertEqual(d["starting_qbs_verified"],1)
    r=d["game_review_queue"][0]
    self.assertFalse(r["model_eligible"])
    self.assertFalse(r["material_absences_verified"])
    self.assertFalse(d["official_eligible"])
 def test_conference_hub_not_a_document(self):
    self.assertFalse(primary_url_ok("https://www.secsports.com/fbreports"))
    x=dict(REPORT,direct_official_report_url="https://www.secsports.com/fbreports")
    self.assertEqual(verify(Q,{"reports":[x]},NOW)["game_specific_reports_verified"],0)
 def test_missing_other_team_rejected(self):
    x=verify(Q,{"reports":[REPORT]},NOW,fetch_fn=lambda url:"November 7, 2026. Texas QB Alex Example Out")
    self.assertEqual(x["game_specific_reports_verified"],0)
 def test_old_date_rejected(self):
    x=verify(Q,{"reports":[REPORT]},NOW,fetch_fn=lambda url:"Texas Missouri November 6, 2026")
    self.assertEqual(x["game_specific_reports_verified"],0)
 def test_cannot_verify_after_kickoff(self):
    late=dt.datetime(2026,11,7,22,tzinfo=UTC)
    x=verify(Q,{"reports":[REPORT]},late,fetch_fn=lambda url:DOC)
    self.assertEqual(x["game_specific_reports_verified"],0)
 def test_strict_qb_excerpt(self):
    self.assertFalse(qb_excerpt_valid(DOC,{"name":"Alex Example","status":"Available","source_excerpt":"Alex Example Available"}))
    self.assertTrue(document_date_present(DOC,"2026-11-07"))
 def test_unknown_domain_and_redirect_blocked(self):
    self.assertFalse(primary_url_ok("https://example.org/a/2026/texas-missouri-report"))
    self.assertFalse(primary_url_ok("https://big12sports.com.evil.test/a/report.html"))
    self.assertFalse(primary_url_ok("http://big12sports.com/documents/abcde"))
if __name__=="__main__":unittest.main()
