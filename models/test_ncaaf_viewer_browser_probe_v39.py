#!/usr/bin/env python3
import datetime as dt
import unittest
from ncaaf_viewer_browser_probe_v39 import inspect,UTC
LINK="https://app.hdintelligence.com/?conf=B12&source=B12&sport=Football&type=report"
P={"games":[{"cfbd_game_id":"401","home_team":"Houston","away_team":"Cincinnati",
            "conference":"big 12","conference_published_viewer_url":LINK}]}
NOW=dt.datetime(2026,11,7,20,tzinfo=UTC)
class TestRenderedViewer(unittest.TestCase):
 def test_browser_render_still_not_player_verification(self):
    d=inspect(P,NOW,render=lambda url:"<html><body><div><h1>Games November 7</h1><p>Initial Report</p><p>Player QB OUT</p></div></body></html>")
    self.assertEqual(d["browser_render_succeeded"],1)
    self.assertTrue(d["games"][0]["report_terms_detected"])
    self.assertFalse(d["games"][0]["exact_matchup_final_report_verified"])
    self.assertFalse(d["games"][0]["player_statuses_verified"])
    self.assertFalse(d["official_eligible"])
 def test_no_unattested_vendor_url(self):
    p={"games":[{**P["games"][0],"conference_published_viewer_url":"https://app.hdintelligence.com/?conf=ACC&source=ACC&sport=Football&type=report"}]}
    d=inspect(p,NOW,render=lambda _: "bad")
    self.assertEqual(d["unique_attested_viewers"],0)
 def test_browser_failure_never_approves(self):
    def fail(_):raise ValueError("browser unavailable")
    d=inspect(P,NOW,render=fail)
    self.assertEqual(d["browser_render_succeeded"],0)
    self.assertFalse(d["official_eligible"])
if __name__=="__main__":unittest.main()
