import base64
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1yTkEAnkNQ6MEKZLBQ0Imd_47hzGUQ1LL2fop2N1tcrQ"
TZ = ZoneInfo("America/New_York")
OUT = Path("dashboard/actual-performance.json")

def money(v):
    if v in (None, ""):
        return 0.0
    s = str(v).replace("$","").replace(",","").strip()
    return round(float(s or 0), 2)

raw = base64.b64decode(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_B64"]).decode("utf-8")
info = json.loads(raw)
scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
creds = Credentials.from_service_account_info(info, scopes=scopes)
book = gspread.authorize(creds).open_by_key(SHEET_ID)

recent = book.worksheet("Recent Performance").get("A1:H80")
dashboard = book.worksheet("Dashboard").get("A1:H10")

periods = {}
for row in recent:
    if len(row) >= 8 and row[0] in {"Today","This Week","Last 7 Days","Last Week (Mon–Sun)","Last 30 Days","Previous 30 Days","Last 90 Days"}:
        periods[row[0]] = row

daily = {}
in_daily = False
for row in recent:
    if row and row[0] == "Date":
        in_daily = True
        continue
    if in_daily and len(row) >= 5 and re.match(r"^[A-Z][a-z]{2} \d{1,2}$", str(row[0])):
        daily[row[0]] = row

now = datetime.now(TZ)
yday_label = (now.replace(hour=0, minute=0, second=0, microsecond=0).date()).strftime("%b %-d")
from datetime import timedelta
yday_label = (now.date() - timedelta(days=1)).strftime("%b %-d")
yesterday_pnl = money(daily.get(yday_label, ["","","","",0])[4])

dash_metrics = dashboard[3] if len(dashboard) > 3 else []
all_time_pnl = money(dash_metrics[2]) if len(dash_metrics) > 2 else 0.0
all_time_winnings = money(dash_metrics[6]) if len(dash_metrics) > 6 else 0.0
all_time_lost = money(dash_metrics[7]) if len(dash_metrics) > 7 else 0.0

data = {
    "updatedAt": now.isoformat(),
    "actualYesterdayPnl": yesterday_pnl,
    "actualWeekPnl": money(periods.get("This Week", [""]*9)[8] if len(periods.get("This Week", [])) > 8 else 0),
    "actual30dPnl": money(periods.get("Last 30 Days", [""]*9)[8] if len(periods.get("Last 30 Days", [])) > 8 else 0),
    "actualAllTimePnl": all_time_pnl,
    "actualAllTimeWinnings": all_time_winnings,
    "actualAllTimeLost": all_time_lost
}

# Recent Performance's net P/L is in column I in the sheet. If the bounded read above
# returned only A:H, fall back to a direct A:I read for these two values.
period_rows = book.worksheet("Recent Performance").get("A1:I20")
for row in period_rows:
    if row and row[0] == "This Week" and len(row) >= 9:
        data["actualWeekPnl"] = money(row[8])
    elif row and row[0] == "Last 30 Days" and len(row) >= 9:
        data["actual30dPnl"] = money(row[8])

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(data, indent=2) + "\n")
print(json.dumps(data))
