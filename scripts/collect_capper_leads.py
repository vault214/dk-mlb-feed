#!/usr/bin/env python3
"""Discover public capper posts across sports. Leads are NOT verified picks."""
import datetime as dt
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "capper-discovery.json"
SEARCHES = {
    "koerner": '"Sean Koerner" "NFL" best bet',
    "stuckey": '"Stuckey" "Action Network" best bet',
    "dellera": '"Joe Dellera" "Action Network" best bet',
    "cody": '"Cody Brown Bets" "best bet"',
}
AUTHOR_TERMS = {
    "koerner": ("sean koerner",),
    "stuckey": ("stuckey",),
    "dellera": ("joe dellera",),
    "cody": ("cody brown bets", "codybrownbets"),
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
        params = urllib.parse.urlencode({"q": query + " when:4d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
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
            # A Google News search match does not prove who actually authored a pick.
            # Keep only explicit name matches in the headline, still unverified.
            if not any(alias in low for alias in AUTHOR_TERMS[capper]):
                continue
            try:
                published_at = parsedate_to_datetime(published).astimezone(dt.timezone.utc)
                if published_at < dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=72):
                    continue
            except (ValueError, TypeError, AttributeError):
                continue
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
    # Keep earlier reviewed leads through temporary RSS outages, but expire after
    # 72 hours so the dashboard never presents last week's article as current.
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=72)
    present = {(x["capperId"], x["sourceUrl"]) for x in unique}
    for key, lead in prior.items():
        if key[0] not in SEARCHES or key in present:
            continue
        try:
            seen_at = dt.datetime.fromisoformat(lead.get("firstSeenUTC", "").replace("Z", "+00:00"))
        except ValueError:
            seen_at = dt.datetime.now(dt.timezone.utc)
        if seen_at.tzinfo and seen_at > cutoff:
            unique.append(lead)
    OUT.write_text(json.dumps({"updatedAtUTC": dt.datetime.now(dt.timezone.utc).isoformat(), "leads": unique, "note": "Discovery links are NOT betting picks. Require original pregame evidence and odds verification before promotion."}, indent=2) + "\n")
    print("Discovered", len(unique), "unverified public leads")

if __name__ == "__main__":
    collect()
