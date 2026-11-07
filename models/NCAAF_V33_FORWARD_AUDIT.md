# NCAAF forward audit v3.3 — prospective research only

Validated by GitHub Actions run **42406364423**, 2026-11-07.

## Automated research workflow
- Workflow: `.github/workflows/ncaaf-forward-v33.yml`
- Schedule: hourly UTC on Fridays, Saturdays, Sundays and Mondays; also manual dispatch and changes to v3.3 audit/tests. GitHub schedule execution can be delayed.
- Inputs: `dashboard/ncaaf-v32-research.json` (the separately generated independent, game-matched pregame FBS probability research feed). No other league is modified.
- Observations: `research/ncaaf-forward/YYYY-MM-DD.json` with pregame fixed-point Kalshi orderbook samples and estimated fees.
- Diagnostic health: `dashboard/ncaaf-v33-health.json`.
- This workflow is **read-only with respect to the exchange**. It neither places orders nor reads account positions. It makes GitHub file updates for the prospective research archive and its sanitized health file. It never touches Model Picks, official/shadow ledgers, the user's finances, or their bankroll.

## Audited market assumptions
- Kalshi orderbook API returns **bids** on YES and NO; a YES taker ask is `1 - best NO bid` and a NO taker ask is `1 - best YES bid`. Audit reconstructs cost from actual displayed opposite-side bid *levels* for one sample contract (NOT 1.00u).
- No fill is promised; orderbook snapshots and series settings can change between requests.
- Taker fee estimate uses the live series `fee_type` and `fee_multiplier`, accepting `quadratic` and `quadratic_with_maker_fees`. Quadratic taker fee approximated conservatively as `ceil_to_cent(0.07 × multiplier × contracts × sampled_vwap_price × (1 − sampled_vwap_price))`. Maker fee schedules are **not** used to estimate taker cost. If multiplier/type is missing or unsupported, the fee is **UNKNOWN**; do not substitute a default.
- Only valid pregame quotes are stored. If model snapshot exceeds 18 hours age or is missing, new predictions are NOT recorded. Starting score and final results are never fed back into the entry-time model.
- A closing-price **proxy** requires a *different*, later pre-kickoff observation at least 5 minutes after the initial observation and within 90 minutes of kickoff. This is not the true last executable closing price.
- Settlement is accepted only on a public Kalshi market with `status=settled` and a valid `result=yes|no`; no score is invented. Cross-check against independent official final scores remains outstanding.
- Win/error statistics are by **contract-side**, with correlated YES/NO contracts; theoretical one-contract P/L is not a portfolio or validated trading result. Never include it in official paper W-L, P/L, ROI, bankroll.

## Production approval blockers — DO NOT AUTO-PROMOTE
1. GAME-SPECIFIC QB / material injury reports for both teams, sourced from current conference/team documents and confirmed before kickoff. An official conference report hub alone is not availability evidence.
2. Quantified, historically validated weather effects. Sourced weather forecasts alone are not a scoring adjustment.
3. Verified current fee/series metadata and a suitable actual stake size in contracts; a one-contract audit sample is not one paper unit.
4. Independent settlement corroboration and repeated close-proxy captures, plus enough forward observations to measure calibration and theoretical net edge without overfitting.
5. Consistent separate-season holdout Brier/log-loss calibration, liquidity and uncertainty reserves, and existing 1u/B+ thresholds.

All data has `official_eligible=false`, `shadow_eligible=false`, and `production_eligible=false`, regardless of the displayed theoretical value. The v2 and v3.2 official pick safeguards remain unchanged.
