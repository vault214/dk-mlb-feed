# DraftKings cloud sync

The DraftKings actual-bet import runs in GitHub Actions. It reads the signed-in browser state from the encrypted repository secret `DK_STORAGE_STATE_GZ_B64`, imports open and settled trades, and upserts them into the private Bets sheet.

It preserves the existing Bets sheet behavior:
- A:R are refreshed from DraftKings.
- S:V annotations are preserved for existing rows.
- New rows default Model Pick? to No.
- The sheet is sorted newest-first.

## Required GitHub Actions secrets

- `GOOGLE_SERVICE_ACCOUNT_JSON_B64` (already used by the dashboard metrics workflow)
- `DK_STORAGE_STATE_GZ_B64`

Do not commit either secret or paste them into chat.

## Refresh the DraftKings session

On a trusted local computer, run:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
python -m playwright install chromium
python dk-cloud-sync/export_session.py
```

Log into DraftKings Predictions in the browser window. The script prints a compressed `DK_STORAGE_STATE_GZ_B64` value. In GitHub, open **Settings → Secrets and variables → Actions**, create or update that repository secret, and paste the value there. Then run **Actions → DraftKings Actual Bet Sync → Run workflow**.

The login happens on the local computer; scheduled imports run in GitHub Actions. QNAP is not required for this importer.
