#!/usr/bin/env python3
"""Read-only, prospective NCAAF research audit: Kalshi depth, fees, closing proxies and settlement.

Never places orders, generates official/shadow picks, or touches user balances.
Research observations are written only BEFORE verified kickoff with model snapshot
strictly earlier than observation and no more than 18 hours old. This is an
archive of observable public asks, not proof of fills. An orderbook quote does
NOT establish a guaranteed executable trade. All results are forward-only.
"""
import argparse
import collections
import datetime as dt
import decimal
import json
import math
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
BASE = "https://external-api.kalshi.com/trade-api/v2"
D = decimal.Decimal
FEE_RATE = D("0.07")  # Conservative standard quadratic taker-fee estimate
ONE_CENT = D("0.01")
MAX_MODEL_AGE_HOURS = 18
MIN_PREKICKOFF_MINUTES = 1
CLOSE_PROXY_MAX_GAP_MINUTES = 90
SETTLEMENT_LOOKBACK_DAYS = 8

def stamp(value):
    if not isinstance(value, str): return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except ValueError:
        return None

def dec(value):
    if value is None or isinstance(value,bool):return None
    try:
        n=D(str(value))
        return n if n.is_finite() else None
    except (decimal.InvalidOperation,ValueError,TypeError):
        return None

def market_url(ticker):
    if not re.fullmatch(r"[A-Z0-9-]{5,160}",str(ticker)):
        raise ValueError("invalid ticker")
    return BASE+"/markets/"+urllib.parse.quote(ticker,safe="-")

def get_json(url):
    req=urllib.request.Request(url, headers={"Accept":"application/json",
                                             "User-Agent":"NCAAFResearchForwardAudit/3.3"})
    try:
        with urllib.request.urlopen(req,timeout=18) as f:return json.load(f)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError, OSError):
        raise ValueError("exchange public endpoint unavailable") from None

def get_market(ticker):
    obj=get_json(market_url(ticker))
    m=obj.get("market")
    if not isinstance(m,dict) or m.get("ticker")!=ticker:
        raise ValueError("market identity mismatch")
    return m

def get_orderbook(ticker):
    obj=get_json(market_url(ticker)+"/orderbook")
    value=obj.get("orderbook_fp")
    if not isinstance(value,dict):
        raise ValueError("missing fixed-point orderbook")
    return value

def get_series(ticker):
    if not re.fullmatch(r"[A-Z0-9-]{4,100}",str(ticker)):
        raise ValueError("invalid series ticker")
    obj=get_json(BASE+"/series/"+urllib.parse.quote(ticker,safe="-"))
    series=obj.get("series")
    if not isinstance(series,dict) or series.get("ticker")!=ticker:
        raise ValueError("series identity mismatch")
    return series

def fee_spec(series, market):
    # Never substitute the default fee multiplier when absent. If a market
    # overrides a fee type/multiplier, it takes precedence.
    typ=market.get("fee_type_override") or series.get("fee_type")
    raw=market.get("fee_multiplier_override")
    if raw is None:raw=series.get("fee_multiplier")
    multiplier=dec(raw)
    if typ!="quadratic" or multiplier is None or multiplier<0 or multiplier>10:
        return None,"unverified or non-quadratic fee type/multiplier"
    return multiplier,None

def taker_fee(contracts,price,multiplier):
    n=dec(contracts);p=dec(price);m=dec(multiplier)
    if n is None or p is None or m is None or n<=0 or p<=0 or p>=1 or m<0:
        return None
    return (FEE_RATE*n*p*(1-p)*m).quantize(ONE_CENT,rounding=decimal.ROUND_CEILING)

def levels(value):
    """Preferred Kalshi orderbook_fp [bid_dollars, fixed_point_contracts]."""
    if not isinstance(value,list): return []
    result=[]
    for item in value:
        if not isinstance(item,list) or len(item)!=2:continue
        bid=dec(item[0]);qty=dec(item[1])
        if bid is None or qty is None or not (D("0")<bid<D("1") and qty>0):continue
        result.append((bid,qty))
    return sorted(result,key=lambda x:x[0],reverse=True)

def simulated_taker(book,side,contracts=D("1")):
    # A no-bid at 0.60 represents a YES ask of 0.40 (and vice versa).
    opp="no_dollars" if side=="YES" else "yes_dollars"
    remaining=dec(contracts)
    if remaining is None or remaining<=0:return None
    bids=levels(book.get(opp))
    if not bids:return None
    paid=D("0");top_price=None;top_qty=None;total_depth=sum(q for p,q in bids)
    for bid,qty in bids:
        ask=D("1")-bid
        if top_price is None:top_price=ask;top_qty=qty
        filled=min(remaining,qty)
        paid+=ask*filled;remaining-=filled
        if remaining<=0:break
    if remaining>0:return {"depth_available":False,
        "available_contracts":str(total_depth),
        "top_ask":float(top_price),"top_qty":float(top_qty)}
    vwap=paid/contracts
    return {"depth_available":True,"available_contracts":float(total_depth),
        "top_ask":float(top_price),"top_qty":float(top_qty),
        "vwap_ask":float(vwap),"book_slippage_pp":round(float(100*(vwap-top_price)),4)}

