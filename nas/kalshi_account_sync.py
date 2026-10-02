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


def summarize(fills, settlements):
    by_sport = defaultdict(lambda: {"fills": 0, "settlements": 0})
    for x in fills:
        by_sport[x["sport"]]["fills"] += 1
    for x in settlements:
        by_sport[x["sport"]]["settlements"] += 1
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

    payload = {
        "schemaVersion": 1,
        "visibility": "sanitized-private-performance-feed",
        "source": "Kalshi authenticated account API",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "fill_count": len(fills),
        "settlement_count": len(settlements),
        "summary_by_sport": summarize(fills, settlements),
        "accounting_note": (
            "This feed intentionally preserves settlement cost/revenue fields. "
            "Downstream sync should compute actual P/L only from documented settlement data, "
            "not from deposits/withdrawals."
        ),
        "fills": fills,
        "settlements": settlements,
    }

    OUT_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    commit = push_github(payload)

    print(f"Saved: {OUT_FILE}")
    print(f"Fills: {len(fills)}")
    print(f"Settlements: {len(settlements)}")
    print(f"GitHub: {REMOTE_PATH}")
    if commit:
        print(f"Commit: {commit}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
