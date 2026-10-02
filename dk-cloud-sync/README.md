# DraftKings cloud sync

One-shot cloud replacement for the former QNAP `dk-predictions-sync` container.

It preserves the existing Bets sheet schema and Trade ID upsert behavior:
- A:R are refreshed from DraftKings.
- S:V annotations are preserved for existing rows.
- New rows default Model Pick? to No.
- The sheet is sorted newest-first.

## Required Render environment variables

- `GOOGLE_SHEET_ID`
- `GOOGLE_WORKSHEET_BETS=Bets`
- `GOOGLE_SERVICE_ACCOUNT_JSON_B64`
- `DK_STORAGE_STATE_B64`
- `TZ=America/New_York`

Do not commit either base64 secret to GitHub.

## Build command

```
pip install -r dk-cloud-sync/requirements.txt && python -m playwright install chromium
```

## Start command

```
python dk-cloud-sync/sync.py
```

## Refreshing the DraftKings session

On a trusted local computer:

```
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
python -m playwright install chromium
python dk-cloud-sync/export_session.py
```

After logging in, copy the generated `DK_STORAGE_STATE_B64` value directly into the Render environment variable. Do not paste it into chat.
