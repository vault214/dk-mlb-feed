#!/usr/bin/env python3
"""Offline weather history tests: only fixed pre-event forecasts are archived."""
import datetime as dt
import unittest

from ncaaf_weather_history_v34 import parse_hourly, fixtures_by_season, collect

UTC=dt.timezone.utc
KICK=dt.datetime(2025,11,1,21,tzinfo=UTC)

class WeatherHistoryTests(unittest.TestCase):
 def test_valid_fixed_day1_prior_weather(self):
    payload={"hourly":{"time":["2025-11-01T20:00","2025-11-01T21:00"],
      "wind_speed_10m_previous_day1":[5,14],
      "precipitation_previous_day1":[0,.8],
      "temperature_2m_previous_day1":[65,52]}}
    r,e=parse_hourly(payload,KICK)
    self.assertIsNone(e)
    self.assertEqual(r["forecast_lead_hours"],24)
    self.assertEqual(r["wind_speed_10m"],14)
    self.assertEqual(r["precipitation"],.8)
    self.assertEqual(r["temperature_2m"],52)
 def test_reject_missing_forecast(self):
    r,e=parse_hourly({"hourly":{"time":["2025-11-01T21:00"]}},KICK)
    self.assertIsNone(r);self.assertIn("MISSING",e)
 def test_outdoor_only_no_hindsight_indoor(self):
    venues=[{"id":5,"dome":False,"name":"Outdoor","latitude":35,"longitude":-80},
            {"id":6,"dome":True,"name":"Dome","latitude":35,"longitude":-80}]
    games={2025:[
       {"id":1,"completed":True,"startDate":"2025-11-01T21:00:00Z",
        "venueId":5,"homeTeam":"A","awayTeam":"B","homePoints":28,"awayPoints":10},
       {"id":2,"completed":True,"startDate":"2025-11-01T21:00:00Z",
        "venueId":6,"homeTeam":"C","awayTeam":"D","homePoints":24,"awayPoints":17}]}
    fixture=fixtures_by_season(games,venues)
    self.assertEqual(len(fixture),1)
    self.assertEqual(fixture[0]["cfbd_game_id"],"1")
 def test_research_only_archive(self):
    fixture=[{"cfbd_game_id":"1","year":2025,"kickoff_utc":KICK.isoformat(),
      "home_team":"A","away_team":"B","home_points":28,"away_points":10,
      "venue_id":5,"stadium":"X","latitude":35,"longitude":-80}]
    fake=lambda lat,lon,kick:({
        "forecast_lead_hours":24,"wind_speed_10m":12,
        "precipitation":0,"temperature_2m":55},None)
    data,health=collect(fixture,[],KICK+dt.timedelta(days=1),fake,1)
    self.assertEqual(health["new_forecasts_archived"],1)
    self.assertFalse(data["records"][0]["model_probability_adjusted"])
    self.assertFalse(health["production_eligible"])
 def test_bad_history_lead_rejected(self):
    fixture=[{"cfbd_game_id":"1","year":2025,"kickoff_utc":KICK.isoformat(),
      "home_team":"A","away_team":"B","home_points":28,"away_points":10,
      "venue_id":5,"stadium":"X","latitude":35,"longitude":-80}]
    fake=lambda lat,lon,kick:({"forecast_lead_hours":0,"wind_speed_10m":12},None)
    data,health=collect(fixture,[],KICK,fake,1)
    self.assertEqual(health["new_forecasts_archived"],0)
    self.assertEqual(health["archived_pregame_forecast_games"],0)
if __name__=="__main__":unittest.main()
