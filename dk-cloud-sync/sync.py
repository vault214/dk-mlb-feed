import base64
import gzip
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

TZ_NAME = os.getenv("TZ", "America/New_York")
LOCAL_TZ = ZoneInfo(TZ_NAME)
DK_BASE_URL = os.getenv("DK_BASE_URL", "https://predictions.draftkings.com").rstrip("/")
ROUTE_QUERY = "?_routes=routes%2F%28%24lang%29._withTradeSlip%2Croutes%2F%28%24lang%29._withTradeSlip.my-trades.%24status"
DK_OPEN_PATH = os.getenv("DK_OPEN_PATH", f"/en/my-trades/open.data{ROUTE_QUERY}")
DK_SETTLED_PATH = os.getenv("DK_SETTLED_PATH", f"/en/my-trades/settled.data{ROUTE_QUERY}")
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
WORKSHEET = os.getenv("GOOGLE_WORKSHEET_BETS", "Bets")

HEADERS = [
    "Trade ID","Date/Time ET","Date/Time UTC","Type","Sport","Market","Selection","Side",
    "Risk","Avg Contract Price","Equivalent American Odds","Settlement Value","Net P/L","Result",
    "DK Event ID","Market Group ID","Combo Legs","Raw Status","Model Pick?","Model","Grade","Notes",
]
CORE_HEADERS = HEADERS[:18]

def parse_iso_utc(value):
    if not value:
        return None
    value = re.sub(r"(\.\d{6})\d+Z$", r"\1Z", str(value))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

def fmt_dt(value, tz):
    dt = parse_iso_utc(value)
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S") if dt else ""

def as_float(value, default=0.0):
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return default

def round_money(value):
    return round(as_float(value), 2)

def american_odds_from_probability(price):
    p = as_float(price)
    if p <= 0 or p >= 1:
        return ""
    odds = (-100 * p / (1 - p)) if p >= 0.5 else (100 * (1 - p) / p)
    return int(round(odds))

def infer_sport(*parts):
    text = " ".join(str(x or "") for x in parts).upper()
    for needle, label in [
        ("WNBA","WNBA"),("MLB","MLB"),("NFL","NFL"),("NBA","NBA"),("NHL","NHL"),
        ("MLS","MLS"),("NCAAF","NCAAF"),("NCAAB","NCAAB"),("UFC","UFC"),("PGA","PGA"),
        ("ATP","Tennis"),("WTA","Tennis")
    ]:
        if needle in text:
            return label
    return "Other"

def result_from_status(position_status="", settlement_status="", market_status=""):
    text = f"{position_status} {settlement_status} {market_status}".lower()
    if "incorrect" in text:
        return "Loss"
    if "correct" in text:
        return "Win"
    if "cancel" in text or "void" in text:
        return "Push"
    if "settled" in text:
        return "Settled"
    return "Open"

def decode_dk_payload(text):
    data = json.loads(text)
    if not isinstance(data, list):
        return data
    memo = {}
    def resolve(index):
        if not isinstance(index, int):
            return index
        if index < 0:
            return None
        if index in memo:
            return memo[index]
        value = data[index]
        if isinstance(value, list):
            out = []
            memo[index] = out
            out.extend(resolve(x) if isinstance(x, int) else x for x in value)
            return out
        if isinstance(value, dict):
            out = {}
            memo[index] = out
            for key, raw_value in value.items():
                if isinstance(key, str) and key.startswith("_") and key[1:].isdigit():
                    decoded_key = resolve(int(key[1:]))
                else:
                    decoded_key = key
                decoded_value = resolve(raw_value) if isinstance(raw_value, int) else raw_value
                out[str(decoded_key)] = decoded_value
            return out
        memo[index] = value
        return value
    return resolve(0)

def find_trade_data(decoded):
    if not isinstance(decoded, dict):
        return None
    preferred = decoded.get("routes/($lang)._withTradeSlip.my-trades.$status")
    if isinstance(preferred, dict):
        route_data = preferred.get("data")
        if isinstance(route_data, dict) and "userPositionGroups" in route_data:
            return route_data
    stack = [decoded]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "userPositionGroups" in node:
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None

