#!/usr/bin/env python3
import datetime as dt
import unittest
from ncaaf_provider_proof_v39 import inspect,vendor_link_ok,UTC
NOW=dt.datetime(2026,11,7,15,tzinfo=UTC)
HUB="https://www.secsports.com/fbreports"
LINK="https://app.hdintelligence.com/?conf=SEC&source=SEC&sport=Football&type=report"
Q={"game_review_queue":[{"cfbd_game_id":"123","conference_game":True,
 "home_conference":"SEC","away_conference":"SEC",
 "home_team":"Texas","away_team":"Georgia",
 "report_discovery_hub":HUB,"kickoff_utc":"2026-11-07T22:00:00Z"}]}
class TestProviderProof(unittest.TestCase):
 def test_official_html_iframe_is_only_source_provenance(self):
    x=inspect(Q,NOW,fetch_fn=lambda u:'<iframe src="'+LINK.replace("&","&amp;")+'"></iframe>')
    self.assertEqual(x["games_with_verified_publisher_link"],1)
    self.assertEqual(x["games"][0]["conference_published_viewer_url"],LINK)
    self.assertFalse(x["games"][0]["final_report_for_this_game_verified"])
    self.assertFalse(x["official_eligible"])
 def test_unsourced_guessed_link_not_accepted(self):
    x=inspect(Q,NOW,fetch_fn=lambda u:"<p>SEC game report</p>")
    self.assertEqual(x["games_with_verified_publisher_link"],0)
 def test_app_conf_mismatch_cannot_be_attested(self):
    wrong=LINK.replace("conf=SEC","conf=ACC")
    self.assertFalse(vendor_link_ok(wrong,"sec"))
 def test_extra_and_duplicate_parameters_rejected(self):
    self.assertFalse(vendor_link_ok(LINK+"&admin=true","sec"))
    self.assertFalse(vendor_link_ok(LINK+"&type=report","sec"))
 def test_unverified_big_ten_nonconference_ignored(self):
    q={"game_review_queue":[{**Q["game_review_queue"][0],
       "conference_game":False,"home_conference":"Big Ten","away_conference":"SEC"}]}
    x=inspect(q,NOW,lambda u:LINK)
    self.assertEqual(x["official_hubs_checked"],0)
 def test_official_hub_failure_not_a_false_clear(self):
    def fail(_):raise ValueError("unavailable")
    x=inspect(Q,NOW,fetch_fn=fail)
    self.assertFalse(x["games"][0]["viewer_embedded_by_official_site"])
    self.assertEqual(x["official_hubs_retrieved"],0)
if __name__=="__main__":unittest.main()
