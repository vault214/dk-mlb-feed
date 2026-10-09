# Cloud account import setup

This branch moves the tracker’s Kalshi account import into GitHub Actions and keeps DraftKings on its existing GitHub Actions workflow. The Kalshi job updates the private Google Sheet directly, then refreshes the dashboard summary. It does not commit new wager-level Kalshi data to the repository.

## One-time GitHub Actions secrets

In `vault214/dk-mlb-feed`, open **Settings → Secrets and variables → Actions** and add:

- `KALSHI_API_KEY_ID`: your Kalshi API key ID.
- `KALSHI_PRIVATE_KEY_PEM`: the contents of the PEM private-key file downloaded from Kalshi.
- `GOOGLE_SERVICE_ACCOUNT_JSON_B64`: already used by the DraftKings and dashboard workflows.

Keep the private key in the GitHub secret. Do not commit it or paste it into chat. The workflow sends it to Kalshi for signed API requests, writes positions to the private Bets sheet, and keeps the temporary JSON in the short-lived Actions runner.

## DraftKings login refresh

Run `python dk-cloud-sync/export_session.py` on a trusted local computer, sign in to DraftKings in the browser it opens, then copy the printed `DK_STORAGE_STATE_GZ_B64` value into the GitHub Actions repository secret with the same name. Run **Actions → DraftKings Actual Bet Sync → Run workflow** once to verify it.

## Verify migration, then retire the NAS account sync

1. Run **Actions → Kalshi Account Bet Sync → Run workflow**.
2. Confirm the run succeeds and new or refreshed Kalshi rows appear in the Bets sheet. The stable `KALSHI-<ticker>` ID makes this safe to rerun.
3. Confirm dashboard totals refresh.
4. Disable the NAS account-trade schedule by setting `ENABLE_KALSHI_ACCOUNT_SYNC=false` on the QNAP. The separate market-board collectors are outside this account-import migration.

GitHub cron uses UTC. The workflow has paired UTC slots and skips the slot that does not correspond to the local 08:00 or 23:30 America/New_York schedule for the current daylight-saving offset. Manual workflow runs are not time-gated.
