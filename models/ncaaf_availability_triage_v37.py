#!/usr/bin/env python3
"""Prospective NCAA matchup QB-risk TRIAGE, never a verified player feed.

Reads game URLs matched by both teams and game date from the external
unaffiliated KickoffStatus index. Parses only the page's main availability
tables ABOVE 'Unofficial Injury Notes' and preserves explicit secondary status
with source URL/time. A QB-labeled player is not proven to be the starter.
Content is NEVER used to adjust probabilities, certify QB availability,
clear material-absence blocks, issue official/shadow bets, or infer not-listed.
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
HOSTS={"kickoffstatus.com","www.kickoffstatus.com"}
MAX_BYTES=1_500_000
RISK={"out":"OUT","doubtful":"DOUBTFUL","questionable":"QUESTIONABLE",
      "game-time decision":"GAME-TIME DECISION","gtd":"GAME-TIME DECISION",
      "out (1st half)":"OUT FIRST HALF","out 1st half":"OUT FIRST HALF"}
ALIASES={"lsu":"louisiana state","ole miss":"mississippi","mtsu":"middle tennessee",
         "wku":"western kentucky","texas a&m":"texas a and m"}
def canon(text):
    t=unicodedata.normalize("NFKD",str(text or "")).encode("ascii","ignore").decode().lower()
    t=t.replace("&"," and ")
    t=re.sub(r"[^a-z0-9]+"," ",t).strip()
    return ALIASES.get(t,t)

class SectionTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading=None;self.current=None;self.muted=False
        self.hbuf=[];self.in_row=False;self.in_cell=False
        self.cellbuf=[];self.cells=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag in ("h2","h3"):
            self.heading=tag;self.hbuf=[]
        elif tag=="tr":
            self.in_row=True;self.cells=[]
        elif tag in ("td","th") and self.in_row:
            self.in_cell=True;self.cellbuf=[]
    def handle_data(self,data):
        if self.heading is not None:self.hbuf.append(data)
        if self.in_cell:self.cellbuf.append(data)
    def handle_endtag(self,tag):
        if self.heading==tag:
            h=" ".join(" ".join(self.hbuf).split())
            if "unofficial injury notes" in h.lower():
                self.muted=True
            elif tag=="h3" and not self.muted:
                self.current=h
            self.heading=None;self.hbuf=[]
        elif tag in ("td","th") and self.in_cell:
            self.cells.append(" ".join(" ".join(self.cellbuf).split()))
            self.in_cell=False;self.cellbuf=[]
        elif tag=="tr" and self.in_row:
            if self.current and not self.muted and self.cells:
                self.rows.append((self.current,self.cells))
            self.in_row=False;self.cells=[]
def which_team(h,home,away):
    # Section labels may include counts ("Oregon 9 Out 1 GTD"), but never
    # guess which side when the normalized label is ambiguous.
    section=canon(h)
    options=[]
    for side,team in (("home",home),("away",away)):
        t=canon(team)
        if section==t or section.startswith(t+" "):
            options.append(side)
    return options[0] if len(options)==1 else None
def parse_game(html,home,away):
    tables=SectionTables();tables.feed(html)
    flags=[];recognized=0
    for section,cells in tables.rows:
        side=which_team(section,home,away)
        if side is None:continue
        # Expected columns: Player | Pos | Status | Report history.
        if len(cells)<3:continue
        position=re.sub(r"\W+","",cells[1]).upper()
        if position not in ("QB","QBS"):continue
        recognized+=1
        status=" ".join(cells[2].lower().split())
        category=RISK.get(status)
        if category is None:
            continue
        # Only report name and explicit status, no inferred starter identity.
        name=re.sub(r"\s*#\s*\d+\s*$","",cells[0]).strip()
        if not name or len(name)>120:continue
        flags.append({"side":side,"name":name,"position":"QB",
            "secondary_status":category,
            "text_status":cells[2],
            "source_type":"THIRD-PARTY TRANSCRIPTION - NOT OFFICIAL EVIDENCE",
            "starting_qb_verified":False,
            "player_status_officially_verified":False})
    return {"qb_position_rows_seen":recognized,"secondary_qb_risk_flags":flags}
def fetch_game(url):
    u=urllib.parse.urlsplit(url)
    if (u.scheme!="https" or u.hostname not in HOSTS or
        not re.fullmatch(r"/games/\d{4}-\d\d-\d\d-[a-z0-9-]+/?",u.path)):
        raise ValueError("unexpected unaffiliated game-page address")
    req=urllib.request.Request(url,headers={"User-Agent":"NCAAFUnverifiedQBSourceTriage/3.7"})
    try:
        with urllib.request.urlopen(req,timeout=18) as resp:
            if urllib.parse.urlsplit(resp.geturl()).hostname not in HOSTS:
                raise ValueError("third-party source redirect not allowed")
            raw=resp.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError("game page too large")
            return raw.decode("utf-8","replace")
    except (urllib.error.URLError,OSError,TimeoutError):
        raise ValueError("third-party game page unavailable") from None
def triage(source,now,fetch_fn=fetch_game):
    results=[]
    for g in source.get("games",[]):
        url=g.get("supplemental_url")
        row={"cfbd_game_id":g.get("cfbd_game_id"),
            "home_team":g.get("home_team"),"away_team":g.get("away_team"),
            "event_date_et":g.get("event_date_et"),
            "source_url":url,"captured_utc":now.isoformat(),
            "status":"NO VERIFIED AVAILABILITY",
            "qb_position_rows_seen":None,"secondary_qb_risk_flags":[],
            "official_qb_verified":False,"actual_starter_confirmed":False,
            "official_injury_verified":False,"used_to_adjust_probabilities":False}
        if url:
            try:
                parsed=parse_game(fetch_fn(url),row["home_team"],row["away_team"])
                row.update(parsed)
                row["status"]="THIRD-PARTY QC ONLY - NOT PRIMARY VERIFICATION"
            except (ValueError,UnicodeError) as e:
                row["status"]="THIRD-PARTY PAGE UNAVAILABLE OR UNPARSABLE"
                row["source_error"]=str(e)[:100]
        results.append(row)
    return {"schemaVersion":1,"sport":"NCAAF","generatedAtUTC":now.isoformat(),
        "status":"UNVERIFIED PRE-KICKOFF QB CONCERN PRIORITIZATION ONLY",
        "game_pages_reviewed":len(results),
        "pages_parsed":sum(r["qb_position_rows_seen"] is not None for r in results),
        "games_with_secondary_qb_risk_flags":sum(bool(r["secondary_qb_risk_flags"]) for r in results),
        "games":results,
        "official_eligible":False,"shadow_eligible":False,"production_eligible":False,
        "note":"Third-party QB position rows are a HUMAN/PRIMARY source verification priority only; never assume this is the actual starter or that other unlisted players are available."}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="dashboard/ncaaf-v36-secondary-leads.json")
    p.add_argument("--output",default="dashboard/ncaaf-v37-availability-triage.json")
    a=p.parse_args()
    obj=json.loads(pathlib.Path(a.source).read_text())
    out=triage(obj,dt.datetime.now(UTC))
    target=pathlib.Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({key:out[key] for key in ("status","game_pages_reviewed","pages_parsed","games_with_secondary_qb_risk_flags","official_eligible")}))
if __name__=="__main__":main()
