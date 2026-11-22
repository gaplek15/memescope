# How Kiro Was Used — MemeScope (Kiroween 2026)

> Kiroween 2026 · Category: Frankenstein · Project: MemeScope
> This write-up is part of the Devpost submission. It is honest about what
> Kiro did, what humans fixed, and where Kiro's free tier got in the way.

## TL;DR

MemeScope was built **spec-first with Kiro CLI in spec mode**. A human wrote
the requirements, design, and task list first; Kiro then implemented the
backend (Phase 2) and frontend (Phase 3) task-by-task in non-interactive
spec runs, guided by steering documents and a pre-commit hook. A human
verified every phase independently (unit tests, live smoke test, end-to-end
browser test) and fixed two real bugs Kiro shipped.

## What Kiro is here

- **Tool:** Kiro CLI `3.5.0` (command line), logged in with a free Builder ID
  (`gaplekromli123@gmail.com`). No Kiro IDE, no Kiro Crew, no MCP servers.
- **Invocation (both implementation phases):**

  ```bash
  cd ~/workspace/kiroween/memescope
  kiro-cli chat --no-interactive --mode spec --trust-all-tools "<prompt>"
  ```

  The prompt pointed Kiro at `.kiro/specs/memescope/tasks.md` and asked it to
  implement the next phase's tasks, then report what it built. Each run was
  a single non-interactive spec-mode session (Phase 2: ~19 min, exit 0).

## 1. Spec-driven development (the core of the workflow)

The project was **not** vibe-coded. The spec existed before any
implementation code:

| Artefact | Content |
| --- | --- |
| `.kiro/specs/memescope/requirements.md` | 33 requirements (REQ-01..33) in EARS format (`When … / Then …`): token input, CMC data, the 8 strict gates, score + verdict, AI narrative, leaderboard, dashboard, non-functional rules |
| `.kiro/specs/memescope/design.md` | Architecture (static frontend + stdlib-only Python backend), data flow across 4 sources, the normalised token model, the 8-gate table with score weights, hooks, security, testing plan |
| `.kiro/specs/memescope/tasks.md` | 30 numbered tasks in 4 phases. Phase 1 (foundation) was human-written preparation; Phases 2–4 are marked `[K]` = needs a logged-in Kiro session |

Kiro read the spec and implemented it task by task, checking tasks off in
`tasks.md` as it went. The spec's execution history is recorded in
`.kiro/specs/memescope/tasks.meta.json` (execution IDs + chat session IDs
per task — verifiable evidence of spec-mode runs, not a hand-written claim).

## 2. Steering documents (persistent context, not per-prompt)

Three steering files shaped every Kiro run, so the same rules did not have
to be re-explained in each prompt:

- **`.kiro/steering/product.md`** — vision, target user (retail meme-coin
  traders), 6 product principles: honest about risk, 1 failed gate = FAIL,
  no buy recommendations, read-only (no transactions).
- **`.kiro/steering/tech.md`** — stack + 10 hard rules, including the two
  domain gotchas that matter most: GoPlus `percent` is a fraction 0–1 (not
  0–100 — misreading it cost a real rug in 2026), and a `None` GoPlus field
  is UNKNOWN (WARN), not clean and not dirty.
- **`.kiro/steering/structure.md`** — canonical directory layout.

Kiro demonstrably followed them: the backend is stdlib-only Python, no API
key ever reaches the browser, `.kiro/` is explicitly protected from
`.gitignore`, and the GoPlus fraction handling is correct in the shipped
code (verified by the 62 unit tests).

## 3. Agent hooks (automation, not decoration)

- **`.kiro/hooks/pre-commit-secret-scan.sh`** (+ `.json` definition):
  a pre-commit hook that blocks any commit containing a secret (API key,
  private key, token) and refuses to commit if `.kiro/` is git-ignored.
- Verified working, not just present: a staged file containing
  `CMC_API_KEY` was blocked by the hook (exit 1, `BLOCKED: possible
  secret`) during Phase 2 verification.

## 4. What Kiro actually built

| Phase | Kiro output |
| --- | --- |
| Phase 2 — backend | `src/screener.py` (8-gate engine, pure functions), `src/sources/` (dexscreener, goplus, onchain, cmc, quote), `src/narrative.py` (template tier + LLM tier behind `LLM_ENDPOINT`), `src/server.py` (stdlib `http.server`, `POST /api/screen`, CORS, 60 s timeout), `src/test_gates.py`, `src/smoke_test.py` — ~2,939 lines |
| Phase 3 — frontend | `web/index.html`, `web/app.js`, `web/style.css` — single-page dark-theme dashboard: token input, 7-step progress, verdict card, market snapshot, 8-gate table, AI narrative, evidence links (DexScreener / GoPlus / BscScan), localStorage leaderboard (LOLOS-only, max 20) — ~1,445 lines |