def obs_key(x):
    return str(x["ticker"])+"|"+str(x["side"])+"|"+str(x["cfbdGameId"])+"|"+str(x["quote_observed_utc"])

def select_rows(research,now):
    base=stamp(research.get("modelCapturedAtUTC"))
    if base is None:return [],"MISSING MODEL PROVENANCE"
    age=(now-base).total_seconds()/3600
    if age<0 or age>MAX_MODEL_AGE_HOURS:
        return [],"MODEL RESEARCH STALE"
    rows=[]
    for r in research.get("rows",[]):
        kick=stamp(r.get("kickoffUTC"))
        if not (r.get("researchOnly") is True and r.get("officialEligible") is False
                and r.get("side") in ("YES","NO") and kick is not None
                and kick>now+dt.timedelta(minutes=MIN_PREKICKOFF_MINUTES)):
            continue
        # New quote must be observed independently, not reusing v3.2's expired ask.
        p=dec(r.get("modelProbability"))
        if p is None or not (0<p<1):continue
        rows.append(r)
    return rows,"READY FOR RESEARCH"

def audit(research, now, market_fn=get_market, orderbook_fn=get_orderbook,
          series_fn=get_series, contracts=D("1"), clock=None):
    candidates,status=select_rows(research,now)
    output={"schemaVersion":1,"sport":"NCAAF","status":status,
            "sampled_at_utc":now.isoformat(),"model_captured_at_utc":research.get("modelCapturedAtUTC"),
            "observations":[],"excluded":{},"candidate_contract_sides":len(candidates),
            "official":None,"shadow":[],"production_eligible":False,
            "research_only":True}
    excluded=collections.Counter()
    markets={};books={};series_cache={}
    for r in candidates:
        ticker=r["ticker"]
        if ticker not in markets:
            try:
                fetched=market_fn(ticker)
                if fetched.get("ticker")!=ticker:raise ValueError("ticker mismatch")
                markets[ticker]=fetched
            except ValueError:markets[ticker]=None
        m=markets[ticker]
        if not m:excluded["MARKET FETCH FAILED"]+=1;continue
        if str(m.get("status","")).lower() not in ("active","open"):
            excluded["MARKET NOT OPEN"]+=1;continue
        kick=stamp(r["kickoffUTC"])
        if kick is None or now>=kick:
            excluded["NOT PREGAME"]+=1;continue
        if ticker not in books:
            try: books[ticker]=orderbook_fn(ticker)
            except ValueError:books[ticker]=None
        book=books[ticker]
        if not book:excluded["ORDERBOOK UNAVAILABLE"]+=1;continue
        series_ticker=str(m.get("series_ticker") or ticker.split("-")[0])
        if series_ticker not in series_cache:
            try:series_cache[series_ticker]=series_fn(series_ticker)
            except ValueError:series_cache[series_ticker]=None
        s=series_cache[series_ticker]
        spec,error=fee_spec(s,m) if s else (None,"series fee metadata unavailable")
        sim=simulated_taker(book,r["side"],contracts=contracts)
        if sim is None:
            excluded["EMPTY OPPOSITE ORDERBOOK"]+=1;continue
        if not sim.get("depth_available"):
            excluded["INSUFFICIENT ASK DEPTH"]+=1;continue
        p=dec(sim["vwap_ask"]); fee=taker_fee(contracts,p,spec) if spec is not None else None
        model=dec(r["modelProbability"])
        # Conservative net research value at a 1-contract sampled book:
        # model payout ($1 if correct) - total filled cost and taker-fee estimate.
        # This is a mark, NOT a guaranteed transaction or paper recommendation.
        expectation=(model-p)*contracts-fee if fee is not None else None
        observed=(clock or (lambda:dt.datetime.now(UTC)))()
        if observed>=kick:excluded["QUOTE OBSERVED AT OR AFTER KICKOFF"]+=1;continue
        row={
            "ticker":ticker,"side":r["side"],"cfbdGameId":str(r["cfbdGameId"]),
            "eventTicker":r.get("eventTicker"),"homeTeam":r.get("homeTeam"),
            "awayTeam":r.get("awayTeam"),"selectionLabel":r.get("selectionLabel"),
            "kickoffUTC":r["kickoffUTC"],
            "model_probability":float(model),"model_captured_utc":research["modelCapturedAtUTC"],
            "quote_observed_utc":observed.isoformat(),
            "market_open_at_observation":True,
            "orderbook_top_ask":sim["top_ask"],"book_vwap_ask":sim["vwap_ask"],
            "top_level_contracts":sim["top_qty"],"available_contracts":sim["available_contracts"],
            "book_slippage_pp":sim["book_slippage_pp"],
            "sample_contracts":float(contracts),"series_ticker":series_ticker,
            "series_fee_type":s.get("fee_type") if s else None,
            "series_fee_multiplier":float(spec) if spec is not None else None,
            "taker_fee_estimate_dollars":float(fee) if fee is not None else None,
            "net_expected_dollars_per_sample":round(float(expectation),5) if expectation is not None else None,
            "fee_method":"estimated quadratic taker, rounded up to $0.01/order" if fee is not None else error,
            "per_contract_asks_not_guaranteed":True,
            "orderbook_sampled_pre_kickoff":True,"qb_game_report_verified":False,
            "injuries_game_report_verified":False,"weather_probability_adjustment_validated":False,
            "historical_edge_validated":False,"research_only":True,
            "official_eligible":False,"shadow_eligible":False,
            "exclusion_reason":"QB/injury verification, weather effect and forward model-edge validation still missing"
        }
        output["observations"].append(row)
    output["excluded"]=dict(excluded)
    output["markets_checked"]=len(markets)
    output["orderbooks_available"]=sum(1 for b in books.values() if b)
    output["observations_with_fee_estimates"]=sum(r["taker_fee_estimate_dollars"] is not None for r in output["observations"])
    return output

