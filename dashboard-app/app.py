import os, json, hashlib, urllib.request, urllib.error
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from sheet_data import get_yesterday_bets

PORT = int(os.environ.get("PORT", "10000"))
PASSWORD = os.environ["DASHBOARD_PASSWORD"]
AUTH_SECRET = os.environ["AUTH_SECRET"]
TOKEN = hashlib.sha256((PASSWORD + ":" + AUTH_SECRET).encode()).hexdigest()
COOKIE_NAME = "gambling_dash_auth"
RAW = "https://raw.githubusercontent.com/vault214/dk-mlb-feed/main"
FEEDS = {
    "picks": RAW + "/dashboard/model-picks.json",
    "tennis": RAW + "/dashboard/tennis-picks.json",
    "model_health": RAW + "/dashboard/model-health.json",
    "nfl": RAW + "/kalshi/nfl-candidates.json",
    "ncaafb": RAW + "/kalshi/ncaafb-candidates.json",
    "nba": RAW + "/kalshi/nba-candidates.json",
    "ncaab": RAW + "/kalshi/ncaab-candidates.json",
    "wnba": RAW + "/kalshi/wnba-candidates.json",
    "mlb": RAW + "/kalshi/mlb-candidates.json",
    "nhl": RAW + "/kalshi/nhl-candidates.json",
    "actual": RAW + "/dashboard/actual-performance.json",
    "cappers": RAW + "/dashboard/capper-consensus.json",
    "capper_discovery": RAW + "/dashboard/capper-discovery.json",
    "capper_qualification": RAW + "/dashboard/capper-qualification.json",
    "capper_archive": RAW + "/dashboard/capper-legacy-archive.json",
}
RESEARCH_V32_URL = RAW + "/dashboard/ncaaf-v32-health.json"
WEATHER_V32_URL = RAW + "/dashboard/ncaaf-v32-weather-health.json"
QUOTE_V32_URL = RAW + "/dashboard/ncaaf-v32-quote-health.json"
FORWARD_V33_URL = RAW + "/dashboard/ncaaf-v33-health.json"
SETTLEMENT_V34_URL = RAW + "/dashboard/ncaaf-v34-settlement-health.json"
AVAILABILITY_V34_URL = RAW + "/dashboard/ncaaf-v34-availability-health.json"
WEATHER_HISTORY_V34_URL = RAW + "/dashboard/ncaaf-v34-weather-history-health.json"
ELIGIBILITY_V35_URL = RAW + "/dashboard/ncaaf-v35-eligibility.json"
PREGAME_V38_URL = RAW + "/dashboard/ncaaf-v38-window.json"
PROVIDER_V39_URL = RAW + "/dashboard/ncaaf-v39-provider-proof.json"
SCORECARD_V39_URL = RAW + "/dashboard/ncaaf-v39-forward-scorecard.json"
SPORTS_V40_READINESS_URL = RAW + "/dashboard/sports-v40-readiness.json"

