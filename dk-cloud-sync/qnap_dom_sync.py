import os
import re
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

TZ_NAME = os.getenv("TZ", "America/New_York")
LOCAL_TZ = ZoneInfo(TZ_NAME)
DK_BASE_URL = os.getenv("DK_BASE_URL", "https://predictions.draftkings.com").rstrip("/")
PROFILE_DIR = os.getenv("DK_PROFILE_DIR", "/app/data/browser-profile")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/secrets/google-service-account.json")
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
WORKSHEET = os.getenv("GOOGLE_WORKSHEET_BETS", "Bets")
MAX_SCROLLS = int(os.getenv("DK_MAX_SCROLLS", "12"))
MAX_POSITIONS_PER_STATUS = int(os.getenv("DK_MAX_POSITIONS_PER_STATUS", "30"))

HEADERS = [
    "Trade ID","Date/Time ET","Date/Time UTC","Type","Sport","Market","Selection","Side",
    "Risk","Avg Contract Price","Equivalent American Odds","Settlement Value","Net P/L","Result",
    "DK Event ID","Market Group ID","Combo Legs","Raw Status","Model Pick?","Model","Grade","Notes",
]
CORE_HEADERS = HEADERS[:18]

MONEY_RE = re.compile(r"\$([0-9,]+(?:\.\d{1,2})?)")
PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
DATE_RE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M$")

NFL_HINTS = {
    "CARDINALS","FALCONS","RAVENS","BILLS","PANTHERS","BEARS","BENGALS","BROWNS","COWBOYS",
    "BRONCOS","LIONS","PACKERS","TEXANS","COLTS","JAGUARS","CHIEFS","RAIDERS","CHARGERS",
    "RAMS","DOLPHINS","VIKINGS","PATRIOTS","SAINTS","GIANTS","JETS","EAGLES","STEELERS",
    "49ERS","SEAHAWKS","BUCCANEERS","TITANS","COMMANDERS"
}

def money_value(text):
    m = MONEY_RE.search(text or "")
    return round(float(m.group(1).replace(",", "")), 2) if m else 0.0

def american_odds_from_probability(price):
    p = float(price or 0)
    if p <= 0 or p >= 1:
        return ""
    odds = (-100 * p / (1 - p)) if p >= 0.5 else (100 * (1 - p) / p)
    return int(round(odds))

def infer_sport(text):
    t = (text or "").upper()
    if "SHOTS ON GOAL" in t or any(x in t for x in [" HURRICANES"," FLYERS"," MAPLE LEAFS"," BRUINS"," JETS"," STARS"," DUCKS"," GOLDEN KNIGHTS"]):
        return "NHL"
    if any(x in t for x in ["REB", "REBOUND", "ASSIST", "3-POINTER", "THREES", "PTS"]):
        return "NBA/WNBA"
    if any(x in t for x in ["STRIKEOUT", "HITS", "HOME RUN", "TOTAL BASES", "PITCHER"]):
        return "MLB"
    if any(team in t for team in NFL_HINTS):
        return "NFL"
    if any(x in t for x in ["TCU","OHIO STATE","MICHIGAN","HOUSTON","NOTRE DAME","NORTH CAROLINA","BYU"]):
        return "NCAAF"
    return "Other"

def parse_et(ts):
    if not ts:
        return "", ""
    dt = datetime.strptime(ts, "%b %d, %Y, %I:%M %p").replace(tzinfo=LOCAL_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def unique_position_links(page, status):
    target = f'/en/my-trades/{status}/details/position/'
    seen = set()
    stable = 0
    previous = -1
    for _ in range(MAX_SCROLLS):
        for i in range(page.locator(f'a[href*="{target}"]').count()):
            href = page.locator(f'a[href*="{target}"]').nth(i).get_attribute("href")
            if href:
                seen.add(href)
        if len(seen) == previous:
            stable += 1
        else:
            stable = 0
        previous = len(seen)
        if stable >= 2:
            break
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1200)
    return sorted(seen, key=lambda href: int(href.rstrip("/").split("/")[-1]), reverse=True)[:MAX_POSITIONS_PER_STATUS]

def my_position_text(page):
    target = page.get_by_text("My Position", exact=True).first
    try:
        target.wait_for(state="visible", timeout=10000)
    except Exception:
        raise RuntimeError("My Position section not found after 10s")
    return target.evaluate("el => el.parentElement.parentElement.innerText")

def clean_lines(text):
    return [x.strip() for x in text.splitlines() if x.strip()]