def filename(archive_dir,day):
    if not re.fullmatch(r"\d{4}-\d\d-\d\d",day):raise ValueError("invalid date")
    return pathlib.Path(archive_dir)/(day+".json")

def archives(archive_dir,now):
    root=pathlib.Path(archive_dir)
    if not root.exists():return {}
    result={}
    for f in root.glob("20??-??-??.json"):
        try:
            day=dt.date.fromisoformat(f.stem)
            if abs((now.date()-day).days)>SETTLEMENT_LOOKBACK_DAYS:
                continue
            obj=json.loads(f.read_text())
            if obj.get("schemaVersion")!=1 or obj.get("sport")!="NCAAF":continue
            result[f.stem]=obj
        except (ValueError,OSError):
            continue
    return result

def merge_snapshot(existing,snapshot):
    all_data=dict(existing)
    for x in snapshot.get("observations",[]):
        day=stamp(x["kickoffUTC"]).astimezone(ET).date().isoformat()
        f=all_data.get(day,{"schemaVersion":1,"sport":"NCAAF","game_date_et":day,
                            "observations":[],"settlements":{}})
        identities={obs_key(row) for row in f["observations"]}
        if obs_key(x) not in identities:
            f["observations"].append(x)
        all_data[day]=f
    return all_data

def settle_archives(datasets, now, market_fn=get_market):
    cache={}
    for day,archive in datasets.items():
        for x in archive["observations"]:
            ticker=x["ticker"];kick=stamp(x.get("kickoffUTC"))
            if kick is None or kick>now+dt.timedelta(minutes=-15):
                continue
            if ticker in (archive.get("settlements") or {}):continue
            if ticker not in cache:
                try:cache[ticker]=market_fn(ticker)
                except ValueError:cache[ticker]=None
            m=cache[ticker]
            if m is None:continue
            outcome=str(m.get("result","")).lower()
            state=str(m.get("status","")).lower()
            if state=="settled" and outcome in ("yes","no"):
                archive.setdefault("settlements",{})[ticker]={
                    "outcome":outcome.upper(),
                    "settled_observed_utc":now.isoformat(),
                    "source":"Kalshi public market result; not an independently audited game score"}
    return datasets

