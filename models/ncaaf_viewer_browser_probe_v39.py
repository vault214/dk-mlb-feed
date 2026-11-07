#!/usr/bin/env python3
"""Bounded Chrome render of ONLY official-conference-attested public HDI viewers.

No private endpoints, authentication, API reverse engineering or betting
actions. The rendered DOM is used to diagnose access; multi-game pages are
never interpreted as game-specific final reports or player evidence.
"""
import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import urllib.parse
from ncaaf_provider_proof_v39 import vendor_link_ok
from ncaaf_viewer_format_probe_v39 import Visible,UTC

def chrome_render(url):
    executable=next((shutil.which(x) for x in ("google-chrome","google-chrome-stable","chromium","chromium-browser") if shutil.which(x)),None)
    if not executable:
        raise ValueError("No system Chrome/Chromium executable")
    proc=subprocess.run([executable,"--headless=new","--no-sandbox","--disable-gpu",
       "--disable-dev-shm-usage","--disable-default-apps","--no-first-run",
       "--disable-extensions","--disable-background-networking",
       "--virtual-time-budget=6500","--dump-dom",url],
       shell=False,capture_output=True,timeout=30,check=False,text=True)
    if proc.returncode!=0 or not proc.stdout.strip().startswith("<"):
        raise ValueError("Headless viewer DOM unavailable")
    if len(proc.stdout)>3_000_000:raise ValueError("Rendered DOM exceeds bounded size")
    return proc.stdout

def inspect(proof,now,render=chrome_render):
    pages={}
    result=[]
    for g in proof.get("games",[]):
        url=g.get("conference_published_viewer_url")
        conf=g.get("conference")
        if not url or not conf or not vendor_link_ok(url,conf):
            continue
        if url not in pages:
            try:
                html=render(url)
                v=Visible();v.feed(html)
                visible=" ".join(" ".join(v.parts).split())
                pages[url]={"browser_render_succeeded":True,
                    "rendered_visible_characters":len(visible),
                    "report_terms_detected":any(x in visible.lower() for x in
                    ("initial report","gameday report","game day report","report posted","report pending")),
                    "source_game_specific":False}
                # We intentionally do NOT serialize player names or source
                # report text; this is a structural/public access check only.
            except (ValueError,TimeoutError,OSError,subprocess.TimeoutExpired):
                pages[url]={"browser_render_succeeded":False,
                    "rendered_visible_characters":None,
                    "report_terms_detected":False,"source_game_specific":False}
        result.append({"cfbd_game_id":g.get("cfbd_game_id"),
            "home_team":g.get("home_team"),"away_team":g.get("away_team"),
            "conference":conf,"viewer_url":url,
            "browser_render_succeeded":pages[url]["browser_render_succeeded"],
            "rendered_visible_characters":pages[url]["rendered_visible_characters"],
            "report_terms_detected":pages[url]["report_terms_detected"],
            "exact_matchup_final_report_verified":False,
            "player_statuses_verified":False,
            "production_eligible":False})
    return {"schemaVersion":1,"sport":"NCAAF",
       "generatedAtUTC":now.isoformat(),
       "status":"AUTHORIZED PUBLIC VIEWER BROWSER STRUCTURE PROBE — NO GAME APPROVAL",
       "unique_attested_viewers":len(pages),
       "browser_render_succeeded":sum(p["browser_render_succeeded"] for p in pages.values()),
       "games":result,
       "official_eligible":False,"shadow_eligible":False,
       "production_eligible":False,
       "note":"A JS-rendered conference-wide page can contain many games. Without isolating the exact dated matchup/final report and independently verifying starter identities, no status or official eligibility may be inferred."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--provider",default="dashboard/ncaaf-v39-provider-proof.json")
    p.add_argument("--output",default="dashboard/ncaaf-v39-browser-probe.json")
    a=p.parse_args()
    proof=json.loads(pathlib.Path(a.provider).read_text())
    out=inspect(proof,dt.datetime.now(UTC))
    target=pathlib.Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in
      ("status","unique_attested_viewers","browser_render_succeeded","official_eligible")}))
if __name__=="__main__":main()
