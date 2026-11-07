# NCAAF probability engine v2.1 — implementation status

Implemented `models/ncaaf_probability_engine_v21.py` as a **research-only screening engine**. It reads the same-day Kalshi candidate board and independent matchup projections. It does not infer projections from Kalshi quotes. It computes Normal-distribution win/cover/over probabilities, both executable YES and NO asks, gross edge and conservative net edge after configurable fees/slippage and uncertainty. It rejects missing FBS, kickoff, injury, weather, provenance, and price data. It emits market coverage, exclusion reasons, and top 10 candidates.

## Required data source — not yet connected

Create `models/data/ncaaf_matchup_projections_YYYY-MM-DD.csv` with the columns documented in the Python module plus `fbs_verified` and `kickoff_et` (ISO 8601 with ET offset). Each row must use the board's exact event_ticker and exact team names. `away_points` and `home_points` must be produced from an independent offense/defense efficiency model with venue, pace, QB/injury and weather adjustments. `margin_sd`, `total_sd`, and `team_sd` must be estimated using out-of-sample residuals; do not assume they are calibrated.

Spread YES contracts require an explicit per-market `spread_yes_mean_<ticker>` projection column (signed mean winning margin after the YES spread), because the board's ticker/selection encoding cannot safely establish contract direction. This is intentionally conservative.

## Calibration gate

Before authorizing official or shadow bets, backtest probabilities on held-out FBS games using Brier score, log loss, reliability bins, and closing-line comparisons, broken down by market category. Check market timestamps, kickoff and fees. Until that is done, the engine's output is **research-only** and cannot trigger sheet picks.

## Run

```bash
python3 models/ncaaf_probability_engine_v21.py --board kalshi/ncaafb-candidates.json --projections models/data/ncaaf_matchup_projections_YYYY-MM-DD.csv --date YYYY-MM-DD --output models/data/ncaaf_screen_YYYY-MM-DD.json
```

Do not create synthetic data or claim historical model calibration. Do not publish raw data or inferred probabilities to the public dashboard without explicit validation. Existing scheduled automation still needs a real independent data pipeline before it can use this script to make picks.
