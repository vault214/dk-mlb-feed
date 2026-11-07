#!/usr/bin/env python3
"""Trace conference-published availability viewers to their public provider.

An official conference HTML page embedding/linking an HD Intelligence viewer
establishes ONLY that the provider is a publisher-authorized source. It does
NOT establish a particular game's final report, a QB's status, or a safe pick.
No vendor API, guessed URL, authentication, or undocumented endpoints used.
"""
import argparse
import datetime as dt
import json
import pathlib
import urllib.parse
from html.parser import HTMLParser
from ncaaf_official_report_discovery_v35 import hub_html

UTC=dt.timezone.utc
APP="app.hdintelligence.com"
CONF_CODES={"sec":"SEC","big 12":"B12","acc":"ACC","big ten":"B1G"}
ALIASES={"southeastern":"sec","sec":"sec","big 12":"big 12","big 12 conference":"big 12",
         "big ten":"big ten","big ten conference":"big ten",
         "acc":"acc","atlantic coast":"acc","atlantic coast conference":"acc"}
OFFICIAL_DOMAINS={
    "sec":("secsports.com","www.secsports.com"),
    "big 12":("big12sports.com","www.big12sports.com","admin.big12sports.com"),
    "acc":("theacc.com","www.theacc.com","admin.theacc.com"),
    "big ten":("bigten.org","www.bigten.org"),
}

class Refs(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        for field in ("src","href","data-src","data-url"):
            if d.get(field):self.links.append(d[field])

def conference(row):
    if row.get("conference_game") is not True:return None
    h=ALIASES.get(str(row.get("home_conference") or "").strip().lower())
    a=ALIASES.get(str(row.get("away_conference") or "").strip().lower())
    return h if h and h==a and h in CONF_CODES else None

def vendor_link_ok(candidate,conf):
    """Allow only exactly sourced, public and explicit football viewer parameters."""
    try:
        p=urllib.parse.urlsplit(candidate)
        if p.scheme!="https" or p.hostname!=APP or p.username or p.password or p.port not in (None,443):
            return False
        if p.path not in ("","/"):return False
        pairs=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
        q=dict(pairs)
        if len(pairs)!=len(q):return False
        if set(q)!={"conf","source","sport","type"}:return False
        code=CONF_CODES[conf]
        return q=={"conf":code,"source":code,"sport":"Football","type":"report"}
    except (ValueError,KeyError,TypeError):return False

def inspect(queue,now,fetch_fn=hub_html):
    groups={}
    for g in queue.get("game_review_queue",[]):
        conf=conference(g)
        hub=g.get("report_discovery_hub")
        if conf and hub:
            p=urllib.parse.urlsplit(hub)
            if p.scheme=="https" and p.hostname in OFFICIAL_DOMAINS[conf]:
                groups[(conf,hub)]=None
    fetched={}
    for conf,hub in sorted(groups):
        try:
            txt=fetch_fn(hub)
            found=Refs();found.feed(txt)
            raw=set(found.links)
            # Some pages ship a URL in a script's embedded config rather than
            # as an iframe tag. Do not infer a URL from an arbitrary match.
            valid=set()
            for link in raw:
                absolute=urllib.parse.urljoin(hub,link)
                if vendor_link_ok(absolute,conf):
                    valid.add(absolute)
            fetched[(conf,hub)]={"hub_retrieved":True,"links":sorted(valid),
                                 "html_ref_count":len(raw)}
        except (OSError,TimeoutError,UnicodeError,ValueError) as e:
            fetched[(conf,hub)]={"hub_retrieved":False,"links":[],
                                 "error":"Official hub could not be read"}
    games=[]
    for g in queue.get("game_review_queue",[]):
        conf=conference(g)
        hub=g.get("report_discovery_hub")
        data=fetched.get((conf,hub),{})
        links=data.get("links",[])
        viewer=links[0] if len(links)==1 else None
        games.append({
            "cfbd_game_id":str(g.get("cfbd_game_id")),
            "home_team":g.get("home_team"),"away_team":g.get("away_team"),
            "kickoff_utc":g.get("kickoff_utc"),
            "conference":conf,
            "official_page":hub if data else None,
            "official_page_retrieved":data.get("hub_retrieved",False),
            "conference_published_viewer_url":viewer,
            "viewer_embedded_by_official_site":bool(viewer),
            "vendor_viewer_is_per_game_document":False,
            "final_report_for_this_game_verified":False,
            "both_starting_qbs_verified":False,
            "status":"PUBLISHER-LINK PROVENANCE ONLY" if viewer else "NO ATTESTED VIEWER LINK",
            "official_eligible":False
        })
    return {"schemaVersion":1,"sport":"NCAAF","generatedAtUTC":now.isoformat(),
            "status":"OFFICIAL CONFERENCE VIEWER PROVENANCE — RESEARCH ONLY",
            "official_hubs_checked":len(groups),
            "official_hubs_retrieved":sum(x["hub_retrieved"] for x in fetched.values()),
            "games_with_verified_publisher_link":sum(x["viewer_embedded_by_official_site"] for x in games),
            "games":games,"official_eligible":False,
            "shadow_eligible":False,"production_eligible":False,
            "note":"An HDI app viewer linked directly from a conference is NOT a game-specific final document. No team, player, QB, report freshness or player absence inference without a separately scoped and auditable report."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="ncaaf-v38-scoped-queue.json")
    p.add_argument("--output",default="dashboard/ncaaf-v39-provider-proof.json")
    a=p.parse_args()
    q=json.loads(pathlib.Path(a.queue).read_text())
    out=inspect(q,dt.datetime.now(UTC))
    dest=pathlib.Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({x:out[x] for x in (
        "status","official_hubs_checked","official_hubs_retrieved",
        "games_with_verified_publisher_link","official_eligible")}))
if __name__=="__main__":main()
