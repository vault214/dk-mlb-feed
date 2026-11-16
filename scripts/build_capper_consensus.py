#!/usr/bin/env python3
"""Build forward-only, evidence-reviewed multisport capper paper tracking.

The capper's historical, published performance is NOT the forward paper sample.
A capper cannot be marked qualified until an independent per-sport ledger meets
all published policy requirements. Nothing here executes bets.
"""
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "dashboard"
INPUT = ROOT / "capper-submissions.json"
OUTPUT = ROOT / "capper-consensus.json"
QUAL = ROOT / "capper-qualification.json"
ARCHIVE = ROOT / "capper-legacy-archive.json"
SPORTS = {"NFL", "NCAAF", "NBA", "NCAAB", "WNBA", "MLB", "NHL", "MLS", "EPL", "SERIEA", "SOCCER"}
RESULTS = {"PENDING", "WIN", "LOSS", "PUSH", "VOID"}

REQUIRED = ("id", "capperId", "sport", "event", "selection", "market", "odds",
            "sourceUrl", "postedAtUTC", "eventStartUTC", "observedAtUTC",
            "bestBetEvidence", "reviewedBy")


def parse_time(value):
    value = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("all times must have a UTC offset")
    return value.astimezone(dt.timezone.utc)


def https_url(value):
    url = urlparse(str(value or ""))
    return url.scheme == "https" and bool(url.netloc) and not url.username and not url.password


def paper_profit(odds, result):
    if result in ("PUSH", "VOID"):
        return 0.0
    if result == "LOSS":
        return -1.0
    if result == "WIN":
        return round(odds / 100 if odds > 0 else 100 / abs(odds), 5)
    return None


def qualify(audit, policy):
    """Require independently auditable *sport-specific* historical evidence."""
    if not audit or audit.get("sourceType") != "INDEPENDENT_FULL_LEDGER" or not audit.get("independentAudit"):
        return False
    if not https_url(audit.get("auditUrl")):
        return False
    settled = int(audit.get("settledPicks") or 0)
    if settled < int(policy["minSettledPicksPerSport"]):
        return False
    if float(audit.get("roiPct") or 0) <= 0:
        return False
    if len(set(audit.get("seasons", []))) < 2:
        return False
    periods = audit.get("nonoverlappingPeriods") or []
    if len(periods) < 2 or any(float(x.get("roiPct") or 0) <= 0 for x in periods):
        return False
    if not audit.get("allPicksPregameTimestamped"):
        return False
    return True


def build():
    baseline = json.loads(OUTPUT.read_text())
    qualifications = json.loads(QUAL.read_text())
    submissions = json.loads(INPUT.read_text()).get("submissions", [])
    archived = {p["id"] for p in json.loads(ARCHIVE.read_text()).get("picks", [])}
    policy = qualifications["policy"]
    roster = qualifications["roster"]
    members = {c["id"]: c for c in roster}
    independently_audited = {
        (a["capperId"], a["sport"]): a
        for a in qualifications.get("independentlyAuditedRecords", [])
    }
    sport_status = {}
    for member in roster:
        for sport in member["sports"]:
            audit = independently_audited.get((member["id"], sport))
            sport_status[member["id"] + ":" + sport] = (
                "AUDITED_POSITIVE" if qualify(audit, policy) else "NOT_YET_QUALIFIED"
            )

    valid, rejected, seen = [], [], set()
    for row in submissions:
        try:
            if any(row.get(k) in (None, "") for k in REQUIRED):
                raise ValueError("missing mandatory field including first observation time")
            if row["id"] in seen or row["id"] in archived:
                raise ValueError("duplicate or archived prior sample")
            member = members.get(row["capperId"])
            if not member or row["sport"] not in member["sports"] or row["sport"] not in SPORTS:
                raise ValueError("capper or sport is not in the new tracking roster")
            if row.get("approvalStatus") != "APPROVED":
                raise ValueError("source review is not approved")
            if not https_url(row["sourceUrl"]):
                raise ValueError("invalid original source URL")
            if len(str(row["bestBetEvidence"]).strip()) < 10:
                raise ValueError("no meaningful best bet evidence")
            posted = parse_time(row["postedAtUTC"])
            observed = parse_time(row["observedAtUTC"])
            start = parse_time(row["eventStartUTC"])
            if posted >= start or observed >= start:
                raise ValueError("posted or first observed after event started")
            if observed < posted:
                raise ValueError("first seen earlier than original publication")
            odds = int(row["odds"])
            if not (abs(odds) >= 100 and abs(odds) <= 10000):
                raise ValueError("American odds outside allowed range")
            result = str(row.get("result", "PENDING")).upper()
            if result not in RESULTS:
                raise ValueError("unknown settlement result")
            if result != "PENDING" and not https_url(row.get("settlementSourceUrl")):
                raise ValueError("settled bet requires independent public settlement evidence")
            if row.get("settledAtUTC") and parse_time(row["settledAtUTC"]) < start:
                raise ValueError("settled before event start")
            et = ZoneInfo("America/New_York")
            entry = {k: row[k] for k in REQUIRED}
            entry.update(
                dateET=start.astimezone(et).date().isoformat(),
                postedAtET=posted.astimezone(et).isoformat(),
                odds=odds, result=result, riskUnits=1.0,
                plUnits=paper_profit(odds, result),
                settlementSourceUrl=row.get("settlementSourceUrl"),
                status="SOURCE_REVIEWED_FORWARD_PAPER",
                qualificationStatus=sport_status[row["capperId"] + ":" + row["sport"]],
                trackRole=member["role"],
            )
            valid.append(entry)
            seen.add(row["id"])
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({"id": row.get("id", "unknown"), "reason": str(exc)})

    baseline["cappers"] = [
        {k: c[k] for k in ("id", "name", "handle", "role")}
        | {"qualificationStatus": "NOT_YET_QUALIFIED"}
        for c in roster
    ]
    baseline["qualificationsBySport"] = sport_status
    baseline["picks"] = sorted(valid, key=lambda p: p["postedAtUTC"], reverse=True)
    baseline["updatedAtUTC"] = dt.datetime.now(dt.timezone.utc).isoformat()
    baseline["rejectedCount"] = len(rejected)
    OUTPUT.write_text(json.dumps(baseline, indent=2) + "\n")
    print(json.dumps({"accepted": len(valid), "rejected": rejected}, indent=2))
    if rejected:
        raise SystemExit("Rejected unverified source evidence; review logs")


if __name__ == "__main__":
    build()
