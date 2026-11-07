#!/usr/bin/env python3
"""Offline tests for CFBD FBS-only and strict pregame advanced metrics."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from ncaaf_cfbd_ingest_v31 import build_snapshot, summarize_team, DataError, instant

def astat(gid, team, success=.49, ppa=.2):
    return {"gameId":gid,"team":team,
            "offense":{"ppa":ppa,"successRate":success,"plays":68},
            "defense":{"ppa":-.12,"successRate":.41,"plays":72}}

class Tests(unittest.TestCase):
    def test_fbs_membership_gate(self):
        with self.assertRaises(DataError):
            build_snapshot(2026,[],[],[],dt.datetime.now(dt.timezone.utc))
    def test_missing_advanced_is_not_fabricated(self):
        self.assertIsNone(summarize_team("X",["1","2","3"],{},3))
    def test_no_future_stat_leakage_and_fbs_only(self):
        teams=[{"school":"Team"+str(i)} for i in range(90)]
        now=dt.datetime(2026,11,7,15,tzinfo=dt.timezone.utc)
        games=[]
        stats=[]
        for i in range(5):
            day=dt.date(2026,10,20)+dt.timedelta(days=i)
            games.append({"id":i+1,"homeTeam":"Team1","awayTeam":"Team2",
                "startDate":day.isoformat()+"T15:00:00Z","completed":True})
            stats.extend([astat(i+1,"Team1"),astat(i+1,"Team2")])
        games.append({"id":99,"homeTeam":"Team1","awayTeam":"Team2",
            "startDate":"2026-11-08T15:00:00Z","completed":False})
        games.append({"id":100,"homeTeam":"Team1","awayTeam":"FCS Club",
            "startDate":"2026-11-08T16:00:00Z","completed":False})
        # This game is completed after snapshot and contains extreme garbage stats.
        games.append({"id":200,"homeTeam":"Team1","awayTeam":"Team2",
            "startDate":"2026-11-10T15:00:00Z","completed":True})
        stats.extend([astat(200,"Team1",.99,99),astat(200,"Team2",.99,99)])
        snap=build_snapshot(2026,games,stats,teams,now)
        self.assertEqual(snap["upcoming_fbs_games"],1)
        self.assertEqual(snap["upcoming_with_minimum_advanced_data"],1)
        self.assertFalse(snap["official_eligible"])
        self.assertEqual(snap["upcoming"][0]["home"]["games"],5)
        self.assertAlmostEqual(snap["upcoming"][0]["home"]["offense_ppa_per_play"],.2)
if __name__=="__main__":
    unittest.main()
