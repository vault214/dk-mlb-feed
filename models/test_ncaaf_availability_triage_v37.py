#!/usr/bin/env python3
"""No unverified sports source may claim confirmed QB injury or starter status."""
import datetime as dt
import unittest
from ncaaf_availability_triage_v37 import triage,parse_game,UTC
NOW=dt.datetime(2026,11,7,18,5,tzinfo=UTC)
URL="https://kickoffstatus.com/games/2026-11-07-oregon-at-ohio-state/"
HTML="""<html><h3>Oregon 9 Out 1 GTD</h3>
<table><tr><th>Player</th><th>Pos</th><th>Status</th><th>History</th></tr>
<tr><td>Dante Moore #5</td><td>QB</td><td>Out</td><td>Listed</td></tr>
<tr><td>Someone Else</td><td>RB</td><td>Out</td><td>Listed</td></tr></table>
<h3>Ohio State 8 Out</h3><table><tr><td>Julian Sayin #10</td><td>QB</td><td>Out</td><td>Listed</td></tr></table>
<h2>Unofficial Injury Notes</h2><table><tr><td>Random QB</td><td>QB</td><td>Out</td></tr></table></html>"""
SRC={"games":[{"cfbd_game_id":"x","home_team":"Ohio State",
"away_team":"Oregon","event_date_et":"2026-11-07","supplemental_url":URL}]}
class TestTriage(unittest.TestCase):
 def test_official_table_copy_is_still_unverified_secondary(self):
    d=triage(SRC,NOW,lambda url:HTML)
    self.assertEqual(d["games_with_secondary_qb_risk_flags"],1)
    self.assertEqual(len(d["games"][0]["secondary_qb_risk_flags"]),2)
    self.assertFalse(d["official_eligible"])
    self.assertFalse(d["games"][0]["official_qb_verified"])
    self.assertFalse(d["games"][0]["actual_starter_confirmed"])
    self.assertFalse(d["games"][0]["used_to_adjust_probabilities"])
 def test_unofficial_notes_not_parsed(self):
    x=parse_game(HTML,"Ohio State","Oregon")
    self.assertEqual(x["qb_position_rows_seen"],2)
    self.assertNotIn("Random QB",[y["name"] for y in x["secondary_qb_risk_flags"]])
 def test_no_qb_rows_does_not_mean_healthy(self):
    x=parse_game('<h3>Oregon</h3><table><tr><td>Person</td><td>OL</td><td>Out</td></tr></table>',"Ohio State","Oregon")
    self.assertEqual(x["qb_position_rows_seen"],0)
    self.assertEqual(x["secondary_qb_risk_flags"],[])
 def test_failed_fetch_never_generates_verified_facts(self):
    def failed(_):raise ValueError("source unavailable")
    d=triage(SRC,NOW,failed)
    self.assertEqual(d["games_with_secondary_qb_risk_flags"],0)
    self.assertFalse(d["games"][0]["official_qb_verified"])
    self.assertIn("UNAVAILABLE",d["games"][0]["status"])
 def test_ambiguous_section_not_matched(self):
    x=parse_game('<h3>Random</h3><table><tr><td>Unknown</td><td>QB</td><td>Out</td></tr></table>',"Ohio State","Oregon")
    self.assertEqual(x["qb_position_rows_seen"],0)
if __name__=="__main__":unittest.main()
