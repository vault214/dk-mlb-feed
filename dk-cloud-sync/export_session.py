#!/usr/bin/env python3
"""Export a compressed DraftKings browser session for the GitHub Actions secret."""

import base64
import gzip
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 820})
    page = context.new_page()
    page.goto("https://predictions.draftkings.com/en/my-trades/open")
    input("Log into DraftKings Predictions in the browser window, confirm My Trades loads, then press Enter here...")
    state = context.storage_state()
    browser.close()

raw = json.dumps(state, separators=(",", ":")).encode("utf-8")
encoded = base64.b64encode(gzip.compress(raw)).decode("ascii")
print("\nDK_STORAGE_STATE_GZ_B64 (add this as a GitHub Actions repository secret; never paste it into chat):\n")
print(encoded)
