# NCAA Football v3.6 — game-level availability leads + daily settlement research

## Implemented (2026-11-07)

**New secondary availability discovery:** `models/ncaaf_supplemental_availability_v36.py` matches both independent CFBD teams and the ET event date against game-specific public links listed by `https://kickoffstatus.com/`. This is an unaffiliated aggregator, not a conference report. The collected links, and only the links, are written to `dashboard/ncaaf-v36-secondary-leads.json`. Its `primary_matchup_document_verified`, `quarterback_verified`, `injuries_verified`, `official_eligible` and `source_player_statuses_used` are always false. The collector never feeds third-party player claims into projections.

**Official report verifier unchanged in policy:** `models/ncaaf_official_report_discovery_v35.py` still attempts links from official SEC, Big 12, Big Ten and ACC conference sites; `models/ncaaf_primary_report_evidence_v35.py` will fetch and check actual direct official matchup documents submitted in `research/ncaaf-primary-availability-input.json`. Generic hubs, embedded unaudited apps, missing team/date/player excerpts and evidence first observed after kickoff are not verification. The official-source ingestion is *not yet reliably available for all conferences*.

**Per-game blocker board:** `models/ncaaf_game_eligibility_v35.py` now annotates each matched game with its third-party review URL and **separate** missing primary document, QB and material-impact verification reasons. Weather, model, quote, fee/depth and independent settled-game criteria remain distinct. The primary-document observation timestamp must be before kickoff. `dashboard/ncaaf-v35-eligibility.json` stays read-only and all games remain research-only with official/shadow false. Dashboard app code adds an explicitly unverified review link only for the exact allowlisted supplemental URLs.

**Independent settlement schedule:** New workflow `.github/workflows/ncaaf-settlement-daily-v36.yml` runs at 08:25 and 20:25 UTC daily (plus manual dispatch and code-change check). It uses `CFBD_API_KEY`, independent CFBD final scores and Kalshi public market results to corroborate archived pregame research observations. Same concurrency group as the existing Friday–Monday hourly forward workflow to avoid conflicting archive writes.

**Settlement correctness:** `models/ncaaf_settlement_verify_v34.py` now preserves the first verification timestamp when rechecked; rechecks don't increment 'newly verified' for unchanged results. If CFBD later disagrees with an archived outcome, the verification is revoked and a conflict is surfaced. It includes current and immediately previous football seasons when validating late December/postseason games across January. Only one distinct game's home-side prediction contributes to independent forward Brier.

## Read-only reports
- `dashboard/ncaaf-v36-secondary-leads.json`: exact third-party matchup links, **not verified player status**.
- `dashboard/ncaaf-v35-source-discovery.json`: direct official document discovery and embedded/inaccessible source gaps.
- `dashboard/ncaaf-v35-verified-availability.json`: actual fetched official game-specific source evidence, if any.
- `dashboard/ncaaf-v35-eligibility.json`: each matchup's blockers and unverified report link.
- `dashboard/ncaaf-v34-settlement-health.json`: independently corroborated settled market outcomes and one winner sample per game.
- `research/ncaaf-forward/YYYY-MM-DD.json`: original pregame observations; independent verified outcomes added separately.
- All official paper picks, original betting ledger/history and bankroll remain untouched.

## What's genuinely blocked

The new third-party link matching reduces research friction but does **not** unblock QB/availability source verification. Because many official conference reports are embedded and not directly accessible to static scraping, game-specific verification may still require direct conference documents, supported official APIs, or a rigorously cited manual review. A player absent from a list is not automatically presumed healthy without that league's exact applicable policy and known starting QB identity.

Forward settlement verification cannot create outcomes before actual results and Kalshi settlement. A small or repeated snapshot sample cannot substitute for dozens of distinct games, calibrated robust edge, current fee/depth and the existing B+ 5pp net minimum. No automatic official or shadow picks are authorized by any v3.6 component.

References:
- SEC official football availability hub: https://www.secsports.com/fbreports
- Big Ten 2026 process: https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx
- Third-party scout (unverified): https://kickoffstatus.com/
