#!/usr/bin/env python3
"""Secondary lead matches must never certify injury/QB availability."""
import datetime as dt
import unittest
from ncaaf_supplemental_availability_v36 import discover,slugs,UTC
NOW=dt.datetime(2026,11,7,15,tzinfo=UTC)
Q={"game_review_queue":[
 {"cfbd_game_id":"1","home_team":"South Carolina","away_team":"Texas A&M",
  "kickoff_utc":"2026-11-07T20:00:00+00:00","event_date_et":"2026-11-07"},
 {"cfbd_game_id":"2","home_team":"Middle Tennessee","away_team":"Western Kentucky",
  "kickoff_utc":"2026-11-07T21:00:00+00:00","event_date_et":"2026-11-07"},
 {"cfbd_game_id":"3","home_team":"LSU","away_team":"Alabama",
  "kickoff_utc":"2026-11-07T21:30:00+00:00","event_date_et":"2026-11-07"},
]}
HTML='''<a href="/games/2026-11-07-texas-a-m-at-south-carolina/">A&M at SC</a>
<a href="https://kickoffstatus.com/games/2026-11-07-wku-at-mtsu/">WKU @ MTSU</a>
<a href="/games/2026-11-07-alabama-at-lsu/">Alabama at LSU</a>
<a href="https://example.com/games/2026-11-07-alabama-at-lsu/">Untrusted other domain</a>'''
class TestSecondary(unittest.TestCase):
 def test_all_three_match_while_still_unverified(self):
  x=discover(Q,HTML,NOW)
  self.assertEqual(x["secondary_matched_games"],3)
  self.assertEqual(slugs("Texas A&M"),{"texas-a-and-m","texas-a-m"})
  self.assertFalse(x["official_eligible"])
  for g in x["games"]:
   self.assertFalse(g["quarterback_verified"])
   self.assertFalse(g["source_player_statuses_used"])
   self.assertFalse(g["primary_matchup_document_verified"])
   self.assertIn("kickoffstatus.com",g["supplemental_url"])
 def test_wrong_day_excluded(self):
  x=discover(Q,'<a href="/games/2026-11-06-alabama-at-lsu/">Alabama LSU</a>',NOW)
  self.assertEqual(x["secondary_matched_games"],0)
 def test_wrong_matchup_excluded(self):
  x=discover(Q,'<a href="/games/2026-11-07-alabama-at-south-carolina/">Alabama SC</a>',NOW)
  self.assertEqual(x["secondary_matched_games"],0)
 def test_untrusted_external_domain_excluded(self):
  x=discover(Q,'<a href="https://example.com/games/2026-11-07-alabama-at-lsu/">Alabama LSU</a>',NOW)
  self.assertEqual(x["secondary_matched_games"],0)
if __name__=="__main__":unittest.main()