def parse_position(position_id, status, text):
    lines = clean_lines(text)
    try:
        bought_i = lines.index("BOUGHT FOR")
    except ValueError:
        raise RuntimeError(f"{position_id}: BOUGHT FOR not found")

    risk = money_value(lines[bought_i + 1] if bought_i + 1 < len(lines) else "")
    pre = lines[1:bought_i]

    result = "Open"
    if any("prediction was correct" in x.lower() for x in lines) or "YOUWON" in lines:
        result = "Win"
    elif any("prediction was incorrect" in x.lower() for x in lines) or "YOULOST" in lines:
        result = "Loss"
    elif any("cancel" in x.lower() or "void" in x.lower() for x in lines):
        result = "Push"
    elif status == "settled":
        result = "Settled"

    payout = 0.0
    payout_label = ""
    for label in ("PAID OUT", "PAYS OUT"):
        if label in lines:
            i = lines.index(label)
            if i + 1 < len(lines):
                payout = money_value(lines[i + 1])
                payout_label = label
                break

    pct = None
    for x in pre:
        m = PCT_RE.match(x)
        if m:
            pct = float(m.group(1)) / 100.0
            break

    shares = None
    bought_times = []
    for i, x in enumerate(lines):
        m = re.match(r"Bought\s+(\d+(?:\.\d+)?)\s+shares\s+for", x, re.I)
        if m:
            shares = (shares or 0) + float(m.group(1))
            if i + 2 < len(lines) and DATE_RE.match(lines[i + 2]):
                bought_times.append(datetime.strptime(lines[i + 2], "%b %d, %Y, %I:%M %p"))

    placed_text = ""
    if bought_times:
        placed_text = min(bought_times).strftime("%b %-d, %Y, %-I:%M %p")
    else:
        for x in lines:
            if DATE_RE.match(x):
                placed_text = x
                break

    dt_et, dt_utc = parse_et(placed_text) if placed_text else ("", "")

    ignore = {"PREDICTIONS","YOUWON","YOULOST","My Position"}
    descriptors = [x for x in pre if x not in ignore and not PCT_RE.match(x)]

    is_combo = any("Pick Combo" in x for x in descriptors)
    combo_type = next((x for x in descriptors if "Pick Combo" in x), "")
    descriptors = [x for x in descriptors if x != combo_type]

    if is_combo:
        row_type = "Combo"
        market = combo_type or "Combo"
        pairs = []
        for i in range(0, len(descriptors), 2):
            a = descriptors[i]
            b = descriptors[i + 1] if i + 1 < len(descriptors) else ""
            pairs.append((a, b))
        selection = ", ".join(a for a, _ in pairs if a)
        combo_legs = " || ".join(" | ".join(x for x in pair if x) for pair in pairs)
        side = ""
    else:
        row_type = "Single"
        combo_legs = ""
        if len(descriptors) >= 2:
            common_markets = ("TO WIN","SPREAD","TOTAL","OVER/UNDER","O/U","MONEYLINE","ALTERNATE")
            if any(k in descriptors[0].upper() for k in common_markets):
                market, selection = descriptors[0], descriptors[1]
            else:
                selection, market = descriptors[0], descriptors[1]
        elif descriptors:
            selection, market = descriptors[0], ""
        else:
            selection, market = "", ""
        side = "Yes"

    avg_price = pct if pct else ((risk / shares) if shares else 0)
    settlement_value = payout if status == "settled" else ""
    net_pl = round(payout - risk, 2) if status == "settled" and result in {"Win","Loss","Push","Settled"} else ""

    all_text = " ".join(lines)
    return {
        "Trade ID": str(position_id),
        "Date/Time ET": dt_et,
        "Date/Time UTC": dt_utc,
        "Type": row_type,
        "Sport": infer_sport(all_text),
        "Market": market,
        "Selection": selection,
        "Side": side,
        "Risk": risk,
        "Avg Contract Price": round(avg_price, 4) if avg_price else "",
        "Equivalent American Odds": american_odds_from_probability(avg_price) if avg_price else "",
        "Settlement Value": settlement_value,
        "Net P/L": net_pl,
        "Result": result,
        "DK Event ID": "",
        "Market Group ID": "",
        "Combo Legs": combo_legs,
        "Raw Status": "Settled" if status == "settled" else "Open",
    }

def google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    ws = client.open_by_key(SHEET_ID).worksheet(WORKSHEET)
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

    refreshed = ws.get_all_values()
    last_row = len(refreshed)
    if last_row >= 2:
        ws.sort((2, "des"), range=f"A2:V{last_row}")
    return {"updated": len(updates), "added": len(appends)}

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        merged = {}

        for status in ("open", "settled"):
            page.goto(f"{DK_BASE_URL}/en/my-trades/{status}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            if "/login" in page.url.lower():
                raise RuntimeError("DraftKings session is not logged in.")

            links = unique_position_links(page, status)
            print(f"{status}: found {len(links)} position links")

            for href in links:
                position_id = href.rstrip("/").split("/")[-1]
                url = href if href.startswith("http") else DK_BASE_URL + href
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
                try:
                    row = parse_position(position_id, status, my_position_text(page))
                    merged[position_id] = row
                    print(f"{status}: parsed {position_id} -> {row['Result']} risk={row['Risk']} pnl={row['Net P/L']}")
                except Exception as exc:
                    print(f"WARN {status} {position_id}: {exc}")

        stats = upsert_rows(list(merged.values()))
        print(json.dumps({"ok": True, "positions": len(merged), **stats}))
        ctx.close()

if __name__ == "__main__":
    main()
