#!/usr/bin/env python3
"""Discover public capper articles and report source health.

Search headlines are research leads, never accepted bets. Preserve source
errors and first observations; avoid stale headline carryover.
"""
import datetime as dt
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "capper-discovery.json"
SEARCHES = {
    "koerner": '"Sean Koerner" NFL NCAAB picks',
    "stuckey": '"Stuckey" "Action Network" picks',
    "dellera": '"Joe Dellera" NBA picks',
    "cody": '"Cody Brown Bets" NBA NFL best bet',
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
UTC = dt.timezone.utc


def timestamp(value):
    try:
        d = parsedate_to_datetime(value).astimezone(UTC)
        return d if d.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def retrieve_rss(query):
    google = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query + " when:3d", "hl": "en-US", "gl": "US", "ceid": "US:en"
    })
    bing = "https://www.bing.com/news/search?" + urllib.parse.urlencode({
        "q": query, "format": "rss", "setlang": "en-US"
    })
    failures = []
    for provider, url in (("GoogleNewsRSS", google), ("BingNewsRSS", bing)):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ResearchMonitoring/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            })
            with urllib.request.urlopen(req, timeout=18) as resp:
                body = resp.read(1_000_000)
            root = ET.fromstring(body)
            if root.tag not in ("rss", "RDF"):
                raise ValueError("not an RSS response")
            return provider, root.findall("./channel/item"), failures
        except (urllib.error.URLError, ValueError, ET.ParseError, TimeoutError) as exc:
            status = getattr(exc, "code", None)
            failures.append(provider + ":" + (str(status) if status else type(exc).__name__))
    return None, [], failures


def collect():
    now = dt.datetime.now(UTC)
    cutoff = now - dt.timedelta(hours=72)
    previous = {}
    prior_success = None
    if OUT.exists():
        try:
            before = json.loads(OUT.read_text())
            previous = {
                (lead["capperId"], lead["sourceUrl"]): lead
                for lead in before.get("leads", [])
            }
            prior_success = before.get("lastSuccessfulSourceScanUTC")
        except (ValueError, KeyError, TypeError):
            pass
    leads, source_status = [], []
    for capper, query in SEARCHES.items():
        provider, items, failures = retrieve_rss(query)
        fresh = 0
        if provider:
            for item in items[:25]:
                title = (item.findtext("title") or "").strip()
                url = (item.findtext("link") or "").strip()
                published = (item.findtext("pubDate") or "").strip()
                pub_dt = timestamp(published)
                if not title or not url or not pub_dt or pub_dt < cutoff or pub_dt > now + dt.timedelta(minutes=10):
                    continue
                low = title.lower()
                author_in_title = any(term in low for term in AUTHOR_TERMS[capper])
                sports = [name for name, terms in SPORT_TERMS.items() if any(term in low for term in terms)]
                prev = previous.get((capper, url), {})
                leads.append({
                    "capperId": capper, "title": title, "sourceUrl": url,
                    "published": published, "publishedAtUTC": pub_dt.isoformat(),
                    "sports": sports,
                    "authorInHeadline": author_in_title,
                    "status": "UNVERIFIED_DISCOVERY_ONLY" if author_in_title else "AUTHOR_UNCONFIRMED",
                    "candidateBestBet": any(s in low for s in ("best bet", "best bets", "pick", "prop")),
                    "reviewNeeded": ["verify actual author", "original pregame publication timestamp", "exact selection and quoted odds", "event start time", "reviewer approval"],
                    "firstSeenUTC": prev.get("firstSeenUTC") or now.isoformat(),
                })
                fresh += 1
        source_status.append({
            "capperId": capper,
            "provider": provider,
            "status": "OK" if provider else "BLOCKED",
            "freshLeads": fresh,
            "errors": failures
        })
        print(capper, "provider", provider or "none", "fresh", fresh, "errors", failures)
    # Retain recent genuine new results through short outages, but never old news.
    seen = set()
    current = []
    for lead in leads:
        key = (lead["capperId"], lead["sourceUrl"])
        if key not in seen:
            current.append(lead)
            seen.add(key)
    for key, lead in previous.items():
        if key in seen or key[0] not in SEARCHES:
            continue
        published = lead.get("publishedAtUTC")
        pub_dt = None
        if published:
            try:
                pub_dt = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        pub_dt = pub_dt or timestamp(lead.get("published", ""))
        if pub_dt and cutoff <= pub_dt <= now and lead.get("firstSeenUTC"):
            current.append(lead)
            seen.add(key)
    successful = sum(x["status"] == "OK" for x in source_status)
    health = "OK" if successful == len(SEARCHES) else "DEGRADED" if successful else "FAILED"
    data = {
        "schemaVersion": 2, "updatedAtUTC": now.isoformat(),
        "scanDateET": now.astimezone(dt.timezone(dt.timedelta(hours=-5))).date().isoformat(),
        "scanHealth": health,
        "lastSuccessfulSourceScanUTC": now.isoformat() if successful else prior_success,
        "sourceStatus": source_status,
        "freshLeadsThisRun": len(leads),
        "retainedRecentLeads": len(current) - len({(x["capperId"], x["sourceUrl"]) for x in leads}),
        "leads": current,
        "note": "Discovery is not automatic verification, even when source health is OK. No inferred bets. RSS providers may block requests."
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print("Capper discovery scan:", health, "providers:", successful, "of", len(SEARCHES),
          "fresh:", len(leads), "recent retained:", data["retainedRecentLeads"])
    # Report failures accurately in GitHub Actions after the JSON heartbeat is committed.
    return successful


if __name__ == "__main__":
    collect()
