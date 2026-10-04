import base64
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1yTkEAnkNQ6MEKZLBQ0Imd_47hzGUQ1LL2fop2N1tcrQ"
WORKSHEET = "Bets"
TZ = ZoneInfo("America/New_York")
OUT = Path("dashboard/actual-performance.json")

def money(v):
    if v in (None, ""):
        return 0.0
    return float(str(v).replace("$","").replace(",","").strip() or 0)

def parse_dt(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    return None

raw = base64.b64decode(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_B64"]).decode("utf-8")
info = json.loads(raw)
scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
creds = Credentials.from_service_account_info(info, scopes=scopes)
ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet(WORKSHEET)
rows = ws.get_all_records()

now = datetime.now(TZ)
today = now.date()
yesterday = today - timedelta(days=1)
week_start = today - timedelta(days=today.weekday())
last30_start = today - timedelta(days=29)

settled = []
for r in rows:
    result = str(r.get("Result") or "").strip().lower()
    if result not in {"win","loss","push","settled"}:
        continue
    dt = parse_dt(r.get("Date/Time ET"))
    if not dt:
        continue
    pnl = money(r.get("Net P/L"))
    settled.append((dt.date(), pnl))

def total_for(start=None, end=None):
    vals = [p for d,p in settled if (start is None or d >= start) and (end is None or d <= end)]
    return round(sum(vals), 2)

all_pnls = [p for _,p in settled]
data = {
    "updatedAt": now.isoformat(),
    "actualYesterdayPnl": total_for(yesterday, yesterday),
    "actualWeekPnl": total_for(week_start, today),
    "actual30dPnl": total_for(last30_start, today),
    "actualAllTimePnl": round(sum(all_pnls), 2),
    "actualAllTimeWinnings": round(sum(p for p in all_pnls if p > 0), 2),
    "actualAllTimeLost": round(abs(sum(p for p in all_pnls if p < 0)), 2),
    "settledBetCount": len(settled)
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(data, indent=2) + "\n")
print(json.dumps(data))
