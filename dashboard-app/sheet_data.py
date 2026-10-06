import base64
import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

CACHE = {"ts": 0, "data": {"date": None, "rows": []}}
SHEET_ID = "1yTkEAnkNQ6MEKZLBQ0Imd_47hzGUQ1LL2fop2N1tcrQ"

def _parse_et(value):
    value = str(value or "").strip()
    for fmt in ("%m/%d/%Y %I:%M %p", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo("America/New_York"))
        except ValueError:
            pass
    return None

def get_yesterday_bets():
    now = time.time()
    if now - CACHE["ts"] < 300 and CACHE["data"].get("date"):
        return CACHE["data"]

    encoded = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "")
    if not encoded:
        return {"date": None, "rows": [], "error": "Google Sheets credential is not configured"}

    info = json.loads(base64.b64decode(encoded).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet("Bets")
    values = ws.get_all_values()
    if not values:
        return {"date": None, "rows": []}

    headers = values[0]
    idx = {name: i for i, name in enumerate(headers)}
    et = ZoneInfo("America/New_York")
    target = datetime.now(et).date() - timedelta(days=1)
    rows = []

    def cell(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else ""

    for row in values[1:]:
        dt = _parse_et(cell(row, "Date/Time ET"))
        if not dt or dt.date() != target:
            continue

        avg_price = cell(row, "Avg Contract Price")
        odds = cell(row, "Equivalent American Odds")
        display_price = odds
        if avg_price:
            try:
                display_price = f"{round(float(avg_price) * 100):.0f}¢" + (f" / {odds}" if odds else "")
            except ValueError:
                display_price = avg_price

        trade_id = cell(row, "Trade ID")
        raw_status = cell(row, "Raw Status")
        platform = "DraftKings"
        if str(trade_id).startswith("KALSHI-") or "Kalshi" in raw_status:
            platform = "Kalshi"
        elif str(trade_id).startswith("ACTION-"):
            platform = "Action"
        elif str(trade_id).startswith("DKP") or str(trade_id).isdigit():
            platform = "DraftKings"

        rows.append({
            "tradeId": trade_id,
            "platform": platform,
            "timeET": dt.strftime("%-I:%M %p"),
            "sport": cell(row, "Sport"),
            "market": cell(row, "Market"),
            "selection": cell(row, "Selection"),
            "risk": cell(row, "Risk"),
            "price": display_price,
            "result": cell(row, "Result"),
            "pnl": cell(row, "Net P/L"),
        })

    data = {"date": target.isoformat(), "rows": rows}
    CACHE["ts"] = now
    CACHE["data"] = data
    return data
