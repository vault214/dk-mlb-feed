#!/usr/bin/env python3
import unittest
from ncaaf_publish_research_v32 import publish

class Tests(unittest.TestCase):
    def test_no_official_shadow_or_private_data(self):
        model={"capturedAtUTC":"2026-11-07T19:00:00+00:00",
          "market_research":{"research_comparisons":[{
           "ticker":"T","side":"YES","cfbd_game_id":"1","event_ticker":"E",
           "home_team":"A","away_team":"B","kickoff_utc":"2026-11-08T01:00:00Z",
           "winner_contract_label":"A","model_probability":.55,
           "not_an_official_or_shadow_pick":True}]}}
        weather={"weather_for_cfbd_game_id":{"1":{"status":"WEATHER FORECAST SOURCED"}}}
        quotes={"capturedAtUTC":"2026-11-07T19:00:00+00:00",
          "research_only_comparisons":[{"ticker":"T","side":"YES",
           "cfbd_game_id":"1","quote_status":"CURRENT QUOTE OBSERVED",
           "latest_observed_ask":.52,"observed_at_utc":"2026-11-07T19:00:00+00:00",
           "gross_model_minus_latest_ask_pp":3}]}
        x=publish(model,weather,quotes)
        self.assertEqual(len(x["rows"]),1)
        self.assertFalse(x["officialEligible"])
        self.assertEqual(x["official"],[])
        self.assertEqual(x["shadow"],[])
        self.assertTrue(x["rows"][0]["researchOnly"])
        self.assertFalse(x["rows"][0]["qbVerified"])
        self.assertNotIn("bank",str(x).lower())
    def test_rejects_unlabeled_research(self):
        with self.assertRaises(ValueError):
            publish({"market_research":{"research_comparisons":[{
                "ticker":"T","side":"YES","cfbd_game_id":"1"}]}},{},
                {"capturedAtUTC":"2026-11-07T19:00:00+00:00"})
if __name__=="__main__":unittest.main()