def find_login_state(decoded):
    stack = [decoded]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "isLoggedIn" in node:
                return bool(node["isLoggedIn"])
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None

def processed_by_ticker(group):
    return {p.get("marketTicker"): p for p in (group.get("processedPositions") or []) if p.get("marketTicker")}

def normalize_groups(groups):
    rows = []
    for group in groups or []:
        kind = str(group.get("type") or "")
        if kind.lower() == "single":
            processed = processed_by_ticker(group)
            for pos in group.get("positions") or []:
                trade_id = pos.get("ticker") or ""
                if not trade_id:
                    continue
                proc = processed.get(trade_id) or {}
                dt_utc = pos.get("mostRecentTradeDateTimeUTC") or group.get("mostRecentTradeTimeUTC")
                status = pos.get("positionStatus") or ""
                market_status = pos.get("marketStatus") or ""
                avg_price = as_float(pos.get("sharePurchasePrice") or proc.get("averagePurchasePrice"))
                selection = pos.get("positionSubtitle") or proc.get("marketTitle") or ""
                rows.append({
                    "Trade ID": trade_id,
                    "Date/Time ET": fmt_dt(dt_utc, LOCAL_TZ),
                    "Date/Time UTC": fmt_dt(dt_utc, timezone.utc),
                    "Type": "Single",
                    "Sport": infer_sport(trade_id, group.get("marketGroupTicker"), group.get("marketGroupTitle")),
                    "Market": group.get("marketGroupTitle") or "",
                    "Selection": selection,
                    "Side": pos.get("tickerSide") or proc.get("tickerSide") or "",
                    "Risk": round_money(pos.get("boughtFor")),
                    "Avg Contract Price": round(avg_price, 4) if avg_price else "",
                    "Equivalent American Odds": american_odds_from_probability(avg_price),
                    "Settlement Value": round_money(pos.get("positionValue")),
                    "Net P/L": round_money(pos.get("positionGains")),
                    "Result": result_from_status(status, "", market_status),
                    "DK Event ID": str(group.get("dkEventId") or ""),
                    "Market Group ID": group.get("marketGroupTicker") or "",
                    "Combo Legs": "",
                    "Raw Status": status or market_status,
                })
        elif kind.lower() == "combo":
            summary = group.get("summary") or {}
            trade_id = summary.get("ticker") or group.get("comboTicker") or ""
            if not trade_id:
                continue
            dt_utc = summary.get("mostRecentTradeDateTimeUTC") or group.get("mostRecentTradeTimeUTC")
            status = summary.get("positionStatus") or group.get("comboStatus") or ""
            settlement = summary.get("settlementStatus") or ""
            avg_price = as_float(summary.get("sharePurchasePrice"))
            legs = group.get("legs") or []
            leg_parts, event_ids, market_group_ids = [], [], []
            for leg in legs:
                if leg.get("dkEventId") is not None:
                    event_ids.append(str(leg["dkEventId"]))
                if leg.get("marketTicker"):
                    market_group_ids.append(str(leg["marketTicker"]))
                pieces = [leg.get("marketGroupTitle") or "", leg.get("marketTitle") or leg.get("marketSubTitle") or "", leg.get("side") or "", leg.get("settlementStatus") or ""]
                leg_parts.append(" | ".join(str(x) for x in pieces if x))
            event_ids = list(dict.fromkeys(event_ids))
            market_group_ids = list(dict.fromkeys(market_group_ids))
            rows.append({
                "Trade ID": trade_id,
                "Date/Time ET": fmt_dt(dt_utc, LOCAL_TZ),
                "Date/Time UTC": fmt_dt(dt_utc, timezone.utc),
                "Type": "Combo",
                "Sport": infer_sport(trade_id, group.get("comboTitle"), group.get("comboSubTitle"), *market_group_ids),
                "Market": group.get("comboTitle") or "Combo",
                "Selection": group.get("comboSubTitle") or "",
                "Side": summary.get("tickerSide") or "",
                "Risk": round_money(summary.get("boughtFor")),
                "Avg Contract Price": round(avg_price, 4) if avg_price else "",
                "Equivalent American Odds": american_odds_from_probability(avg_price),
                "Settlement Value": round_money(summary.get("positionValue")),
                "Net P/L": round_money(summary.get("positionGains")),
                "Result": result_from_status(status, settlement),
                "DK Event ID": ",".join(event_ids),
                "Market Group ID": ",".join(market_group_ids),
                "Combo Legs": " || ".join(leg_parts),
                "Raw Status": status or group.get("comboStatus") or "",
            })
    return rows

