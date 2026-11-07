#!/usr/bin/env python3
import datetime as dt
import unittest
from ncaaf_viewer_format_probe_v39 import inspect,UTC
NOW=dt.datetime(2026,11,7,20,tzinfo=UTC)
LINK="https://app.hdintelligence.com/?conf=B12&source=B12&sport=Football&type=report"
GAME={"cfbd_game_id":"401","conference":"big 12",
      "conference_published_viewer_url":LINK,"home_team":"Houston","away_team":"Cincinnati"}
class ProbeSafety(unittest.TestCase):
 def test_static_html_can_be_read_but_not_approved(self):
    d=inspect({"games":[GAME]},NOW,lambda url:"<html><body><h1>Game Reports</h1><p>"+("A"*1400)+"</p></body></html>")
    self.assertEqual(d["viewers_retrieved"],1)
    self.assertFalse(d["games"][0]["specific_game_final_report_verified"])
    self.assertFalse(d["official_eligible"])
 def test_js_shell_does_not_mean_team_available(self):
    d=inspect({"games":[GAME]},NOW,lambda url:'<html><body><div id="root"></div><script>secret</script></body></html>')
    self.assertTrue(d["games"][0]["requires_js_or_rendering"])
    self.assertFalse(d["games"][0]["starting_qb_verified"])
 def test_unattested_viewer_ignored(self):
    d=inspect({"games":[{**GAME,"conference_published_viewer_url":None}]},NOW,lambda url:"bad")
    self.assertEqual(d["attested_viewers_probed"],0)
 def test_conflict_link_rejected(self):
    d=inspect({"games":[{**GAME,"conference":"acc"}]},NOW,lambda url:"bad")
    self.assertEqual(d["viewers_retrieved"],0)
 def test_network_failure_no_clear(self):
    def fail(u):raise ValueError("no access")
    d=inspect({"games":[GAME]},NOW,fail)
    self.assertEqual(d["viewers_retrieved"],0)
    self.assertFalse(d["official_eligible"])
if __name__=="__main__":unittest.main()