HTML = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gambling Dashboard</title>
<style>
:root{--bg:#071019;--panel:#0e1a26;--line:#213448;--text:#edf5ff;--muted:#91a5ba;--green:#37df8b;--red:#ff6578;--amber:#efc163;--blue:#68a8ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% -10%,#123249 0,#071019 35%);color:var(--text);font-family:Inter,system-ui,sans-serif}
header,main{max-width:1380px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:20px;align-items:center}
h1,h2,h3{margin:0}.eyebrow{font-size:11px;font-weight:900;letter-spacing:.13em;color:#59dca1}.sub{color:var(--muted);font-size:12px;line-height:1.45}
button{background:#102131;color:#dce9f4;border:1px solid #294258;border-radius:9px;padding:9px 12px;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric,.panel,.card{background:linear-gradient(160deg,#0f1d2a,#0b1722);border:1px solid var(--line);border-radius:16px;padding:17px}
.metric .v{font-size:27px;font-weight:900;margin:7px 0}.panel{margin-top:16px}.twocol{display:grid;grid-template-columns:1.25fr .9fr;gap:16px}
.stack{display:flex;flex-direction:column;gap:10px}.card{background:#0a1620}.row{display:flex;justify-content:space-between;gap:10px}.pick{font-weight:800;margin:5px 0}.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.chip{font-size:11px;border:1px solid #2b4359;border-radius:999px;padding:4px 7px;color:#cbd9e7}
.off{background:#0d2b20;color:#89efb8}.sha{background:#2a2310;color:#f1cf7b}.pas{background:#18222c;color:#b7c5d4}.hero{border:2px solid #2f9e67;background:linear-gradient(145deg,#0b2119,#0a1620);box-shadow:0 0 0 1px #1a5139 inset}.hero .pick{font-size:22px}.official-banner{display:flex;align-items:center;gap:8px;color:#8ff3bd;font-weight:900;letter-spacing:.08em;font-size:12px}.official-banner:before{content:"";width:9px;height:9px;border-radius:50%;background:#37df8b;box-shadow:0 0 14px #37df8b}
.section-gap{margin-top:16px}.kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.kpi{background:#09141e;border:1px solid #20364a;border-radius:13px;padding:13px}.kpi .big{font-size:22px;font-weight:900;margin-top:5px}
table{width:100%;border-collapse:collapse;min-width:780px}th,td{padding:10px;border-bottom:1px solid #1b2c3c;text-align:left;font-size:13px}th{font-size:11px;color:#8095aa;text-transform:uppercase}.scroll{overflow:auto}
.pos{color:var(--green)}.neg{color:var(--red)}.muted{color:var(--muted)}.health{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);margin-right:6px}.dot.ok{background:var(--green)}
.league-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.league-card{background:#0a1620;border:1px solid #20364a;border-radius:14px;padding:14px}.league-title{font-weight:900;font-size:16px}.league-state{font-size:20px;font-weight:900;margin:7px 0}
.notice{border:1px solid #314b62;background:#0b1a26;border-radius:12px;padding:12px;color:#bcd0e1;font-size:12px;line-height:1.5}.view-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}.season-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.view-tab.active{border-color:#37df8b;color:#8ff3bd;background:#0d2b20}.tabs{display:flex;gap:8px;flex-wrap:wrap}.tab{font-weight:800}.tab.active{border-color:#37df8b;color:#8ff3bd;background:#0d2b20}.sport-record{font-size:24px;font-weight:900;margin:6px 0}.bankbox{border:1px solid #24465a;background:#0a1721;border-radius:14px;padding:15px;margin-top:12px}
@media(max-width:980px){.grid{grid-template-columns:repeat(2,1fr)}.twocol{grid-template-columns:1fr}.health,.league-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){header,main{padding:16px}.grid{grid-template-columns:1fr 1fr}.health,.league-grid{grid-template-columns:1fr}.kpi-row{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}}
</style></head>
<body>
<header><div><div class="eyebrow">PRIVATE MODEL ANALYTICS</div><h1>Gambling Dashboard</h1></div><div><span id="stamp" class="sub">Loading…</span> <button onclick="load()">Refresh</button> <button onclick="logout()">Log out</button></div></header>
<main>
<div class="view-tabs"><button id="overviewTab" class="view-tab active" onclick="setMainView('overview')">Dashboard</button><button id="yesterdayTab" class="view-tab" onclick="setMainView('yesterday')">Yesterday Transactions</button><button id="tennisTab" class="view-tab" onclick="setMainView('tennis')">Tennis Picks</button><button id="tennisCappersTab" class="view-tab" onclick="setMainView('tennisCappers')">Tennis Capper Evaluation</button></div>
<div id="overviewView">
<section><div class="eyebrow">ACTUAL BETTING PERFORMANCE</div><div class="grid" id="actualMetrics" style="margin-top:8px"></div></section>
<section class="panel"><div class="eyebrow">ACTUAL BY PLATFORM</div><h2>DraftKings vs Kalshi</h2><div id="platformActuals" class="grid" style="margin-top:12px"></div></section>

<section class="twocol">
<div class="panel">
  <div class="eyebrow">TODAY'S OFFICIAL BETS</div><h2>Official Picks</h2>
  <div id="officialToday" class="stack" style="margin-top:12px"><div class="sub">Loading today’s picks…</div></div>
  <div class="section-gap"><div class="eyebrow">SHADOW / PASS</div><div id="otherToday" class="stack" style="margin-top:10px"></div></div>
  <div class="section-gap sub"><span id="tennisOverviewStatus" aria-live="polite">Tennis model loading…</span> <button type="button" onclick="setMainView('tennis')">Tennis model details</button></div>
</div>
<div class="panel">
  <div class="eyebrow">MODEL BANKROLL</div><h2>Paper Model Capital</h2>
  <div class="kpi-row" style="margin-top:12px">
    <div class="kpi"><div class="sub">Total Capital</div><div id="paperTotal" class="big">100.00u</div></div>
    <div class="kpi"><div class="sub">Available</div><div id="paperAvail" class="big">100.00u</div></div>
    <div class="kpi"><div class="sub">Committed</div><div id="paperCommitted" class="big">0.00u</div></div>
  </div>
  <p class="sub">This is the paper-model bankroll, not your DraftKings/account cash balance. Pending stakes are shown as committed rather than treated as a loss.</p>
  <div class="bankbox"><div class="eyebrow">BANK REFILL</div><div id="bankRefill" style="font-size:25px;font-weight:900;margin-top:5px">—</div><div id="bankRefillDetail" class="sub" style="margin-top:6px"></div><div id="bookCashFlow" class="sub" style="margin-top:6px"></div></div>
</div>
</section>
<section class="panel"><div class="eyebrow">SPORT COMPARISON</div><h2>How Are the Models Doing?</h2><div class="season-tabs" id="seasonTabs"><button class="tab active" data-season="ACTIVE" onclick="setSeasonView('ACTIVE')">Active Season</button><button class="tab" data-season="ALL" onclick="setSeasonView('ALL')">All-Time</button></div><div class="tabs" id="trackTabs" style="margin-top:12px"><button class="tab active" data-track="OFFICIAL" onclick="setPerfTrack('OFFICIAL')">Official</button><button class="tab" data-track="SHADOW" onclick="setPerfTrack('SHADOW')">Shadow</button></div><div class="tabs" id="perfTabs" style="margin-top:10px"><button class="tab active" data-league="ALL" onclick="setPerfLeague('ALL')">All Sports</button><button class="tab" data-league="MLB" onclick="setPerfLeague('MLB')">MLB</button><button class="tab" data-league="NFL" onclick="setPerfLeague('NFL')">NFL</button><button class="tab" data-league="NCAAF" onclick="setPerfLeague('NCAAF')">NCAAF</button><button class="tab" data-league="NBA" onclick="setPerfLeague('NBA')">NBA</button><button class="tab" data-league="NCAAB" onclick="setPerfLeague('NCAAB')">NCAAB</button><button class="tab" data-league="WNBA" onclick="setPerfLeague('WNBA')">WNBA</button><button class="tab" data-league="NHL" onclick="setPerfLeague('NHL')">NHL</button><button class="tab" data-league="EPL" onclick="setPerfLeague('EPL')">Premier League</button><button class="tab" data-league="SERIEA" onclick="setPerfLeague('SERIEA')">Serie A</button><button class="tab" data-league="MLS" onclick="setPerfLeague('MLS')">MLS</button><button class="tab" data-league="TENNIS" onclick="setPerfLeague('TENNIS')">Tennis</button></div><div id="sportHeadline" class="notice" style="margin-top:12px"></div><div id="sportPerf" class="grid" style="margin-top:12px"></div></section>

<div id="capperHome"><section id="capperPanel" class="panel"><div class="eyebrow">SOURCE-VERIFIED PAPER TRACKING</div><h2 id="capperTitle">Capper Performance by Sport</h2><button id="tennisCapperShortcut" type="button" onclick="setMainView('tennisCappers')" style="margin-top:10px">View tennis capper picks</button><div id="capperScanBanner" class="notice" style="margin-top:12px">Checking source scan status...</div>
<div class="eyebrow" style="margin-top:18px">LATEST SOURCE-LINKED PICKS · FORWARD AND ARCHIVED</div>
<div class="scroll" style="margin-top:10px"><table><thead><tr><th>Capper</th><th>Sport</th><th>Date</th><th>Selection</th><th>Odds</th><th>Result</th><th>Tracking cohort</th><th>Source</th></tr></thead><tbody id="capperLatestRows"></tbody></table></div>
<div class="notice" style="margin-top:12px">Forward W–L–P and ROI use reviewed picks observed before match start. Publisher-reported records appear below for reference. All results use paper units.</div>
<div class="eyebrow" style="margin-top:20px">SELECT CAPPER</div>
<div id="capperTabs" class="tabs" role="tablist" aria-label="Capper" style="margin-top:9px"></div>
<div class="eyebrow" style="margin-top:18px">SELECT SPORT</div>
<div id="capperSportTabs" class="tabs" role="tablist" aria-label="Sport" style="margin-top:9px"></div>
<div id="capperHeadline" class="notice" style="margin-top:14px"></div>
<div id="capperCards" class="grid" style="margin-top:12px"></div>
<div class="eyebrow" style="margin-top:20px">FORWARD PAPER RESULTS BY SPORT</div>
<div class="scroll" style="margin-top:10px"><table><thead><tr><th>Sport</th><th>W-L-P</th><th>Pending</th><th>Net units</th><th>ROI</th><th>Qualification</th></tr></thead><tbody id="capperForwardRows"></tbody></table></div>
<div class="eyebrow" style="margin-top:20px">SOURCE-REVIEWED PICKS · FORWARD SAMPLE</div>
<div class="scroll" style="margin-top:12px"><table><thead><tr><th>Game date</th><th>Sport</th><th>Event</th><th>Selection</th><th>Odds</th><th>Result</th><th>P/L</th><th>Source</th></tr></thead><tbody id="capperRows"></tbody></table></div>
<div class="eyebrow" style="margin-top:20px">PREVIOUS SOURCED PICKS · ARCHIVED (EXCLUDED FROM FORWARD ROI)</div>
<div class="scroll" style="margin-top:10px"><table><thead><tr><th>Date</th><th>Sport</th><th>Event</th><th>Selection</th><th>Odds</th><th>Result</th><th>Source</th></tr></thead><tbody id="capperArchivedRows"></tbody></table></div>
<div class="eyebrow" style="margin-top:20px">PUBLISHED HISTORY · NOT INDEPENDENTLY AUDITED</div>
<div class="scroll" style="margin-top:10px"><table><thead><tr><th>Sport</th><th>Reported W-L-P</th><th>Reported units</th><th>Reported ROI</th><th>As of</th><th>Audit status</th><th>Source</th></tr></thead><tbody id="capperEvidenceRows"></tbody></table></div>
<div id="capperStatus" class="sub" style="margin-top:10px"></div>
<div id="capperLeadList" class="stack" style="margin-top:12px"></div></section></div>
<section class="panel"><div class="eyebrow">LEAGUES</div><h2>Model Status & Advice</h2><div id="leagueGrid" class="league-grid" style="margin-top:12px"></div></section>
<section class="panel"><div class="eyebrow">VALIDATION LAB · RESEARCH ONLY</div><h2>Model Health Across All Seven Sports</h2>
  <div class="notice" style="margin-top:12px">These are preliminary retrospective model diagnostics, not live betting predictions or proof of profitable Kalshi edges. Green data-collection jobs do not authorize paper picks.</div>
  <div id="researchSummary" class="sub" style="margin-top:12px">Research health report not yet available.</div>
  <div id="researchHealth" class="league-grid" style="margin-top:12px"></div>
</section>
<section class="panel">
  <div class="eyebrow">NCAA FOOTBALL · INDIVIDUAL EVIDENCE CHECKS</div>
  <h2>Which Matchups Are Blocked?</h2>
  <div class="notice" style="margin-top:12px">These are research diagnostics, not betting recommendations. No game is automatically approved; official and shadow picks retain independent policy checks.</div>
  <div id="eligibilitySummary" class="sub" style="margin-top:12px">Awaiting game-by-game research report.</div>
  <div id="eligibilityGrid" class="league-grid" style="margin-top:12px"></div>
</section>



<section class="panel"><div class="eyebrow">MODEL PERFORMANCE</div><h2>Official / Shadow Ledger</h2><div id="modelPerf" class="grid" style="margin-top:12px"></div></section>

<section class="panel"><div class="eyebrow">LEDGER</div><h2>Recent Picks</h2><div class="scroll" style="margin-top:12px"><table><thead><tr><th>Date</th><th>League</th><th>Track</th><th>Selection</th><th>Edge</th><th>Grade</th><th>Result</th></tr></thead><tbody id="rowsTable"></tbody></table></div></section>

<section class="panel"><div class="eyebrow">SYSTEM</div><h2>Feed Health</h2><div id="health" class="health" style="margin-top:12px"></div></section>
</div>
<div id="yesterdayView" style="display:none">
<section class="panel" style="margin-top:0"><div class="eyebrow">RECONCILIATION</div><h2>Yesterday's Betting Transactions</h2><div id="yesterdaySummary" class="grid" style="margin-top:12px"></div><div id="yesterdayMeta" class="sub" style="margin-top:12px"></div><div class="scroll" style="margin-top:12px"><table><thead><tr><th>Time ET</th><th>Platform</th><th>Sport</th><th>Market</th><th>Selection</th><th>Risk</th><th>Price</th><th>Result</th><th>Net P/L</th><th>Trade ID</th></tr></thead><tbody id="yesterdayRows"></tbody></table></div></section>
</div>
<div id="tennisView" style="display:none">
<section class="panel">
<h2>ATP &amp; WTA Singles Model</h2>
<p class="sub">Paper picks for Kalshi match winners. The model uses surface Elo, checks the scheduled start and live pregame quotes, and excludes selections above 75% model probability. History from <a class="sub" target="_blank" rel="noopener noreferrer" href="https://huggingface.co/datasets/minmaxxxer/atp-wta-matches-with-odds">Min Maxxxer / Tennis Odds Actor</a>.</p>
<div id="tennisFeedStatus" class="notice" aria-live="polite"></div>
<h3 style="margin-top:16px">Today's picks</h3>
<div class="scroll"><table><thead><tr><th>Track</th><th>Match / start ET</th><th>Selection</th><th>Model win</th><th>YES ask</th><th>Edge after fee</th><th>Risk</th><th>Result</th></tr></thead><tbody id="tennisTodayRows"></tbody></table></div>
<h3 style="margin-top:16px">Paper performance</h3>
<div id="tennisPerformance" class="grid" style="margin-top:12px"></div>
<h3 style="margin-top:16px">Recent previous picks</h3>
<div class="scroll"><table><thead><tr><th>Track</th><th>Match / start ET</th><th>Selection</th><th>Model win</th><th>YES ask</th><th>Edge after fee</th><th>Risk</th><th>Result</th></tr></thead><tbody id="tennisPreviousRows"></tbody></table></div>
</section></div>
<div id="tennisCappersView" style="display:none"></div>
</main>
<script>
let picksLoaded=false,picksUnavailable=false,capperPicksUnavailable=false,tennisRowsForOverview=[],tennisUnavailable=false,tennisData=null,tennisCapperView=false,overviewCapperId="koerner",overviewCapperSport="ALL";
let capperData=null,capperDiscovery=null,capperQualification=null,capperArchive=null,capperSelectedId="koerner",capperSelectedSport="ALL",rows=[],statusData={feeds:[]},researchData={leagues:[]},ncaafContext={},privateMetrics={},yesterdayBets={date:null,rows:[]},perfLeague="ALL",perfTrack="OFFICIAL",seasonView="ACTIVE";
const ACTIVE_LEAGUES=["NFL","NCAAF","NBA","NHL","NCAAB","EPL","SERIEA","MLS","TENNIS"];
const ALL_LEAGUES=["MLB","NFL","NCAAF","NBA","WNBA","NHL","NCAAB","EPL","SERIEA","MLS","TENNIS"];
function scopedRows(){
 const available=seasonView==="ALL"?rows:rows.filter(r=>ACTIVE_LEAGUES.includes(r.league));
 return available.concat(tennisRowsForOverview);
}
function tennisOverviewRow(pick){
 return {
  league:"TENNIS",dateET:pick.dateET,trackType:pick.track,
  selection:pick.selection+" to win (Kalshi YES)",
  event:pick.tour+" · "+pick.tournament+" · vs. "+pick.opponent,
  category:"Singles match winner",odds:(pick.ask*100).toFixed(1)+"¢ YES",
  edge:(pick.edge*100).toFixed(1),stakeUnits:pick.stakeUnits,
  reason:"Model win probability "+(pick.probability*100).toFixed(1)+"% · Edge after estimated fee",
  result:pick.result,plUnits:pick.plUnits,boardTimestampET:pick.observedAtUTC
 };
}
const E=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
const N=v=>{const n=parseFloat(String(v??"").replace(/[+%$u,]/g,""));return Number.isFinite(n)?n:null};
const etDateFormat=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"});
function todayET(){
 const parts=Object.fromEntries(etDateFormat.formatToParts(new Date()).map(({type,value})=>[type,value]));
 return [parts.year,parts.month,parts.day].join("-");
}
const settled=r=>["WIN","WON","LOSS","LOST","PUSH","SCALAR"].includes(String(r.result||"").toUpperCase());
function perf(rs){let w=0,l=0,p=0,pnl=0,risk=0;rs.filter(settled).forEach(r=>{const x=String(r.result||"").toUpperCase();if(x.includes("WIN"))w++;else if(x.includes("LOSS")||x.includes("LOST"))l++;else if(x==="PUSH")p++;const q=N(r.plUnits);if(q!==null)pnl+=q;const s=N(r.stakeUnits);if(s!==null)risk+=s});return{w,l,p,pnl,risk,roi:risk?100*pnl/risk:null}}
const unit=v=>{const n=N(v);return n===null?"—":(n>0?"+":"")+n.toFixed(2)+"u"};
const money=v=>{const n=N(v);return n===null?"—":(n<0?"-$":"$")+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})};
function friendly(r){
 if(r.trackType==="OFFICIAL" && r.category==="Total" && String(r.selection||"").startsWith("NO — Over")){
   return "UNDER "+E(r.line||"")+" POINTS";
 }
 return E(r.selection||"");
}
function renderActual(){
 const vals=[
  ["Yesterday",privateMetrics.actualYesterdayPnl],
  ["This Week",privateMetrics.actualWeekPnl],
  ["Last 30 Days",privateMetrics.actual30dPnl],
  ["All Time",privateMetrics.actualAllTimePnl]
 ];
 actualMetrics.innerHTML=vals.map(x=>{const n=N(x[1]);return '<div class="metric"><div class="sub">'+x[0]+' Net P/L</div><div class="v '+(n>0?'pos':n<0?'neg':'')+'">'+money(x[1])+'</div><div class="sub">Settled tracked betting performance</div></div>'}).join("");
 const refill=N(privateMetrics.netBankRefill); bankRefill.textContent=money(refill);
 bankRefill.className=refill>0?"pos":refill<0?"neg":"";
 bankRefillDetail.textContent="Returned to bank "+money(privateMetrics.returnedToBank)+" · Added from bank "+money(privateMetrics.addedFromBank);
 bookCashFlow.textContent="DraftKings net "+money(privateMetrics.draftKingsNetBankRefill)+" · Kalshi net "+money(privateMetrics.kalshiNetBankRefill)+" (cash flow only)";
 const platforms=[["DraftKings",privateMetrics.draftKingsPnl],["Kalshi",privateMetrics.kalshiPnl]];
 platformActuals.innerHTML=platforms.map(x=>{const n=N(x[1]);return '<div class="metric"><div class="sub">'+x[0]+' Actual P/L</div><div class="v '+(n>0?'pos':n<0?'neg':'')+'">'+money(x[1])+'</div><div class="sub">Settled tracked bets only</div></div>'}).join("");
}
function pickCard(r,hero){
 const execution=r.odds?'<span class="chip">Execution: '+E(r.odds)+'</span>':'';
 return '<div class="card '+(hero?'hero':'')+'">'+(hero?'<div class="official-banner">OFFICIAL PICK</div>':'')+'<div class="row"><span class="chip '+(r.trackType==="OFFICIAL"?'off':r.trackType==="SHADOW"?'sha':'pas')+'">'+E(r.trackType)+'</span><span>'+E(r.result||"Pending")+'</span></div><div class="pick">'+friendly(r)+'</div><div class="sub">'+E(r.league)+' · '+E(r.event)+'</div><div class="chips"><span class="chip">'+E(r.category)+'</span>'+execution+(r.edge?'<span class="chip">Edge '+E(r.edge)+' pp</span>':'')+(r.confidence?'<span class="chip">'+E(r.confidence)+'</span>':'')+(r.stakeUnits?'<span class="chip">Stake '+E(r.stakeUnits)+'u</span>':'')+'</div><div class="sub" style="margin-top:8px">'+E(r.reason||"")+'</div></div>';
}
function renderToday(){
 const date=todayET();
 const t=scopedRows().filter(r=>r.dateET===date);
 const status=tennisModelStatus(date,t.filter(r=>r.league==="TENNIS").length);
 tennisOverviewStatus.textContent="Tennis · "+status.detail;
 const waiting=picksUnavailable?"The main picks feed is unavailable.":"Loading the main picks feed…";
 const hasTennis=t.some(r=>r.league==="TENNIS");
 if(!picksLoaded&&!hasTennis){
  officialToday.textContent=waiting;
  otherToday.textContent="";
  return;
 }
 const off=t.filter(r=>r.trackType==="OFFICIAL"), other=t.filter(r=>r.trackType!=="OFFICIAL");
 officialToday.innerHTML=off.length?off.map(r=>pickCard(r,true)).join(""):'<div class="notice">No Official picks have been published for '+E(todayET())+' ET.</div>';
 otherToday.innerHTML=other.length?other.map(r=>pickCard(r,false)).join(""):'<div class="sub">No shadows or passes today.</div>';
 if(!picksLoaded)officialToday.insertAdjacentHTML("beforeend",'<div class="sub">'+E(waiting)+'</div>');
}
function renderBankroll(){
 const tracked=rows.filter(r=>r.trackType==="OFFICIAL" && N(r.officialBankrollUnits)!==null);
 const values=tracked.map(r=>N(r.officialBankrollUnits)).filter(v=>v!==null);
 const available=values.length?values[values.length-1]:100;
 const committed=tracked.filter(r=>!settled(r)).reduce((a,r)=>a+(N(r.stakeUnits)||0),0);
 const total=available+committed;
 paperTotal.textContent=total.toFixed(2)+"u";
 paperAvail.textContent=available.toFixed(2)+"u";
 paperCommitted.textContent=committed.toFixed(2)+"u";
}
function renderLeagueGrid(){
 const leagues=seasonView==="ALL"?ALL_LEAGUES:ACTIVE_LEAGUES;
 const current=scopedRows();
 const date=todayET();
 leagueGrid.innerHTML=leagues.map(l=>{
   const today=current.filter(r=>r.league===l&&r.dateET===date);
   const off=today.find(r=>r.trackType==="OFFICIAL");
   const pass=today.find(r=>r.trackType==="PASS");
   const sh=today.filter(r=>r.trackType==="SHADOW").length;
   const feed=(statusData.feeds||[]).find(f=>f.key.toUpperCase()===l || (l==="NCAAF"&&f.key==="ncaafb"));
   let state="No current model entry",detail="";
   const freshFeed=feed&&feed.ok&&(!feed.date||feed.date===todayET());
   if(off){state="OFFICIAL PICK";detail=friendly(off);}
   else if(pass){state=E(pass.selection||"PASS");detail=E(pass.reason||"");}
   else if(l==="TENNIS"){const status=tennisModelStatus(date,today.length);state=E(status.state);detail=E(status.detail);}
   else if(feed&&feed.ok&&!freshFeed){state="STALE BOARD";detail="Last published board: "+E(feed.date||"unknown")+". Waiting for the next scheduled refresh.";}
   else if(l==="MLB"&&freshFeed){state="BOARD LIVE";detail=(feed.count||0)+" MLB candidates available — model advice has not synced yet.";}
   else if(freshFeed){state="FEED LIVE";detail=(feed.count||0)+" candidates/entries available.";}
   else if(feed&&!feed.ok){state="NO LIVE FEED";detail="Waiting for the next scheduled board.";}
   return '<div class="league-card"><div class="league-title">'+l+'</div><div class="league-state '+(state==="OFFICIAL PICK"?'pos':'')+'">'+state+'</div><div class="sub">'+detail+'</div><div class="sub" style="margin-top:8px">'+sh+' shadow'+(sh===1?'':'s')+' today</div></div>';
 }).join("");
}
function setSeasonView(v){seasonView=v;perfLeague="ALL";document.querySelectorAll("#seasonTabs .tab").forEach(b=>b.classList.toggle("active",b.dataset.season===v));renderLeagueGrid();renderSportComparison();renderModelPerf();renderLedger();renderHealth();renderToday();}
function setPerfLeague(l){perfLeague=l;document.querySelectorAll("#perfTabs .tab").forEach(b=>b.classList.toggle("active",b.dataset.league===l));renderSportComparison()}
function setPerfTrack(t){perfTrack=t;document.querySelectorAll("#trackTabs .tab").forEach(b=>b.classList.toggle("active",b.dataset.track===t));renderSportComparison()}
function sportVerdict(p,track){
 const n=p.w+p.l;if(!n)return "No settled "+track+" bets yet — still collecting evidence.";
 const rate=100*p.w/n;
 if(n<5)return "Very early sample — "+p.w+"-"+p.l+" so far. Too soon to judge the model.";
 if(track==="SHADOW"){
   if(rate>=60)return "🔥 Shadow ideas are hitting well so far — useful evidence for model development.";
   if(rate<40)return "🧊 Shadow ideas are struggling — useful signal that these marginal edges are not holding up.";
   return "⚖️ Shadow results are mixed so far — keep collecting evidence.";
 }
 if(p.pnl>=3 && rate>=60)return "🔥 This model is killing it so far — strong record and positive units.";
 if(p.pnl>0)return "📈 Positive so far — the model is making money, but keep watching the sample.";
 if(p.pnl<=-3 || rate<40)return "🧊 This model is struggling — negative results warrant a close look before trusting the edge.";
 return "⚖️ Mixed results so far — no clear edge in the settled sample yet.";
}
function renderSportComparison(){
 const leagues=seasonView==="ALL"?ALL_LEAGUES:ACTIVE_LEAGUES;
 document.querySelectorAll("#perfTabs .tab").forEach(b=>{b.style.display=leagues.includes(b.dataset.league)||b.dataset.league==="ALL"?"":"none";});
 if(perfLeague!=="ALL"&&!leagues.includes(perfLeague))perfLeague="ALL";
 document.querySelectorAll("#perfTabs .tab").forEach(b=>b.classList.toggle("active",b.dataset.league===perfLeague));
 const selected=perfLeague==="ALL"?leagues:[perfLeague];
 const tracked=scopedRows().filter(r=>r.trackType===perfTrack);
 const cards=selected.map(l=>{
  const rs=tracked.filter(r=>r.league===l);
  const p=perf(rs);
  const n=p.w+p.l;
  const rate=n?100*p.w/n:null;
  const scalar=rs.filter(r=>r.result==="SCALAR").length;
  const note=scalar?scalar+" partial settlement"+(scalar===1?"":"s")+" included in units and ROI.":sportVerdict(p,perfTrack);
  return {l,p,rate,note};
 });
 const trackLabel=perfTrack==="OFFICIAL"?"OFFICIAL":"SHADOW";
 if(perfLeague==="ALL"){
   const all=perf(tracked);
   const rate=(all.w+all.l)?100*all.w/(all.w+all.l):null;
   sportHeadline.innerHTML="<b>All-sports "+trackLabel+" record: "+all.w+"-"+all.l+(all.p?"-"+all.p:"")+"</b>"+(perfTrack==="OFFICIAL"?" · "+unit(all.pnl)+(all.roi!==null?" · ROI "+all.roi.toFixed(1)+"%":""):(rate!==null?" · Hit rate "+rate.toFixed(1)+"%":""))+"<br><span class='sub'>"+(perfTrack==="OFFICIAL"?"Official settled paper bets only; shadow bets never affect these records.":"Shadow results are diagnostic only and do not affect the official bankroll.")+"</span>";
 }else{
   const x=cards[0];
   sportHeadline.innerHTML="<b>"+x.l+" "+trackLabel+": "+x.p.w+"-"+x.p.l+(x.p.p?"-"+x.p.p:"")+(perfTrack==="OFFICIAL"?" · "+unit(x.p.pnl)+(x.p.roi!==null?" · ROI "+x.p.roi.toFixed(1)+"%":""):(x.rate!==null?" · Hit rate "+x.rate.toFixed(1)+"%":""))+"</b><br>"+x.note;
 }
 sportPerf.innerHTML=cards.map(x=>'<div class="metric"><div class="sub">'+x.l+' '+trackLabel+'</div><div class="sport-record">'+x.p.w+'-'+x.p.l+(x.p.p?'-'+x.p.p:'')+'</div>'+(perfTrack==="OFFICIAL"?'<div class="'+(x.p.pnl>0?'pos':x.p.pnl<0?'neg':'')+'"><b>'+unit(x.p.pnl)+'</b>'+(x.p.roi!==null?' · '+x.p.roi.toFixed(1)+'% ROI':'')+'</div>':'<div><b>'+(x.rate!==null?x.rate.toFixed(1)+'% hit rate':'—')+'</b></div>')+'<div class="sub" style="margin-top:7px">'+x.note+'</div></div>').join("");
}
function renderModelPerf(){
 const current=scopedRows();const off=perf(current.filter(r=>r.trackType==="OFFICIAL")),sh=perf(current.filter(r=>r.trackType==="SHADOW"));
 modelPerf.innerHTML='<div class="metric"><div class="sub">Official Record</div><div class="v">'+off.w+'-'+off.l+'</div><div class="sub">'+unit(off.pnl)+(off.roi!==null?' · ROI '+off.roi.toFixed(1)+'%':'')+'</div></div><div class="metric"><div class="sub">Shadow Record</div><div class="v">'+sh.w+'-'+sh.l+'</div><div class="sub">'+unit(sh.pnl)+' diagnostic only</div></div><div class="metric"><div class="sub">Pending Official</div><div class="v">'+current.filter(r=>r.trackType==="OFFICIAL"&&!settled(r)&&String(r.result||"").toUpperCase()!=="PASS").length+'</div><div class="sub">Open paper selections</div></div><div class="metric"><div class="sub">Total Model Entries</div><div class="v">'+current.length+'</div><div class="sub">Official + shadow + pass</div></div>';
}
function renderLedger(){
 rowsTable.innerHTML=[...scopedRows()].sort((a,b)=>String(b.boardTimestampET||b.dateET).localeCompare(String(a.boardTimestampET||a.dateET))).map(r=>'<tr><td>'+E(r.dateET)+'</td><td>'+E(r.league)+'</td><td><span class="chip '+(r.trackType==="OFFICIAL"?'off':r.trackType==="SHADOW"?'sha':'pas')+'">'+E(r.trackType)+'</span></td><td>'+friendly(r)+'</td><td>'+E(r.edge||"—")+'</td><td>'+E(r.confidence||"—")+'</td><td>'+E(r.result||"Pending")+'</td></tr>').join("");
}
function renderNcaafEligibility(){
 const data=ncaafContext.eligibility||{};
 const games=data.games||[];
 if(!games.length){
   eligibilitySummary.textContent="No per-game eligibility research has been published yet.";
   eligibilityGrid.innerHTML="";
   return;
 }
 const generated=new Date(data.generatedAtUTC||0);
 const expired=!Number.isFinite(generated.getTime()) || Date.now()-generated.getTime()>120000;
 eligibilitySummary.textContent=games.length+" matchups · "+(data.games_blocked??games.length)+" blocked · "+(data.generatedAtUTC||"unknown capture time")+" · "
   +(expired?"SAVED RESEARCH SNAPSHOT EXPIRED — QUOTES NOT LIVE":"As-of-capture quote check only")
   +" · independent settled game sample "+(data.forward_independent_verified_games??0)+" / "+(data.minimum_distinct_forward_games_research_target??40)+" research target.";
 eligibilityGrid.innerHTML=games.map(g=>{
   const issues=(g.reasons||[]).slice(0,5).map(x=>'<div class="sub" style="margin-top:4px">• '+E(x)+'</div>').join("");
   const more=(g.reasons||[]).length>5?'<div class="sub">+'+E(g.reasons.length-5)+' additional checks</div>':'';
   const qbFlags=(g.secondary_qb_risk_flags_unverified||[]).filter(q=>q.source_type==="THIRD-PARTY TRANSCRIPTION - NOT OFFICIAL EVIDENCE").slice(0,4);
   const qbRisk=qbFlags.length?'<div class="sub" style="margin-top:7px">Unverified QB-position concerns (third-party only): '+qbFlags.map(q=>E(q.name)+' — '+E(q.secondary_status)).join('; ')+'</div>':'';
   const lead=String(g.supplemental_report_lead_url||"");
   const leadSafe=/^https:\/\/kickoffstatus\.com\/games\/[a-z0-9\/-]+\/?$/.test(lead);
   const leadText=leadSafe?'<div class="sub" style="margin-top:7px"><a href="'+E(lead)+'" target="_blank" rel="noopener noreferrer">Third-party matchup notes (NOT verified)</a></div>':'';
   return '<div class="league-card"><div class="league-title">'+E(g.away_team)+' at '+E(g.home_team)+'</div>'
     +'<div class="chip pas" style="display:inline-block;margin:8px 0">RESEARCH ONLY</div>'
     +'<div class="sub">Kickoff: '+E(g.kickoff_utc||"—")+'</div>'
     +'<div class="sub">Status: '+E(g.status)+'</div>'
     +'<div class="sub">Fee/depth-checked sides at capture: '+E(g.valid_live_quote_sides??0)+' / '+E(g.available_contract_side_samples??0)+'</div>'
     +'<div class="sub">Primary report verified: '+(g.game_specific_report_verified?"Yes":"No")+'</div>'
     +'<div class="sub">Conference report stage: '+E(g.conference_final_report_stage||"Not checked")+'</div>'
     +'<div class="sub">Final report deadline: '+E(g.conference_final_report_due_utc||"No verified conference policy")+'</div>'
     +leadText
     +qbRisk
     +'<div style="margin-top:7px"><b>Unmet checks</b>'+issues+more+'</div></div>';
 }).join("");
}
function renderResearchHealth(){
 const sports=["NCAAF","NFL","NBA","NHL","NCAAB","MLB","WNBA"];
 const mapped=new Map((researchData.leagues||[]).map(x=>[x.league,x]));
 const forwardReadiness=new Map((((ncaafContext||{}).sportsReadiness||{}).sports||[]).map(x=>[x.sport,x]));
 const label=n=>n===null||n===undefined?"—":Number(n).toFixed(3);
 const hasReport=(researchData.leagues||[]).length>0;
 researchSummary.textContent=hasReport
  ? "Research report: "+E((researchData.generatedAtUTC||"").slice(0,16).replace("T"," "))+" UTC · 0 production-approved leagues · Separate-season score-only evaluations."
  : "Research report not published yet. The seven-sport validation workflow must complete before accuracy results appear.";
 researchHealth.innerHTML=sports.map(league=>{
  const x=mapped.get(league);
  if(!x)return '<div class="league-card"><div class="league-title">'+league+'</div><div class="sub" style="margin-top:8px">Awaiting backtest</div></div>';
  const report=x.research_status||"UNAVAILABLE";
  const r40=forwardReadiness.get(league)||{};
  const baseline=label(x.home_prior_baseline_brier);
  const brier=label(x.winner_brier);
  const hasImprovement=x.improvement_vs_home_baseline!=null;
  const improvement=hasImprovement?(Number(x.improvement_vs_home_baseline)>0?"+":"")+Number(x.improvement_vs_home_baseline).toFixed(3):"—";
  const m=x.market_board||{};
  const gaps=(x.missing_verified_inputs||[]).slice(0,3).join(", ");
  const v=league==="NCAAF"?ncaafContext.model||{}:{};
  const w=league==="NCAAF"?ncaafContext.weather||{}:{};
  const q=league==="NCAAF"?ncaafContext.quotes||{}:{};
  const f=league==="NCAAF"?ncaafContext.forward||{}:{};
  const v34=league==="NCAAF"?ncaafContext.settlement||{}:{};
  const a34=league==="NCAAF"?ncaafContext.availability||{}:{};
  const w34=league==="NCAAF"?ncaafContext.weatherHistory||{}:{};
  const source39=league==="NCAAF"?ncaafContext.publisherSource||{}:{};
  const score39=league==="NCAAF"?ncaafContext.forwardScorecard||{}:{};
  const improved=v.calibration?'<div class="sub" style="margin-top:7px">CFBD enhanced research: '+E(v.calibration.holdout_games)+' blind-test games · Brier '+E(Number(v.calibration.holdout_brier).toFixed(3))+' · '+E(v.market_matching?.matched_events??"—")+' matched pregame Kalshi moneylines</div>':'';
  const wx=w.counts?'<div class="sub">Kickoff forecast context: '+E(w.counts.forecast_available??0)+' weather reports · '+E(w.counts.indoor_venue??0)+' indoor venues</div>':'';
  const quotes=q.unique_tickers_checked!==undefined?'<div class="sub">Public ask checks: '+E(q.unique_tickers_checked??0)+' contracts · '+E(q.market_request_results?.["CURRENT QUOTE OBSERVED"]??0)+' current asks · no execution depth verified</div>':'';
  const forward=f.archived_observations!==undefined?'<div class="sub" style="margin-top:7px">Forward validation: '+E(f.archived_observations)+' archived observations · '+E(f.latest_orderbooks_available??0)+' sampled books · '+E(f.latest_fee_estimations??0)+' fee estimates</div><div class="sub">Closing price proxies: '+E(f.closing_price_proxy_pairs??0)+' · resolved contract sides: '+E(f.contract_side_outcomes??0)+' · research only</div>':'';
  const settlement=v34.independently_verified_tickers!==undefined?'<div class="sub">Independent final score + market verified: '+E(v34.independently_verified_tickers)+' tickers · unique game samples '+E(v34.unique_game_winner_samples??0)+'</div>':'';
  const availability=a34.matched_games!==undefined?'<div class="sub">Official availability review: '+E(a34.matched_games)+' games · '+E(a34.game_specific_reports_verified??0)+' actual game reports verified</div>':'';
  const historicalWx=w34.archived_pregame_forecast_games!==undefined?'<div class="sub">Historic 24h-ahead weather: '+E(w34.archived_pregame_forecast_games)+' games · probability impact uncalibrated</div>':'';
  const publisher=source39.official_hubs_checked!==undefined?'<div class="sub">Publisher source check: '+E(source39.official_hubs_retrieved??0)+' / '+E(source39.official_hubs_checked??0)+' official portals reachable · '+E(source39.games_with_verified_publisher_link??0)+' matched games with conference-attested viewer (NOT player verification)</div>':'';
  const scorecard=score39.independently_verified_game_probability_samples!==undefined?'<div class="sub" style="margin-top:7px">Forward game scorecard: '+E(score39.independently_verified_game_probability_samples)+' independently verified games · '+E(score39.market_midpoint_baseline_samples??0)+' market comparison samples · '+E(score39.precommitted_research_candidate_games??0)+' pregame research candidates · '+E(score39.precommitted_candidate_games_awaiting_independent_settlement??0)+' awaiting settlement · '+E(score39.research_edge_strategy_distinct_games??0)+' settled candidates</div><div class="sub">Model Brier: '+E(score39.model_home_probability_brier??"Not yet measurable")+' · Historical theoretical net return: '+E(score39.theoretical_one_contract_net_pnl_sum??"No settled samples")+' (not real or official paper P/L)</div>':'';
  const forward40=r40.state?'<div class="sub" style="margin-top:8px"><b>Forward readiness: '+E(r40.state)+'</b> · '+E(r40.unique_games_with_market_snapshots??0)+' observed games · '+E(r40.independent_settled_game_samples??0)+' independently settled · '+E(r40.new_prospective_games_pending??0)+' pending</div><div class="sub">Next evidence: '+E(r40.next_model_evidence||"Not available")+'</div>':'';
  return '<div class="league-card"><div class="league-title">'+E(league)+'</div><div class="chip pas" style="display:inline-block;margin:8px 0">RESEARCH ONLY</div>'
   +'<div class="sub">Status: '+E(report)+'</div><div class="sub">Holdout games: '+E(x.holdout_games??"—")+'</div>'
   +'<div class="sub">Winner Brier: '+E(brier)+' · Baseline: '+E(baseline)+'</div>'
   +'<div class="sub">Improvement: '+E(improvement)+' (positive is better)</div>'
   +'<div class="sub">Board: '+E(m.date_et||"—")+' · '+E(m.candidate_market_count??"—")+' markets</div>'
   +'<div class="sub">Missing: '+E(gaps||"verified inputs")+'</div>'+improved+wx+quotes+forward+settlement+availability+historicalWx+publisher+scorecard+forward40+'</div>';
 }).join("");
}
function renderHealth(){
 health.innerHTML=(statusData.feeds||[]).filter(f=>seasonView==="ALL"||!["mlb","wnba"].includes(String(f.key).toLowerCase())).map(f=>{const fresh=f.ok&&(!f.date||f.date===todayET());return '<div class="card"><div><span class="dot '+(fresh?'ok':'')+'"></span><b>'+E(f.key.toUpperCase())+'</b></div><div class="sub" style="margin-top:7px">'+(f.ok?(fresh?"Current: ":"Stale: ")+E(f.date||"Available")+(f.count!=null?' · '+E(f.count)+' items':''):(f.status===404?'Not published yet':'Unavailable'))+'</div></div>'}).join("");
}
function setMainView(view){
 for(const id of ["overview","yesterday","tennis","tennisCappers"]){
  document.getElementById(id+"View").style.display=id===view?"block":"none";
  const tab=document.getElementById(id+"Tab");
  tab.classList.toggle("active",id===view);
  tab.setAttribute("aria-pressed",String(id===view));
 }
 const showTennis=view==="tennisCappers";
 if(showTennis===tennisCapperView)return;
 tennisCapperView=showTennis;
 if(showTennis){
  overviewCapperId=capperSelectedId;
  overviewCapperSport=capperSelectedSport;
  capperSelectedSport="TENNIS";
  tennisCappersView.append(capperPanel);
 }else{
  capperSelectedId=overviewCapperId;
  capperSelectedSport=overviewCapperSport;
  capperHome.append(capperPanel);
 }
 tennisCapperShortcut.hidden=showTennis;
 capperTitle.textContent=showTennis?"Tennis Capper Evaluation":"Capper Performance by Sport";
 renderCappers();
}
function tennisRows(picks,empty){
 const start=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
 return picks.map(p=>'<tr><td>'+E(p.track)+'</td><td>'+E(p.tour+" · "+p.tournament)+'<div class="sub">'+E(start.format(new Date(p.matchStartUTC))+" ET")+'</div></td><td><strong>'+E(p.selection)+'</strong><div class="sub">vs. '+E(p.opponent)+' · '+E(p.surface)+' · Best of '+E(p.bestOf)+'</div></td><td>'+E((p.probability*100).toFixed(1))+'%</td><td>'+E((p.ask*100).toFixed(1))+'¢</td><td>'+E((p.edge*100).toFixed(1))+' pp</td><td>'+E(p.stakeUnits)+'u</td><td>'+E(p.result)+(p.plUnits==null?'':' · '+E(capperUnits(p.plUnits)))+'</td></tr>').join("")||'<tr><td colspan="8">'+E(empty)+'</td></tr>';
}
function tennisModelStatus(date,pickCount){
 if(!tennisData)return tennisUnavailable?{state:"FEED UNAVAILABLE",detail:"Tennis model feed unavailable."}:{state:"LOADING",detail:"Model feed loading…"};
 if(tennisData.dateET!==date)return {state:"AWAITING TODAY’S RUN",detail:"Last report was "+tennisData.dateET+" ET."};
 const sources=Object.values(tennisData.sources||{});
 if(pickCount)return {state:"PICKS POSTED",detail:pickCount+" paper "+(pickCount===1?"pick":"picks")+" posted today."};
 if(!sources.length||sources.some(source=>source.status!=="OK"))return {state:"INCOMPLETE SCAN",detail:"Today’s tennis scan has incomplete source coverage."};
 return {state:"NO QUALIFYING PICK",detail:"No tennis pick has qualified today."};
}
function renderTennis(){
 const date=todayET();
 const current=tennisData?.dateET===date;
 const tracks=["OFFICIAL","SHADOW"];
 const picks=tennisData?.picks||[];
 const todays=picks.filter(p=>p.dateET===date);
 const previous=picks.filter(p=>p.dateET<date).slice().reverse().slice(0,20);
 const sources=Object.entries(tennisData?.sources||{}).map(([tour,x])=>tour+" "+(x.status==="OK"?x.matchedMarkets+" matched / "+x.scheduledSingles+" upcoming":x.status.toLowerCase()));
 const attempted=tennisData?.updatedAtUTC?new Date(tennisData.updatedAtUTC).toLocaleString("en-US",{timeZone:"America/New_York"})+" ET":"—";
 tennisFeedStatus.textContent=tennisData?(current?"Last run ":"Last report is from "+tennisData.dateET+" · Last run ")+attempted+" · "+sources.join(" · "):"Tennis model feed unavailable.";
 tennisTodayRows.innerHTML=tennisRows(todays,tennisModelStatus(date,todays.length).detail);
 tennisPreviousRows.innerHTML=tennisRows(previous,"No previous tennis picks recorded.");
 tennisPerformance.innerHTML=tracks.map(track=>{
  const record=picks.filter(p=>p.track===track);
  const closed=record.filter(p=>p.plUnits!=null);
  const risk=closed.reduce((sum,p)=>sum+p.stakeUnits,0);
  const pl=closed.reduce((sum,p)=>sum+p.plUnits,0);
  const wins=closed.filter(p=>p.result==="WIN").length;
  const losses=closed.filter(p=>p.result==="LOSS").length;
  return '<div class="metric"><div class="sub">'+E(track)+'</div><div class="v">'+wins+'–'+losses+'</div><div class="sub">'+E(risk?capperUnits(pl)+" · "+capperPct(100*pl/risk)+" ROI":"Awaiting settlement")+' · '+(record.length-closed.length)+' pending'+(closed.length>wins+losses?' · '+(closed.length-wins-losses)+' scalar settled':'')+'</div></div>';
 }).join("");
}
function renderYesterday(){
 const rs=yesterdayBets.rows||[];
 const totalRisk=rs.reduce((a,r)=>a+(N(r.risk)||0),0);
 const settledRs=rs.filter(r=>["Win","Loss","Push","Settled"].includes(String(r.result||"")));
 const pnl=settledRs.reduce((a,r)=>a+(N(r.pnl)||0),0);
 const wins=settledRs.filter(r=>String(r.result)==="Win").length;
 const losses=settledRs.filter(r=>String(r.result)==="Loss").length;
 const open=rs.filter(r=>String(r.result)==="Open").length;
 yesterdaySummary.innerHTML=[
  ["Transactions",rs.length],
  ["Total Risk",money(totalRisk)],
  ["Settled Record",wins+"-"+losses],
  ["Settled Net P/L",money(pnl)]
 ].map(x=>'<div class="metric"><div class="sub">'+x[0]+'</div><div class="v">'+x[1]+'</div></div>').join("");
 yesterdayMeta.textContent=(yesterdayBets.date?"Date: "+yesterdayBets.date+" · ":"")+(open?open+" still open/unsettled · ":"")+"Use this table to cross-check yesterday against DraftKings/Kalshi.";
 yesterdayRows.innerHTML=rs.length?rs.map(r=>'<tr><td>'+E(r.timeET||"")+'</td><td>'+E(r.platform||"")+'</td><td>'+E(r.sport||"")+'</td><td>'+E(r.market||"")+'</td><td>'+E(r.selection||"")+'</td><td>'+money(r.risk)+'</td><td>'+E(r.price||r.odds||"—")+'</td><td>'+E(r.result||"")+'</td><td>'+money(r.pnl)+'</td><td>'+E(r.tradeId||"")+'</td></tr>').join(""):'<tr><td colspan="10" class="muted">No transactions were loaded for yesterday.</td></tr>';
}
function capperPaperStats(picks){
 const closed=picks.filter(p=>["WIN","LOSS","PUSH"].includes(String(p.result||"").toUpperCase())&&p.plUnits!==null&&p.plUnits!==undefined&&p.riskUnits!==null&&p.riskUnits!==undefined&&Number.isFinite(Number(p.plUnits))&&Number.isFinite(Number(p.riskUnits))&&Number(p.riskUnits)>0);
 const w=closed.filter(p=>String(p.result).toUpperCase()==="WIN").length;
 const l=closed.filter(p=>String(p.result).toUpperCase()==="LOSS").length;
 const push=closed.filter(p=>String(p.result).toUpperCase()==="PUSH").length;
 const pending=picks.filter(p=>String(p.result||"PENDING").toUpperCase()==="PENDING").length;
 const units=closed.reduce((n,p)=>n+Number(p.plUnits),0);
 const risk=closed.reduce((n,p)=>n+Number(p.riskUnits),0);
 return {w,l,push,pending,units,risk,roi:risk?100*units/risk:null};
}
function capperUnits(n){return (n>0?"+":"")+n.toFixed(2)+"u"}
function capperPct(n){return n===null?"—":(n>0?"+":"")+n.toFixed(1)+"%"}
function renderCappers(){
 const scan=capperDiscovery||{};
 const calendarDay=todayET();
 const sourceStatus=(scan.sourceStatus||[]).filter(x=>!tennisCapperView||x.capperId==="zachcohen");
 const scopedScan=tennisCapperView?sourceStatus[0]:null;
 const attempt=tennisCapperView?scopedScan?.checkedAtUTC:scan.updatedAtUTC;
 const scanDate=attempt?new Date(attempt).toLocaleDateString("sv-SE",{timeZone:"America/New_York"}):"";
 const scanHealth=tennisCapperView?scopedScan?.status:scan.scanHealth;
 const fresh=tennisCapperView?scopedScan?.freshLeads:scan.freshLeadsThisRun;
 const sourceSummary=sourceStatus.map(x=>(x.provider||x.capperId)+" "+x.status.toLowerCase()).join(" · ");
 const scannedToday=scanDate===calendarDay;
 const scanProblem=!scannedToday||scanHealth!=="OK";
 capperScanBanner.style.borderColor=scanProblem?"#b08337":"#2f9e67";
 capperScanBanner.textContent=(!scannedToday?"No source scan recorded today. ":scanHealth==="OK"?"Source scan ran today. ":"Today's source scan status is "+(scanHealth||"unknown")+". ")+
   (attempt?"Last attempt "+new Date(attempt).toLocaleString("en-US",{timeZone:"America/New_York"})+" ET · "+(fresh||0)+" public leads · "+sourceSummary:"");
 const meta=capperQualification||{};
 const rosterById=new Map((capperData?.cappers||[]).map(c=>[c.id,c]));
 for(const capper of meta.roster||[])rosterById.set(capper.id,{...rosterById.get(capper.id),...capper});
 const roster=[...rosterById.values()];
 const cs=tennisCapperView?roster.filter(c=>c.sports?.includes("TENNIS")):roster;
 if(!cs.length){
  capperHeadline.textContent=capperData||capperQualification?"No capper roster was published for this view.":capperPicksUnavailable?"Capper picks feed is unavailable.":"Loading capper records…";
  for(const element of [capperCards,capperTabs,capperSportTabs,capperLatestRows,capperForwardRows,capperRows,capperArchivedRows,capperEvidenceRows,capperLeadList])element.innerHTML="";
  return;
 }
 if(!cs.some(c=>c.id===capperSelectedId))capperSelectedId=cs[0].id;
 const active=cs.find(c=>c.id===capperSelectedId);
 const sports=active.sports||[];
 if(tennisCapperView)capperSelectedSport="TENNIS";
 else if(capperSelectedSport!=="ALL"&&!sports.includes(capperSelectedSport))capperSelectedSport="ALL";
 const sport=capperSelectedSport;
 const matchesSport=p=>sport==="ALL"||p.sport===sport;
 const archivedAll=capperArchive?.picks||[];
 const archived=archivedAll.filter(p=>p.capperId===active.id&&matchesSport(p));
 const picks=(capperData?.picks||[]).filter(p=>p.capperId===active.id&&p.sourceUrl&&(p.postedAtET||p.observedAtET)&&p.selection&&p.dateET&&p.status==="SOURCE_REVIEWED_FORWARD_PAPER");
 const selected=picks.filter(matchesSport);
 const status=capperData?.qualificationsBySport||{};
 const role=({PRIMARY_BENCHMARK:"Primary research benchmark",EVALUATION:"Evaluation candidate",COMPARISON_ONLY:"Comparison only"})[active.role]||"Research";
 capperTabs.innerHTML=cs.map(c=>'<button type="button" class="tab'+(c.id===active.id?" active":"")+'" data-capper="'+E(c.id)+'" role="tab" aria-selected="'+(c.id===active.id)+'">'+E(c.name)+'</button>').join("");
 capperSportTabs.innerHTML=(tennisCapperView?['TENNIS']:['ALL',...sports]).map(k=>'<button type="button" class="tab'+(sport===k?" active":"")+'" data-capper-sport="'+E(k)+'" role="tab" aria-selected="'+(sport===k)+'">'+E(k==="ALL"?"All sports":k)+'</button>').join("");
 const total=capperPaperStats(selected);
 const qSport=sport==="ALL"?"all tracked sports":sport;
 const qualified=sport==="ALL"?sports.filter(sp=>status[active.id+":"+sp]==="AUDITED_POSITIVE"):status[active.id+":"+sport]==="AUDITED_POSITIVE"?[sport]:[];
 capperHeadline.innerHTML='<strong>'+E(active.name)+' · '+E(qSport)+'</strong><div class="sub">'+E(role)+' · '+E(qualified.length?"Independently audited positive: "+qualified.join(", "):"No independently qualified sports")+' · Results below are from our forward-observed paper picks only.</div>';
 capperCards.innerHTML=[
  ["Forward W-L-P",total.w+"-"+total.l+"-"+total.push,total.pending+" pending · "+selected.length+" observed"],
  ["Net paper units",total.risk?capperUnits(total.units):"—",total.risk?"Settled paper picks only":"No settled forward picks"],
  ["Forward paper ROI",capperPct(total.roi),total.risk?total.risk.toFixed(2)+"u settled risk":"Not enough forward data"],
  ["Tracked selections",String(selected.length),sports.length+" tracked sport"+(sports.length===1?"":"s")]
 ].map(x=>'<div class="metric"><div class="sub">'+E(x[0])+'</div><div class="v">'+E(x[1])+'</div><div class="sub">'+E(x[2])+'</div></div>').join("");
 const sportList=sport==="ALL"?sports:[sport];
 capperForwardRows.innerHTML=sportList.map(sp=>{
  const grouped=picks.filter(p=>p.sport===sp);
  const st=capperPaperStats(grouped);
  const audited=status[active.id+":"+sp]==="AUDITED_POSITIVE";
  return '<tr><td>'+E(sp)+'</td><td>'+st.w+'-'+st.l+'-'+st.push+'</td><td>'+st.pending+'</td><td>'+E(st.risk?capperUnits(st.units):"—")+'</td><td>'+E(capperPct(st.roi))+'</td><td>'+E(audited?"Independently audited":"Not yet independently qualified")+'</td></tr>';
 }).join("")||'<tr><td colspan="6">No sports assigned to this capper.</td></tr>';
 const allCurrent=capperData?.picks||[];
 const latest=[...allCurrent.map(p=>({...p,cohort:"Forward paper"})),...archivedAll.map(p=>({...p,cohort:"Research archive"}))].filter(p=>!tennisCapperView||p.sport==="TENNIS").sort((a,b)=>String(b.eventStartUTC||b.dateET).localeCompare(String(a.eventStartUTC||a.dateET))).slice(0,12);
 const capNames=Object.fromEntries([...cs.map(c=>[c.id,c.name]),["sartori","Tony Sartori"]]);
 capperLatestRows.innerHTML=latest.length?latest.map(p=>'<tr><td>'+E(capNames[p.capperId]||p.capperId)+'</td><td>'+E(p.sport)+'</td><td>'+E(p.dateET||"—")+'</td><td>'+E(p.selection)+'</td><td>'+E(p.odds===null||p.odds===undefined?"—":(Number(p.odds)>0?"+":"")+p.odds)+'</td><td>'+E(p.result||"PENDING")+'</td><td>'+E(p.cohort)+'</td><td><a href="'+E(p.sourceUrl)+'" target="_blank" rel="noopener noreferrer">Original</a></td></tr>').join(""):'<tr><td colspan="8">'+(capperPicksUnavailable?"Capper picks feed is unavailable.":"No sourced picks in forward tracking or the research archive.")+'</td></tr>';
 capperArchivedRows.innerHTML=archived.length?archived.map(p=>'<tr><td>'+E(p.dateET||"—")+'</td><td>'+E(p.sport||"—")+'</td><td>'+E(p.event||"—")+'</td><td>'+E(p.selection)+'</td><td>'+E(p.odds===null||p.odds===undefined?"—":(Number(p.odds)>0?"+":"")+p.odds)+'</td><td>'+E(p.result||"PENDING")+'</td><td><a href="'+E(p.sourceUrl)+'" target="_blank" rel="noopener noreferrer">Article</a></td></tr>').join(""):'<tr><td colspan="7">No earlier archived selections for this capper and sport.</td></tr>';
  const recent=[...selected].sort((a,b)=>String(b.eventStartUTC||b.dateET).localeCompare(String(a.eventStartUTC||a.dateET))).slice(0,100);
 capperRows.innerHTML=recent.length?recent.map(p=>{
  const pl=p.plUnits!==null&&p.plUnits!==undefined&&["WIN","LOSS","PUSH"].includes(String(p.result||"").toUpperCase())&&Number.isFinite(Number(p.plUnits))?capperUnits(Number(p.plUnits)):"—";
  return '<tr><td>'+E(p.dateET||"—")+'</td><td>'+E(p.sport||"—")+'</td><td>'+E(p.event||"—")+'</td><td><strong>'+E(p.selection)+'</strong><div class="sub">'+E(p.market||"")+' · '+E(p.publicationTimeVerified?"Published "+p.postedAtET:"First seen "+(p.observedAtET||"pregame"))+'</div></td><td>'+E(p.odds||"—")+'</td><td>'+E(p.result||"PENDING")+'</td><td>'+E(pl)+'</td><td><a href="'+E(p.sourceUrl)+'" target="_blank" rel="noopener noreferrer">Original</a></td></tr>';
 }).join(""):'<tr><td colspan="8">No forward-reviewed '+E(sport==="ALL"?"picks":"picks for "+sport)+' for '+E(active.name)+' yet. Previously archived picks are excluded from this fresh sample.</td></tr>';
 const published=(meta.publishedRecords||[]).filter(r=>r.capperId===active.id&&(sport==="ALL"||r.sport===sport));
 capperEvidenceRows.innerHTML=published.length?published.map(r=>{
  const units=r.reportedUnits===null||r.reportedUnits===undefined?null:Number(r.reportedUnits);
  const audited=Boolean(r.verifiedROI&&r.multiSeasonVerified&&r.subperiodConsistencyVerified);
  const state=r.sport==="ALL"?"All sports combined · not sport-qualified":units!==null&&units<0?"Published negative return":audited?"Independent audit details required":"Publisher/third-party report only";
  return '<tr><td>'+E(r.sport)+'</td><td>'+E(r.wins)+"-"+E(r.losses)+"-"+E(r.pushes)+'</td><td>'+E(units===null?"—":capperUnits(units))+'</td><td>'+E(r.reportedROI===null||r.reportedROI===undefined?"—":capperPct(Number(r.reportedROI)))+'</td><td>'+E(r.asOfET||"—")+'</td><td>'+E(state)+'</td><td><a href="'+E(r.sourceUrl)+'" target="_blank" rel="noopener noreferrer">Reported record</a></td></tr>';
 }).join(""):'<tr><td colspan="7">No published historical record available for this capper and sport. This does not mean a 0-0 record.</td></tr>';
 const leads=(capperDiscovery?.leads||[]).filter(l=>l.capperId===active.id&&l.candidateBestBet&&(sport==="ALL"||!(l.sports||[]).length||(l.sports||[]).includes(sport))).slice(0,8);
 capperLeadList.innerHTML=leads.length?'<div class="eyebrow">UNVERIFIED PUBLIC LEADS · NOT PICKS</div>'+leads.map(l=>'<div class="card"><div class="sub">'+E(l.published||"Publication date unavailable")+'</div><div class="pick">'+E(l.title)+'</div><div class="sub">Needs original pregame evidence and odds verification</div><a href="'+E(l.sourceUrl)+'" target="_blank" rel="noopener noreferrer">Review source</a></div>').join(""):'<div class="sub">No public leads pending review for this tab.</div>';
 capperStatus.textContent="Showing "+recent.length+" of "+selected.length+" forward paper picks · Published history not included in our W-L or ROI · Last source scan: "+(attempt||"not yet run");
}
function setCapperView(id){
 const roster=capperQualification?.roster||capperData?.cappers||[];
 if(!roster.some(c=>c.id===id))return;
 capperSelectedId=id;capperSelectedSport="ALL";renderCappers();
}
function setCapperSportView(sport){
 const roster=capperQualification?.roster||capperData?.cappers||[];
 const active=roster.find(c=>c.id===capperSelectedId);
 if(!active||(sport!=="ALL"&&!(active.sports||[]).includes(sport)))return;
 capperSelectedSport=sport;renderCappers();
}
document.getElementById("capperTabs").addEventListener("click",ev=>{
 const button=ev.target.closest("button[data-capper]");
 if(button)setCapperView(button.getAttribute("data-capper"));
});
document.getElementById("capperSportTabs").addEventListener("click",ev=>{
 const button=ev.target.closest("button[data-capper-sport]");
 if(button)setCapperSportView(button.getAttribute("data-capper-sport"));
});
let loadVersion=0;
async function load(){
 const version=++loadVersion;
 const failures=[];
 const fetchSection=async (name,apply)=>{
  const timeout=new AbortController();
  const timer=setTimeout(()=>timeout.abort(),name==="status"||name==="ncaaf-research-health"?40000:15000);
  let data=null;
  try{
   const response=await fetch("/api/"+name,{cache:"no-store",signal:timeout.signal});
   if(version!==loadVersion)return;
   if(response.status===401){location.href="/login";return;}
   if(!response.ok)throw new Error("HTTP "+response.status);
   data=await response.json();
  }catch{
   if(version!==loadVersion)return;
   failures.push(name);
  }finally{
   clearTimeout(timer);
  }
  if(version===loadVersion){
   try{apply(data);}
   catch(error){failures.push(name);console.error("Could not render "+name,error);}
  }
 };
 const modelRows=data=>{
  if(Array.isArray(data?.rows)){rows=data.rows;picksLoaded=true;}
  picksUnavailable=!data;
  renderToday();renderBankroll();renderLeagueGrid();renderSportComparison();renderModelPerf();renderLedger();
 };
 await Promise.allSettled([
  fetchSection("picks",modelRows),
  fetchSection("status",data=>{if(data)statusData=data;renderHealth();renderLeagueGrid();}),
  fetchSection("private-metrics",data=>{if(data)privateMetrics=data;renderActual();renderBankroll();}),
  fetchSection("yesterday-bets",data=>{if(data)yesterdayBets=data;renderYesterday();}),
  fetchSection("model-health",data=>{if(data)researchData=data;renderResearchHealth();}),
  fetchSection("ncaaf-research-health",data=>{if(data)ncaafContext=data;renderResearchHealth();renderNcaafEligibility();}),
  fetchSection("cappers",data=>{
   if(data)capperData=data;
   capperPicksUnavailable=!capperData;
   renderCappers();
  }),
  fetchSection("capper-qualification",data=>{if(data)capperQualification=data;renderCappers();}),
  fetchSection("capper-discovery",data=>{if(data)capperDiscovery=data;renderCappers();}),
  fetchSection("capper-archive",data=>{if(data)capperArchive=data;renderCappers();}),
  fetchSection("tennis",data=>{
   if(Array.isArray(data?.picks)){
    tennisData=data;
    tennisRowsForOverview=data.picks.map(tennisOverviewRow);
   }
   tennisUnavailable=!tennisData;
   renderToday();renderLeagueGrid();renderSportComparison();renderModelPerf();renderLedger();renderTennis();
  })
 ]);
 if(version!==loadVersion)return;
 const stampTime=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"2-digit"}).format(new Date())+" ET";
 stamp.textContent=failures.length?"Partial feed · "+failures.join(", ")+" unavailable · "+stampTime:"Updated "+stampTime;
}
async function logout(){await fetch("/api/logout",{method:"POST"});location.href="/login"}
load();setInterval(load,300000);
</script></body></html>'''

LOGIN = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dashboard Login</title><style>body{margin:0;background:#071019;color:#edf5ff;font-family:Inter,system-ui;display:grid;place-items:center;min-height:100vh}.box{width:min(420px,calc(100% - 40px));background:#0e1a26;border:1px solid #213448;border-radius:20px;padding:30px}input{width:100%;box-sizing:border-box;background:#071019;border:1px solid #2c4359;color:white;border-radius:10px;padding:13px;margin:16px 0}button{width:100%;padding:13px;border:0;border-radius:10px;background:#37df8b;font-weight:900}</style></head><body><div class="box"><div style="color:#59dca1;font-size:11px;font-weight:900;letter-spacing:.13em">PRIVATE ANALYTICS</div><h1>Gambling Dashboard</h1><p>Enter your dashboard password.</p><form method="post" action="/login"><input type="password" name="password" autofocus><button>Open Dashboard</button></form></div></body></html>'''

def fetch_json(url):
    req = urllib.request.Request(url + "?v=" + str(os.times().elapsed), headers={"User-Agent":"gambling-dashboard"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())

class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="text/html", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        if headers:
            for k,v in headers.items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(body.encode() if isinstance(body,str) else body)

    def authed(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie"))
        return c.get(COOKIE_NAME) and c[COOKIE_NAME].value == TOKEN

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/health":
            return self.send(200, json.dumps({"ok":True}), "application/json")
        if p == "/login":
            if self.authed(): return self.redirect("/")
            return self.send(200, LOGIN)
        if not self.authed():
            if p.startswith("/api/"): return self.send(401, json.dumps({"error":"unauthorized"}), "application/json")
            return self.redirect("/login")
        if p == "/":
            return self.send(200, HTML)
        if p == "/api/ncaaf-research-health":
            out={}
            for key,url in (("model",RESEARCH_V32_URL),("weather",WEATHER_V32_URL),("quotes",QUOTE_V32_URL),("forward",FORWARD_V33_URL),("settlement",SETTLEMENT_V34_URL),("availability",AVAILABILITY_V34_URL),("weatherHistory",WEATHER_HISTORY_V34_URL),("eligibility",ELIGIBILITY_V35_URL),("pregameWindow",PREGAME_V38_URL),("publisherSource",PROVIDER_V39_URL),("forwardScorecard",SCORECARD_V39_URL),("sportsReadiness",SPORTS_V40_READINESS_URL)):
                try: out[key]=fetch_json(url)
                except Exception: out[key]={}
            return self.send(200,json.dumps(out),"application/json")
        if p == "/api/model-health":
            try: return self.send(200,json.dumps(fetch_json(FEEDS["model_health"])),"application/json")
            except Exception: return self.send(404,json.dumps({"error":"research report not published yet"}),"application/json")
        if p == "/api/tennis":
            try: return self.send(200,json.dumps(fetch_json(FEEDS["tennis"])),"application/json")
            except Exception: return self.send(503,json.dumps({"error":"tennis model feed unavailable"}),"application/json")
        if p == "/api/capper-discovery":
            try: return self.send(200,json.dumps(fetch_json(FEEDS["capper_discovery"])),"application/json")
            except Exception: return self.send(200,json.dumps({"leads":[],"updatedAtUTC":None}),"application/json")
        if p == "/api/capper-archive":
            try: return self.send(200,json.dumps(fetch_json(FEEDS["capper_archive"])),"application/json")
            except Exception: return self.send(503,json.dumps({"picks":[]}),"application/json")
        if p == "/api/capper-qualification":
            try: return self.send(200,json.dumps(fetch_json(FEEDS["capper_qualification"])),"application/json")
            except Exception: return self.send(503,json.dumps({"error":"capper qualification report unavailable"}),"application/json")
        if p == "/api/cappers":
            try: return self.send(200,json.dumps(fetch_json(FEEDS["cappers"])),"application/json")
            except Exception: return self.send(503,json.dumps({"error":"capper feed unavailable"}),"application/json")
        if p == "/api/picks":
            try: return self.send(200, json.dumps(fetch_json(FEEDS["picks"])), "application/json")
            except Exception as e: return self.send(502, json.dumps({"error":str(e)}), "application/json")
        if p == "/api/private-metrics":
            try:
                actual=fetch_json(FEEDS["actual"])
            except Exception:
                actual={}
            data={
                "actualYesterdayPnl": actual.get("actualYesterdayPnl", os.environ.get("ACTUAL_YESTERDAY_PNL")),
                "actualWeekPnl": actual.get("actualWeekPnl", os.environ.get("ACTUAL_WEEK_PNL")),
                "actual30dPnl": actual.get("actual30dPnl", os.environ.get("ACTUAL_30D_PNL")),
                "actualAllTimePnl": actual.get("actualAllTimePnl", os.environ.get("ACTUAL_ALL_TIME_PNL")),
                "actualAllTimeWinnings": actual.get("actualAllTimeWinnings", os.environ.get("ACTUAL_ALL_TIME_WINNINGS")),
                "actualAllTimeLost": actual.get("actualAllTimeLost", os.environ.get("ACTUAL_ALL_TIME_LOST")),
                "returnedToBank": os.environ.get("RETURNED_TO_BANK"),
                "addedFromBank": os.environ.get("ADDED_FROM_BANK"),
                "netBankRefill": os.environ.get("NET_BANK_REFILL"),
                "draftKingsPnl": actual.get("draftKingsPnl", os.environ.get("DRAFTKINGS_PNL")),
                "kalshiPnl": actual.get("kalshiPnl", os.environ.get("KALSHI_PNL")),
                "draftKingsReturnedToBank": os.environ.get("DRAFTKINGS_RETURNED_TO_BANK"),
                "draftKingsAddedFromBank": os.environ.get("DRAFTKINGS_ADDED_FROM_BANK"),
                "draftKingsNetBankRefill": os.environ.get("DRAFTKINGS_NET_BANK_REFILL"),
                "kalshiReturnedToBank": os.environ.get("KALSHI_RETURNED_TO_BANK"),
                "kalshiAddedFromBank": os.environ.get("KALSHI_ADDED_FROM_BANK"),
                "kalshiNetBankRefill": os.environ.get("KALSHI_NET_BANK_REFILL")
            }
            return self.send(200,json.dumps(data),"application/json")
        if p == "/api/yesterday-bets":
            try:
                data=get_yesterday_bets()
            except Exception as e:
                data={"date":None,"rows":[],"error":str(e)}
            return self.send(200,json.dumps(data),"application/json")
        if p == "/api/status":
            out=[]
            for key,url in FEEDS.items():
                try:
                    d=fetch_json(url)
                    out.append({"key":key,"ok":True,"date":d.get("board_date_et") or d.get("slate_date_et"),"count":d.get("candidate_market_count") if d.get("candidate_market_count") is not None else len(d.get("rows",d.get("games",[])))})
                except urllib.error.HTTPError as e: out.append({"key":key,"ok":False,"status":e.code})
                except Exception: out.append({"key":key,"ok":False})
            return self.send(200,json.dumps({"feeds":out}),"application/json")
        return self.send(404,"Not found")

    def do_POST(self):
        p = urlparse(self.path).path
        length=int(self.headers.get("Content-Length","0"))
        data=parse_qs(self.rfile.read(length).decode()) if length else {}
        if p == "/login":
            if data.get("password",[""])[0] == PASSWORD:
                h={"Set-Cookie":f"{COOKIE_NAME}={TOKEN}; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000; Path=/"}
                return self.redirect("/",h)
            return self.redirect("/login")
        if p == "/api/logout":
            return self.send(200,json.dumps({"ok":True}),"application/json",{"Set-Cookie":f"{COOKIE_NAME}=; HttpOnly; Secure; SameSite=Lax; Max-Age=0; Path=/"})
        return self.send(404,"Not found")

    def redirect(self, location, headers=None):
        h={"Location":location}
        if headers: h.update(headers)
        self.send_response(302)
        for k,v in h.items(): self.send_header(k,v)
        self.end_headers()

    def log_message(self, fmt, *args):
        print("%s - - %s" % (self.address_string(), fmt%args))

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
