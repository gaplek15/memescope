# MemeScope — Design

> Kiroween 2026 · Category: **Frankenstein**
> One app, four incompatible data sources, one honest verdict.

## 1. Overview

MemeScope is a meme-coin screener for retail traders. The user pastes a
token contract address; the app queries four independent data sources,
runs 8 strict gates, and returns a screening report with a score, a verdict
(LOLOS / GAGAL), and a plain-language AI risk narrative.

The "Frankenstein" element: the four sources were never designed to work
together.

| Source | What it is | Protocol | Auth | Data shape |
|---|---|---|---|---|
| CoinMarketCap | Centralised market-data API | REST + API key | Key (header) | JSON, CMC schema |
| GoPlus Security | Centralised contract-security API | REST, keyless | None | JSON, `"1"`/`"0"` string flags, `percent` as 0–1 fraction |
| DexScreener | DEX market-data API | REST, keyless | None | JSON, `pairs[]` with nested `liquidity.usd`, `volume.h24` |
| BSC RPC (public node) | On-chain reads | JSON-RPC | None | Hex-encoded uint256 (eth_call) |

Stitching them together is the product: one normalised token model feeds the
8 gates, and the gates feed one verdict. No source is trusted blindly — each
gate shows the raw numbers behind its decision.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (static HTML + vanilla JS, no build step)             │
│  index.html · app.js · style.css                                │
│  - token input + chain selector                                 │
│  - progress indicator (which source is being queried)           │
│  - report view (gates, score, verdict, narrative)               │
│  - leaderboard (localStorage)                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ fetch() — direct browser calls for keyless APIs
                       │ POST /api/screen — for keyed / server-side steps
┌──────────────────────┴──────────────────────────────────────────┐
│  Backend (Python 3, stdlib only, no framework)                  │
│  src/server.py  — tiny HTTP server (http.server)                │
│  src/screener.py — the 8-gate engine (ported from             │
│                     ~/workspace/meme_watch/screen_strict.py)    │
│  src/sources/                                                   │
│    cmc.py       — CoinMarketCap client (key from env var)       │
│    goplus.py    — GoPlus token + address security client        │
│    dexscreener.py — DexScreener pairs client                    │
│    onchain.py   — BSC JSON-RPC eth_call helpers                 │
│                   (balanceOf, totalSupply)                      │
│    quote.py     — reverse sell-quote (DEX router quote)         │
│  src/narrative.py — AI risk narrative (template + optional LLM) │
└─────────────────────────────────────────────────────────────────┘
```

### Why this split

- **Keyless APIs (DexScreener, GoPlus) are called from the browser.**
  No server needed, no key to leak, no CORS problem (both allow it).
- **Keyed API (CMC) and on-chain reads go through the Python backend.**
  The CMC key must never reach the browser. The backend also owns the
  8-gate engine, so the screening logic is identical between the CLI
  (`screen_strict.py`) and the web app — one source of truth, ported once.
- **The backend is stdlib-only.** No pip install, no framework, no build
  step. It runs with `python3 src/server.py`. This keeps the project
  runnable on any machine, including the developer's phone-adjacent
  workflow (Termux) and the grading environment.

### Data flow (one screening)

```
address in
  ├─ validate EVM address (regex)                    [REQ-01, REQ-03]
  ├─ DexScreener /tokens/{addr} → best BSC pair      [Gate 1, Gate 8]
  │    └─ no pair? → try /pairs/bsc/{pair} fallback
  ├─ CoinMarketCap /cryptocurrency/quotes/latest     [REQ-05]
  │    └─ not listed? → mark "not listed", continue  [REQ-06]
  ├─ GoPlus /token_security/56?contract_addresses=   [Gate 2, 3, 4, 5, 6]
  │    ├─ lp_holders (percent is a 0–1 FRACTION)
  │    └─ holders (same fraction rule)
  ├─ BSC eth_call: balanceOf(pair, dead) +           [Gate 4]
  │    totalSupply(pair) → on-chain burn %
  ├─ GoPlus /address_security/{owner,creator}        [Gate 6]
  ├─ reverse quote: sell $1 of token → BNB            [Gate 7]
  │    └─ quote fails + liq ≥ $1,000 → WARN, not FAIL
  ├─ score = Σ gate weights (PASS full, WARN half)   [REQ-16]
  ├─ verdict = GAGAL if any FAIL else LOLOS          [REQ-17]
  └─ AI narrative from gate results                  [REQ-20..22]
       └─ LLM unavailable → template narrative
