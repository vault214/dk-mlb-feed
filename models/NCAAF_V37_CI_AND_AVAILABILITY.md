# NCAA Football v3.7 — GitHub Actions cleanup and primary-source availability triage

Updated: November 7, 2026.

## Why the two screenshots showed non-green workflows

**Forward run #17 (commit `57dd49a`):** one *offline test fixture* incorrectly asserted no blockers after new explicit game-document, QB, and player-impact checks were added. The engine correctly reported the missing evidence; the old test expectation was obsolete. The test later incorporated a verified pre-kickoff report-observation timestamp and later CI passed. The Node 20 deprecation notice in the screenshot was only a warning, not the failure cause.

**Forward run #21 (commit `1154609`):** GitHub Actions concurrency canceled a waiting push job in favor of a newer waiting request. The job did not finish and did not indicate a failed model, bad secret, or lost position.

## Changes made

- `.github/workflows/ncaaf-forward-v33.yml`: on **push**, run only `checks` (all offline regression suites). Run `forward` market and evidence collection only on its existing Friday–Monday hourly schedule or manual `workflow_dispatch`, and only after checks pass. The collection job retains a serial concurrency group shared with independent daily settlement reconciliation; rapid code commits no longer generate redundant full scans and pending cancellation alerts.
- Upgrade to `actions/checkout@v5` and `actions/setup-python@v6` (Node 24-compatible releases) in the forward and daily-settlement workflows to address the deprecation warning.
- `models/ncaaf_availability_triage_v37.py` uses the previously verified CFBD team/game/date join in `dashboard/ncaaf-v36-secondary-leads.json` to retrieve third-party matchup pages, parse QB-position rows *only above* the site's separately labeled unofficial notes section, and identify OUT / DOUBTFUL / QUESTIONABLE / GAME-TIME DECISION concern signals. A player with QB position is not automatically verified as the team's starting QB; source transcriptions may contain errors or lag.
- Output `dashboard/ncaaf-v37-availability-triage.json` retains captured timestamp, source game page, explicit unverified status, and zero official/production eligibility. Failed fetch, unsupported page markup, no listed QB or ambiguous team => unknown, never healthy.
- `models/ncaaf_game_eligibility_v35.py` now annotates each game's eligibility report with these **unverified** quarterback-position concerns only when the external page was captured strictly before the game's kickoff. The annotations never change calculated probabilities or official/shadow gates.
- Dashboard source `dashboard-app/app.py` displays possible unverified QB concerns alongside the per-matchup blockers and cross-reference links, not as officially confirmed information. A GitHub source update is not proof of live dashboard deployment.
- `models/test_ncaaf_availability_triage_v37.py` and per-game tests fail if unverified data would be presented as primary verification or if postkickoff data could be treated as pregame.

## Evidence not yet available

The official SEC/Big Ten/ACC/Big 12 report hubs are often dynamic or embedded, and the third-party game pages frequently link back only to a generic conference hub. They cannot by themselves certify **actual game-specific** primary documents, both actual starting QB statuses, or injury impact calibration. Those remain fail-closed until primary team/conference documentation with accurate pre-kickoff provenance is retrieved. No guesses or secondary summaries may satisfy them.

Settlement evidence requires the real final score and an independently settled public Kalshi contract. The twice-daily reconciliation workflow is already operative, including cross-year catchup. It cannot fabricate settled outcomes before games end.

No v3.7 feature places a trade, promotes an official/shadow paper entry, or modifies the user's bankroll, bets or historical ledgers. The existing B+ >=5pp robust net edge requirement and conservative 1u rule remain intact.

Run references:
- Original test failure: https://github.com/vault214/dk-mlb-feed/actions/runs/42412372373
- Original superseded/canceled run: https://github.com/vault214/dk-mlb-feed/actions/runs/42412586443
- Passed split-structure push tests: https://github.com/vault214/dk-mlb-feed/actions/runs/42413424281
- Passed Node-24 action update checks: https://github.com/vault214/dk-mlb-feed/actions/runs/42413466166
- Passed daily result audit: https://github.com/vault214/dk-mlb-feed/actions/runs/42413470165

