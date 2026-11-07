# NCAAF v3.9: Official publisher provenance and honest independent forward performance
Updated November 7, 2026. Scope: NCAA Football research only; no exchange orders, wagers, account access, official/shadow picks, changed bankroll or modified historical betting ledger.

## 1. What the source verification actually established

**Source A: primary official conference website.** `models/ncaaf_provider_proof_v39.py` reads the official SEC, Big 12, Big Ten or ACC reporting hub, scoped by CFBD game ID, both teams, conference membership and game-date context. It only recognizes a public HD Intelligence football viewer if the exact URL appears as a link/iframe in the real conference HTML. It strictly validates HTTPS, `app.hdintelligence.com`, the four query parameters `conf`, `source`, `sport=Football`, `type=report`, and an exact matching conference code; guessed provider URLs are prohibited.

**Live verification, November 7:** Three official reporting hubs were fetched successfully; Big 12's official page attested one HDI viewer that maps to two tracked Big 12 matchups. The particular SEC and Big Ten hub pages inspected did not expose an attested vendor viewer to this static link collector. This does NOT mean they publish no reports.

**Source B: vendor's public HTML.** `models/ncaaf_viewer_format_probe_v39.py` opened ONLY the officially attested Big 12 viewer and found 7,629 initial HTML bytes but just 15 visible text characters: client-side JavaScript is necessary.

**Source C: publicly rendered page.** `models/ncaaf_viewer_browser_probe_v39.py` used sandboxed headless system Chrome with a bounded execution time on the attested public HDI viewer. Chrome successfully rendered 3,161 characters of visible page text. However, the verified game-day report *for one specific CFBD fixture* was not isolated, no confirmed starting QB identified, and no published player's status was certified. Browser rendering is a structural access result only.

Reports:
- `dashboard/ncaaf-v39-provider-proof.json`: official publisher endorsement of the viewer, not player evidence
- `dashboard/ncaaf-v39-viewer-probe.json`: HTTP visible HTML / JavaScript dependency
- `dashboard/ncaaf-v39-browser-probe.json`: headless rendered viewer format, not a game-scoped report

All three tools fail closed if a source is inaccessible, redirects off an allowlist, or a game is not applicable to that conference policy.

**Why no QB green status yet?** A conference-wide viewer may contain numerous games and updates. To mark one starter's status verified, the model still needs the official final game-day report for the **exact match and date**, two correctly identified starters and roster/two-deep scope, an auditable update time strictly before kickoff, and a predeclared approach to unknown players/material absences. HDI's public viewer and a third-party injury transcription by themselves cannot meet those requirements. Do NOT infer unlisted players are healthy or actual starters without a complete applicable game-specific report.

## 2. Independent scorecard, without ex-post cherry-picking

`models/ncaaf_forward_scorecard_v39.py` reads only already archived, pregame Kalshi quote snapshots in `research/ncaaf-forward/YYYY-MM-DD.json` and the independent `verified_outcomes` fields populated by `models/ncaaf_settlement_verify_v34.py`. It requires a correct home/away CFBD game identity, model captured no later than the quote timestamp, quote strictly before kickoff, and independently reconciled *both* CFBD final score and Kalshi settled market result. Repeated snapshots and correlated YES/NO contract sides never inflate independent game count.

Metrics (reported only with genuinely verified games):
- Single home-team winner probability per independent game: Brier score and log loss
- Same-time Kalshi YES/NO book implied YES bid/ask midpoint (only where matching quotes exist), with Brier/log-loss reference; this is **not** an exchange closing price
- Earliest as-of pregame batch (within 120 seconds): pick at most one deterministic *research* contract-side per game only if model probability exceeds observed one-contract VWAP ask plus estimated taker fees, a 4 percentage-point uncertainty reserve, and at least 5 additional percentage points. One contract is not the user's 1.00u paper stake.
- **Crucial anti-survivorship design:** candidate selection occurs without consulting settlement status. Pending or non-reconciled chosen contracts remain in the pending set rather than being discarded in favor of a retrospectively verified runner-up. Only independently verified outcomes can contribute hypothetical one-contract P/L, wins, or Brier.
- Closing price *proxies* only when a second pregame quote is at least five minutes later and within 90 minutes of kickoff; a proxy is never a guaranteed executable closing quote.
- No statistical approval from a tiny sample. The research target of >=40 distinct settled games is only a first evaluation size, **not proof of edge or profitability**. All model and official/shadow eligibility flags remain false.

Daily workflow `.github/workflows/ncaaf-settlement-daily-v36.yml` now runs the new scorecard after independently reconciling settlements, and commits `dashboard/ncaaf-v39-forward-scorecard.json`. The scorecard also appears on the code-version dashboard's NCAAF health card.

**First actual November 7 report:**
- 13 independent games with pregame market observations
- 3 pregame research candidates chosen from the forward archive using the stated price/fee/uncertainty screen
- 3 of those awaiting independent settlement
- 0 independently verified game outcomes; *no measured forward Brier, win-rate or hypothetical net P/L yet*

## 3. Actions and permissions

No new API keys are required. Existing `CFBD_API_KEY` remains in GitHub Actions secrets and is not exposed in reports.

GitHub workflows:
- `.github/workflows/ncaaf-provider-proof-v39.yml`: inspect actual conference publisher link provenance, vendor HTTP format and browser rendering; scheduled on Friday/Saturday and on code updates
- `.github/workflows/ncaaf-forward-v33.yml`: 15-minute, three-hour pregame collection of public Kalshi quotes and report discovery (scheduled or manual); publishing depends on an actual kickoff window
- `.github/workflows/ncaaf-settlement-daily-v36.yml`: twice-daily independently corroborated settlement and one-game forward accuracy scorecard
- On code pushes, safety checks run, and the forward workflow deliberately skips live collection. GitHub schedule runs are not hard real-time.

## 4. What still blocks official selection

The actual, unique, complete game-specific final report for relevant starters and player impacts, properly calibrated material absence/weather adjustments (or conservative exclusions), a sufficient new prospective sample of uncorrelated settled games with a durable positive net edge, and fresh intended-stake-sized Kalshi executable-book validation. These requirements are not relaxed by a green software test or a vendor app that renders successfully.

Tests cover forged vendor URLs, wrong conference/query matches, JS-shell evidence, postkickoff data leakage, exact-game duplicate counting, independently corroborated results, and prevention of outcome-based survivorship.

References:
- https://www.hdintelligence.com/privacy-policy
- https://www.secsports.com/reports
- https://admin.big12sports.com/news/2025/8/13/general-big-12-conference-to-begin-player-availability-reporting-for-football-womens-and-mens-basketball.aspx
- https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx
- https://admin.theacc.com/sports/2025/8/28/availability-reporting.aspx
