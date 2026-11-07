#!/usr/bin/env python3
"""Discover public cross-conference availability leads, never verified QB facts.

Kickoff Status is an unaffiliated third-party summary with links to
conference reports. This file gathers only game URLs matched by BOTH
team slugs and ET event date. No player statuses / injury confirmations
are accepted from it, and it never marks an eligibility gate complete.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UTC=dt.timezone.utc
SOURCE="https://kickoffstatus.com/"
KNOWN_HOSTS={"kickoffstatus.com","www.kickoffstatus.com"}
ALTERNATES={
    "middle-tennessee":("mtsu","middle-tennessee"),
    "western-kentucky":("wku","western-kentucky"),
    "mississippi":("ole-miss","mississippi"),
    "louisiana-state":("lsu","louisiana-state"),
    "texas-san-antonio":("utsa","texas-san-antonio"),
    "texas-am":("texas-a-m","texas-am"),
    "brigham-young":("byu","brigham-young"),
    "southern-california":("usc","southern-california"),
    "central-florida":("ucf","central-florida"),
    "connecticut":("uconn","connecticut"),
    "north-carolina":("unc","north-carolina"),
    "southern-mississippi":("southern-miss","southern-mississippi"),
}
def slug(text):
    s=unicodedata.normalize("NFKD",str(text or "")).encode("ascii","ignore").decode().lower()
    s=s.replace("&"," and ").replace("'","")
    s=re.sub("[^a-z0-9]+","-",s).strip("-")
    if s.endswith("-and-m"):s=s[:-6]+"-a-m"
    return s

def slugs(team):
    raw=slug(team)
    result=set(ALTERNATES.get(raw,(raw,)))
    if raw.endswith("-state"):result.add(raw[:-6]+"-st")
    if raw=="texas-a-and-m":result.add("texas-a-m")
    if raw=="san-jose-state":result.add("san-jose-st")
    return result

class GameLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.href=None;self.chunks=[];self.items=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            h=dict(attrs).get("href","")
            self.href=h if h else None
            self.chunks=[]
    def handle_data(self,text):
        if self.href is not None:self.chunks.append(text)
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            self.items.append((self.href," ".join(self.chunks)))
            self.href=None;self.chunks=[]

def fetch_index(url=SOURCE):
    req=urllib.request.Request(url,headers={
        "User-Agent":"IndependentFootballAvailabilityLeadAudit/3.6",
        "Accept":"text/html"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            p=urllib.parse.urlsplit(r.geturl())
            if p.hostname not in KNOWN_HOSTS or p.scheme!="https":
                raise ValueError("secondary source redirect outside source")
            body=r.read(1_500_001)
            if len(body)>1_500_000:raise ValueError("secondary index too large")
            return body.decode("utf-8","replace")
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ValueError("secondary source currently unavailable") from None

def discover(queue,html,now):
    parser=GameLinks()
    parser.feed(html)
    slugs_to_link={}
    for href,label in parser.items:
        url=urllib.parse.urljoin(SOURCE,href)
        p=urllib.parse.urlsplit(url)
        if p.scheme!="https" or p.hostname not in KNOWN_HOSTS:continue
        match=re.fullmatch(r"/games/(\d{4}-\d\d-\d\d)-([a-z0-9-]+)-(?:at|vs)-([a-z0-9-]+)/?",p.path)
        if not match:continue
        date,away,home=match.groups()
        # Never use claim-like text without checking the underlying document.
        slugs_to_link.setdefault((date,away,home),url)
    out=[]
    for g in queue.get("game_review_queue",[]):
        day=g.get("event_date_et")
        away=slugs(g.get("away_team"));home=slugs(g.get("home_team"))
        matches={url for (date,a,h),url in slugs_to_link.items()
                 if date==day and a in away and h in home}
        if len(matches)==1:
            url=next(iter(matches));label="THIRD-PARTY GAME INDEX LINK — NOT VERIFIED"
        elif len(matches)>1:
            url=None;label="AMBIGUOUS THIRD-PARTY GAME LINKS — NOT VERIFIED"
        else:
            url=None;label="NO THIRD-PARTY GAME LINK — NOT VERIFIED"
        out.append({
            "cfbd_game_id":str(g["cfbd_game_id"]),
            "home_team":g["home_team"],"away_team":g["away_team"],
            "event_date_et":day,"kickoff_utc":g["kickoff_utc"],
            "supplemental_url":url,
            "source":"unaffiliated third-party game report index",
            "status":label,
            "primary_matchup_document_verified":False,
            "quarterback_verified":False,
            "injuries_verified":False,
            "source_player_statuses_used":False,
            "official_eligible":False,
        })
    return {
        "schemaVersion":1,"sport":"NCAAF","generatedAtUTC":now.isoformat(),
        "status":"SUPPLEMENTAL AVAILABILITY DISCOVERY — NO PRIMARY VERIFICATION",
        "unique_secondary_game_links":len(slugs_to_link),
        "queue_matchups":len(out),
        "secondary_matched_games":sum(bool(x["supplemental_url"]) for x in out),
        "games":out,"production_eligible":False,
        "official_eligible":False,"shadow_eligible":False,
        "note":"External aggregator links are leads for human/primary-source research only, NOT verified medical status, roster, official injury or quarterback evidence. Do not use to generate probabilities or picks."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="dashboard/ncaaf-v34-availability-health.json")
    p.add_argument("--output",default="dashboard/ncaaf-v36-secondary-leads.json")
    args=p.parse_args()
    queue=json.loads(pathlib.Path(args.queue).read_text())
    now=dt.datetime.now(UTC)
    try:
        html=fetch_index()
        obj=discover(queue,html,now)
    except ValueError as e:
        obj=discover(queue,"",now)
        obj["status"]="SUPPLEMENTAL SOURCE UNAVAILABLE — NO PRIMARY VERIFICATION"
        obj["retrieval_error"]=str(e)
    out=pathlib.Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(obj,indent=2)+"\n")
    print(json.dumps({k:obj[k] for k in ("status","queue_matchups","secondary_matched_games","official_eligible")}))
if __name__=="__main__":main()
