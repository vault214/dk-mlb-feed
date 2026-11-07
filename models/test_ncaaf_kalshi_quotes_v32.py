#!/usr/bin/env python3
import datetime as dt
import unittest
from ncaaf_kalshi_live_quotes_v32 import extract, review

class Tests(unittest.TestCase):
    def test_current_dollar_asks(self):
        now=dt.datetime(2026,11,7,19,tzinfo=dt.timezone.utc)
        row=extract({"ticker":"KXNCAAFGAME-26NOV07ABC-ABC",
           "status":"active","close_time":"2026-11-08T01:00:00Z",
           "yes_ask_dollars":"0.38","no_ask_dollars":"0.63"},now)
        self.assertEqual(row["status"],"CURRENT QUOTE OBSERVED")
        self.assertEqual(row["yes_ask"],.38)
        self.assertFalse(row["production_eligible"])
    def test_dollar_one_cannot_be_one_cent(self):
        now=dt.datetime(2026,11,7,19,tzinfo=dt.timezone.utc)
        row=extract({"ticker":"X","status":"active","close_time":"2026-11-08T01:00:00Z",
            "yes_ask_dollars":"1.000","no_ask_dollars":"0.01"},now)
        self.assertEqual(row["status"],"NOT A VALID OPEN OFFER")
    def test_closed_market_fails(self):
        now=dt.datetime(2026,11,7,19,tzinfo=dt.timezone.utc)
        row=extract({"ticker":"X","status":"closed","close_time":"2026-11-07T01:00:00Z",
            "yes_ask_dollars":"0.45","no_ask_dollars":"0.56"},now)
        self.assertEqual(row["status"],"NOT A VALID OPEN OFFER")
    def test_research_review_never_issues_picks(self):
        ticker="KXNCAAFGAME-26NOV07ABC-ABC"
        x=review({"market_research":{"research_comparisons":[
            {"ticker":ticker,"side":"YES","cfbd_game_id":"123",
             "model_probability":.6,"ask":.5}]}},
            fetch_fn=lambda ticker:{"ticker":ticker,"status":"active",
             "close_time":"2099-12-31T00:00:00Z","yes_ask_dollars":"0.53",
             "no_ask_dollars":"0.48"})
        self.assertEqual(x["unique_tickers_checked"],1)
        self.assertEqual(x["contract_sides_reviewed"],1)
        self.assertIsNone(x["official"])
        self.assertIsNone(x.get("trade"))
        self.assertFalse(x["research_only_comparisons"][0]["production_eligible"])
if __name__=="__main__":unittest.main()
