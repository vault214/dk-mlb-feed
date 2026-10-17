# Balanced-Conservative Sports Paper Model v2.0
Effective: 2026-10-17 (prospective only)

## Leagues
NCAAF, NFL, MLB, NHL, WNBA, and NCAA basketball where a model and current market feed are available. This document defines shared selection policy; it does not by itself change ChatGPT scheduled-task prompts or create new feeds.

## Non-negotiable data checks
Use each league's authoritative market candidate board. Verify current America/New_York board date, positive candidate count, valid game date and FBS-only scope for NCAAF, and executable yes_ask/no_ask (never midpoint). If stale, missing, empty, or invalid: DATA PASS. Never invent odds, injury reports, probabilities, or market prices.

## Probability and cost methodology
Estimate fair probabilities using independently supported team/player metrics, matchup, lineup/QB/injuries, rest/travel, pace, weather, and market context. Quantify uncertainty; do not treat external consensus as an independent calibrated model. Break-even = executable ask / 100 for cent quotes, before fees. Gross edge (pp) = 100*(model probability - break-even). Net edge (pp) = gross edge minus explicit estimated fees/slippage and an uncertainty reserve. Report assumptions; if reliable estimation impossible, PASS rather than invent a model probability. Avoid double-counting correlated information.

## Grades and decisions
A/A-: strong robust positive net edge and high confidence, OFFICIAL eligible.
B+: net edge >= 5 percentage points after costs and uncertainty, defensible calibrated probability and sound liquidity, OFFICIAL eligible.
B/B-: defensible positive net edge below official bar, SHADOW eligible, with explicit rejection reason.
C or worse: PASS. No forced picks. At most one OFFICIAL paper bet of 1.00u per league per scheduled run. Shadow stakes are hypothetical 1.00u and never count toward official P/L or bankroll. No retroactive shadow promotions.

## Scope and record integrity
For NCAAF Friday evening: only current Friday FBS games; Saturday morning: only current Saturday FBS games. Do not double-count previous runs. Preserve historical entries and existing official/shadow records; version-tag new picks v2.0. Use unique Entry IDs and deduplicate. Settle when verifiable, with official and shadow P/L separate. A/B/C = strongest side/spread, total, additional qualifying market, as available.

## Dashboard
Canonical source: Google Sheet Model Picks tab. Do not alter Bets tab. After successful sheet reconciliation, rebuild dashboard/model-picks.json from FULL current Model Picks tab, retaining existing schemaVersion/visibility/note/rows and only the approved sanitized model fields. Never publish actual-bet, matched-trade, cash-flow, bank account, transaction ID, or dollar balance fields.

## Validation
Compare v2.0 against prior policy prospectively by number of official plays, closing-line movement where measurable, calibration/Brier score, win rate, net units, drawdown, and shadow performance. A frequency target is diagnostic only, not a quota. Review after sufficient settled sample; no guaranteed profitability.
