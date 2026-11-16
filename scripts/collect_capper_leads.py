#!/usr/bin/env python3
"""Discover public capper posts across sports. Leads are NOT verified picks."""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "capper-discovery.json"
SEARCHES = {
    "cody": '"Cody Brown Bets" "best bet"',
    "koerner": '"Sean Koerner" "pick"',
    "stuckey": '"Stuckey" "Action Network" "pick"',
    "sartori": '"Tony Sartori" "Daily Dangles" NHL best bet',
    "dellera": '"Joe Dellera" "Action Network" "NBA" pick',
    "andylang": '"Andy Lang" "WagerTalk" "free pick"',
}
SPORT_TERMS = {
    "NFL": ("nfl", "football", "chiefs", "eagles"),
    "NBA": ("nba", "basketball", "lakers", "celtics"),
    "NCAAB": ("ncaab", "college basketball", "march madness"),
    "NCAAF": ("ncaaf", "college football"),
    "NHL": ("nhl", "hockey"),
    "MLB": ("mlb", "baseball"),
    "SOCCER": ("soccer", "premier league", "serie a", "mls"),
}
def collect():
    leads = []
    for capper, query in SEARCHES.items():
        params = urllib.parse.urlencode({"q": query + " when:14d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
        req = urllib.request.Request("https://news.google.com/rss/search?" + params, headers={"User-Agent": "Mozilla/5.0 capper-research/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                root = ET.fromstring(response.read(1_000_000))
        except Exception as exc:
            print(capper, "discovery unavailable:", type(exc).__name__)
            continue
        for item in root.findall("./channel/item")[:20]:
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            published = item.findtext("pubDate") or ""
            if not title or not url:
                continue
            low = title.lower()
            sports = [name for name, terms in SPORT_TERMS.items() if any(t in low for t in terms)]
            leads.append({"capperId": capper, "title": title, "sourceUrl": url, "published": published, "sports": sports, "status": "UNVERIFIED_DISCOVERY_ONLY"})
    seen = set()
    unique = []
    for lead in leads:
        key = (lead["capperId"], lead["sourceUrl"])
        if key not in seen:
            unique.append(lead)
            seen.add(key)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Preserve human-readable candidate evidence for review, not a wager ledger.
    for lead in unique:
        title = lead["title"].lower()
        lead["candidateBestBet"] = any(term in title for term in ("best bet", "best bets", "stuckey's spot"))
        lead["reviewNeeded"] = ["original post timestamp", "exact event and selection", "American odds", "event start time", "human approval"]
    # A discovery run is not a verified pick: preserve the first time each lead
    # was seen, even if syndication pages update their headline later.
    first_seen = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        prior = { (x["capperId"], x["sourceUrl"]): x for x in json.loads(OUT.read_text()).get("leads", []) }
    except (FileNotFoundError, ValueError, KeyError):
        prior = {}
    for lead in unique:
        lead["firstSeenUTC"] = prior.get((lead["capperId"], lead["sourceUrl"]), {}).get("firstSeenUTC", first_seen)
    OUT.write_text(json.dumps({"updatedAtUTC": dt.datetime.now(dt.timezone.utc).isoformat(), "leads": unique, "note": "Discovery links are NOT betting picks. Require original pregame evidence and odds verification before promotion."}, indent=2) + "\n")
    print("Discovered", len(unique), "unverified public leads")

if __name__ == "__main__":
    collect()
