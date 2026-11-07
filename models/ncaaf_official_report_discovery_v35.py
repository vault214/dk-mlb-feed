#!/usr/bin/env python3
"""Find candidate official NCAAF matchup reports linked directly from conference hubs.

Discovery never verifies document content, QBs, statuses or readiness. Only
documents subsequently downloaded and checked by ncaaf_primary_report_evidence
can be regarded as a primary report; dynamic embeds can remain undiscoverable.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from ncaaf_primary_report_evidence_v35 import primary_url_ok,UTC

MAX_HUB_BYTES=2_000_000

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items=[]
        self.href=None
        self.text=[]
        self.iframes=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="a":
            self.href=attrs.get("href");self.text=[]
        elif tag=="iframe" and attrs.get("src"):
            self.iframes.append(attrs["src"])
    def handle_data(self,text):
        if self.href is not None:self.text.append(text)
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            self.items.append((self.href," ".join(self.text)))
            self.href=None;self.text=[]

def hub_html(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NCAAFOfficialReportDiscovery/3.5"})
    with urllib.request.urlopen(req,timeout=16) as f:
        if urllib.parse.urlsplit(f.geturl()).hostname!=urllib.parse.urlsplit(url).hostname:
            raise ValueError("conference hub redirected to external provider")
        data=f.read(MAX_HUB_BYTES+1)
        if len(data)>MAX_HUB_BYTES:raise ValueError("report hub too large")
        return data.decode("utf-8","replace")

def compact(x):
    return "".join(ch for ch in str(x or "").lower() if ch.isalnum())

def discover(queue,now,fetch_fn=hub_html):
    items=queue.get("game_review_queue",[])
    hubs=sorted({g.get("report_discovery_hub") for g in items if g.get("report_discovery_hub")})
    pages={}
    for hub in hubs:
        try:
            parser=Links();parser.feed(fetch_fn(hub))
            pages[hub]=parser
        except (OSError,ValueError,TimeoutError,UnicodeError):
            pages[hub]=None
    found=[];details=[]
    for g in items:
        hub=g.get("report_discovery_hub")
        if not hub:continue
        doc=pages.get(hub)
        kick=dt.datetime.fromisoformat(g["kickoff_utc"])
        if kick.tzinfo is None or kick<=now:continue
        possible=[]
        if doc:
            for href,label in doc.items:
                url=urllib.parse.urljoin(hub,href)
                blob=compact(label+" "+href)
                if (primary_url_ok(url) and
                    compact(g["home_team"]) in blob and
                    compact(g["away_team"]) in blob):
                    possible.append(url)
        possible=sorted(set(possible))
        details.append({"cfbd_game_id":g["cfbd_game_id"],
            "home_team":g["home_team"],"away_team":g["away_team"],
            "kickoff_utc":g["kickoff_utc"],
            "candidate_urls":possible,
            "report_hub_retrieved":doc is not None,
            "hub_embedded_iframes":len(doc.iframes) if doc else 0,
            "document_content_verified":False,
            "notes":"HTML links only; conference JS/iframe reports may not expose direct document links"})
        # Only unique direct official links are proposed to the content verifier.
        if len(possible)==1:
            found.append({"cfbd_game_id":g["cfbd_game_id"],
                "home_team":g["home_team"],"away_team":g["away_team"],
                "direct_official_report_url":possible[0],"qbs":{}})
    return {"schemaVersion":1,"sport":"NCAAF",
        "generatedAtUTC":now.isoformat(),
        "status":"OFFICIAL DIRECT REPORT DISCOVERY — NOT VERIFIED",
        "conference_hubs_checked":len(hubs),
        "conference_hubs_fetchable":sum(x is not None for x in pages.values()),
        "matchups_checked":len(details),
        "unambiguous_direct_report_candidates":len(found),
        "candidate_evidence":{"schemaVersion":1,"sport":"NCAAF","reports":found},
        "matchups":details,
        "production_eligible":False,"official_eligible":False,
        "note":"Discovery does not imply a game-specific report is authentic or current; source text is checked separately. Embedded third-party reports often require a supported feed."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="dashboard/ncaaf-v34-availability-health.json")
    p.add_argument("--output",default="dashboard/ncaaf-v35-source-discovery.json")
    a=p.parse_args()
    q=json.loads(pathlib.Path(a.queue).read_text())
    out=discover(q,dt.datetime.now(UTC))
    f=pathlib.Path(a.output);f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in
        ("status","conference_hubs_checked","conference_hubs_fetchable",
         "matchups_checked","unambiguous_direct_report_candidates",
         "production_eligible")}))
if __name__=="__main__":main()
