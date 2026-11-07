# Seven-sport forward research v4.0 — November 7, 2026

The existing independent sports-paper models stay in place with their original constraints. This milestone adds **new read-only** prospective market observations and independent game-final reconciliation for four in-season sports, without substituting market prices for model probabilities or modifying picks, bank data, bankroll, records or odds history.

## Coverage

| Sport | Research state | First verified capture | Most important blocker |
| --- | --- | --- | --- |
| NCAAF | Existing v3.9 independent pregame model and settlements | 13 distinct games observed; 3 pregame research candidates; 0 independent settled outcomes | Primary dated game reports and proven long-run net edge |
| NFL | v4.0 game moneyline scanner live; no capture on bootstrap | 0 (last NFL candidate board dated Nov 5, stale on Nov 7) | Fresh game-winner candidate board and independently matched, timestamped book |
| NBA | v4.0 real pregame game-winner research | 6 distinct ESPN games matched and live asks sampled | Independent **model** win probabilities, starters/minutes, injuries and forward settlement |
| NHL | v4.0 real pregame game-winner research | 8 distinct ESPN games matched and live asks sampled | Independent model performance was worse than simple historical home prior; starting goalie and xG required |
| NCAAB men | v4.0 real pregame game-winner research | 8 distinct ESPN games matched and live asks sampled | Adjusted team strength, rosters/starters, independent predictions and forward settlement |
| MLB | Offseason | None | Restart at next season, confirm pitchers/lineups/weather; historical winner baseline underperformed |
| WNBA | Offseason | None | Restart next season with confirmed lineups/minutes |

## New data collectors

- `models/sport_moneyline_forward_v40.py` collects only **game-winner** contracts for NFL/NBA/NHL/NCAAB, never spreads, totals or player props. Requires two distinct winners on the same Kalshi event, one unique ESPN future game with both team names/IDs and ET date matched, 10–360 minutes before kickoff, an actual current public Kalshi market/open status, a **freshly fetched** bid-side orderbook for both YES and NO, at least one contract of bid depth on both sides, and a quote timestamp before kickoff. The board's old yes/no asks are ignored. Fee metadata is checked from series where available. Snapshot of exactly one *home-team YES* contract is used for the future market baseline. **No independent model probability is manufactured**.
- `models/sport_moneyline_settlement_v40.py` runs separately, reads archived quote records, looks up the exact ESPN game ID/date/teams and its completed final score, then confirms the same Kalshi ticker is settled to a matching YES/NO outcome. Missing, tied, mismatched, unsettled or ambiguous results never verify. Repeated snapshots from the same game do not inflate performance. The market midpoint Brier/log loss is a market **reference**; independent model Brier, inferred edge, and hypothetical profit remain explicitly null until genuine model input and precommitted selection rules exist.
- `models/sport_readiness_v40.py` fuses seven-sport historical score-only research, the new capture/settlement summaries, and NCAAF v3.9 forward records into one concise missing-evidence dashboard. A positive historical rolling-score Brier improvement is **not** an exchange value/profitability claim.

## Automation, schedules and safety

- `.github/workflows/sports-forward-capture-v40.yml` — at 16, 18, 20, 22, 00, 02 and 04 UTC daily (UTC schedule; DST local clock shifts), tests then maximum eight uniquely verified game-winner events per league per run. The first one-time bootstrap run completed successfully November 7, 2026. Every new quote must be captured prospectively, with actual order book and independent event ID, not backfilled.
- `.github/workflows/sports-forward-settlement-v40.yml` — at 11:35 and 23:35 UTC daily, independenty reconciles recent real results and publishes the combined seven-sport health report. GitHub Actions can delay, skip, or occasionally fail a scheduled run; check run conclusions, do not assume every scheduled tick is guaranteed.
- Both jobs share `sports-forward-v40` concurrency for data-writing segments, and use bounded safe git rebase-push retries to avoid writing over unrelated paper model workflows. On ordinary changes to the capture files, only offline checks run. A special one-time `[bootstrap-sports]` commit was used to exercise collection immediately; ordinary pushes will not initiate market collection.
- `research/sports-forward/<LEAGUE>/<YYYY-MM-DD>.json`: read-only market observations and, after independent corroboration, separate `verified_outcomes`. No actual wagers, private account information, or order entry.
- `dashboard/sports-v40-capture-health.json`, `dashboard/sports-v40-result-health.json`, `dashboard/sports-v40-readiness.json`: sanitized data for research and dashboard visualization.
- `dashboard-app/app.py` now reads the seven-sport readiness report and annotates each league card. A source-code update alone is **not** verification of the live Render dashboard deployment.

## Exact user safeguards retained

The existing balanced-conservative v2.0 paper model remains authoritative. A model may only produce an official B+ or better 1.00u paper selection when the existing independently justified probability, current verified Kalshi ask, fee-adjusted robust >=5 percentage-point net edge and complete sport-specific information are all available. No automatic research-to-official or research-to-shadow promotion. Never copy raw candidate board midpoint into independent model probability.

NFL candidate-board freshness and ESPN event mapping, per-sport verified starters, goalie/pitcher and lineup features, enough distinct settled forward games, calibrated tails, and actual stake-sized liquidity remain unresolved. Source collection quality is a **research milestone** and not model production authorization.

Research sources: public Kalshi market and orderbooks (https://docs.kalshi.com/getting_started/orderbook_responses), ESPN site scoreboards (unofficial public interface), prior independent historical research in `dashboard/model-health.json`.
