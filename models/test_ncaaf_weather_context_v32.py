#!/usr/bin/env python3
import datetime as dt
import unittest
from ncaaf_weather_context_v32 import enrich

class WeatherTests(unittest.TestCase):
    def test_stadium_check_and_forecast_context_research_only(self):
        now=dt.datetime(2026,11,7,19,tzinfo=dt.timezone.utc)
        research={"market_research":{"research_comparisons":[
          {"cfbd_game_id":"1"},{"cfbd_game_id":"1"},{"cfbd_game_id":"2"}]}}
        games=[
          {"id":1,"startDate":"2026-11-08T02:00:00Z",
           "completed":False,"venueId":12},
          {"id":2,"startDate":"2026-11-08T02:00:00Z",
           "completed":False,"venueId":13}]
        venues=[{"id":12,"name":"Stadium A","dome":False,
                 "latitude":33.0,"longitude":-82.0},
                {"id":13,"name":"Stadium B","dome":True}]
        def fake(lat,lon,kickoff,now):
            return {"model_source":"Mock weather","weather_effect_on_probability_calibrated":False},None
        x=enrich(research,games,venues,now,fake)
        self.assertEqual(x["counts"]["matched_events"],2)
        self.assertEqual(x["counts"]["forecast_available"],1)
        self.assertEqual(x["counts"]["indoor_venue"],1)
        self.assertFalse(x["production_eligible"])
        self.assertFalse(x["official_eligible"])
        self.assertEqual(x["weather_for_cfbd_game_id"]["2"]["status"],"INDOOR VENUE")
    def test_unknown_roof_fails_closed(self):
        now=dt.datetime(2026,11,7,19,tzinfo=dt.timezone.utc)
        x=enrich({"market_research":{"research_comparisons":[{"cfbd_game_id":"1"}]}},
          [{"id":1,"startDate":"2026-11-08T02:00:00Z","completed":False,"venueId":3}],
          [{"id":3,"dome":None,"latitude":35,"longitude":-80}],now,
          lambda *_: (_ for _ in ()).throw(RuntimeError("should not fetch")))
        self.assertEqual(x["counts"]["unverified_venue"],1)
        self.assertEqual(x["counts"]["forecast_available"],0)
if __name__=="__main__":unittest.main()
