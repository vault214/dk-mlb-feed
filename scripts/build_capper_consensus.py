#!/usr/bin/env python3
"""Validate sourced multisport capper picks and grade settled 1u paper wagers.

Input dashboard/capper-submissions.json is a review/approval record, NOT an
automatically inferred bet. No record is published without source evidence,
pregame timing, exact price, and explicit best-bet designation.
"""
import datetime as dt
import json
import math
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "dashboard"
INPUT = ROOT / "capper-submissions.json"
OUTPUT = ROOT / "capper-consensus.json"
CAPS = {"cody", "koerner", "stuckey"}
SPORTS = {"NFL", "NCAAF", "NBA", "NCAAB", "WNBA", "MLB", "NHL", "MLS", "EPL", "SERIEA", "SOCCER"}
RESULTS = {"PENDING", "WIN", "LOSS", "PUSH", "VOID"}
REQUIRED = ("id", "capperId", "sport", "event", "selection", "market", "odds", "sourceUrl", "postedAtUTC", "eventStartUTC", "bestBetEvidence", "reviewedBy")

def instant(value):
    d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone required")
    return d.astimezone(dt.timezone.utc)

def grade(odds, result):
    if result in ("PUSH", "VOID"):
        return 0.0
    if result == "LOSS":
        return -1.0
    if result == "WIN":
        return round(odds / 100 if odds > 0 else 100 / abs(odds), 5)
    return None

def build():
    baseline = json.loads(OUTPUT.read_text())
    records = json.loads(INPUT.read_text()).get("submissions", []) if INPUT.exists() else []
    valid, rejected, seen = [], [], set()
    for row in records:
        try:
            if any(not row.get(k) for k in REQUIRED):
                raise ValueError("missing required evidence")
            if row["id"] in seen:
                raise ValueError("duplicate ID")
            if row["capperId"] not in CAPS or row["sport"] not in SPORTS:
                raise ValueError("unknown capper or sport")
            if row.get("approvalStatus") != "APPROVED":
                raise ValueError("not approved by reviewer")
            url = urlparse(row["sourceUrl"])
            if url.scheme != "https" or not url.netloc or url.username or url.password:
                raise ValueError("invalid source URL")
            if len(row["bestBetEvidence"].strip()) < 10:
                raise ValueError("best-bet evidence too short")
            posted, start = instant(row["postedAtUTC"]), instant(row["eventStartUTC"])
            if posted >= start:
                raise ValueError("source not pregame")
            odds = int(row["odds"])
            if odds == 0 or abs(odds) < 100 or abs(odds) > 10000:
                raise ValueError("invalid American odds")
            result = row.get("result", "PENDING").upper()
            if result not in RESULTS:
                raise ValueError("invalid result")
            if result != "PENDING" and not row.get("settlementSourceUrl"):
                raise ValueError("settlement evidence required")
            if result != "PENDING":
                settled = urlparse(row["settlementSourceUrl"])
                if settled.scheme != "https" or not settled.netloc:
                    raise ValueError("invalid settlement source")
            if row.get("settledAtUTC") and instant(row["settledAtUTC"]) < start:
                raise ValueError("settled before start")
            et = posted.astimezone(ZoneInfo("America/New_York"))
            entry = {k: row[k] for k in ("id", "capperId", "sport", "event", "selection", "market", "sourceUrl", "postedAtUTC", "eventStartUTC", "bestBetEvidence", "reviewedBy")}
            entry.update(dateET=et.date().isoformat(), postedAtET=et.isoformat(), odds=odds, result=result, riskUnits=1.0, plUnits=grade(odds, result), settlementSourceUrl=row.get("settlementSourceUrl"), status="VERIFIED_REVIEWED")
            valid.append(entry)
            seen.add(row["id"])
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({"id": row.get("id", "unknown"), "reason": str(exc)})
    baseline["picks"] = sorted(valid, key=lambda r: r["postedAtUTC"], reverse=True)
    baseline["updatedAtUTC"] = dt.datetime.now(dt.timezone.utc).isoformat()
    baseline["rejectedCount"] = len(rejected)
    OUTPUT.write_text(json.dumps(baseline, indent=2) + "\n")
    print(json.dumps({"published": len(valid), "rejected": rejected}, indent=2))
    if rejected:
        raise SystemExit("Some submitted picks failed validation; see log")

if __name__ == "__main__":
    build()
