# Seven-sport Kalshi paper-model research v3.0
Updated: 2026-11-07

## Coverage
| League | Market source | Critical *independent* features still needed |
|---|---|---|
| NCAAF | `kalshi/ncaafb-candidates.json` | Verified FBS-only scope; adjusted team efficiencies; true pace; starting quarterback; injuries; venue; weather |
| NFL | `kalshi/nfl-candidates.json` | EPA/success rates; true pace; QB/offensive line; injuries; play-calling; weather |
| NBA | `kalshi/nba-candidates.json` | Possession-adjusted efficiency, projected minutes/usage, expected starters, injuries, rotation |
| NHL | `kalshi/nhl-candidates.json` | Expected goals, confirmed goalies and goalie quality, special teams, injuries, rest |
| Men's NCAAB | `kalshi/ncaab-candidates.json` | Adjusted efficiency/possessions, Division I validation, roster/transfers, rotation, venue, rest |
| MLB | `kalshi/mlb-candidates.json` | Probable/confirmed starters, pitch counts, bullpen, handedness, lineups, park/weather, pitcher props |
| WNBA | `kalshi/wnba-candidates.json` | Adjusted efficiency/pace, starters/minutes/usage, injuries, player prop distributions |

## What was implemented
- `multisport_collect_v30.py`: historical completed scores from ESPN's unofficial scoreboard endpoints; no live lineup or advanced data inferred.
- `multisport_features_v30.py`: shrunk, last-eight rolling score-based baseline strictly from **earlier calendar dates**; rest-day indicators; excludes games without at least five prior appearances per team. It is **not a true pace or advanced efficiency model**.
- `multisport_backtest_v30.py`: fixed time/season boundary, train/test strictly separated by calendar date, research winner Brier, log loss and league prior baseline, error SD from training games only.
- `multisport_health_v30.py`: all-league research and board-quality summaries, sanitized for the dashboard. All leagues **production_eligible=false, official_eligible=false**.
- `test_multisport_v30.py`: no-day-leakage, nonoverlap, supported sports, source parsing, safety gating.
- `.github/workflows/multisport-research-v30.yml`: weekly/manual/on-code-change research workflow, artifacts and conditional health publication to `dashboard/model-health.json`.
- `dashboard-app/app.py`: separate *Model Health Across All Seven Sports* section, distinct from official/shadow betting records. Men's NCAAB added to league navigation.
- All relevant model automations point to this research infrastructure, without enabling MLB or WNBA in the offseason.

## Decision safeguards
- Passing CI is **not** evidence that projections are calibrated or have positive value.
- This pipeline does not score live Kalshi contracts or place bets; it does not change historical picks, bankroll, accounts, or sheets.
- Do not estimate a new official pick using merely the rolling-score proxy, ESPN game scores, or Kalshi price itself.
- Continue using the established balanced-conservative v2 policy for **independently validated** probabilities: executable YES/NO ask, timestamped pregame status, appropriate fees/slippage and uncertainty, liquidity, and strictly positive robust net edge; B+ requires at least 5 pp net edge. Maximum one 1.00u official paper pick per league per run, shadows independent, no forced picks.
- When historical market ask snapshots or independent player/team feature evidence are missing, label **INSUFFICIENT MODEL COVERAGE** or **DATA PASS**, not “no edge.”
- MLB and WNBA remain intentionally inactive in the offseason; historical diagnostics may run independently.
- No extrapolation from the score-only winner test to spreads, totals, team totals or player props.

## Promotion checklist per league, not a single blanket switch
1. Obtain independent, timestamped *pre-event* team and player metric data with source, freshness and missingness audit. Do not retroactively treat after-game data as pregame.
2. Add independent league-specific model architecture and distributional probabilities for the exact market contract. Store home/away, starters, injury, weather and model version provenance.
3. Walk-forward, **separate-season** evaluation; compare against strong home/away, ratings and publicly available baseline models; validate calibration curves and Brier/log loss by probability bucket. Distinct seasons must have no shared train/test dates.
4. Archive timestamped **executable** Kalshi YES/NO asks, fees, spreads, liquidity and settlement conditions for forward performance; historical backtests require historical executable prices. Evaluate expected net value after friction and uncertainty.
5. Ensure FBS/D-I/eligible league membership, pre-kickoff timestamps, market semantics, lineup/goalie/pitcher status and no look-ahead.
6. Only after independent holdout accuracy and live paper forward validation can an individual league/market be considered for official eligibility. Preserve current conservative policy, canonical Google Sheet, existing dashboard and unique IDs.

## Known limitations
- ESPN endpoints are unofficial and can change; zero HTTP failures does not guarantee schedule completeness.
- The baseline is shrinkage of points scored/allowed with a global prior; it ignores opponent rating networks, actual possession rates, replacement players and offseason roster shifts.
- NHL moneyline draws/regulation/overtime and market-specific settlement require explicit handling before any bets.
- A market with an active status or valid ask in the candidate board does not prove quote freshness or that the game has not started.
- Historical baseline Brier improvements **do not prove positive betting value**. Official gating stays separate from these results.
