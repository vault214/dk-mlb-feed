#!/usr/bin/env python3
"""NCAAF v3.5 game-by-game eligibility tests: no guesswork or silent approvals."""
import datetime as dt
import unittest
from ncaaf_game_eligibility_v35 import screen,weather_check,UTC

NOW=dt.datetime(2026,11,7,17,tzinfo=UTC)
KICK="2026-11-07T22:00:00+00:00"
AT="2026-11-07T16:59:30+00:00"
GID="123"
TICK="KXNCAAFGAME-TEST-HOME"

def inputs():
    row={"cfbdGameId":GID,"homeTeam":"Texas","awayTeam":"Missouri",
         "kickoffUTC":KICK,"side":"YES","ticker":TICK,
         "modelProbability":.7,"researchOnly":True,
         "weatherForecastStatus":"WEATHER FORECAST SOURCED",
         "weatherSnapshot":{"gust_mph":12,"precipitation_probability_pct":10,"temperature_f":67}}
    research={"modelCapturedAtUTC":"2026-11-07T16:45:00+00:00",
              "rows":[row]}
    av={"game_review_queue":[{"cfbd_game_id":GID,
       "report_discovery_hub":"https://www.secsports.com/fbreports",
       "game_specific_primary_report_url":None,
       "report_published_at_utc":None,
       "two_teams_report_coverage_confirmed":False,
       "starting_qb_names_confirmed":False,
       "starting_qb_statuses_verified":False,
       "material_absences_verified":False,
       "risk_adjustment_backtested":False}]}
    model={"calibration":{"holdout_games":288,"improvement":.03,"ece":.058}}
    settle={"unique_game_winner_samples":0,"forward_unique_game_brier":None}
    obs={"cfbdGameId":GID,"ticker":TICK,"side":"YES",
         "quote_observed_utc":AT,"kickoffUTC":KICK,
         "book_vwap_ask":.48,"sample_contracts":1,
         "taker_fee_estimate_dollars":.02,
         "market_open_at_observation":True,
         "depth_scenarios_contracts":{"1":{"depth_available":True}}}
    return research,av,model,settle,{"2026-11-07":{"observations":[obs]}}

