# MemeScope — Implementation Tasks

> Kiroween 2026 · Category: Frankenstein · Deadline: 4 Dec 2026 14:00 PT
> Check off tasks as they are completed. Tasks marked `[K]` need a logged-in
> Kiro session; the rest can be done as preparation.

## Phase 1 — Foundation (pre-Kiro, done in this preparation pass)

- [x] 1. Create project structure (`src/`, `web/`, `docs/`, `prototype/`, `.kiro/`).
- [x] 2. Write `.kiro/specs/memescope/requirements.md` (EARS, REQ-01..33).
- [x] 3. Write `.kiro/specs/memescope/design.md` (architecture, data flow, gates).
- [x] 4. Write `.kiro/steering/product.md`, `tech.md`, `structure.md`.
- [x] 5. Write `.kiro/hooks/pre-commit-secret-scan.sh` + hook definition.
- [x] 6. Write `README.md`, `LICENSE` (MIT), `.gitignore` (must NOT ignore `.kiro/`).
- [x] 7. Build `prototype/demo_screen.py` — CLI demo of the screening flow for
      one example token (uses the real gate logic, canned API data).
- [x] 8. Build `prototype/demo.html` — static demo page showing a sample report.

## Phase 2 — Backend (Kiro implementation)

- [x] 9. [K] Install the pre-commit hook (`cp .kiro/hooks/pre-commit-secret-scan.sh
      .git/hooks/pre-commit && chmod +x`) and verify it blocks a dummy secret.
- [x] 10. [K] Port the 8-gate engine from `~/workspace/meme_watch/screen_strict.py`
      into `src/screener.py` as pure functions over the normalised token model
      (no `print`, return structured results).
- [x] 11. [K] Implement `src/sources/dexscreener.py` (pairs lookup + pair fallback).
- [x] 12. [K] Implement `src/sources/goplus.py` (token security + address security).
- [x] 13. [K] Implement `src/sources/onchain.py` (eth_call balanceOf/totalSupply,
      dead-address burn %).
- [x] 14. [K] Implement `src/sources/cmc.py` (quotes/latest, key from
      `CMC_API_KEY` env var, graceful "not listed" fallback).
- [x] 15. [K] Implement `src/sources/quote.py` (reverse sell-quote for $1 of token).
- [x] 16. [K] Implement `src/narrative.py` (template tier first, LLM tier behind
      env var, never sends keys/wallets).
- [x] 17. [K] Implement `src/server.py` (stdlib `http.server`, `POST /api/screen`,
      JSON in/out, CORS for local dev, 60s timeout).
- [x] 18. [K] Write `src/test_gates.py` (PASS/FAIL/UNKNOWN per gate, no network)
      and make all tests pass.
- [x] 19. [K] Live smoke test: screen one real example token end-to-end and
      confirm all 8 gates return a result.

## Phase 3 — Frontend

- [x] 20. [K] Build `web/index.html` (input form, chain selector, progress
      indicator, report view, leaderboard).
      <!-- Built: single-page dashboard with form, 7-step progress indicator, verdict card, market snapshot, gates table, narrative, evidence links, leaderboard, always-visible disclaimer. -->
- [x] 21. [K] Build `web/app.js` (keyless APIs direct from browser; keyed steps
      via `/api/screen`; progress states; localStorage leaderboard).
      <!-- Built: EVM address validation, 2s-interval progress steps, 65s AbortController timeout, report rendering, localStorage leaderboard (max 20, deduplicated by address, LOLOS-only), formatting helpers, ?api= URL param override. -->
- [x] 22. [K] Build `web/style.css` (dark theme, mobile-first, stacked layout
      on small screens).
      <!-- Built: dark theme (#0d1117 bg, #161b22 surfaces), LOLOS green / GAGAL red / WARN amber tokens, PASS/FAIL/WARN badge styles, gate table with alternating rows, evidence pill badges, mobile-first single-column, 768px breakpoint widens market grid to 3 columns. -->
- [x] 23. [K] Wire evidence links (DexScreener pair, GoPlus token, BscScan
      contract) into every report.
      <!-- Built: renderEvidenceLinks() generates DexScreener /bsc/{pair}, GoPlus /token-security/{chain}/{addr}, and chain-matched explorer link (BscScan/Etherscan/Polygonscan) as pill badges. -->
- [x] 24. [K] Verify the "not listed on CMC" fallback renders correctly.
      <!-- Built: cmc_listed === false shows amber "Not listed on CoinMarketCap" note in market card; price/liquidity/volume fields still populated from DexScreener data in the same response. -->

## Phase 4 — Polish, docs, submission

- [x] 25. [K] Write `docs/api-notes.md` (per-source endpoint notes + gotchas:
      GoPlus fraction 0–1, None fields, DexScreener pairs:null fallback).
      <!-- Verified against final implementation 2026-11-22; added BNB-price
      gotcha (priceUsd = base-token price) + PancakeSwap getAmountsOut method. -->
- [x] 26. [K] Record demo video (< 3 min, YouTube public): input → screening →
      report → leaderboard.
      <!-- Done 2026-11-22: docs/demo.mp4, 43.5s, 1280x720 h264. Real CAKE
      screening (GAGAL 35/100, 8 gates, 3 evidence links) + honest empty-state
      leaderboard — 3 LOLOS candidates tried live (ANT, Mubarak, TST), all
      correctly GAGAL; no leaderboard entries faked. YouTube upload pending
      (needs user's account). -->
- [x] 27. [K] Write the "How Kiro was used" write-up (specs, hooks, steering,
      MCP if used, what changed vs vibe coding).
      <!-- Written: docs/how-kiro-was-used.md — honest about 2 human bug fixes,
      6× 429 throttle, no MCP / no Crew used. -->
- [x] 28. [K] Final repo check: public GitHub repo, MIT LICENSE visible in
      About, `.kiro/` present at root and NOT in `.gitignore`, no secrets
      anywhere (`git log` + hook scan clean).
      <!-- Done 2026-11-22: repo public, MIT detected by GitHub, .kiro/ in
      tree, hook scan 0 hits + pre-commit hook passes, 3 doc dummy values
      removed before push. -->
- [x] 29. [K] Create the GitHub repo (`gaplek15/memescope`), push, verify the
      `.kiro/` directory renders on github.com.
      <!-- Done 2026-11-22: repo id 1467295993, 34 files pushed via Contents
      API (incl. docs/demo.mp4), About + 10 topics set, tree verified via API. -->
- [~] 30. [K] Submit on Devpost (category: Frankenstein, repo URL, live demo
      URL, video URL, description, Kiro write-up) before 4 Dec 2026 14:00 PT.
