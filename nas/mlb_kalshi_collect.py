#!/usr/bin/env python3
import base64
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API_BASE = "https://external-api.kalshi.com/trade-api/v2"
TZ = ZoneInfo("America/New_York")
OUT_DIR = Path("/app/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SERIES = {
    "game": "KXMLBGAME",
    "spread": "KXMLBSPREAD",
    "total": "KXMLBTOTAL",
    "strikeouts": "KXMLBKS",
    "outs_recorded": "KXMLBOUTS",
}

CATEGORY_CAPS = {
    "game": 40,
    "spread": 45,
    "total": 35,
    "strikeouts": 55,
    "outs_recorded": 45,
}

PER_EVENT_CAPS = {
    "game": 99,
    "spread": 3,
    "total": 3,
    "strikeouts": 6,
    "outs_recorded": 4,
}

MAX_TOTAL = 220
MAX_SPREAD = 0.15
HORIZON_DAYS = 2

REMOTE_PATH = "kalshi/mlb-candidates.json"
DEFAULT_REPO = "vault214/dk-mlb-feed"
DEFAULT_BRANCH = "main"

TICKER_DATE_RE = re.compile(r"-(\d{2}[A-Z]{3}\d{2}\d{4})")

def now_et():
    return datetime.now(TZ)

def iso_utc():
    return datetime.now(timezone.utc).isoformat()

def fnum(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None

def dollars(m, stem):
    v = fnum(m.get(stem + "_dollars"))
    if v is not None:
        return v
    cents = fnum(m.get(stem))
    if cents is not None:
        return cents / 100.0
    return None

def api_get(path, params):
    q = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{q}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "jarvis-kalshi-mlb-collector/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_series(series_ticker):
    markets = []
    cursor = None
    while True:
        params = {
            "series_ticker": series_ticker,
            "status": "open",
            "limit": 1000,
        }
        if cursor:
            params["cursor"] = cursor
        payload = api_get("/markets", params)
        batch = payload.get("markets") or []
        markets.extend(batch)
        cursor = payload.get("cursor")
        if not cursor or not batch:
            break
    return markets

def event_dt_et(event_ticker):
    m = TICKER_DATE_RE.search(event_ticker or "")
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1).title(), "%y%b%d%H%M")
        return dt.replace(tzinfo=TZ)
    except Exception:
        return None

def activity(m):
    vals = [
        fnum(m.get("volume_24h_fp")),
        fnum(m.get("volume_fp")),
        fnum(m.get("open_interest_fp")),
        fnum(m.get("volume_24h")),
        fnum(m.get("volume")),
        fnum(m.get("open_interest")),
    ]
    return max([x for x in vals if x is not None] or [0.0])

def quote_spread(bid, ask):
    if bid is None or ask is None:
        return None
    return max(0.0, ask - bid)

def normalized_market(raw, category):
    yes_bid = dollars(raw, "yes_bid")
    yes_ask = dollars(raw, "yes_ask")
    no_bid = dollars(raw, "no_bid")
    no_ask = dollars(raw, "no_ask")
    last = dollars(raw, "last_price")

    side_spreads = [
        x for x in (
            quote_spread(yes_bid, yes_ask),
            quote_spread(no_bid, no_ask),
        )
        if x is not None
    ]
    min_spread = min(side_spreads) if side_spreads else None

    dt = event_dt_et(raw.get("event_ticker") or raw.get("ticker"))
    return {
        "source": "Kalshi",
        "sport": "MLB",
        "sport_key": "mlb",
        "category": category,
        "series_ticker": SERIES[category],
        "event_ticker": raw.get("event_ticker"),
        "ticker": raw.get("ticker"),
        "title": raw.get("title"),
        "subtitle": raw.get("subtitle"),
        "yes_sub_title": raw.get("yes_sub_title"),
        "no_sub_title": raw.get("no_sub_title"),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "last_price": last,
        "bid_ask_spread": min_spread,
        "volume_24h": fnum(raw.get("volume_24h_fp")) if raw.get("volume_24h_fp") is not None else fnum(raw.get("volume_24h")),
        "volume": fnum(raw.get("volume_fp")) if raw.get("volume_fp") is not None else fnum(raw.get("volume")),
        "open_interest": fnum(raw.get("open_interest_fp")) if raw.get("open_interest_fp") is not None else fnum(raw.get("open_interest")),
        "liquidity": fnum(raw.get("liquidity_dollars")) if raw.get("liquidity_dollars") is not None else fnum(raw.get("liquidity")),
        "open_time": raw.get("open_time"),
        "close_time": raw.get("close_time"),
        "expected_expiration_time": raw.get("expected_expiration_time"),
        "event_start_et": dt.isoformat() if dt else None,
        "strike_type": raw.get("strike_type"),
        "floor_strike": raw.get("floor_strike"),
        "cap_strike": raw.get("cap_strike"),
        "custom_strike": raw.get("custom_strike"),
        "rules_primary": raw.get("rules_primary"),
        "rules_secondary": raw.get("rules_secondary"),
        "_activity": activity(raw),
    }

def eligible(m, start_date, end_date):
    dt_s = m.get("event_start_et")
    if not dt_s:
        return False
    try:
        d = datetime.fromisoformat(dt_s).astimezone(TZ).date()
    except Exception:
        return False
    if not (start_date <= d <= end_date):
        return False
    if m["yes_ask"] is None and m["no_ask"] is None:
        return False

    spreads = []
    if m["yes_bid"] is not None and m["yes_ask"] is not None:
        spreads.append(max(0.0, m["yes_ask"] - m["yes_bid"]))
    if m["no_bid"] is not None and m["no_ask"] is not None:
        spreads.append(max(0.0, m["no_ask"] - m["no_bid"]))
    if spreads and min(spreads) > MAX_SPREAD:
        return False
    if (m.get("_activity") or 0) <= 0:
        return False
    return True

