#!/usr/bin/env python3
"""
Pull the authenticated user's Kalshi fills and settlement records, sanitize them,
and publish a private-performance feed to GitHub.

Secrets never leave the NAS. Required environment variables:
  KALSHI_API_KEY_ID
  KALSHI_PRIVATE_KEY_PATH   (PEM file path, e.g. /app/secrets/kalshi-private.pem)
  GITHUB_TOKEN / GH_TOKEN / GITHUB_PAT

Optional:
  GITHUB_REPOSITORY (default vault214/dk-mlb-feed)
  GITHUB_BRANCH     (default main)
  KALSHI_INCLUDE_HISTORICAL_FILLS=true
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

API_ROOT = "https://external-api.kalshi.com"
API_PREFIX = "/trade-api/v2"
OUT_DIR = Path("/app/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "kalshi_account_trades.json"

REMOTE_PATH = "kalshi/account-trades.json"
DEFAULT_REPO = "vault214/dk-mlb-feed"
DEFAULT_BRANCH = "main"

API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID", "").strip()
PRIVATE_KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()


def load_private_key():
    if not PRIVATE_KEY_PATH:
        raise RuntimeError("KALSHI_PRIVATE_KEY_PATH is not set")
    path = Path(PRIVATE_KEY_PATH)
    if not path.exists():
        raise RuntimeError(f"Kalshi private key file not found: {path}")
    with path.open("rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign(private_key, timestamp_ms, method, full_path):
    path = full_path.split("?")[0]
    message = f"{timestamp_ms}{method.upper()}{path}".encode("utf-8")
    if isinstance(private_key, Ed25519PrivateKey):
        raw = private_key.sign(message)
    else:
        raw = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
    return base64.b64encode(raw).decode("ascii")


def kalshi_get(private_key, endpoint, params=None):
    params = params or {}
    query = urllib.parse.urlencode(params)
    full_path = API_PREFIX + endpoint
    url = API_ROOT + full_path + (("?" + query) if query else "")
    ts = str(int(time.time() * 1000))
    headers = {
        "KALSHI-ACCESS-KEY": API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sign(private_key, ts, "GET", full_path),
        "Accept": "application/json",
        "User-Agent": "gambling-dashboard-kalshi-account-sync/1.0",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def paginate(private_key, endpoint, list_key, extra=None):
    items = []
    cursor = None
    while True:
        params = {"limit": 1000}
        if extra:
            params.update(extra)
        if cursor:
            params["cursor"] = cursor
        payload = kalshi_get(private_key, endpoint, params)
        batch = payload.get(list_key) or []
        items.extend(batch)
        cursor = payload.get("cursor")
        if not cursor or not batch:
            break
    return items


def infer_sport(ticker):
    t = (ticker or "").upper()
    checks = [
        ("KXNHL", "NHL"),
        ("KXNFL", "NFL"),
        ("KXNBA", "NBA"),
        ("KXWNBA", "WNBA"),
        ("KXMLB", "MLB"),
        ("KXNCAAF", "NCAAF"),
        ("KXCFB", "NCAAF"),
        ("KXNCAA", "NCAAF"),
    ]
    for prefix, sport in checks:
        if t.startswith(prefix):
            return sport
    return "Other"


def fp(v):
    try:
        return float(v)
    except Exception:
        return None


def safe_fill(f):
    ticker = f.get("market_ticker") or f.get("ticker")
    return {
        "fill_id": f.get("fill_id"),
        "trade_id": f.get("trade_id"),
        "order_id": f.get("order_id"),
        "ticker": ticker,
        "sport": infer_sport(ticker),
        "outcome_side": f.get("outcome_side") or f.get("side"),
        "book_side": f.get("book_side"),
        "action": f.get("action"),
        "count": fp(f.get("count_fp")),
        "yes_price": fp(f.get("yes_price_dollars")),
        "no_price": fp(f.get("no_price_dollars")),
        "fee_cost": fp(f.get("fee_cost")),
        "is_taker": f.get("is_taker"),
        "created_time": f.get("created_time"),
        "exchange_index": f.get("exchange_index"),
        "subaccount_number": f.get("subaccount_number"),
    }


def safe_settlement(s):
    ticker = s.get("ticker")
    return {
        "ticker": ticker,
        "event_ticker": s.get("event_ticker"),
        "sport": infer_sport(ticker),
        "market_result": s.get("market_result"),
        "yes_count": fp(s.get("yes_count_fp")),
        "yes_total_cost": fp(s.get("yes_total_cost_dollars")),
        "no_count": fp(s.get("no_count_fp")),
        "no_total_cost": fp(s.get("no_total_cost_dollars")),
        "revenue_cents": s.get("revenue"),
        "value_cents": s.get("value"),
        "fee_cost": fp(s.get("fee_cost")),
        "settled_time": s.get("settled_time"),
        "exchange_index": s.get("exchange_index"),
    }


def build_positions(fills, settlements):
    """Aggregate member fills into one accounting row per Kalshi market."""
    by_ticker = defaultdict(list)
    for fill in fills:
        if fill.get("ticker"):
            by_ticker[fill["ticker"]].append(fill)

    settlement_by_ticker = {s.get("ticker"): s for s in settlements if s.get("ticker")}
    positions = []

    for ticker, market_fills in by_ticker.items():
        market_fills = sorted(market_fills, key=lambda x: x.get("created_time") or "")
        net_contracts = {"yes": 0.0, "no": 0.0}
        bought_contracts = {"yes": 0.0, "no": 0.0}
        buy_premium = {"yes": 0.0, "no": 0.0}
        gross_buy_cost = 0.0
        gross_sell_proceeds = 0.0
        fees = 0.0

        for x in market_fills:
            side = (x.get("outcome_side") or "").lower()
            action = (x.get("action") or "").lower()
            count = x.get("count") or 0.0
            price = x.get("yes_price") if side == "yes" else x.get("no_price")
            price = price or 0.0
            fee = x.get("fee_cost") or 0.0
            fees += fee

            if side not in ("yes", "no"):
                continue
            if action == "buy":
                net_contracts[side] += count
                bought_contracts[side] += count
                buy_premium[side] += count * price
                gross_buy_cost += count * price
            elif action == "sell":
                net_contracts[side] -= count
                gross_sell_proceeds += count * price

        dominant_side = "yes" if net_contracts["yes"] >= net_contracts["no"] else "no"
        total_bought = bought_contracts["yes"] + bought_contracts["no"]
        avg_entry = (
            (buy_premium["yes"] + buy_premium["no"]) / total_bought
            if total_bought > 0 else None
        )

        settlement = settlement_by_ticker.get(ticker)
        settled = settlement is not None
        settlement_payout = 0.0
        result = "Open"
        pnl = None

        if settled:
            winning_side = (settlement.get("market_result") or "").lower()
            if winning_side in ("yes", "no"):
                settlement_payout = max(0.0, net_contracts.get(winning_side, 0.0))
            pnl = gross_sell_proceeds + settlement_payout - gross_buy_cost - fees
            if pnl > 1e-9:
                result = "Win"
            elif pnl < -1e-9:
                result = "Loss"
            else:
                result = "Push"

        positions.append({
            "trade_id": "KALSHI-" + ticker,
            "ticker": ticker,
            "event_ticker": settlement.get("event_ticker") if settlement else None,
            "sport": infer_sport(ticker),
            "selection_side": dominant_side.upper(),
            "net_yes_contracts": round(net_contracts["yes"], 6),
            "net_no_contracts": round(net_contracts["no"], 6),
            "gross_contracts_bought": round(total_bought, 6),
            "gross_buy_cost": round(gross_buy_cost, 6),
            "gross_sell_proceeds": round(gross_sell_proceeds, 6),
            "fees": round(fees, 6),
            "risk": round(gross_buy_cost + fees, 6),
            "avg_entry_price": round(avg_entry, 6) if avg_entry is not None else None,
            "settlement_payout": round(settlement_payout, 6) if settled else None,
            "net_pnl": round(pnl, 6) if pnl is not None else None,
            "result": result,
            "market_result": settlement.get("market_result") if settlement else None,
            "opened_time": market_fills[0].get("created_time") if market_fills else None,
            "last_fill_time": market_fills[-1].get("created_time") if market_fills else None,
            "settled_time": settlement.get("settled_time") if settlement else None,
            "fill_ids": [x.get("fill_id") for x in market_fills if x.get("fill_id")],
        })

    return sorted(positions, key=lambda x: x.get("settled_time") or x.get("last_fill_time") or "", reverse=True)


def summarize(fills, settlements, positions):
    by_sport = defaultdict(lambda: {"fills": 0, "settlements": 0, "positions": 0, "settled_positions": 0})
    for x in fills:
        by_sport[x["sport"]]["fills"] += 1
    for x in settlements:
        by_sport[x["sport"]]["settlements"] += 1
    for x in positions:
        by_sport[x["sport"]]["positions"] += 1
        if x.get("result") in ("Win", "Loss", "Push"):
            by_sport[x["sport"]]["settled_positions"] += 1
    return dict(sorted(by_sport.items()))


def github_token():
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"):
        v = os.environ.get(key)
        if v:
            return v.strip()
    raise RuntimeError("No GitHub token found (GITHUB_TOKEN / GH_TOKEN / GITHUB_PAT)")


def github_repo():
    repo = (os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GITHUB_REPO") or DEFAULT_REPO).strip()
    if "/" not in repo:
        repo = "vault214/" + repo
    return repo


def gh_request(method, url, token, body=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "gambling-dashboard-kalshi-account-sync/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def push_github(payload):
    token = github_token()
    repo = github_repo()
    branch = (os.environ.get("GITHUB_BRANCH") or DEFAULT_BRANCH).strip()
    encoded_path = urllib.parse.quote(REMOTE_PATH, safe="/")
    api = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"

    sha = None
    try:
        current = gh_request("GET", api + "?" + urllib.parse.urlencode({"ref": branch}), token)
        sha = current.get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    raw = json.dumps(payload, indent=2) + "\n"
    body = {
        "message": "Refresh sanitized Kalshi account trade feed",
        "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    result = gh_request("PUT", api, token, body)
    return result.get("commit", {}).get("sha")


def main():
    if not API_KEY_ID:
        raise RuntimeError("KALSHI_API_KEY_ID is not set")

    private_key = load_private_key()

    print("Fetching live Kalshi fills...")
    fills_raw = paginate(private_key, "/portfolio/fills", "fills")

    if os.environ.get("KALSHI_INCLUDE_HISTORICAL_FILLS", "true").lower() == "true":
        try:
            print("Fetching historical Kalshi fills...")
            hist = paginate(private_key, "/historical/fills", "fills")
            seen = {x.get("fill_id") for x in fills_raw}
            fills_raw.extend(x for x in hist if x.get("fill_id") not in seen)
        except urllib.error.HTTPError as exc:
            print(f"Historical fills unavailable ({exc.code}); continuing with live fills.")

    print("Fetching Kalshi settlements...")
    settlements_raw = paginate(private_key, "/portfolio/settlements", "settlements")

    fills = [safe_fill(x) for x in fills_raw]
    settlements = [safe_settlement(x) for x in settlements_raw]
    positions = build_positions(fills, settlements)

    payload = {
        "schemaVersion": 1,
        "visibility": "sanitized-private-performance-feed",
        "source": "Kalshi authenticated account API",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "fill_count": len(fills),
        "settlement_count": len(settlements),
        "position_count": len(positions),
        "summary_by_sport": summarize(fills, settlements, positions),
        "accounting_note": (
            "Per-market actual P/L is derived from member fills: sell proceeds + winning-side "
            "settlement payout - buy premium - fill fees. Deposits/withdrawals are excluded."
        ),
        "positions": positions,
        "fills": fills,
        "settlements": settlements,
    }

    OUT_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    commit = push_github(payload)

    print(f"Saved: {OUT_FILE}")
    print(f"Fills: {len(fills)}")
    print(f"Settlements: {len(settlements)}")
    print(f"Positions: {len(positions)}")
    print(f"GitHub: {REMOTE_PATH}")
    if commit:
        print(f"Commit: {commit}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
