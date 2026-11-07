# NCAA Football probability research v3.2

Updated: 2026-11-07. **Paper research only. Neither production approval nor official/shadow picks.**

## Live research workflow

Workflow: `.github/workflows/ncaaf-cfbd-v32.yml`

Secrets: GitHub Actions repository secret `CFBD_API_KEY`; never write it to output/logs.

Runs when the model changes, on manual dispatch, and Friday/Saturday morning (UTC schedule). Python standard library, tests run first. Produces private GitHub Actions artifacts and three deliberately sanitized dashboard health feeds.

| File | Information | Eligibility |
| --- | --- | --- |
| `dashboard/ncaaf-v32-health.json` | Train / calibration / holdout Brier, calibration error, matched moneyline contract counts | Research only |
| `dashboard/ncaaf-v32-weather-health.json` | CFBD venue/dome matches and Open-Meteo kickoff forecast coverage | Research only, **no untested weather adjustments** |
| `dashboard/ncaaf-v32-quote-health.json` | Matched-ticker public Kalshi ask capture, open and preclose status counts | Research only, **no depth/fee validation** |

## Data architecture

1. Pull CFBD `/teams/fbs`, `/games` with FBS classification, and `/stats/game/advanced` separately for 2024, 2025, and 2026.
2. Generate **only prior-ET-date** rolling advanced game PPA, success rate and play-count features; plus a strictly prior-result Elo-style strength proxy, neutral venue and rest days. Each season resets its game history; skip teams without 3 prior games of advanced data. Do not derive independent probabilities from Kalshi quotes.
3. Train penalized logistic on 2024 game winners; fit Platt calibration with 2025 outcomes; evaluate once on untouched 2026 games. Report reliability bins, expected calibration error, Brier, log loss, and empirical home-win baseline.
4. For *future* FBS games with verified kickoff, map full two-team Kalshi GAME event pairs by exact unambiguous school or approved alias. One-sided events, FCS opponents and ambiguous nicknames are excluded.
5. For matched pregame venues, use CFBD `/venues` + Open-Meteo hourly forecasts for outdoor stadiums. Never interpret a sourced forecast as a verified QB report or backtested weather scoring adjustment.
6. Query Kalshi's public `/markets/{ticker}` API for each matched ticker. Record the **observed timestamp**, actual YES/NO ask, open/preclose status, and any change from the stored candidate board. Do not claim current quote depth or historical availability. Do not use prices to train the model.

## Explicit remaining production blockers

- Actual current *game-specific* official conference availability / QB reports for both teams. SEC (https://www.secsports.com/fbreports), Big 12 (https://big12sports.com/sports/2025/8/21/availability-reporting.aspx), Big Ten and ACC publish reports under their official sites. Merely visiting a hub is **not proof** a quarterback is available. Conference coverage may exclude non-conference games.
- Injury/QB impact **calibration against historical availability before kickoff**, not a guess of points lost.
- Weather probability effects must be trained and evaluated using **historically available forecasts** (weather forecasts retrieved after games are data leakage).
- Market orderbook *ask-side executable depth*, liquidity, exact fee calculation, and realistic slippage. Public market-summary asks alone are insufficient for a robust 1u paper pick.
- A saved series of timestamped, *pregame* Kalshi quotes and independent forecasts for forward evaluation. A Brier score improvement does not establish a betting advantage.
- Manual quality gate, separate historical holdout seasons, and existing 1.00u official max and positive net-edge policies.

All three feeds intentionally set `production_eligible=false`. They never write the canonical Google Sheet, `dashboard/model-picks.json`, real trades, or the paper bankroll. No automatic pick is promoted from research to official or shadow.
