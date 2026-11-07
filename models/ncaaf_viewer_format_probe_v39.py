#!/usr/bin/env python3
"""Read-only format probe for conference-attested public availability viewer.

No private HDI API or authentication. Public HTML is inspected for whether
matchup-specific text exists in the HTTP response; it is NOT proof of game
reports, starting QBs or availability. Never publishes raw player details.
"""
import argparse
import datetime as dt
import html.parser
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request

from ncaaf_provider_proof_v39 import vendor_link_ok
UTC=dt.timezone.utc
LIMIT=1_500_000

class Visible(html.parser.HTMLParser):
    def __init__(self):
        super().__init__();self.block=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","noscript"):self.block+=1
    def handle_endtag(self,tag):
        if tag in ("script","style","noscript") and self.block:self.block-=1
    def handle_data(self,text):
        if not self.block:self.parts.append(text)

def read(url):
    req=urllib.request.Request(url,headers={
        "User-Agent":"NCAAFPublicReportSourceFormatProbe/3.9",
        "Accept":"text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req,timeout=22) as resp:
            target=resp.geturl()
            if urllib.parse.urlsplit(target).hostname!="app.hdintelligence.com":
                raise ValueError("Viewer redirected away from trusted publisher")
            body=resp.read(LIMIT+1)
            if len(body)>LIMIT:raise ValueError("Public viewer HTML exceeded bounded size")
            return body.decode("utf-8","replace")
    except (urllib.error.URLError,TimeoutError,OSError,UnicodeError):
        raise ValueError("Public viewer could not be retrieved") from None

def inspect(proof,now,fetch_fn=read):
    examined={}
    games=[]
    for g in proof.get("games",[]):
        link=g.get("conference_published_viewer_url")
        conf=g.get("conference")
        if not link or not conf or not vendor_link_ok(link,conf):continue
        if link not in examined:
            try:
                raw=fetch_fn(link)
                visible=Visible();visible.feed(raw)
                plain=" ".join(" ".join(visible.parts).split())
                examined[link]={"retrieved":True,"html_bytes":len(raw.encode("utf-8")),
                    "visible_chars":len(plain),"js_hydration_likely":len(plain)<1000,
                    "content_is_a_matchup_specific_final_report":False}
            except ValueError:
                examined[link]={"retrieved":False,"html_bytes":None,
                    "visible_chars":None,"js_hydration_likely":None,
                    "content_is_a_matchup_specific_final_report":False}
        games.append({"cfbd_game_id":g.get("cfbd_game_id"),
            "conference":conf,"home_team":g.get("home_team"),
            "away_team":g.get("away_team"),
            "viewer":link,"viewer_retrieved":examined[link]["retrieved"],
            "visible_html_characters":examined[link]["visible_chars"],
            "requires_js_or_rendering":examined[link]["js_hydration_likely"],
            "specific_game_final_report_verified":False,
            "starting_qb_verified":False,"official_eligible":False})
    return {"schemaVersion":1,"sport":"NCAAF",
        "generatedAtUTC":now.isoformat(),
        "status":"OFFICIAL PUBLIC VIEWER HTTP FORMAT PROBE — NOT PLAYER VERIFICATION",
        "attested_viewers_probed":len(examined),
        "viewers_retrieved":sum(x["retrieved"] for x in examined.values()),
        "viewer_fetch_health":list(examined.values()),
        "matched_games":len(games),"games":games,
        "official_eligible":False,"shadow_eligible":False,"production_eligible":False,
        "note":"This only determines if conference-attested HDI viewer HTML can be read. Player status or even a correct match must still be isolated with game/time/report source evidence. JavaScript-rendered pages require a permitted rendering strategy."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--provider",default="dashboard/ncaaf-v39-provider-proof.json")
    p.add_argument("--output",default="dashboard/ncaaf-v39-viewer-probe.json")
    a=p.parse_args()
    proof=json.loads(pathlib.Path(a.provider).read_text())
    out=inspect(proof,dt.datetime.now(UTC))
    dest=pathlib.Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({x:out[x] for x in ("status","attested_viewers_probed","viewers_retrieved","matched_games","official_eligible")}))
if __name__=="__main__":main()