class TestEligibility(unittest.TestCase):
    def test_holds_even_with_apparent_large_edge(self):
        x=screen(*inputs(),NOW)
        self.assertEqual(x["matched_games"],1)
        self.assertEqual(x["games_blocked"],1)
        row=x["games"][0]
        self.assertEqual(row["valid_live_quote_sides"],1)
        self.assertTrue(row["research_side_comparisons"][0]["research_edge_at_least_5pp"])
        self.assertFalse(row["official_eligible"])
        self.assertTrue(any("QB" in reason for reason in row["reasons"]))
        self.assertTrue(any("FORWARD" in reason for reason in row["reasons"]))
    def test_severe_weather_block(self):
        r,*rest=inputs()
        r["rows"][0]["weatherSnapshot"]["gust_mph"]=32
        z=screen(r,*rest,NOW)
        self.assertIn("SEVERE WEATHER UNCERTAINTY — CONSERVATIVE PASS",z["games"][0]["reasons"])
        self.assertFalse(z["official_eligible"])
    def test_weather_status_only_never_counts_as_clear(self):
        self.assertFalse(weather_check({"weatherForecastStatus":"WEATHER FORECAST SOURCED"})["clear"])
    def test_expired_quote_not_fresh(self):
        x=list(inputs())
        x[4]["2026-11-07"]["observations"][0]["quote_observed_utc"]="2026-11-07T16:48:00+00:00"
        z=screen(*x,NOW)
        self.assertEqual(z["games"][0]["valid_live_quote_sides"],0)
        self.assertTrue(any("FRESH" in y for y in z["games"][0]["reasons"]))
    def test_kickoff_blocks(self):
        z=screen(*inputs(),NOW+dt.timedelta(hours=6))
        self.assertEqual(z["games"][0]["status"],"NOT PREGAME")
        self.assertFalse(z["official_eligible"])
    def test_future_quote_not_used(self):
        x=list(inputs())
        x[4]["2026-11-07"]["observations"][0]["quote_observed_utc"]="2026-11-07T17:30:00+00:00"
        z=screen(*x,NOW)
        self.assertEqual(z["games"][0]["valid_live_quote_sides"],0)
    def test_unverified_qb_triage_only_if_observed_pregame(self):
        triage={"generatedAtUTC":"2026-11-07T16:55:00+00:00",
                "games":[{"cfbd_game_id":GID,
                    "secondary_qb_risk_flags":[{"side":"home","name":"Sample QB",
                       "secondary_status":"OUT","source_type":
                       "THIRD-PARTY TRANSCRIPTION - NOT OFFICIAL EVIDENCE"}]}]}
        z=screen(*inputs(),NOW,None,triage)
        self.assertEqual(len(z["games"][0]["secondary_qb_risk_flags_unverified"]),1)
        self.assertFalse(z["games"][0]["secondary_qb_flags_used_for_model"])
        self.assertFalse(z["games"][0]["official_eligible"])
        triage["generatedAtUTC"]="2026-11-07T23:00:00+00:00"
        z=screen(*inputs(),NOW,None,triage)
        self.assertEqual(z["games"][0]["secondary_qb_risk_flags_unverified"],[])
    def test_third_party_report_link_never_unblocks_evidence(self):
        lead={"games":[{"cfbd_game_id":GID,
               "supplemental_url":"https://kickoffstatus.com/games/2026-11-07-texas-at-missouri/",
               "status":"THIRD-PARTY GAME INDEX LINK — NOT VERIFIED"}]}
        x=screen(*inputs(),NOW,lead)
        row=x["games"][0]
        self.assertIsNotNone(row["supplemental_report_lead_url"])
        self.assertFalse(row["supplemental_data_counted_as_verified"])
        self.assertFalse(row["game_specific_report_verified"])
        self.assertFalse(row["official_eligible"])
        self.assertIn("PRIMARY GAME-SPECIFIC AVAILABILITY DOCUMENT UNVERIFIED",row["reasons"])
    def test_document_source_before_kickoff_without_report_published_is_not_qb_confirmation(self):
        inputs_ = list(inputs())
        review=inputs_[1]["game_review_queue"][0]
        review.update({"two_teams_report_coverage_confirmed":True,
                       "game_specific_primary_report_url":"https://www.secsports.com/games/official-matchup-document",
                       "report_observed_at_utc":"2026-11-07T16:00:00+00:00"})
        row=screen(*inputs_,NOW)["games"][0]
        self.assertTrue(row["game_specific_report_verified"])
        self.assertFalse(row["qb_and_injury_verified"])
        self.assertIn("BOTH STARTING QB STATUSES NOT VERIFIED",row["reasons"])
    def test_no_auto_eligibility_even_if_mocks_pass(self):
        x=list(inputs())
        review=x[1]["game_review_queue"][0]
        review.update({
          "two_teams_report_coverage_confirmed":True,
          "starting_qb_names_confirmed":True,
          "starting_qb_statuses_verified":True,
          "material_absences_verified":True,
          "risk_adjustment_backtested":True,
          "game_specific_primary_report_url":"https://www.secsports.com/report/fixture123",
          "report_published_at_utc":"2026-11-07T16:00:00+00:00",
          "report_observed_at_utc":"2026-11-07T16:20:00+00:00"})
        x[3].update({"unique_game_winner_samples":80,"forward_unique_game_brier":.20})
        z=screen(*x,NOW)
        self.assertEqual(z["games"][0]["reasons"],[])
        self.assertFalse(z["games"][0]["official_eligible"])
        self.assertFalse(z["official_eligible"])
if __name__=="__main__":
    unittest.main()
