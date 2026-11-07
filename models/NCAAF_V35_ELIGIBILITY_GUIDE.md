# NCAA Football v3.5 — game-by-game eligibility research

Updated: November 7, 2026. **Every v3.5 row is RESEARCH ONLY and is never auto-approved as an official or shadow paper bet.** This applies even when an apparent Kalshi pricing difference exceeds 5 percentage points.

## Sources and workflows

The existing Friday-Monday hourly read-only action `.github/workflows/ncaaf-forward-v33.yml` now:

1. Runs offline tests for orderbook fees, settlement corroboration, eligibility and official source authenticity.
2. Captures **new** Kalshi best-book fills for 1, 10 and 100 hypothetical contracts (not a defined paper-betting unit).
3. Corroborates independently settled Kalshi market results with CollegeFootballData game-final winners.
4. Searches official SEC, Big 12, Big Ten and ACC conference report hubs for **unambiguous direct matchup report URLs**. If a conference hosts the reports in JavaScript/iframes or refuses automated access, its primary documents remain unverified. Discovery does **not** certify a QB or injured player.
5. Validates available direct conference report content against both teams and exact game date. Optional named QB statuses require verifiable excerpts in the actual official source text, captured **before kickoff**.
6. Builds a per-game diagnostic with precise reasons for exclusion, comparing only a *fresh* (<=120-second) pregame sampled orderbook and independently sourced probability. All records are research-only.
7. Commits reports to the repo without modifying trades, bankroll, paper picks, or the canonical Google Sheet.

| Report | Purpose |
| --- | --- |
| `dashboard/ncaaf-v35-eligibility.json` | Individual matchups, per-game exclusions, weather-screen status, observed book/fee edge (research only) |
| `dashboard/ncaaf-v35-source-discovery.json` | Direct official report candidates, official hub connectivity, embedded reports or unavailable hosts |
| `dashboard/ncaaf-v35-verified-availability.json` | Primary document, date, exact teams and explicit QB excerpts verified (where available) |
| `dashboard/ncaaf-v34-settlement-health.json` | Independently corroborated completed games and unique-game forward Brier |
| `dashboard/ncaaf-v33-health.json` | Quote-depth, fees, independent-game pregame closing-price proxies |
| `dashboard/ncaaf-v32-research.json` | Independent model probabilities and sourced kickoff weather snapshot |

The authenticated private dashboard `dashboard-app/app.py` now displays a separate **Which Matchups Are Blocked?** section, though the currently deployed application version has to be verified separately from the GitHub file.

## Source evidence intake (optional, for embedded reports)

The actual direct document URL can be manually added to `research/ncaaf-primary-availability-input.json` when an official conference uses a JavaScript-only or embedded report. Do **not** paste a policy hub URL, a third-party injury aggregator, or unsourced roster speculation.

For each report in the `reports` array, use:

```json
{
  "cfbd_game_id": "CFBD_ID_FROM_GAME_QUEUE",
  "home_team": "EXACT_CFBD_HOME_NAME",
  "away_team": "EXACT_CFBD_AWAY_NAME",
  "direct_official_report_url": "ACTUAL_DIRECT_OFFICIAL_DOCUMENT_URL",
  "qbs": {
    "home": {
      "name": "EXACT_PLAYER_NAME",
      "status": "Out",
      "source_excerpt": "EXACT_QUOTE_FROM_OFFICIAL_DOCUMENT_CONTAINING_NAME_AND_STATUS"
    },
    "away": {
      "name": "EXACT_PLAYER_NAME",
      "status": "Available",
      "source_excerpt": "EXACT_QUOTE_FROM_OFFICIAL_DOCUMENT_CONTAINING_NAME_AND_STATUS"
    }
  }
}
```

These fields are *examples only*, not actual players or official links. They must match the source document, its game date, both team names, and be verified before kickoff; otherwise they remain unverified. Unlisted QB status is **not** automatically treated as Available unless the current official league rules explicitly establish the meaning and completeness of that report. Even a verified document does **not** prove untested player impact coefficients, so the availability and model approval check stays closed.

## Evidence policy and thresholds

- Current v3.5 model holdout diagnostic: at least 250 games, a positive Brier improvement against a home-prior baseline, and ECE below 0.06. These are **diagnostic checks**, not sufficient profitability evidence, and should be predeclared before new training/holdout cycles. The 2026 holdout is not a reusable blind test if tuning has referenced its outcomes.
- The independent forward-result **research target** is at least 40 distinct settled CFBD games (not 40 market-sides and not hundreds of repeated quote observations). This sample size does **not**, by itself, prove profitability.
- Fresh quote: orderbook and series-fee snapshot observed before kickoff, at most 120 seconds old, with verified at least one-contract depth (more for actual intended exposure). An open market or a candidate-board ask alone does not establish liquidity or fillability.
- Research net edge: independent model probability minus observed book VWAP minus estimated quadratic taker fees, further reduced by 4 percentage points of model uncertainty, with an existing 5 percentage-point B+ research threshold. This is not an official price or risk approval.
- Weather: indoor is considered sheltered; otherwise sourced kickoff forecasts must include temperature, gust and precipitation probability. A **conservative qualitative exclusion rule**, not a trained probability coefficient, flags gust >=25 mph, precipitation probability >=65%, or temperature <=25F / >=100F.
- No unverified QB report, dynamic webpage, conference policy link, weather status string, or old model quote can independently satisfy a game. No league-wide global unlock.
- Never interpret a one-contract forward-theoretical P/L as an actual trade, or record it in the paper bankroll.

The workflow does not initiate background work outside scheduled GitHub Actions, make external Kalshi trades, or send betting orders.
