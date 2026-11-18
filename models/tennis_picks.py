#!/usr/bin/env python3
"""Capture and grade ATP/WTA paper picks from public pregame inputs."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ncaaf_forward_audit_v33 import D, fee_spec, get_orderbook, levels, taker_fee

OUT = Path(__file__).resolve().parents[1] / "dashboard" / "tennis-picks.json"
ET = ZoneInfo("America/New_York")
API = "https://api.elections.kalshi.com/trade-api/v2"
HISTORY = "https://huggingface.co/datasets/minmaxxxer/atp-wta-matches-with-odds"
SCORES = "https://site.api.espn.com/apis/site/v2/sports/tennis/{}/scoreboard"
TOURS = {"ATP": "KXATPMATCH", "WTA": "KXWTAMATCH"}
OTHER_SERIES = {"ATP Challenger": "KXATPCHALLENGERMATCH",
                "WTA Challenger": "KXWTACHALLENGERMATCH", "ITF": "KXITFMATCH"}
PREGAME_BUFFER = timedelta(minutes=2)
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
    try:
        with urlopen(request, timeout=18) as response:
            return response.read().decode("utf-8")
    except HTTPError as error:
        raise ValueError(f"{urlsplit(url).hostname} returned HTTP {error.code}") from error


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


def key(name):
    normalized = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in normalized if c.isascii() and c.isalnum())


def ratings_for(tour, day):
    rows = {}
    for year in (day.year - 1, day.year):
        url = f"{HISTORY}/resolve/main/{tour.lower()}_matches_{year}.csv"
        for row in csv.DictReader(get(url).splitlines()):
            if row["match_id"] and row["start_time_utc"]:
                rows[row["match_id"]] = row
    overall = defaultdict(lambda: 1500.0)
    surface_ratings = defaultdict(lambda: 1500.0)
    aliases, match_counts = defaultdict(set), defaultdict(int)
    latest = None
    for row in sorted(rows.values(), key=lambda r: r["start_time_utc"]):
        date = utc(row["start_time_utc"]).astimezone(ET).date()
        surface = row["surface"].lower()
        score = row["score"]
        if (date >= day or surface not in SURFACES
                or not re.fullmatch(r"(?:\d+-\d+(?:\(\d+\))?)(?: \d+-\d+(?:\(\d+\))?)+", score)):
            continue
        winner, loser = row["winner_id"], row["loser_id"]
        if not winner or not loser or winner == loser:
            continue
        for side in ("winner", "loser"):
            player = row[f"{side}_id"]
            aliases[key(row[f"{side}_name"])].add(player)
            match_counts[player] += 1
        update_elo(overall, winner, loser)
        update_elo(surface_ratings, (winner, surface), (loser, surface))
        latest = date
    if latest is None or day - latest > timedelta(days=35):
        raise ValueError("historical match results are stale")
    return latest, overall, surface_ratings, aliases, match_counts


def update_elo(ratings, winner, loser):
    change = 24 * (1 - probability(ratings[winner], ratings[loser], 3))
    ratings[winner] += change
    ratings[loser] -= change


def match_rating(name, surface, data):
    _, overall, surface_ratings, aliases, match_counts = data
    words = name.split()
    if len(words) < 2:
        return None
    labels = {key(" ".join(words[index:]) + words[0][0]) for index in range(1, len(words))}
    ids = set().union(*(aliases.get(label, set()) for label in labels))
    if len(ids) != 1:
        return None
    player = ids.pop()
    if match_counts[player] < 15:
        return None
    return 0.6 * overall[player] + 0.4 * surface_ratings[player, surface]


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
    schedule = list(scheduled(tour, day))
    if not schedule:
        return [], {"status": "OK", "scheduledSingles": 0, "matchedMarkets": 0, "eligibleCandidates": 0}
    ratings = ratings_for(tour, day)
    ratings_day = ratings[0]
    series = json.loads(get(API + "/series/" + TOURS[tour]))["series"]
    if series.get("ticker") != TOURS[tour]:
        raise ValueError("series identity mismatch")
    candidates, matched, quote_errors = [], 0, 0
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
        if cutoff <= datetime.now(timezone.utc) + PREGAME_BUFFER:
            continue
        matched += 1
        point_ratings = [match_rating(market["yes_sub_title"], surface, ratings) for market in markets]
        if None in point_ratings:
            continue
        for index, market in enumerate(markets):
            candidate = price_pick(series, market, point_ratings[index], point_ratings[1-index], int(best_of))
            if not candidate:
                continue
            try:
                book = get_orderbook(market["ticker"])
            except (OSError, ValueError):
                quote_errors += 1
                continue
            yes, no = levels(book.get("yes_dollars")), levels(book.get("no_dollars"))
            if not yes or not no:
                continue
            candidate = price_pick(series, market | {
                "yes_bid_dollars": yes[0][0], "yes_ask_dollars": 1 - no[0][0],
                "yes_ask_size_fp": no[0][1],
            }, point_ratings[index], point_ratings[1-index], int(best_of))
            if not candidate or cutoff <= datetime.now(timezone.utc) + PREGAME_BUFFER:
                continue
            candidates.append(candidate | {
                "ticker": market["ticker"], "eventTicker": event["event_ticker"],
                "selection": market["yes_sub_title"], "opponent": markets[1-index]["yes_sub_title"],
                "matchStartUTC": cutoff.isoformat(), "observedAtUTC": datetime.now(timezone.utc).isoformat(),
                "dateET": day.isoformat(), "tour": tour, "tournament": tournament,
                "ratingsDate": ratings_day.isoformat(), "surface": surface, "bestOf": int(best_of),
            })
    return candidates, {"status": "PARTIAL" if quote_errors else "OK", "quoteErrors": quote_errors,
                        "scheduledSingles": len(schedule), "matchedMarkets": matched,
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
    if p > 0.75 or ask > 0.75:
        return None
    return {"probability": p, "ask": ask, "fee": fee, "edge": edge, "rating": rating,
            "opponentRating": opponent, "result": "PENDING", "plUnits": None}


def capture(candidates, ledger, day):
    booked = [p for p in ledger if p["dateET"] == day]
    remaining = [p for p in candidates
                 if utc(p["matchStartUTC"]) > datetime.now(timezone.utc) + PREGAME_BUFFER
                 and all(p["ticker"] != old["ticker"] for old in booked)]
    if remaining and not any(p["track"] == "OFFICIAL" for p in booked):
        pool = [p for p in remaining
                if p["probability"] >= 0.48 and p["edge"] >= 0.05]
        official = max(pool, key=lambda p: p["edge"]) if pool else max(
            remaining, key=lambda p: (p["probability"], p["edge"]))
        pick = official | {"track": "OFFICIAL", "stakeUnits": 1.0,
                           "selectionBasis": "EDGE_QUALIFIED" if pool else "MINIMUM_ACTION"}
        ledger.append(pick)
        booked.append(pick)
        remaining.remove(official)
    if not remaining or any(p["track"] == "SHADOW" for p in booked):
        return
    official = next(p for p in booked if p["track"] == "OFFICIAL")
    riskier = [p for p in remaining if p["probability"] < official["probability"]]
    if not riskier:
        return
    distinct = [p for p in riskier if p["eventTicker"] != official["eventTicker"]]
    pool = distinct or riskier
    edge_qualified = [p for p in pool if p["probability"] < 0.50 and p["edge"] >= 0.025]
    shadow = max(edge_qualified or pool, key=lambda p: (p["edge"], -p["probability"]))
    ledger.append(shadow | {"track": "SHADOW", "stakeUnits": 0.5,
                            "selectionBasis": "EDGE_QUALIFIED" if edge_qualified else "MINIMUM_ACTION"})


def other_tour_coverage(series, day, now):
    return sum(1 for _, milestone in market_page(series)
               if milestone["details"].get("status") in {"not_started", "SCH"}
               and utc(milestone["start_date"]) > now
               and utc(milestone["start_date"]).astimezone(ET).date() == day)


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
    candidates, sources, unresolved, unmodeled = [], {}, [], {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(settle, p): p["ticker"] for p in ledger
                   if p["result"] == "PENDING" and utc(p["matchStartUTC"]) < now}
        tours = {tour: pool.submit(evaluate, tour, day) for tour in TOURS}
        coverage = {name: pool.submit(other_tour_coverage, series, day, now)
                    for name, series in OTHER_SERIES.items()}
        for tour, future in tours.items():
            try:
                rows, sources[tour] = future.result()
                candidates.extend(rows)
            except (OSError, ValueError, KeyError, TypeError) as error:
                sources[tour] = {"status": "UNAVAILABLE", "reason": str(error)[:160] if isinstance(error, ValueError) else type(error).__name__}
        capture(candidates, ledger, day.isoformat())
        for name, future in coverage.items():
            try:
                unmodeled[name] = future.result()
            except (OSError, ValueError, KeyError, TypeError):
                unmodeled[name] = None
        for future, ticker in pending.items():
            try:
                future.result()
            except (OSError, ValueError, KeyError, TypeError):
                unresolved.append(ticker)
    out = {"dateET": day.isoformat(), "updatedAtUTC": now.isoformat(), "sources": sources,
           "settlementErrors": unresolved, "unmodeledUpcoming": unmodeled, "picks": ledger}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "picks"}, indent=2))


if __name__ == "__main__":
    main()
