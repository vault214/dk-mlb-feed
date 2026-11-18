#!/usr/bin/env python3
"""Capture and grade ATP/WTA paper picks from public pregame inputs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import unescape
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ncaaf_forward_audit_v33 import D, fee_spec, get_orderbook, levels, taker_fee

OUT = Path(__file__).resolve().parents[1] / "dashboard" / "tennis-picks.json"
ET = ZoneInfo("America/New_York")
API = "https://api.elections.kalshi.com/trade-api/v2"
RATINGS = "https://tennisabstract.com/reports/{}_elo_ratings.html"
SCORES = "https://site.api.espn.com/apis/site/v2/sports/tennis/{}/scoreboard"
TOURS = {"ATP": "KXATPMATCH", "WTA": "KXWTAMATCH"}
# Only named surfaces we can identify reliably. Unknown surfaces get no pick.
SURFACES = {
    "hard": ("atp world tour finals", "atp finals", "wta finals", "australian open",
             "us open", "indian wells", "miami open", "cincinnati open", "canadian open",
             "shanghai masters", "paris masters", "qatar open", "dubai championships"),
    "clay": ("french open", "roland garros", "monte carlo", "madrid open", "italian open",
             "barcelona open"),
    "grass": ("wimbledon", "halle open", "queen s club", "eastbourne"),
}


def get(url, **query):
    if query:
        url += "?" + urlencode(query)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urlopen(request, timeout=18) as response:
        return response.read().decode("utf-8")


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


def key(name):
    normalized = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in normalized if c.isascii() and c.isalnum())


def parse_ratings(html):
    date = re.search(r"Last update:\s*(\d{4}-\d{2}-\d{2})", html)
    table = re.search(r'<table id="reportable".*?</table>', html, re.S)
    if date is None or table is None:
        raise ValueError("ratings table unavailable")
    players = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table.group(), re.S):
        cells = [unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 11 or not cells[0].isdigit():
            continue
        players[key(cells[1])] = {surface: float(cells[index])
                                  for surface, index in (("hard", 6), ("clay", 8), ("grass", 10))
                                  if re.fullmatch(r"\d+(?:\.\d+)?", cells[index])}
    if not players:
        raise ValueError("no ratings parsed")
    return datetime.fromisoformat(date[1]).date(), players


def probability(rating, opponent, best_of):
    p = 1 / (1 + 10 ** ((opponent - rating) / 400))
    if best_of == 3:
        return p
    # Recover the implied independent set probability, then price first-to-three.
    low, high = 0.0, 1.0
    for _ in range(34):
        mid = (low + high) / 2
        if mid ** 2 * (3 - 2 * mid) < p:
            low = mid
        else:
            high = mid
    s = (low + high) / 2
    return s ** 3 * (1 + 3 * (1 - s) + 6 * (1 - s) ** 2)


def market_page(series):
    cursor = ""
    while True:
        page = json.loads(get(API + "/events", series_ticker=series, status="open",
                              with_nested_markets="true", with_milestones="true",
                              limit=100, cursor=cursor))
        milestones = {m.get("details", {}).get("main_game_event_ticker"): m
                      for m in page.get("milestones", [])}
        for event in page["events"]:
            milestone = milestones.get(event["event_ticker"])
            if milestone:
                yield event, milestone
        cursor = page.get("cursor")
        if not cursor:
            return


def scheduled(tour, day):
    feed = json.loads(get(SCORES.format(tour.lower()), dates=day.strftime("%Y%m%d")))
    for event in feed["events"]:
        for group in event.get("groupings", []):
            if group.get("grouping", {}).get("slug") not in {"mens-singles", "womens-singles"}:
                continue
            for match in group["competitions"]:
                if not match.get("timeValid") or match["status"]["type"]["state"] != "pre":
                    continue
                players = frozenset(key(c["athlete"]["displayName"])
                                    for c in match["competitors"]
                                    if c.get("athlete", {}).get("displayName"))
                start = utc(match["startDate"])
                if len(players) == 2 and start.astimezone(ET).date() == day:
                    yield players, start


def evaluate(tour, day):
    now = datetime.now(timezone.utc)
    ratings_day, ratings = parse_ratings(get(RATINGS.format(tour.lower())))
    if not timedelta(0) <= day - ratings_day <= timedelta(days=14):
        raise ValueError("ratings out of date")
    schedule = list(scheduled(tour, day))
    series = json.loads(get(API + "/series/" + TOURS[tour]))["series"]
    if series.get("ticker") != TOURS[tour]:
        raise ValueError("series identity mismatch")
    candidates, matched = [], 0
    for event, milestone in market_page(TOURS[tour]):
        details = milestone["details"]
        start = utc(milestone["start_date"])
        if (milestone["type"] != "tennis_tournament_singles"
                or details.get("status") != "not_started"
                or start.astimezone(ET).date() != day or start <= now):
            continue
        tournament = details.get("tournament_name", "")
        surface = next((s for s, names in SURFACES.items()
                        if any(key(n) in key(tournament) for n in names)), None)
        best_of = str(details.get("best_of"))
        if not surface or best_of not in {"3", "5"}:
            continue
        markets = event.get("markets", [])
        if len(markets) != 2 or not event.get("mutually_exclusive"):
            continue
        names = [key(m.get("yes_sub_title", "")) for m in markets]
        starts = [actual for pair, actual in schedule
                  if pair == frozenset(names) and abs(actual - start) <= timedelta(hours=2)]
        if len(starts) != 1:
            continue
        cutoff = min(starts[0], start)
        if cutoff <= datetime.now(timezone.utc) + timedelta(minutes=10):
            continue
        matched += 1
        point_ratings = [ratings.get(name, {}).get(surface) for name in names]
        if None in point_ratings:
            continue
        for index, market in enumerate(markets):
            candidate = price_pick(series, market, point_ratings[index], point_ratings[1-index], int(best_of))
            if not candidate:
                continue
            book = get_orderbook(market["ticker"])
            yes, no = levels(book.get("yes_dollars")), levels(book.get("no_dollars"))
            if not yes or not no:
                continue
            candidate = price_pick(series, market | {
                "yes_bid_dollars": yes[0][0], "yes_ask_dollars": 1 - no[0][0],
                "yes_ask_size_fp": no[0][1],
            }, point_ratings[index], point_ratings[1-index], int(best_of))
            if not candidate or cutoff <= datetime.now(timezone.utc) + timedelta(minutes=10):
                continue
            candidates.append(candidate | {
                "ticker": market["ticker"], "eventTicker": event["event_ticker"],
                "selection": market["yes_sub_title"], "opponent": markets[1-index]["yes_sub_title"],
                "matchStartUTC": cutoff.isoformat(), "observedAtUTC": datetime.now(timezone.utc).isoformat(),
                "dateET": day.isoformat(), "tour": tour, "tournament": tournament,
                "ratingsDate": ratings_day.isoformat(), "surface": surface, "bestOf": int(best_of),
            })
    return candidates, {"status": "OK", "scheduledSingles": len(schedule), "matchedMarkets": matched,
                        "eligibleCandidates": len(candidates), "ratingsDate": ratings_day.isoformat()}


def price_pick(series, market, rating, opponent, best_of):
    try:
        ask = float(market["yes_ask_dollars"])
        bid = float(market["yes_bid_dollars"])
        size = float(market["yes_ask_size_fp"])
    except (KeyError, TypeError, ValueError):
        return None
    if (market.get("status") != "active" or market.get("result") != ""
            or not 0 < bid <= ask < 1 or round(ask - bid, 4) > 0.04 or not size >= 10):
        return None
    p = probability(rating, opponent, best_of)
    multiplier, _ = fee_spec(series, market)
    if multiplier is None:
        return None
    fee = float(taker_fee(D("1"), D(str(ask)), multiplier))
    edge = p - ask - fee
    if p > 0.75 or edge < 0.025:
        return None
    return {"probability": p, "ask": ask, "fee": fee, "edge": edge, "rating": rating,
            "opponentRating": opponent, "result": "PENDING", "plUnits": None}


def capture(candidates, ledger, day):
    for track in ("OFFICIAL", "SHADOW"):
        if any(p["track"] == track and p["dateET"] == day for p in ledger):
            continue
        booked = {p["eventTicker"] for p in ledger}
        if track == "OFFICIAL":
            eligible = [p for p in candidates if p["probability"] >= 0.48 and p["edge"] >= 0.05]
            ranking = lambda p: (p["edge"], p["probability"])
        else:
            eligible = [p for p in candidates if p["probability"] < 0.50]
            ranking = lambda p: (p["edge"], -p["probability"])
        pick = max((p for p in eligible if p["eventTicker"] not in booked), key=ranking, default=None)
        if pick:
            ledger.append(pick | {"track": track, "stakeUnits": 1.0 if track == "OFFICIAL" else 0.5})


def settle(pick):
    market = json.loads(get(API + "/markets/" + pick["ticker"]))["market"]
    if market.get("status") not in {"finalized", "settled"}:
        return
    result = market.get("result")
    if result == "yes":
        payout = 1.0
    elif result == "no":
        payout = 0.0
    elif result == "scalar":
        payout = float(market["settlement_value_dollars"])
        if not 0 <= payout <= 1:
            raise ValueError("invalid scalar settlement")
    else:
        return
    cost = pick["ask"] + pick["fee"]
    pick["result"] = {"yes": "WIN", "no": "LOSS", "scalar": "SCALAR"}[result]
    pick["plUnits"] = round(pick["stakeUnits"] * (payout / cost - 1), 5)


def main():
    now = datetime.now(timezone.utc)
    day = now.astimezone(ET).date()
    ledger = json.loads(OUT.read_text())["picks"] if OUT.exists() else []
    candidates, sources, unresolved = [], {}, []
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(settle, p): p["ticker"] for p in ledger
                   if p["result"] == "PENDING" and utc(p["matchStartUTC"]) < now}
        tours = {tour: pool.submit(evaluate, tour, day) for tour in TOURS}
        for tour, future in tours.items():
            try:
                rows, sources[tour] = future.result()
                candidates.extend(rows)
            except (OSError, ValueError, KeyError, TypeError) as error:
                sources[tour] = {"status": "UNAVAILABLE", "reason": type(error).__name__}
        for future, ticker in pending.items():
            try:
                future.result()
            except (OSError, ValueError, KeyError, TypeError):
                unresolved.append(ticker)
    capture(candidates, ledger, day.isoformat())
    out = {"dateET": day.isoformat(), "updatedAtUTC": now.isoformat(), "sources": sources,
           "settlementErrors": unresolved, "picks": ledger}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "picks"}, indent=2))


if __name__ == "__main__":
    main()