def google_sheet():
    raw = base64.b64decode(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_B64"]).decode("utf-8")
    info = json.loads(raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    ws = sheet.worksheet(WORKSHEET)
    current_headers = ws.row_values(1)
    if current_headers[:len(HEADERS)] != HEADERS:
        raise RuntimeError("Bets header mismatch; refusing to write.")
    return ws

def upsert_rows(rows):
    if not rows:
        return {"updated": 0, "added": 0}
    ws = google_sheet()
    all_values = ws.get_all_values()
    existing_by_id = {}
    for idx, row in enumerate(all_values[1:], start=2):
        if row and row[0]:
            existing_by_id[str(row[0])] = idx
    updates, appends = [], []
    for row in rows:
        trade_id = str(row["Trade ID"])
        core_values = [row.get(h, "") for h in CORE_HEADERS]
        if trade_id in existing_by_id:
            sheet_row = existing_by_id[trade_id]
            updates.append({"range": f"A{sheet_row}:R{sheet_row}", "values": [core_values]})
        else:
            appends.append(core_values + ["No", "", "", ""])
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")
    last_row = len(all_values) + len(appends)
    if last_row >= 2:
        ws.sort((2, "des"), range=f"A2:V{last_row}")
    return {"updated": len(updates), "added": len(appends)}

def fetch_with_page(page, path, label):
    result = page.evaluate("""async (url) => {
      const r = await fetch(url, {method:'GET', credentials:'include', cache:'no-store',
        headers:{'accept':'*/*','cache-control':'no-cache','pragma':'no-cache'}});
      return {status:r.status, ok:r.ok, url:r.url, text:await r.text()};
    }""", path)
    if not result.get("ok"):
        raise RuntimeError(f"{label} request failed: HTTP {result.get('status')} {result.get('url')}")
    text = result.get("text", "")
    if not text.lstrip().startswith("["):
        raise RuntimeError(f"{label} returned non-.data content; DraftKings session likely expired.")
    return text

def main():
    storage_raw = gzip.decompress(base64.b64decode(os.environ["DK_STORAGE_STATE_GZ_B64"])).decode("utf-8")
    storage = json.loads(storage_raw)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(storage_state=storage, viewport={"width":1400,"height":820})
        page = context.new_page()
        page.goto(f"{DK_BASE_URL}/en/my-trades/open", wait_until="domcontentloaded", timeout=60000)
        open_decoded = decode_dk_payload(fetch_with_page(page, DK_OPEN_PATH, "open"))
        settled_decoded = decode_dk_payload(fetch_with_page(page, DK_SETTLED_PATH, "settled"))
        if False in [find_login_state(open_decoded), find_login_state(settled_decoded)]:
            raise RuntimeError("DraftKings session expired; refresh DK_STORAGE_STATE_B64.")
        open_data, settled_data = find_trade_data(open_decoded), find_trade_data(settled_decoded)
        if open_data is None or settled_data is None:
            raise RuntimeError("Could not locate userPositionGroups; DraftKings route/session changed.")
        open_rows = normalize_groups(open_data.get("userPositionGroups"))
        settled_rows = normalize_groups(settled_data.get("userPositionGroups"))
        merged = {r["Trade ID"]: r for r in open_rows if r.get("Trade ID")}
        merged.update({r["Trade ID"]: r for r in settled_rows if r.get("Trade ID")})
        stats = upsert_rows(list(merged.values()))
        print(json.dumps({
            "ok": True,
            "open_rows": len(open_rows),
            "settled_rows": len(settled_rows),
            "unique_rows": len(merged),
            **stats
        }))
        browser.close()

if __name__ == "__main__":
    main()
