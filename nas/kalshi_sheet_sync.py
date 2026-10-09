#!/usr/bin/env python3
"""Idempotently upsert the sanitized Kalshi account feed into the private Bets sheet."""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "1yTkEAnkNQ6MEKZLBQ0Imd_47hzGUQ1LL2fop2N1tcrQ").strip()
WORKSHEET = os.environ.get("GOOGLE_WORKSHEET_BETS", "Bets").strip()
TZ = ZoneInfo(os.environ.get("TZ", "America/New_York"))
OUTPUT_DIR = Path(os.environ.get("KALSHI_OUTPUT_DIR", "/app/data"))
INPUT_FILE = OUTPUT_DIR / "kalshi_account_trades.json"

CORE_HEADERS = [
    "Trade ID", "Date/Time ET", "Date/Time UTC", "Type", "Sport", "Market",
    "Selection", "Side", "Risk", "Avg Contract Price", "Equivalent American Odds",
    "Settlement Value", "Net P/L", "Result", "DK Event ID", "Market Group ID",
    "Combo Legs", "Raw Status",
]
EXPECTED_HEADERS = CORE_HEADERS + ["Model Pick?", "Model", "Grade", "Notes"]


def _number(value, digits=4):
    if value in (None, ""):
        return None
    return round(float(value), digits)


def _opened_time(position):
    value = position.get("opened_time") or position.get("last_fill_time")
    if not value:
        return "", ""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    utc_value = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    et_value = parsed.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")
    return et_value, utc_value


def _american_odds(price):
    if price is None or price <= 0 or price >= 1:
        return ""
    odds = (1 - price) / price * 100 if price < 0.5 else -(price / (1 - price) * 100)
    return int(round(odds))


def source_note(position):
    fields = [
        "Source=Kalshi",
        f"fees={position.get('fees') or 0}",
        f"net_yes={position.get('net_yes_contracts') or 0}",
        f"net_no={position.get('net_no_contracts') or 0}",
    ]
    if position.get("market_result"):
        fields.append(f"market_result={position['market_result']}")
    if position.get("settled_time"):
        fields.append(f"settled_time={position['settled_time']}")
    return "; ".join(fields)


def position_to_row(position):
    trade_id = str(position.get("trade_id") or "")
    if not trade_id.startswith("KALSHI-"):
        raise ValueError("Kalshi position is missing its stable KALSHI- trade ID")

    side = str(position.get("selection_side") or "").upper()
    if side not in {"YES", "NO"}:
        side = "YES" if (position.get("net_yes_contracts") or 0) >= (position.get("net_no_contracts") or 0) else "NO"

    result = str(position.get("result") or "Open")
    if result not in {"Open", "Win", "Loss", "Push"}:
        result = "Open"
    date_et, date_utc = _opened_time(position)
    average_price = _number(position.get("avg_entry_price"), 6)
    ticker = str(position.get("ticker") or trade_id.removeprefix("KALSHI-"))

    return [
        trade_id,
        date_et,
        date_utc,
        "Single",
        str(position.get("sport") or "Other"),
        ticker,
        f"{side} — {ticker}",
        side,
        _number(position.get("risk")),
        average_price,
        _american_odds(average_price),
        _number(position.get("settlement_payout")) if result != "Open" else "",
        _number(position.get("net_pnl")) if result != "Open" else "",
        result,
        "",
        str(position.get("event_ticker") or ""),
        "",
        "Kalshi Settled" if result != "Open" else "Kalshi Open",
    ]


def _worksheet():
    encoded = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "")
    if not encoded:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON_B64 is not set")
    info = json.loads(base64.b64decode(encoded).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials).open_by_key(SHEET_ID).worksheet(WORKSHEET)


def sync_rows(rows, note_by_id):
    if not rows:
        return {"updated": 0, "added": 0}

    ws = _worksheet()
    values = ws.get_all_values()
    if not values or values[0][:len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
        raise RuntimeError("Bets header mismatch; refusing to write.")

    existing_by_id = {
        str(row[0]): index
        for index, row in enumerate(values[1:], start=2)
        if row and row[0]
    }
    updates = []
    note_updates = []
    appends = []

    for row in rows:
        trade_id = row[0]
        sheet_row = existing_by_id.get(trade_id)
        if sheet_row:
            updates.append({"range": f"A{sheet_row}:R{sheet_row}", "values": [row]})
            current = values[sheet_row - 1]
            current_note = current[21] if len(current) > 21 else ""
            if not current_note or current_note.startswith("Source=Kalshi;"):
                note_updates.append({"range": f"V{sheet_row}", "values": [[note_by_id.get(trade_id, "Source=Kalshi")]]})
        else:
            appends.append(row + ["No", "", "", note_by_id.get(trade_id, "Source=Kalshi")])

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if note_updates:
        ws.batch_update(note_updates, value_input_option="USER_ENTERED")
    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")
    last_row = len(values) + len(appends)
    if last_row >= 2:
        ws.sort((2, "des"), range=f"A2:V{last_row}")
    return {"updated": len(updates), "added": len(appends)}


def main():
    if not INPUT_FILE.exists():
        raise RuntimeError(f"Kalshi account feed not found: {INPUT_FILE}")
    payload = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    positions = payload.get("positions") or []
    positions = [p for p in positions if str(p.get("trade_id") or "").startswith("KALSHI-")]
    rows = [position_to_row(position) for position in positions]
    note_by_id = {str(p["trade_id"]): source_note(p) for p in positions}
    stats = sync_rows(rows, note_by_id)
    print(json.dumps({"ok": True, "positions": len(rows), **stats}))


if __name__ == "__main__":
    main()
