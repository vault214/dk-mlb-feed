#!/usr/bin/env python3
"""Fail-closed direct, game-specific primary availability report verification.

A conference POLICY HUB is not player evidence. This verifier accepts an
explicitly listed official MATCHUP document URL and checks source domain,
game date, both teams, text extraction, and pregame observation timestamp.
Optional QB facts require exact source excerpts. QB absence from a list is
NEVER inferred to mean healthy. It does not assign untested injury adjustments,
book bets, or certify an independent model.
"""
import argparse
import copy
import datetime as dt
import io
import json
import pathlib
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")
OFFICIAL_HOSTS={
  "www.secsports.com","secsports.com",
  "big12sports.com","www.big12sports.com",
  "bigten.org","www.bigten.org",
  "theacc.com","www.theacc.com",
}
POLICY_HUB_PATHS={
  "/", "/fbreports", "/reports",
  "/sports/2025/8/21/availability-reporting.aspx",
  "/sports/2025/8/28/availability-reporting.aspx"
}
MAX_BYTES=2_500_000

def parsedate(value):
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except (ValueError,AttributeError):return None

def clean(text):
    return " ".join(str(text).replace("\xa0"," ").split()).lower()

def primary_url_ok(url):
    try:
        p=urllib.parse.urlsplit(url)
        return (p.scheme=="https" and p.hostname in OFFICIAL_HOSTS
                and p.username is None and p.password is None
                and p.port in (None,443)
                and p.path.rstrip("/").lower() not in {x.rstrip("/") for x in POLICY_HUB_PATHS}
                and len(p.path)>12)
    except (ValueError,TypeError):return False

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","noscript"):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ("script","style","noscript") and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def remote_document(url):
    if not primary_url_ok(url):raise ValueError("not a direct official conference document URL")
    req=urllib.request.Request(url,headers={
        "User-Agent":"IndependentCFBPrimaryAvailabilityResearch/3.5",
        "Accept":"text/html,application/pdf"})
    try:
        with urllib.request.urlopen(req,timeout=20) as f:
            final=f.geturl()
            if not primary_url_ok(final):raise ValueError("redirected away from official source")
            blob=f.read(MAX_BYTES+1)
            if len(blob)>MAX_BYTES:raise ValueError("primary report too large")
            mime=(f.headers.get("Content-Type") or "").lower()
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ValueError("source document could not be fetched") from None
    if "pdf" in mime or blob[:4]==b"%PDF":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("PDF text support unavailable; install pypdf") from None
        try:
            reader=PdfReader(io.BytesIO(blob))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            raise ValueError("PDF had no reliably extracted report text") from None
    if "html" not in mime and not blob.lstrip().startswith(b"<!"):
        raise ValueError("unsupported primary report format")
    parser=TextParser()
    parser.feed(blob.decode("utf-8","replace"))
    return " ".join(parser.parts)

def document_date_present(text,day):
    date=dt.date.fromisoformat(day)
    month=date.strftime("%B").lower()
    short=date.strftime("%b").lower()
    formats=(date.isoformat(),date.strftime("%m/%d/%Y"),
             f"{month} {date.day}, {date.year}",
             f"{short} {date.day}, {date.year}",
             f"{short}. {date.day}, {date.year}")
    low=clean(text)
    return any(x in low for x in formats)

def qb_excerpt_valid(text,record):
    name=clean(record.get("name"))
    status=clean(record.get("status"))
    excerpt=clean(record.get("source_excerpt"))
    statuses={"out","available","questionable","doubtful","probable","game time decision","out 1st half"}
    if len(name)<5 or status not in statuses or not (15<=len(excerpt)<=200):
        return False
    return name in excerpt and status in excerpt and excerpt in clean(text)

