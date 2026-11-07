# NCAA Football v3.4 — availability, independent settlement and ex-ante weather research

Implementation date: November 7, 2026. All features are **research only** and retain the original balanced-conservative paper-betting thresholds. These tools never execute trades or modify the canonical Google Sheet, Bets tab, model-picks.json, or official/shadow paper ledgers.

## Implemented

### Independent final-result corroboration
- `models/ncaaf_settlement_verify_v34.py` checks each archived Kalshi contract against CFBD `/games` final scores, official game ID, exact CFBD home/away identities, kickoff-time match, and independently verified public Kalshi market `status=settled` result.
- A public market result that conflicts with the CFBD winner is blocked and listed in `conflicts`; no result is invented or silently counted.
- A completed game is not automatically treated as a settled contract. No pending event is settled early.
- The script writes independently corroborated outcomes to `research/ncaaf-forward/YYYY-MM-DD.json` under `verified_outcomes`, preserving the preexisting research observations.
- `dashboard/ncaaf-v34-settlement-health.json` shows verified market counts, conflicts and **one home-side model Brier observation per independent game**, not four correlated contract sides. Settlement checks use the `CFBD_API_KEY` GitHub repository secret; token not printed.

### Game-specific availability review
- `models/ncaaf_availability_queue_v34.py` matches research games to CFBD `/games` conference membership and discovers the applicable **primary reporting policy hub**, when available (SEC, Big 12, Big Ten, ACC).
- `dashboard/ncaaf-v34-availability-health.json` provides actual event-specific review list, source hub, kickoff, whether the matchup is a conference contest, and **explicitly unknown** QB and impact-player statuses.
- Report policy hubs and secondary injury aggregators are NOT evidence that a specific starting QB is available. No player verification flag is set merely because a hub exists. Verification must use a genuine game-specific primary report with timestamp, both teams, specific QB and impact-player statuses, and uncertainty.
- Conference policies may not cover nonconference games; don't falsely infer absence of an injury report means healthy roster.
- This research queue is automatically updated by `.github/workflows/ncaaf-cfbd-v32.yml`.

### Historical weather with correct forecast provenance
- `models/ncaaf_weather_history_v34.py` obtains CFBD completed games and outdoor venue coordinates, then uses **Open-Meteo Previous Runs API** `_previous_day1` weather variables. These are forecasts at a fixed 24-hour lead, **not reanalysis or today's updated historical observations**.
- `research/ncaaf-weather/prior-day.json` stores source-provenance observations for 2024, 2025 and 2026 games. `dashboard/ncaaf-v34-weather-history-health.json` records coverage/error counts and always marks the weather effect **NOT CALIBRATED**.
- A bounded, stratified 30-game daily backfill (`.github/workflows/ncaaf-weather-history-v34.yml`) populates different calendar weeks and seasons to limit opening-week sampling bias.
- The archive is **not a weather-adjusted model**. Only after enough prior-forecast samples and season-separated game predictions can a weather effect be trained and evaluated.

### Orderbook, fees, forward performance
- `models/ncaaf_forward_audit_v33.py` reconstructs YES/NO taker asks from *opposite-side bids*, archives observed fixed-point depth and Kalshi series fee multiplier/type, and estimates quadratic taker fees (without treating estimates as charged fees).
- It now stress-tests the orderbook for 1, 10 and 100 hypothetical contracts. These are not the user's undefined 1.00u paper stake.
- Closing-price **proxy** requires two independent pregame observations at least 5 minutes apart and the later one within 90 minutes of kickoff. This is not necessarily the actual final executable exchange price.
- Forward-price movements are now also summarized **once per independent CFBD game**, selecting the home-team YES research contract to avoid treating correlated YES/NO market sides as independent observations.
- The archive has no automatic official or shadow promotion, regardless of apparent edge or observed market depth.
- `.github/workflows/ncaaf-forward-v33.yml` runs the forward audit and the independent settlement check on the existing research archive.

## Promoting a model is NOT yet justified

Actual game-specific QB/injury report interpretation remains unverified, and the impact of an unavailable QB or high-impact player has no independently calibrated coefficient. The sourced weather forecasts lack a validated weather adjustment. A fee quote and displayed depth do not establish actual fillability; closing-price proxies and independently corroborated settlements require more prospective observations and enough uncorrelated game samples.

To promote an individual contract type, require (1) enough stable holdout and forward calibration, (2) QB/availability report evidence and calibrated sensitivities or an explicitly justified uncertainty reserve, (3) weather effect trained and evaluated without future leakage, (4) executable asks with fresh timestamp, adequate depth for a defined paper stake and current fee schedule, and (5) robust positive net edge meeting existing A/A-/B+ criteria. No quotas. Preserve all original history and records.

## Model and market source reference

- CFBD `/games`: https://apinext.collegefootballdata.com/api/games
- SEC availability hub: https://www.secsports.com/fbreports
- ACC availability policies: https://theacc.com/sports/2025/8/28/availability-reporting.aspx
- Big Ten 2026 game-day process: https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx
- Open-Meteo fixed-lead historical forecasts: https://open-meteo.com/en/docs/previous-runs-api
- Kalshi current fee schedule: https://kalshi.com/fee-schedule

No credentials are stored in the repository, and the archive contains no user trades, bank accounts, or personally identifying account data.
