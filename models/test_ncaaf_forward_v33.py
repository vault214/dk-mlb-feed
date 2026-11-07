#!/usr/bin/env python3
"""Offline v3.3 research-only tests. No external calls or account activity."""
import datetime as dt
from decimal import Decimal as D
import unittest

from ncaaf_forward_audit_v33 import (
    simulated_taker, fee_spec, taker_fee, audit, merge_snapshot,
    settle_archives, summarize, select_rows
)

UTC=dt.timezone.utc

class ForwardAuditTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,11,7,18,tzinfo=UTC)
        self.kick=self.now+dt.timedelta(hours=2)
        self.research={
          "modelCapturedAtUTC":(self.now-dt.timedelta(minutes=40)).isoformat(),
          "quoteResearchExpiresUTC":(self.now-dt.timedelta(minutes=38)).isoformat(),
          "rows":[{
              "ticker":"KXNCAAFGAME-26NOV07TEST-AAA",
              "eventTicker":"KXNCAAFGAME-26NOV07TEST",
              "cfbdGameId":"1234","side":"YES",
              "modelProbability":.70,
              "kickoffUTC":self.kick.isoformat(),
              "homeTeam":"AAA","awayTeam":"BBB",
              "selectionLabel":"AAA",
              "researchOnly":True,"officialEligible":False
          }]}
        self.book={"yes_dollars":[["0.3000","5.00"]],
                   "no_dollars":[["0.6000","3.00"],["0.5500","1.00"]]}
        self.market={"ticker":"KXNCAAFGAME-26NOV07TEST-AAA",
                     "status":"active","series_ticker":"KXNCAAFGAME"}
        self.series={"ticker":"KXNCAAFGAME","fee_type":"quadratic",
                     "fee_multiplier":1}
    def test_inverse_book_and_depth(self):
        yes=simulated_taker(self.book,"YES",D("1"))
        self.assertTrue(yes["depth_available"])
        self.assertAlmostEqual(yes["top_ask"],.4)
        no=simulated_taker(self.book,"NO",D("1"))
        self.assertAlmostEqual(no["vwap_ask"],.7)
        yes_4=simulated_taker(self.book,"YES",D("4"))
        self.assertAlmostEqual(yes_4["vwap_ask"],.4125)
        self.assertFalse(simulated_taker(self.book,"YES",D("7"))["depth_available"])
    def test_fee_multiplier_and_round_up(self):
        mult,error=fee_spec(self.series,self.market)
        self.assertIsNone(error)
        self.assertEqual(taker_fee(D("1"),D(".40"),mult),D(".02"))
        with_maker={**self.series,"fee_type":"quadratic_with_maker_fees"}
        self.assertEqual(fee_spec(with_maker,self.market)[0],D("1"))
        s={**self.series};del s["fee_multiplier"]
        self.assertIsNotNone(fee_spec(s,self.market)[1])
    def test_research_only_capture(self):
        snap=audit(self.research,self.now,
          market_fn=lambda tick:self.market,
          orderbook_fn=lambda tick:self.book,
          series_fn=lambda tick:self.series,clock=lambda:self.now)
        self.assertEqual(len(snap["observations"]),1)
        row=snap["observations"][0]
        self.assertAlmostEqual(row["book_vwap_ask"],.4)
        self.assertAlmostEqual(row["net_expected_dollars_per_sample"],.28)
        self.assertEqual(row["taker_fee_estimate_dollars"],.02)
        self.assertFalse(row["official_eligible"])
        self.assertFalse(row["qb_game_report_verified"])
        self.assertFalse(snap["production_eligible"])
    def test_stale_model_prevents_capture(self):
        data=dict(self.research)
        data["modelCapturedAtUTC"]=(self.now-dt.timedelta(hours=19)).isoformat()
        self.assertEqual(select_rows(data,self.now)[1],"MODEL RESEARCH STALE")
        snap=audit(data,self.now,market_fn=lambda ticker:self.market)
        self.assertEqual(snap["observations"],[])
    def test_archive_dedupe_and_settlement(self):
        snap=audit(self.research,self.now,
          market_fn=lambda tick:self.market,
          orderbook_fn=lambda tick:self.book,
          series_fn=lambda tick:self.series,clock=lambda:self.now)
        a=merge_snapshot({},snap)
        a=merge_snapshot(a,snap)
        self.assertEqual(len(a["2026-11-07"]["observations"]),1)
        a=settle_archives(a,self.kick+dt.timedelta(hours=1),
            market_fn=lambda tick:{**self.market,"status":"settled","result":"yes"})
        report=summarize(a,self.kick+dt.timedelta(hours=1),snap)
        self.assertEqual(report["contract_side_outcomes"],1)
        self.assertAlmostEqual(report["forward_contract_side_brier"],.09)
        self.assertFalse(report["production_eligible"])
        self.assertEqual(report["closing_price_proxy_pairs"],0)
    def test_requires_two_distinct_closing_proxy_observations(self):
        initial=audit(self.research,self.now,market_fn=lambda t:self.market,
            orderbook_fn=lambda t:self.book,series_fn=lambda t:self.series,
            clock=lambda:self.now)
        archive=merge_snapshot({},initial)
        self.assertEqual(summarize(archive,self.now,initial)["closing_price_proxy_pairs"],0)
        later=self.now+dt.timedelta(minutes=60)
        more=audit(self.research,later,market_fn=lambda t:self.market,
            orderbook_fn=lambda t:self.book,series_fn=lambda t:self.series,
            clock=lambda:later)
        archive=merge_snapshot(archive,more)
        self.assertEqual(summarize(archive,later,more)["closing_price_proxy_pairs"],1)
    def test_no_false_settlement(self):
        snap=audit(self.research,self.now,
          market_fn=lambda tick:self.market,
          orderbook_fn=lambda tick:self.book,
          series_fn=lambda tick:self.series,clock=lambda:self.now)
        a=merge_snapshot({},snap)
        a=settle_archives(a,self.kick+dt.timedelta(hours=1),
          market_fn=lambda tick:{**self.market,"status":"closed","result":"yes"})
        self.assertEqual(a["2026-11-07"]["settlements"],{})

if __name__=="__main__":unittest.main()
