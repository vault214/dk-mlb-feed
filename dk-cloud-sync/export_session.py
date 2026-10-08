import base64
import gzip
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("dk-storage-state.json")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1400, "height": 820})
    page = context.new_page()
    page.goto("https://predictions.draftkings.com/en/my-trades/open")
    input("Log into DraftKings Predictions in the browser window, confirm My Trades loads, then press Enter here...")
    context.storage_state(path=str(OUT))
    browser.close()

raw = OUT.read_bytes()
print("\nSaved:", OUT.resolve())
print("\nDK_STORAGE_STATE_GZ_B64 (add this as a GitHub Actions repository secret; never paste it into chat):\n")
print(base64.b64encode(gzip.compress(raw)).decode())
