import os, json, hashlib, urllib.request, urllib.error
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "10000"))
PASSWORD = os.environ["DASHBOARD_PASSWORD"]
AUTH_SECRET = os.environ["AUTH_SECRET"]
TOKEN = hashlib.sha256((PASSWORD + ":" + AUTH_SECRET).encode()).hexdigest()
COOKIE_NAME = "gambling_dash_auth"
RAW = "https://raw.githubusercontent.com/vault214/dk-mlb-feed/main"
FEEDS = {
    "picks": RAW + "/dashboard/model-picks.json",
    "nfl": RAW + "/kalshi/nfl-candidates.json",
    "ncaafb": RAW + "/kalshi/ncaafb-candidates.json",
    "nba": RAW + "/kalshi/nba-candidates.json",
    "wnba": RAW + "/kalshi/wnba-candidates.json",
    "mlb": RAW + "/kalshi/mlb-candidates.json",
}

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
.notice{border:1px solid #314b62;background:#0b1a26;border-radius:12px;padding:12px;color:#bcd0e1;font-size:12px;line-height:1.5}.bankbox{border:1px solid #24465a;background:#0a1721;border-radius:14px;padding:15px;margin-top:12px}
@media(max-width:980px){.grid{grid-template-columns:repeat(2,1fr)}.twocol{grid-template-columns:1fr}.health,.league-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){header,main{padding:16px}.grid{grid-template-columns:1fr 1fr}.health,.league-grid{grid-template-columns:1fr}.kpi-row{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}}
</style></head>
<body>
<header><div><div class="eyebrow">PRIVATE MODEL ANALYTICS</div><h1>Gambling Dashboard</h1></div><div><span id="stamp" class="sub">Loading…</span> <button onclick="load()">Refresh</button> <button onclick="logout()">Log out</button></div></header>
<main>
<section><div class="eyebrow">ACTUAL BETTING PERFORMANCE</div><div class="grid" id="actualMetrics" style="margin-top:8px"></div></section>

<section class="twocol">
<div class="panel">
  <div class="eyebrow">TODAY'S OFFICIAL BETS</div><h2>Official Picks</h2>
  <div id="officialToday" class="stack" style="margin-top:12px"></div>
  <div class="section-gap"><div class="eyebrow">SHADOW / PASS</div><div id="otherToday" class="stack" style="margin-top:10px"></div></div>
</div>
<div class="panel">
  <div class="eyebrow">MODEL BANKROLL</div><h2>Paper Model Capital</h2>
  <div class="kpi-row" style="margin-top:12px">
    <div class="kpi"><div class="sub">Total Capital</div><div id="paperTotal" class="big">100.00u</div></div>
    <div class="kpi"><div class="sub">Available</div><div id="paperAvail" class="big">100.00u</div></div>
    <div class="kpi"><div class="sub">Committed</div><div id="paperCommitted" class="big">0.00u</div></div>
  </div>
  <p class="sub">This is the paper-model bankroll, not your DraftKings/account cash balance. Pending stakes are shown as committed rather than treated as a loss.</p>
  <div class="bankbox"><div class="eyebrow">BANK REFILL</div><div id="bankRefill" style="font-size:25px;font-weight:900;margin-top:5px">—</div><div id="bankRefillDetail" class="sub" style="margin-top:6px"></div></div>
</div>
</section>

<section class="panel"><div class="eyebrow">LEAGUES</div><h2>Model Status & Advice</h2><div id="leagueGrid" class="league-grid" style="margin-top:12px"></div></section>

<section class="panel"><div class="eyebrow">MODEL PERFORMANCE</div><h2>Official / Shadow Ledger</h2><div id="modelPerf" class="grid" style="margin-top:12px"></div></section>

<section class="panel"><div class="eyebrow">LEDGER</div><h2>Recent Picks</h2><div class="scroll" style="margin-top:12px"><table><thead><tr><th>Date</th><th>League</th><th>Track</th><th>Selection</th><th>Edge</th><th>Grade</th><th>Result</th></tr></thead><tbody id="rowsTable"></tbody></table></div></section>

<section class="panel"><div class="eyebrow">SYSTEM</div><h2>Feed Health</h2><div id="health" class="health" style="margin-top:12px"></div></section>
</main>
<script>
let rows=[],statusData={feeds:[]},privateMetrics={};
const E=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
const N=v=>{const n=parseFloat(String(v??"").replace(/[+%$u,]/g,""));return Number.isFinite(n)?n:null};
const todayET=()=>new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const settled=r=>["WIN","WON","LOSS","LOST","PUSH"].includes(String(r.result||"").toUpperCase());
function perf(rs){let w=0,l=0,p=0,pnl=0,risk=0;rs.filter(settled).forEach(r=>{const x=String(r.result||"").toUpperCase();if(x.includes("WIN"))w++;else if(x.includes("LOSS")||x.includes("LOST"))l++;else p++;const q=N(r.pnlUnits);if(q!==null)pnl+=q;const s=N(r.stakeUnits);if(s!==null)risk+=s});return{w,l,p,pnl,risk,roi:risk?100*pnl/risk:null}}
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
  ["Today",privateMetrics.actualTodayPnl],
  ["This Week",privateMetrics.actualWeekPnl],
  ["Last 30 Days",privateMetrics.actual30dPnl],
  ["All Time",privateMetrics.actualAllTimePnl]
 ];
 actualMetrics.innerHTML=vals.map(x=>{const n=N(x[1]);return '<div class="metric"><div class="sub">'+x[0]+' Net P/L</div><div class="v '+(n>0?'pos':n<0?'neg':'')+'">'+money(x[1])+'</div><div class="sub">Settled tracked betting performance</div></div>'}).join("");
 const refill=N(privateMetrics.netBankRefill); bankRefill.textContent=money(refill);
 bankRefill.className=refill>0?"pos":refill<0?"neg":"";
 bankRefillDetail.textContent="Returned to bank "+money(privateMetrics.returnedToBank)+" · Added from bank "+money(privateMetrics.addedFromBank);
}
function pickCard(r,hero){
 const execution=r.odds?'<span class="chip">Execution: '+E(r.odds)+'</span>':'';
 return '<div class="card '+(hero?'hero':'')+'">'+(hero?'<div class="official-banner">OFFICIAL PICK</div>':'')+'<div class="row"><span class="chip '+(r.trackType==="OFFICIAL"?'off':r.trackType==="SHADOW"?'sha':'pas')+'">'+E(r.trackType)+'</span><span>'+E(r.result||"Pending")+'</span></div><div class="pick">'+friendly(r)+'</div><div class="sub">'+E(r.league)+' · '+E(r.event)+'</div><div class="chips"><span class="chip">'+E(r.category)+'</span>'+execution+(r.edge?'<span class="chip">Edge '+E(r.edge)+' pp</span>':'')+(r.confidence?'<span class="chip">'+E(r.confidence)+'</span>':'')+(r.stakeUnits?'<span class="chip">Stake '+E(r.stakeUnits)+'u</span>':'')+'</div><div class="sub" style="margin-top:8px">'+E(r.reason||"")+'</div></div>';
}
function renderToday(){
 const t=rows.filter(r=>r.dateET===todayET());
 const off=t.filter(r=>r.trackType==="OFFICIAL"), other=t.filter(r=>r.trackType!=="OFFICIAL");
 officialToday.innerHTML=off.length?off.map(r=>pickCard(r,true)).join(""):'<div class="notice">No OFFICIAL model bet has been posted for today yet.</div>';
 otherToday.innerHTML=other.length?other.map(r=>pickCard(r,false)).join(""):'<div class="sub">No shadows or passes today.</div>';
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
 const leagues=["NFL","MLB","NCAAF","NBA","WNBA"];
 leagueGrid.innerHTML=leagues.map(l=>{
   const rs=rows.filter(r=>r.league===l), today=rs.filter(r=>r.dateET===todayET());
   const off=today.find(r=>r.trackType==="OFFICIAL");
   const pass=today.find(r=>r.trackType==="PASS");
   const sh=today.filter(r=>r.trackType==="SHADOW").length;
   const feed=(statusData.feeds||[]).find(f=>f.key.toUpperCase()===l || (l==="NCAAF"&&f.key==="ncaafb"));
   let state="No current model entry",detail="";
   if(off){state="OFFICIAL PICK";detail=friendly(off);}
   else if(pass){state=E(pass.selection||"PASS");detail=E(pass.reason||"");}
   else if(l==="MLB"&&feed&&feed.ok){state="BOARD LIVE";detail=(feed.count||0)+" MLB games available — model advice has not synced yet.";}
   else if(feed&&feed.ok){state="FEED LIVE";detail=(feed.count||0)+" candidates/entries available.";}
   else if(feed&&!feed.ok){state="NO LIVE FEED";detail="Waiting for the next scheduled board.";}
   return '<div class="league-card"><div class="league-title">'+l+'</div><div class="league-state '+(state==="OFFICIAL PICK"?'pos':'')+'">'+state+'</div><div class="sub">'+detail+'</div><div class="sub" style="margin-top:8px">'+sh+' shadow'+(sh===1?'':'s')+' today</div></div>';
 }).join("");
}
function renderModelPerf(){
 const off=perf(rows.filter(r=>r.trackType==="OFFICIAL")),sh=perf(rows.filter(r=>r.trackType==="SHADOW"));
 modelPerf.innerHTML='<div class="metric"><div class="sub">Official Record</div><div class="v">'+off.w+'-'+off.l+'</div><div class="sub">'+unit(off.pnl)+(off.roi!==null?' · ROI '+off.roi.toFixed(1)+'%':'')+'</div></div><div class="metric"><div class="sub">Shadow Record</div><div class="v">'+sh.w+'-'+sh.l+'</div><div class="sub">'+unit(sh.pnl)+' diagnostic only</div></div><div class="metric"><div class="sub">Pending Official</div><div class="v">'+rows.filter(r=>r.trackType==="OFFICIAL"&&!settled(r)).length+'</div><div class="sub">Open paper selections</div></div><div class="metric"><div class="sub">Total Model Entries</div><div class="v">'+rows.length+'</div><div class="sub">Official + shadow + pass</div></div>';
}
function renderLedger(){
 rowsTable.innerHTML=[...rows].sort((a,b)=>String(b.boardTimestampET||b.dateET).localeCompare(String(a.boardTimestampET||a.dateET))).map(r=>'<tr><td>'+E(r.dateET)+'</td><td>'+E(r.league)+'</td><td><span class="chip '+(r.trackType==="OFFICIAL"?'off':r.trackType==="SHADOW"?'sha':'pas')+'">'+E(r.trackType)+'</span></td><td>'+friendly(r)+'</td><td>'+E(r.edge||"—")+'</td><td>'+E(r.confidence||"—")+'</td><td>'+E(r.result||"Pending")+'</td></tr>').join("");
}
function renderHealth(){
 health.innerHTML=(statusData.feeds||[]).map(f=>'<div class="card"><div><span class="dot '+(f.ok?'ok':'')+'"></span><b>'+E(f.key.toUpperCase())+'</b></div><div class="sub" style="margin-top:7px">'+(f.ok?E(f.date||"Available")+(f.count!=null?' · '+E(f.count)+' items':''):(f.status===404?'Not published yet':'Unavailable'))+'</div></div>').join("");
}
function render(){renderActual();renderToday();renderBankroll();renderLeagueGrid();renderModelPerf();renderLedger();renderHealth()}
async function load(){
 try{
  const [p,s,m]=await Promise.all([fetch("/api/picks",{cache:"no-store"}),fetch("/api/status",{cache:"no-store"}),fetch("/api/private-metrics",{cache:"no-store"})]);
  if(p.status===401){location.href="/login";return}
  const d=await p.json(); rows=d.rows||[]; statusData=s.ok?await s.json():{feeds:[]}; privateMetrics=m.ok?await m.json():{}; render();
  stamp.textContent="Updated "+new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"2-digit"}).format(new Date())+" ET";
 }catch(e){stamp.textContent="Feed error";}
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
        if p == "/api/picks":
            try: return self.send(200, json.dumps(fetch_json(FEEDS["picks"])), "application/json")
            except Exception as e: return self.send(502, json.dumps({"error":str(e)}), "application/json")
        if p == "/api/private-metrics":
            data={
                "actualTodayPnl": os.environ.get("ACTUAL_TODAY_PNL"),
                "actualWeekPnl": os.environ.get("ACTUAL_WEEK_PNL"),
                "actual30dPnl": os.environ.get("ACTUAL_30D_PNL"),
                "actualAllTimePnl": os.environ.get("ACTUAL_ALL_TIME_PNL"),
                "actualAllTimeWinnings": os.environ.get("ACTUAL_ALL_TIME_WINNINGS"),
                "actualAllTimeLost": os.environ.get("ACTUAL_ALL_TIME_LOST"),
                "returnedToBank": os.environ.get("RETURNED_TO_BANK"),
                "addedFromBank": os.environ.get("ADDED_FROM_BANK"),
                "netBankRefill": os.environ.get("NET_BANK_REFILL"),
                "draftKingsPnl": os.environ.get("DRAFTKINGS_PNL")
            }
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
