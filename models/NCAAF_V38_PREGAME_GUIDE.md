# NCAA Football v3.8: targeted kickoff-window reporting and market research
Updated 2026-11-07. All calculations remain **research only**. No bets, trades, official/shadow picks, personal-account reads or bankroll mutations.

## What's implemented

### Time-aware report policy
`models/ncaaf_pregame_window_v38.py` matches the CFBD game ID, exact home/away names and UTC kickoff from the independent model feed against the queue of conference fixtures. It only uses the conference report policy if **both teams share the same recognized conference and CFBD marks the game as a conference matchup**.

| Conference | Final game-day report due | Primary policy source |
|---|---:|---|
| SEC | 90 minutes before kickoff | https://www.secsports.com/reports |
| Big 12 | 90 minutes before kickoff | https://big12sports.com/sports/2025/8/21/availability-reporting.aspx |
| Big Ten | 120 minutes before kickoff | https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx |
| ACC | 120 minutes before kickoff | https://admin.theacc.com/sports/2025/8/28/availability-reporting.aspx |

SEC / Big Ten policies provide that an unlisted player may be considered Available within the scope of a **complete applicable report**. This is NOT proof that an unidentified player is the starting quarterback. The system **does not** infer any unlisted player's status without an independently verified starter identity and the complete actual game-specific final report. The source discovery portal, a timestamp or a third-party report link never satisfies that requirement. Neither Big 12 nor ACC automatically receives the same inference in this project.

### Scheduled pregame collection
The existing `.github/workflows/ncaaf-forward-v33.yml` now checks 15-minute clock ticks on Friday/Saturday daytime/evening UTC and adjacent Saturday/Sunday early UTC (covering evening Eastern kickoffs). Actual collection only runs when a CFBD-verified game has **less than or equal to three hours remaining** before kickoff and has **not started**; otherwise all expensive market and report steps skip. GitHub Actions scheduled triggers can be delayed and are not hard real-time.

The selector outputs:
- `dashboard/ncaaf-v38-window.json`: per-game UTC kickoff, final report due time, stage, 15-minute cadence, explicit false source/official flags
- `ncaaf-v38-filtered-research.json`: transient, only in-window independent game and contract-side research rows
- `ncaaf-v38-scoped-queue.json`: transient, only in-window exact CFBD matchups for official and secondary source discovery

When in window, the read-only forward pipeline runs relevant Kalshi orderbooks and fee samples only for selected games, searches primary official report portals, separately captures unverified third-party QB concern signals, checks any actual direct official game document, and updates individual game blockers and the research archive.

The independent settled-score reconciliation workflow `.github/workflows/ncaaf-settlement-daily-v36.yml` remains separate at twice daily to avoid repeatedly requesting full-season CFBD results every 15 minutes.

### Reports and dashboard
- `dashboard/ncaaf-v38-window.json` is published after a capture window run; missing or stale is not evidence of the absence of games.
- `dashboard/ncaaf-v35-eligibility.json` records each in-window game's report stage, deadline, official policy link, verified primary-document status, source and QB blockers, weather and contract-side price/fee checks.
- `dashboard-app/app.py` now displays an explicit conference final-report due time and stage in each game's blocker panel. GitHub source updates do not prove live deployment.

### Safety / testing
- `models/test_ncaaf_pregame_window_v38.py` tests 90/120-minute deadlines, no nonconference rule carryover, UTC kickoff, exact 3h window, mismatch blocking, and safe omission-policy caveats.
- On a GitHub code push, the workflow runs offline tests without launching the market collection. On schedule/manual, it runs the checks then conditional market capture. This prevents the previous burst of canceled queued runs.
- A verified report or 5pp apparent net edge is **not enough** to enable a wager; pregame starter/impact validation, fresh executable prices, adequate stake-sized depth and independently settled forward edge remain required under the existing balanced-conservative B+ rules. All v3.8 official/production/shadow flags remain false.

## Important operating limitations
1. Many actual SEC/ACC/Big 12 conference reports are rendered inside embedded third-party applications. The site may not expose a trustworthy direct document through static HTML. Our collector retains an explicit blocker instead of treating a parent page as proof.
2. The 15-minute schedule depends on GitHub Actions availability; it is not guaranteed to complete within precisely 15 minutes.
3. Historical weather and player-impact effects remain uncalibrated and cannot change the win probability in this release.
4. The forward settlement sample must accumulate independent, actually settled games. Repeated quote observations from one matchup are not separate validation samples.

## Verification
Inspect workflow green **checks** job after push:
https://github.com/vault214/dk-mlb-feed/actions/workflows/ncaaf-forward-v33.yml

For a complete market capture, check a run with `event=schedule` (or `workflow_dispatch`) and confirm that the **forward** job executed, not merely the offline tests. The research archive and window report will be published only if an actual three-hour pregame window was active.