```

### Normalised token model

All four sources are normalised into one dict before the gates run:

```python
{
  "address": "0x…", "chain_id": 56,
  "name": str, "symbol": str,
  "price_usd": float, "market_cap": float | None,   # CMC or DexScreener
  "liquidity_usd": float, "volume_24h": float,
  "buys_1h": int, "sells_1h": int,
  "pair_age_hours": float, "change_6h": float | None,
  "pair_address": "0x…", "dex": str,
  "goplus": {...raw GoPlus result...},
  "lp_locked_pct": float, "lp_burned_pct": float,
  "top1_holder_pct": float, "top5_holder_pct": float,
  "owner": "0x…", "creator": "0x…",
  "sell_quote_usd": float | None,
}
```

The gates read only this model — never the raw API responses. That is what
makes the four sources interchangeable and testable.

## 3. The 8 Gates (ported from screen_strict.py)

| # | Gate | Source(s) | Pass condition |
|---|---|---|---|
| 1 | Market | DexScreener | liq ≥ $20k, vol24 ≥ $5k, buys > sells (1h), age ≥ 6h |
| 2 | GoPlus security | GoPlus | no honeypot, can buy/sell all, tax ≤ 5%, no proxy/hidden owner/selfdestruct, owner can't change balance, not mintable |
| 3 | Owner renounced | GoPlus | owner == 0x0 (or empty) |
| 4 | LP lock/burn | GoPlus + on-chain | locked + burned ≥ 95%, and (burned > 0 or a lock ends > 90 days out) |
| 5 | Holder concentration | GoPlus | top1 non-lock holder < 5%, top5 < 15% |
| 6 | Reputation | GoPlus address | owner & creator: 0 malicious contracts, no crime flags |
| 7 | Sell path | Router quote | selling $1 returns ≥ $0.50 (else WARN if liq ≥ $1k) |
| 8 | Survival | DexScreener | 6h change > −50% |

Weights for the 0–100 score: Market 15, GoPlus 20, Owner 15, LP 20,
Holders 10, Reputation 10, Sell path 5, Survival 5.

Known traps (learned the hard way, 2026-11-06):
- GoPlus `percent` is a **fraction 0–1**, not 0–100. Multiply by 100.
- GoPlus fields can be `None`/`""` when not yet analysed → UNKNOWN (WARN),
  not FAIL. Only an explicit `"1"` fails a security sub-check.
- A token can be GoPlus-clean and still rug. The verdict is about
  *mechanical* traps, not about the deployer's future decisions. The UI
  must say this every time (REQ-18).

## 4. AI Risk Narrative

Two tiers, same input (the gate results):

1. **Template tier (always available).** Deterministic sentences assembled
   from the gate results: names the worst failed gate first, quotes its
   numbers, and adds the residual-risk disclaimer when everything passes.
2. **LLM tier (optional).** When an LLM endpoint is configured (env var),
   the gate results are sent as a short structured prompt and the returned
   3–6 sentences replace the template. The LLM never sees any key, seed, or
   wallet data — only public gate numbers.

The narrative is generated server-side (`src/narrative.py`) so the frontend
never needs an LLM key.

## 5. Leaderboard

- Stored in the browser (`localStorage`, key `memescope.leaderboard`).
- Only LOLOS tokens are added, ranked by score descending.
- Each entry: address, name/symbol, score, liquidity, screened-at timestamp.
- Restored on page load (REQ-24). No server-side database — the app stays
  static-hostable.

## 6. File Structure

```
memescope/
├── .kiro/
│   ├── specs/memescope/
│   │   ├── requirements.md   # EARS requirements (this spec's source)
│   │   ├── design.md         # this file
│   │   └── tasks.md          # numbered implementation tasks
│   ├── steering/
│   │   ├── product.md        # vision, users, principles
│   │   ├── tech.md           # stack + security rules
│   │   └── structure.md      # directory layout
│   └── hooks/
│       └── pre-commit-secret-scan.sh   # blocks commits containing secrets
├── src/
│   ├── server.py             # stdlib HTTP server, /api/screen endpoint
│   ├── screener.py           # 8-gate engine (ported from screen_strict.py)
│   ├── narrative.py          # AI risk narrative (template + LLM tier)
│   └── sources/
│       ├── __init__.py
│       ├── cmc.py
│       ├── goplus.py
│       ├── dexscreener.py
│       ├── onchain.py
│       └── quote.py
├── web/
│   ├── index.html            # dashboard (single page)
│   ├── app.js                # frontend logic
│   └── style.css             # dark theme, mobile-first
├── prototype/                # concept validation (pre-Kiro)
│   ├── demo.html             # static demo page for 1 example token
│   └── demo_screen.py        # CLI demo of the screening flow
├── docs/
│   └── api-notes.md          # per-source API notes + gotchas
├── README.md
├── LICENSE                   # MIT
└── .gitignore                # NEVER ignores .kiro/
```

## 7. Hooks

### pre-commit-secret-scan (`.kiro/hooks/pre-commit-secret-scan.sh`)

Runs before every commit (installed as a git pre-commit hook). It scans
staged files for secret patterns (API keys, `sk-`, `xoxb-`, private-key
headers, seed-phrase-like word lists, `CMC_API_KEY` with a real value) and
aborts the commit when a match is found. It also refuses to commit if
`.kiro/` was accidentally added to `.gitignore`.

Rationale: the project handles a CMC API key and the author has a standing
rule never to leak credentials. A hook is cheaper than a leaked key.

Hook definition (Kiro agent hooks format) lives in
`.kiro/hooks/pre-commit-secret-scan.json` alongside the script; see
`tasks.md` task 9 for the install step.

## 8. Security

- No API key in the repo, ever. CMC key comes from `CMC_API_KEY` env var.
- The frontend never receives the CMC key; all CMC calls go through the
  Python backend.
- No wallet connection, no signing, no transactions. MemeScope only reads
  public data — it cannot move funds and never asks for a wallet.
- The app never recommends buying. It reports facts and a verdict.

## 9. Testing

- **Gate unit tests** (`src/test_gates.py`): each gate tested with a canned
  normalised token model — PASS case, FAIL case, and UNKNOWN case for
  GoPlus fields. No network needed.
- **Live smoke test**: screen one known example token end-to-end and check
  that all 8 gates return a result (PASS/FAIL/WARN, never a crash).
- **Secret-scan test**: a dummy file containing `CMC_API_KEY` must
  be rejected by the pre-commit hook.
