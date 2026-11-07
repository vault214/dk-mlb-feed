#!/usr/bin/env python3
"""NCAAF v3.2 offline tests. No credentials, network, or live betting."""
import datetime as dt
import unittest
from ncaaf_cfbd_model_v32 import (
    FEATURES, build_season, stats_by_game, match_markets,
    fit_scaler, fit_logistic, fit_platt, probability, train_and_evaluate
)

def stat(gid,team,ppa=.1,success=.5):
    return {"gameId":gid,"team":team,
        "offense":{"ppa":ppa,"successRate":success,"plays":70},
        "defense":{"ppa":ppa-.06,"successRate":.43,"plays":67}}

def game(gid,day,h="Texas",a="Missouri",hs=14,as_=10,completed=True):
    return {"id":gid,"homeTeam":h,"awayTeam":a,
       "startDate":day+"T18:00:00Z","completed":completed,
       "homePoints":hs if completed else None,"awayPoints":as_ if completed else None,
       "neutralSite":False,"startTimeTBD":False}

TEAMS=[{"school":"Team"+str(i)} for i in range(90)]+[
    {"school":"Texas","abbreviation":"TEX"},
    {"school":"Missouri","abbreviation":"MIZZ"}]

class TestNCAAFModelV32(unittest.TestCase):
    def test_season_features_are_strictly_prior_date(self):
        earlier=[game(i, "2026-10-%02d"%(10+i),hs=20,as_=10) for i in range(1,5)]
        today=[game(10,"2026-11-07",hs=300,as_=2),
               game(11,"2026-11-07",hs=3,as_=0)]
        tomorrow=game(12,"2026-11-08",completed=False)
        stats=[]
        for g in earlier+today:
            stats.extend([stat(g["id"],"Texas",ppa=.2 if g["id"]<10 else 99),
                          stat(g["id"],"Missouri",ppa=-.1 if g["id"]<10 else 99)])
        now=dt.datetime(2026,11,7,20,tzinfo=dt.timezone.utc)
        output=build_season(2026,earlier+today+[tomorrow],stats,TEAMS,now)
        rows=[x for x in output["labeled"] if x["date_et"]=="2026-11-07"]
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["features"],rows[1]["features"])
        self.assertEqual(len(output["upcoming"]),1)
        self.assertEqual(output["upcoming"][0]["feature_cutoff_exclusive_et"],"2026-11-08")
        self.assertFalse(output["upcoming"][0]["production_eligible"])

    def test_pair_mapping_requires_two_verified_moneyline_labels(self):
        now=dt.datetime(2026,11,7,18,tzinfo=dt.timezone.utc)
        soon={"cfbd_game_id":"a","date_et":"2026-11-07","home_team":"Texas",
           "away_team":"Missouri","kickoff_utc":"2026-11-07T22:00:00+00:00",
           "features":[0.0]*len(FEATURES)}
        board={"board_date_et":"2026-11-07","markets":[
            {"ticker":"A","event_ticker":"M1","market_category":"game",
             "event_date":"2026-11-07","status":"active",
             "yes_selection":"Texas","yes_ask":.55,"no_ask":.46},
            {"ticker":"B","event_ticker":"M1","market_category":"game",
             "event_date":"2026-11-07","status":"active",
             "yes_selection":"Missouri","yes_ask":.46,"no_ask":.55},
            {"ticker":"C","event_ticker":"M2","market_category":"game",
             "event_date":"2026-11-07","status":"active",
             "yes_selection":"Texas","yes_ask":.5,"no_ask":.51}]}
        sc=[(0,1)]*len(FEATURES)
        matched=match_markets(board,TEAMS,[soon],now,sc,[0.0]*(len(FEATURES)+1),[1,0])
        self.assertEqual(matched["matched_events"],1)
        self.assertEqual(matched["compared_contract_sides"],4)
        self.assertIsNone(matched["official"])
        self.assertTrue(all(not r["quote_timestamp_verified"] for r in matched["research_comparisons"]))
        stale=match_markets({"board_date_et":"2026-11-06","markets":[]},TEAMS,[soon],now,sc,[0]*(len(FEATURES)+1),[1,0])
        self.assertEqual(stale["status"],"BOARD DATE STALE")
    def test_unknown_alias_and_fcs_are_not_guessed(self):
        now=dt.datetime(2026,11,7,18,tzinfo=dt.timezone.utc)
        board={"board_date_et":"2026-11-07","markets":[
            {"ticker":"X","event_ticker":"T","market_category":"game",
             "event_date":"2026-11-07","status":"active","yes_selection":"Texas","yes_ask":.5},
            {"ticker":"Y","event_ticker":"T","market_category":"game",
             "event_date":"2026-11-07","status":"active","yes_selection":"FCS Tigers","yes_ask":.5}]}
        x=match_markets(board,TEAMS,[],now,[(0,1)]*len(FEATURES),[0]*(len(FEATURES)+1),[1,0])
        self.assertEqual(x["matched_events"],0)
        self.assertFalse(x["production_eligible"])

if __name__=="__main__":
    unittest.main()