def verify(queue,inputs,now,fetch_fn=remote_document):
    result=copy.deepcopy(queue)
    indexed={str(g["cfbd_game_id"]):g for g in result.get("game_review_queue",[])}
    counters={"report_source_candidates":0,"source_text_verified":0,"both_qbs_explicitly_verified":0,
              "source_errors":0}
    for report in inputs.get("reports",[]):
        gid=str(report.get("cfbd_game_id") or "")
        g=indexed.get(gid)
        if not g:continue
        counters["report_source_candidates"]+=1
        url=report.get("direct_official_report_url")
        kick=parsedate(g["kickoff_utc"])
        if not primary_url_ok(url):
            g["primary_report_check"]="POLICY HUB OR UNTRUSTED URL — NOT VERIFIED"
            counters["source_errors"]+=1;continue
        if kick is None or now>=kick:
            g["primary_report_check"]="SOURCE SUBMITTED AFTER KICKOFF — NOT PREGAME VERIFIED"
            counters["source_errors"]+=1;continue
        if report.get("home_team")!=g["home_team"] or report.get("away_team")!=g["away_team"]:
            g["primary_report_check"]="SUBMITTED GAME IDENTITY MISMATCH"
            counters["source_errors"]+=1;continue
        try: text=fetch_fn(url)
        except ValueError as exc:
            g["primary_report_check"]="DOCUMENT NOT VERIFIED: "+str(exc)[:100]
            counters["source_errors"]+=1;continue
        if not (g["home_team"].lower() in clean(text)
                and g["away_team"].lower() in clean(text)
                and document_date_present(text,g["event_date_et"])):
            g["primary_report_check"]="DOCUMENT DOES NOT VERIFY BOTH TEAMS AND MATCH DATE"
            counters["source_errors"]+=1;continue
        # Document relevance can be established without conflating that with
        # quarterback status or in-game player availability.
        g["game_specific_primary_report_url"]=url
        g["report_observed_at_utc"]=now.isoformat()
        g["primary_report_check"]="DIRECT OFFICIAL MATCHUP DOCUMENT CONTENT VERIFIED"
        g["two_teams_report_coverage_confirmed"]=True
        counters["source_text_verified"]+=1
        qbs=report.get("qbs",{})
        home=qb_excerpt_valid(text,qbs.get("home",{}))
        away=qb_excerpt_valid(text,qbs.get("away",{}))
        g["starting_qb_names_confirmed"]=bool(home and away)
        g["starting_qb_statuses_verified"]=bool(home and away)
        # Player impact sensitivity is not calibrated. Never mark it complete
        # by looking at a published lineup or manually entered assumption.
        g["material_absences_verified"]=False
        g["risk_adjustment_backtested"]=False
        g["model_eligible"]=False
        if home and away:
            g["qb_status_evidence"]={
                side:{"name":qbs[side]["name"],"status":qbs[side]["status"],
                      "source_excerpt":qbs[side]["source_excerpt"]}
                for side in ("home","away")}
            counters["both_qbs_explicitly_verified"]+=1
    result["status"]="PRIMARY AVAILABILITY MATCHUP DOCUMENT CHECK — RESEARCH ONLY"
    result["report_source_candidates"]=counters["report_source_candidates"]
    result["game_specific_reports_verified"]=counters["source_text_verified"]
    result["starting_qbs_verified"]=counters["both_qbs_explicitly_verified"]
    result["injury_availability_verified"]=0
    result["source_document_errors"]=counters["source_errors"]
    result["official_eligible"]=False
    result["shadow_eligible"]=False
    result["production_eligible"]=False
    result["generatedAtUTC"]=now.isoformat()
    result["note"]="A document with both teams/date is not proof of QB fitness or lineup strength. Explicit QB quotations are checked only when supplied. No automatic picks or injury impact assumptions."
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="dashboard/ncaaf-v34-availability-health.json")
    p.add_argument("--input",default="research/ncaaf-primary-availability-input.json")
    p.add_argument("--discovery",default=None)
    p.add_argument("--output",default="dashboard/ncaaf-v35-verified-availability.json")
    a=p.parse_args()
    q=json.loads(pathlib.Path(a.queue).read_text())
    incoming=json.loads(pathlib.Path(a.input).read_text())
    if incoming.get("schemaVersion")!=1 or not isinstance(incoming.get("reports"),list):
        raise ValueError("source input schema invalid")
    if a.discovery:
        detected=json.loads(pathlib.Path(a.discovery).read_text())
        proposed=detected.get("candidate_evidence",{}).get("reports",[])
        if not isinstance(proposed,list):
            raise ValueError("malformed direct report discovery candidates")
        indexed={(str(x.get("cfbd_game_id")),str(x.get("direct_official_report_url")))
                 for x in incoming["reports"]}
        for candidate in proposed:
            key=(str(candidate.get("cfbd_game_id")),str(candidate.get("direct_official_report_url")))
            if key not in indexed:
                incoming["reports"].append(candidate)
                indexed.add(key)
    value=verify(q,incoming,dt.datetime.now(UTC))
    target=pathlib.Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(value,indent=2)+"\n")
    print(json.dumps({key:value[key] for key in (
        "status","matched_games","report_source_candidates",
        "game_specific_reports_verified","starting_qbs_verified",
        "injury_availability_verified","production_eligible")}))
if __name__=="__main__":main()
