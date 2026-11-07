#!/usr/bin/env python3
import datetime as dt
import unittest
from ncaaf_official_report_discovery_v35 import discover
UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,7,17,tzinfo=UTC)
HUB="https://big12sports.com/sports/2025/8/21/availability-reporting.aspx"
Q={"game_review_queue":[
 {"cfbd_game_id":"123","home_team":"Texas Tech","away_team":"West Virginia",
  "kickoff_utc":"2026-11-07T22:00:00+00:00","report_discovery_hub":HUB}]}
DOC="https://big12sports.com/documents/2026/11/7/texas-tech-west-virginia-report.pdf"
HTML='<html><a href="'+DOC+'">Texas Tech vs West Virginia (Nov 7)</a></html>'
class Tests(unittest.TestCase):
 def test_candidate_not_verification(self):
    d=discover(Q,NOW,fetch_fn=lambda url:HTML)
    self.assertEqual(d["unambiguous_direct_report_candidates"],1)
    self.assertEqual(d["candidate_evidence"]["reports"][0]["direct_official_report_url"],DOC)
    self.assertFalse(d["matchups"][0]["document_content_verified"])
    self.assertFalse(d["official_eligible"])
 def test_hub_only_no_candidate(self):
    d=discover(Q,NOW,fetch_fn=lambda url:'<html><a href="/sports/2025/8/21/availability-reporting.aspx">Football Reports</a></html>')
    self.assertEqual(d["unambiguous_direct_report_candidates"],0)
 def test_embedded_app_does_not_count_as_verified(self):
    d=discover(Q,NOW,fetch_fn=lambda url:'<iframe src="https://app.hdintelligence.com/foo"></iframe>')
    self.assertEqual(d["matchups"][0]["hub_embedded_iframes"],1)
    self.assertEqual(d["unambiguous_direct_report_candidates"],0)
if __name__=="__main__":unittest.main()