Total: **~4,384 lines** across `src/` + `web/`, all generated inside Kiro
spec-mode runs.

## 5. What humans did (and why it matters)

Kiro was not perfect, and this submission does not pretend otherwise.
A human verified each phase independently instead of relaying Kiro's
claims, and fixed two real bugs:

1. **`src/sources/quote.py` — BNB price wrong 540× (human fix).**
   Kiro's first version took `pairs[0].priceUsd` from the WBNB/BUSD pair.
   DexScreener's `priceUsd` is the price of the pair's **base token** — and
   the base token there is BUSD (~$1.00), not BNB. Every sell-quote came
   back ~$0.002 and Gate 7 could never PASS. The human fix: only accept a
   pair whose `baseToken.address` is WBNB, with a fallback chain
   (DexScreener WBNB pairs → known pair endpoint → CoinGecko → 600).
   After the fix the live smoke test returned a $1.00 sell-quote for CAKE
   and Gate 7 PASSED. This gotcha is now documented in `docs/api-notes.md`.
2. **`src/server.py` — `datetime.utcnow()` deprecated (human fix).**
   Replaced with `datetime.now(datetime.timezone.utc)` in 2 places; the
   server log is now warning-free.

Independent verification results (run by the human, not by Kiro):
- Unit tests: **62/62 PASS** (`python3 src/test_gates.py`, no network).
- Live smoke test (CAKE): all 8 gates returned results — score **35/100,
  verdict GAGAL** (correct for a governance token: mintable, live owner,
  0% LP locked/burned, top holder 94.05%). CMC degraded gracefully to
  "not listed" without an API key.
- Live server: `POST /api/screen` → HTTP 200, verdict + score + 8 gates +
  317-char narrative.
- End-to-end browser test (headless Chrome via CDP): example-token flow
  renders the full report; "not listed on CMC" fallback renders correctly.

## 6. Where Kiro got in the way

- **Free-tier throttling.** During Phase 2, Kiro hit **6× HTTP 429
  `CREDIT_CONSUMPTION_RATE_EXCEEDED`** (Builder ID free tier) and each time
  retried after ~5 minutes. The run still finished (exit 0), but it added
  roughly 30 minutes of wall-clock waiting. Registered Kiroween
  participants can request free credits via the Devpost Resources tab —
  that is the honest fix, and it is what we recommend to anyone repeating
  this workflow.
- **No MCP used.** The workflow needed no MCP servers: all four data
  sources (DexScreener, GoPlus, BSC RPC, CMC) are plain HTTPS APIs, and the
  steering docs carried the domain rules. Adding MCP would have been
  decoration, so we did not.
- **Kiro Crew not used.** The CLI's spec mode was sufficient; Crew's
  multi-agent workspace was unnecessary for a single-developer build.

## 7. Spec-driven vs vibe coding — what actually changed

| Vibe coding (prompt → code) | This project (spec → tasks → code) |
| --- | --- |
| Requirements live in the chat history and drift | Requirements are versioned files (REQ-01..33) the agent must satisfy |
| "Make it work" is the acceptance test | Each task has a checkable outcome; tests + live smoke test are tasks 18–19 |
| Domain gotchas get re-explained (or forgotten) | Steering docs persist the gotchas (GoPlus fraction, None = UNKNOWN) across runs |
| Review is "does it look right?" | Review is "do the 62 tests pass, does the live token screen correctly, does the hook block secrets?" |
| The write-up is written from memory | `tasks.meta.json` records execution IDs and session IDs per task |

The practical difference: when Kiro shipped the 540× BNB-price bug, the
spec + tests made it *findable* — the smoke test's Gate 7 result ($0.00)
contradicted the spec, so the bug was caught in verification instead of
reaching the demo. Vibe coding would have had no such tripwire.

## 8. Reproducing this workflow

1. Write `requirements.md` (EARS), `design.md`, `tasks.md` under
   `.kiro/specs/<project>/` **before** asking Kiro to write code.
2. Put domain gotchas and hard rules in `.kiro/steering/` — they persist
   across runs.
3. Add a hook that enforces at least one rule automatically
   (ours: no secrets in commits, `.kiro/` never ignored).
4. Run Kiro in non-interactive spec mode per phase; keep each run scoped
   to one phase.
5. Verify independently: unit tests + a live end-to-end run against a real
   input. Do not ship Kiro's self-reported success without checking it.
