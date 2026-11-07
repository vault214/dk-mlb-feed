#!/usr/bin/env python3
"""Research-only ESPN historical final-score collection for seven leagues.
ESPN site endpoints are unofficial; verify completeness and rights before reliance.
No Kalshi quotes, pregame injury verification, or player-level data is inferred.
"""
import argparse
import datetime as dt
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

CONFIG = {
    "NCAAF": ("football", "college-football", {"groups": "80"}),
    "NFL": ("football", "nfl", {}),
    "NBA": ("basketball", "nba", {}),
    "NHL": ("hockey", "nhl", {}),
    "NCAAB": ("basketball", "mens-college-basketball", {"groups": "50"}),
    "MLB": ("baseball", "mlb", {}),
    "WNBA": ("basketball", "wnba", {}),
}
ET = ZoneInfo("America/New_York")

def scoreboard_url(league, day):
    sport, slug, extra = CONFIG[league]
    params = {"dates": day.strftime("%Y%m%d"), "limit": "500", **extra}
    return ("https://site.api.espn.com/apis/site/v2/sports/" +
            sport + "/" + slug + "/scoreboard?" + urllib.parse.urlencode(params))

def fetch_day(league, day, tries=3):
    url = scoreboard_url(league, day)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ResearchSportsModel/3.0"})
            with urllib.request.urlopen(req, timeout=30) as f:
                payload = json.load(f)
            if not isinstance(payload.get("events"), list):
                raise ValueError("missing events list")
            if len(payload["events"]) >= 500:
                raise ValueError("possible scoreboard truncation")
            return payload, url
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            if attempt == tries - 1:
                raise RuntimeError(str(exc)) from exc
            time.sleep(0.5 * (attempt + 1))

def parse_final(event, source, league):
    if not isinstance(event, dict) or not event.get("id"):
        return None
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    status = (comp.get("status") or event.get("status") or {}).get("type") or {}
    if not status.get("completed"):
        return None
    season_type = (event.get("season") or {}).get("type")
    if season_type == 1:  # exclude exhibition/preseason, keep regular and post
        return None
    teams = comp.get("competitors") or []
    home = next((x for x in teams if x.get("homeAway") == "home"), None)
    away = next((x for x in teams if x.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    try:
        home_points = int(home["score"])
        away_points = int(away["score"])
        home_id = str(home["team"]["id"])
        away_id = str(away["team"]["id"])
        instant = dt.datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        if instant.tzinfo is None or home_points < 0 or away_points < 0:
            return None
    except (KeyError, ValueError, TypeError):
        return None
    return {
        "id": str(event["id"]), "league": league,
        "date": instant.astimezone(ET).date().isoformat(),
        "start_utc": instant.astimezone(dt.timezone.utc).isoformat(),
        "home_id": home_id, "away_id": away_id,
        "home_team": home["team"].get("displayName", home_id),
        "away_team": away["team"].get("displayName", away_id),
        "home_points": home_points, "away_points": away_points,
        "neutral_site": bool(comp.get("neutralSite", False)),
        "source": source,
    }

def collect(league, start, end):
    day = dt.date.fromisoformat(start)
    end_date = dt.date.fromisoformat(end)
    if end_date < day:
        raise ValueError("end precedes start")
    games, failures = {}, []
    dates_checked = 0
    while day <= end_date:
        try:
            response, url = fetch_day(league, day)
            for event in response["events"]:
                record = parse_final(event, url, league)
                if record is not None:
                    games[record["id"]] = record
        except RuntimeError as exc:
            failures.append({"date": day.isoformat(), "error": str(exc)[:300]})
        dates_checked += 1
        day += dt.timedelta(days=1)
    return {
        "schema_version": 3, "league": league, "start": start, "end": end,
        "dates_checked": dates_checked, "failed_dates": failures,
        "games": sorted(games.values(), key=lambda x: (x["date"], x["start_utc"], x["id"])),
        "source": "unofficial ESPN site scoreboard; game scores only",
        "production_eligible": False,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--league", choices=CONFIG, required=True)
    p.add_argument("--start", required=True); p.add_argument("--end", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = collect(args.league, args.start, args.end)
    pathlib.Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"league": args.league, "games": len(result["games"]),
                      "failed_dates": len(result["failed_dates"]),
                      "dates_checked": result["dates_checked"],
                      "production_eligible": False}))

if __name__ == "__main__":
    main()