def summarize(datasets,now,snapshot):
    allrows=[r for a in datasets.values() for r in a["observations"]]
    groups=collections.defaultdict(list)
    settlements={}
    for a in datasets.values():
        settlements.update(a.get("settlements",{}))
    for r in allrows:groups[(r["ticker"],r["side"],r["cfbdGameId"])].append(r)
    first=[];comparisons=[];settled=[]
    close_proxy_games=set()
    for key,observations in groups.items():
        observations.sort(key=lambda r:r["quote_observed_utc"])
        base=observations[0]
        first.append(base)
        kick=stamp(base["kickoffUTC"])
        pre=[r for r in observations if stamp(r["quote_observed_utc"])<kick]
        near=[r for r in pre if 0<=(kick-stamp(r["quote_observed_utc"])).total_seconds()/60<=CLOSE_PROXY_MAX_GAP_MINUTES]
        close=near[-1] if near else None
        if close is not None:
            close_proxy_games.add(key)
            comparisons.append({
                "ticker":key[0],"side":key[1],
                "first_observed_utc":base["quote_observed_utc"],
                "pre_kickoff_proxy_utc":close["quote_observed_utc"],
                "entry_ask":base["book_vwap_ask"],"last_pre_kickoff_ask":close["book_vwap_ask"],
                "closing_proxy_movement_pp":round(100*(base["book_vwap_ask"]-close["book_vwap_ask"]),3),
                "proxy_is_true_exchange_closing_price":False})
        outcome=settlements.get(key[0],{}).get("outcome")
        if outcome not in ("YES","NO"):continue
        y=1 if key[1]==outcome else 0
        p=base["model_probability"]
        pnl=None
        if base["taker_fee_estimate_dollars"] is not None:
            pnl=round(y-(base["book_vwap_ask"]+base["taker_fee_estimate_dollars"]),5)
        settled.append({"ticker":key[0],"side":key[1],
            "cfbdGameId":key[2],"result":outcome,
            "winner_indicator":y,"model_probability":p,
            "brier":round((p-y)**2,6),
            "theoretical_one_contract_pnl_after_estimated_fee":pnl})
    briers=[x["brier"] for x in settled]
    pnl=[x["theoretical_one_contract_pnl_after_estimated_fee"] for x in settled
        if x["theoretical_one_contract_pnl_after_estimated_fee"] is not None]
    return {
        "schemaVersion":1,"sport":"NCAAF",
        "generatedAtUTC":now.isoformat(),
        "status":"FORWARD RESEARCH ONLY",
        "latest_capture_status":snapshot["status"],
        "latest_candidate_sides":snapshot["candidate_contract_sides"],
        "latest_depth_checked":snapshot.get("markets_checked",0),
        "latest_orderbooks_available":snapshot.get("orderbooks_available",0),
        "latest_fee_estimations":snapshot.get("observations_with_fee_estimates",0),
        "latest_eligible_official":0,"latest_eligible_shadow":0,
        "archived_observations":len(allrows),
        "unique_contract_sides":len(first),
        "closing_price_proxy_pairs":len(comparisons),
        "contract_side_outcomes":len(settled),
        "forward_contract_side_brier":round(sum(briers)/len(briers),6) if briers else None,
        "theoretical_one_contract_pnl_sum":round(sum(pnl),5) if pnl else None,
        "theoretical_one_contract_pnl_count":len(pnl),
        "closing_proxy_examples":comparisons[:5],
        "exclusions":snapshot["excluded"],
        "critical_missing_checks":[
            "Verified GAME-SPECIFIC QB and injury reports for BOTH teams",
            "Independent historical weather probability adjustment calibration",
            "Validated forward net-edge accuracy, sufficient sample and market liquidity",
            "Independent final game result crosscheck, closing book within suitable pre-kickoff interval",
            "Orderbook sampling is not trade execution; fee is estimate, never a charged fee"],
        "official_eligible":False,"shadow_eligible":False,"production_eligible":False,
        "note":"Forward observations are per contract-side, highly correlated. Do not sum as independent bets or use theoretical PNL as real or official paper PNL."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--research",default="dashboard/ncaaf-v32-research.json")
    p.add_argument("--archive-dir",default="research/ncaaf-forward")
    p.add_argument("--health",default="dashboard/ncaaf-v33-health.json")
    p.add_argument("--contracts",default="1")
    args=p.parse_args()
    now=dt.datetime.now(UTC)
    unit=dec(args.contracts)
    if unit is None or unit<=0 or unit>100:
        raise ValueError("invalid research contract sample")
    research=json.loads(pathlib.Path(args.research).read_text())
    snap=audit(research,now,contracts=unit)
    existing=archives(args.archive_dir,now)
    data=merge_snapshot(existing,snap)
    data=settle_archives(data,now)
    directory=pathlib.Path(args.archive_dir)
    directory.mkdir(parents=True,exist_ok=True)
    for day,obj in data.items():
        filename(args.archive_dir,day).write_text(json.dumps(obj,indent=2)+"\n")
    report=summarize(data,now,snap)
    out=pathlib.Path(args.health);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in (
        "status","latest_capture_status","latest_candidate_sides",
        "latest_depth_checked","latest_orderbooks_available","latest_fee_estimations",
        "archived_observations","closing_price_proxy_pairs",
        "contract_side_outcomes","production_eligible")}))
if __name__=="__main__":
    try:main()
    except (ValueError,KeyError) as e:
        # No credentials used; ensure traceback doesn't leak user secrets.
        print("NCAAF forward research audit failed: "+str(e),file=sys.stderr)
        sys.exit(1)
