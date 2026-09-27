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
    "mlb": RAW + "/mlb-board.json",
}

HTML = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gambling Dashboard</title>
<style>
:root{--bg:#071019;--panel:#0e1a26;--line:#213448;--text:#edf5ff;--muted:#91a5ba;--green:#37df8b;--red:#ff6578;--amber:#efc163}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% -10%,#123249 0,#071019 35%);color:var(--text);font-family:Inter,system-ui,sans-serif}
header,main{max-width:1380px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:20px;align-items:center}
h1,h2{margin:0}.eyebrow{font-size:11px;font-weight:900;letter-spacing:.13em;color:#59dca1}.sub{color:var(--muted);font-size:12px}
button{background:#102131;color:#dce9f4;border:1px solid #294258;border-radius:9px;padding:9px 12px;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric,.panel,.card{background:linear-gradient(160deg,#0f1d2a,#0b1722);border:1px solid var(--line);border-radius:16px;padding:17px}
.metric .v{font-size:27px;font-weight:900;margin:7px 0}.panel{margin-top:16px}.twocol{display:grid;grid-template-columns:1.3fr .9fr;gap:16px}
.stack{display:flex;flex-direction:column;gap:10px}.card{background:#0a1620}.row{display:flex;justify-content:space-between;gap:10px}.pick{font-weight:800;margin:5px 0}.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.chip{font-size:11px;border:1px solid #2b4359;border-radius:999px;padding:4px 7px;color:#cbd9e7}.off{background:#0d2b20;color:#89efb8}.sha{background:#2a2310;color:#f1cf7b}.pas{background:#18222c;color:#b7c5d4}
table{width:100%;border-collapse:collapse;min-width:780px}th,td{padding:10px;border-bottom:1px solid #1b2c3c;text-align:left;font-size:13px}th{font-size:11px;color:#8095aa;text-transform:uppercase}.scroll{overflow:auto}
.pos{color:var(--green)}.neg{color:var(--red)}.muted{color:var(--muted)}.health{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);margin-right:6px}.dot.ok{background:var(--green)}
.login{min-height:100vh;display:grid;place-items:center}.loginbox{width:min(420px,calc(100% - 36px));background:#0e1a26;border:1px solid var(--line);border-radius:20px;padding:30px}input{width:100%;background:#071019;color:white;border:1px solid #2c4359;border-radius:10px;padding:13px;margin:14px 0}.loginbox button{width:100%;background:#37df8b;color:#04120a;font-weight:900}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.twocol{grid-template-columns:1fr}.health{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){header,main{padding:16px}.grid{grid-template-columns:1fr 1fr}.health{grid-template-columns:1fr}}
</style></head>
<body>
<header><div><div class="eyebrow">PRIVATE MODEL ANALYTICS</div><h1>Gambling Dashboard</h1></div><div><span id="stamp" class="sub">Loading…</span> <button onclick="load()">Refresh</button> <button onclick="logout()">Log out</button></div></header>
<main>
<section class="grid" id="metrics"></section>
<section class="twocol">
<div class="panel"><div class="eyebrow">TODAY</div><h2>Model Card</h2><div id="today" class="stack" style="margin-top:12px"></div></div>
<div class="panel"><div class="eyebrow">PERFORMANCE</div><h2>Official / Shadow</h2><div id="perf" style="margin-top:12px"></div><div style="margin-top:18px" class="eyebrow">OFFICIAL BANKROLL</div><div id="bankroll" style="font-size:30px;font-weight:900;margin-top:6px">100.00u</div><p class="sub">Private cash-flow connection is not enabled yet. Bank transactions and dollar balances are intentionally excluded.</p></div>
</section>
<section class="panel"><div class="eyebrow">LEDGER</div><h2>Recent Picks</h2><div class="scroll" style="margin-top:12px"><table><thead><tr><th>Date</th><th>League</th><th>Track</th><th>Selection</th><th>Edge</th><th>Grade</th><th>Result</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section class="panel"><div class="eyebrow">SYSTEM</div><h2>Feed Health</h2><div id="health" class="health" style="margin-top:12px"></div></section>
</main>
<script>
let rows=[];
const E=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
const N=v=>{const n=parseFloat(String(v??"").replace(/[+%$u,]/g,""));return Number.isFinite(n)?n:null};
const todayET=()=>new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const settled=r=>["WIN","WON","LOSS","LOST","PUSH"].includes(String(r.result||"").toUpperCase());
function perf(rs){let w=0,l=0,p=0,pnl=0,risk=0;rs.filter(settled).forEach(r=>{const x=String(r.result||"").toUpperCase();if(x.includes("WIN"))w++;else if(x.includes("LOSS")||x.includes("LOST"))l++;else p++;const q=N(r.pnlUnits);if(q!==null)pnl+=q;const s=N(r.stakeUnits);if(s!==null)risk+=s});return{w,l,p,pnl,roi:risk?100*pnl/risk:null}}
const unit=v=>{const n=N(v);return n===null?"—":(n>0?"+":"")+n.toFixed(2)+"u"};
function render(){
 const official=rows.filter(r=>r.trackType==="OFFICIAL"), shadow=rows.filter(r=>r.trackType==="SHADOW");
 const windows=[["Today",r=>r.dateET===todayET()],["This Week",r=>Date.now()-new Date(r.dateET+"T12:00:00-04:00").getTime()<=7*86400000],["Last 30 Days",r=>Date.now()-new Date(r.dateET+"T12:00:00-04:00").getTime()<=30*86400000],["All Time",r=>true]];
 metrics.innerHTML=windows.map(([label,f])=>{const p=perf(official.filter(f));return '<div class="metric"><div class="sub">'+label+'</div><div class="v '+(p.pnl>0?'pos':p.pnl<0?'neg':'')+'">'+unit(p.pnl)+'</div><div class="sub">'+p.w+'-'+p.l+(p.roi!==null?' · ROI '+p.roi.toFixed(1)+'%':'')+'</div></div>'}).join("");
 const t=rows.filter(r=>r.dateET===todayET()); today.innerHTML=t.length?t.map(r=>'<div class="card"><div class="row"><span class="chip '+(r.trackType==="OFFICIAL"?'off':r.trackType==="SHADOW"?'sha':'pas')+'">'+E(r.trackType)+'</span><span>'+E(r.result||"Pending")+'</span></div><div class="pick">'+E(r.selection)+'</div><div class="sub">'+E(r.league)+' · '+E(r.event)+'</div><div class="chips"><span class="chip">'+E(r.category)+'</span>'+(r.edge?'<span class="chip">Edge '+E(r.edge)+' pp</span>':'')+(r.confidence?'<span class="chip">'+E(r.confidence)+'</span>':'')+'</div><div class="sub" style="margin-top:8px">'+E(r.reason||"")+'</div></div>').join(""):'<p class="muted">No model entries for today yet.</p>';
 const po=perf(official), ps=perf(shadow); perf.innerHTML='<div class="grid" style="grid-template-columns:1fr 1fr"><div class="card"><div class="eyebrow">OFFICIAL</div><div class="v" style="font-size:24px;font-weight:900">'+po.w+'-'+po.l+'</div><div>'+unit(po.pnl)+'</div></div><div class="card"><div class="eyebrow">SHADOW</div><div class="v" style="font-size:24px;font-weight:900">'+ps.w+'-'+ps.l+'</div><div>'+unit(ps.pnl)+'</div></div></div>';
 const br=official.map(r=>N(r.officialBankrollUnits)).filter(v=>v!==null); bankroll.textContent=(br.length?br[br.length-1]:100).toFixed(2)+"u";
 rowsEl=document.getElementById("rows"); rowsEl.innerHTML=[...rows].sort((a,b)=>String(b.boardTimestampET||b.dateET).localeCompare(String(a.boardTimestampET||a.dateET))).map(r=>'<tr><td>'+E(r.dateET)+'</td><td>'+E(r.league)+'</td><td>'+E(r.trackType)+'</td><td>'+E(r.selection)+'</td><td>'+E(r.edge||"—")+'</td><td>'+E(r.confidence||"—")+'</td><td>'+E(r.result||"Pending")+'</td></tr>').join("");
}
async function load(){
 try{
  const [p,s]=await Promise.all([fetch("/api/picks",{cache:"no-store"}),fetch("/api/status",{cache:"no-store"})]);
  if(p.status===401){location.href="/login";return}
  const d=await p.json(); rows=d.rows||[]; render();
  const st=await s.json(); health.innerHTML=(st.feeds||[]).map(f=>'<div class="card"><div><span class="dot '+(f.ok?'ok':'')+'"></span><b>'+E(f.key.toUpperCase())+'</b></div><div class="sub" style="margin-top:7px">'+(f.ok?E(f.date||"Available")+(f.count!=null?' · '+E(f.count)+' items':''):(f.status===404?'Not published yet':'Unavailable'))+'</div></div>').join("");
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