def quality(m):
    spread = m.get("bid_ask_spread")
    spread_penalty = 100.0 * (spread if spread is not None else 0.25)
    v24 = max(0.0, m.get("volume_24h") or 0.0)
    oi = max(0.0, m.get("open_interest") or 0.0)
    vol = max(0.0, m.get("volume") or 0.0)
    return (
        -spread_penalty
        + 2.0 * math.log1p(v24)
        + 1.0 * math.log1p(oi)
        + 0.5 * math.log1p(vol)
    )

def reduce_candidates(markets):
    by_event = defaultdict(list)
    for m in markets:
        by_event[(m["category"], m.get("event_ticker") or m.get("ticker"))].append(m)

    stage1 = []
    for (cat, _), group in by_event.items():
        cap = PER_EVENT_CAPS.get(cat, 3)
        stage1.extend(sorted(group, key=quality, reverse=True)[:cap])

    by_cat = defaultdict(list)
    for m in stage1:
        by_cat[m["category"]].append(m)

    stage2 = []
    for cat, group in by_cat.items():
        cap = CATEGORY_CAPS.get(cat, 30)
        stage2.extend(sorted(group, key=quality, reverse=True)[:cap])

    return sorted(stage2, key=quality, reverse=True)[:MAX_TOTAL]

def clean_for_json(m):
    out = dict(m)
    out.pop("_activity", None)
    out["quality_score"] = round(quality(m), 4)
    return out

def github_repo():
    repo = (
        os.environ.get("GITHUB_REPOSITORY")
        or os.environ.get("GITHUB_REPO")
        or DEFAULT_REPO
    ).strip()
    if "/" not in repo:
        owner = os.environ.get("GITHUB_OWNER", "vault214").strip()
        repo = f"{owner}/{repo}"
    return repo

def github_token():
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"):
        value = os.environ.get(key)
        if value:
            return value.strip()
    return None

def gh_request(method, url, token, body=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "jarvis-kalshi-mlb-collector/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}

def push_github(payload):
    token = github_token()
    if not token:
        raise RuntimeError("No GitHub token found. Expected GITHUB_TOKEN, GH_TOKEN, or GITHUB_PAT.")

    repo = github_repo()
    branch = os.environ.get("GITHUB_BRANCH", DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    path_q = urllib.parse.quote(REMOTE_PATH, safe="/")
    base = f"https://api.github.com/repos/{repo}/contents/{path_q}"

    sha = None
    try:
        current = gh_request("GET", base + "?" + urllib.parse.urlencode({"ref": branch}), token)
        sha = current.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    raw = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    body = {
        "message": f"Update Kalshi MLB candidates for {payload['board_date_et']}",
        "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    result = gh_request("PUT", base, token, body)
    return result.get("commit", {}).get("sha")

def main():
    today = now_et().date()
    end_date = today + timedelta(days=HORIZON_DAYS)

    print("=" * 72)
    print("KALSHI MLB COLLECTOR")
    print(f"ET board date: {today}")
    print(f"Horizon: {today} through {end_date}")
    print("=" * 72)

    raw_count = 0
    normalized = []
    series_counts = {}

    for category, series in SERIES.items():
        print(f"\nFetching {category}: {series}")
        markets = fetch_series(series)
        series_counts[category] = len(markets)
        raw_count += len(markets)
        print(f"  open markets: {len(markets)}")
        normalized.extend(normalized_market(m, category) for m in markets)

    model_ready = [m for m in normalized if eligible(m, today, end_date)]
    candidates = reduce_candidates(model_ready)

    category_counts = Counter(m["category"] for m in candidates)
    no_current_markets = len(model_ready) == 0

    payload = {
        "source": "Kalshi",
        "sport": "MLB",
        "sport_key": "mlb",
        "board_date_et": today.isoformat(),
        "through_date_et": end_date.isoformat(),
        "fetched_at_utc": iso_utc(),
        "raw_market_count": raw_count,
        "source_model_market_count": len(model_ready),
        "candidate_market_count": len(candidates),
        "no_current_markets": no_current_markets,
        "markets_by_type": dict(sorted(category_counts.items())),
        "series_open_market_counts": series_counts,
        "selection_rules": {
            "max_total": MAX_TOTAL,
            "max_bid_ask_spread": MAX_SPREAD,
            "horizon_days": HORIZON_DAYS,
            "category_caps": CATEGORY_CAPS,
            "per_event_caps": PER_EVENT_CAPS,
            "pricing_note": "YES uses yes_ask; NO uses no_ask. Midpoint is diagnostic only.",
        },
        "markets": [clean_for_json(m) for m in candidates],
    }

    out = OUT_DIR / "kalshi_mlb_candidates.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nCandidate JSON: {out}")
    print(f"Raw markets: {raw_count}")
    print(f"Model-ready: {len(model_ready)}")
    print(f"Candidates: {len(candidates)}")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat}: {count}")

    commit = push_github(payload)
    print(f"\nGITHUB PUSH COMPLETE: {REMOTE_PATH}")
    if commit:
        print(f"Commit: {commit}")

    if no_current_markets:
        print("\nNO CURRENT MLB KALSHI MARKETS IN HORIZON")
        print("This is a clean empty-board result, not a collector crash.")

    print("\nMLB KALSHI PIPELINE COMPLETE")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise
