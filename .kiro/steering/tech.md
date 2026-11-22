# MemeScope — Tech Steering

> Stack choices and hard rules. These are constraints, not suggestions.

## Stack

- **Backend:** Python 3, standard library only (`http.server`, `urllib`,
  `json`). No framework, no pip dependencies. Rationale: the project must
  run anywhere with a single command (`python3 src/server.py`), including
  minimal environments.
- **Frontend:** Static HTML + vanilla JavaScript + one CSS file. No build
  step, no framework, no bundler. Rationale: the dashboard must be
  hostable on any static host (GitHub Pages) and readable by a judge in
  minutes.
- **Data sources:**
  - CoinMarketCap API — keyed, via backend only (key never reaches the
    browser). Key from `CMC_API_KEY` environment variable.
  - GoPlus Security API — keyless, REST.
  - DexScreener API — keyless, REST.
  - BSC public JSON-RPC — keyless, `eth_call` for `balanceOf`/`totalSupply`.
- **Storage:** Browser `localStorage` for the leaderboard. No server-side
  database, no accounts.

## Hard rules

1. **Never commit a secret.** No API key, seed phrase, private key, password,
   or token in any file, comment, test fixture, or commit message. The
   pre-commit hook (`.kiro/hooks/pre-commit-secret-scan.sh`) enforces this;
   never bypass it with `--no-verify`.
2. **Never show a secret.** Never print, log, paste, or screenshot a key,
   seed, or credential. File paths only.
3. **`.kiro/` must be committed.** Do NOT add `.kiro/` or any sub-folder to
   `.gitignore`. The Kiroween judges require the `.kiro/` directory at the
   repo root. If it is missing, the submission is disqualified.
4. **GoPlus `percent` is a fraction 0–1, not 0–100.** Always multiply by 100
   before comparing with a percentage threshold. (Learned 2026-11-06: BCHN's
   LP data was misread before the rug.)
5. **GoPlus fields can be `None` or `""`.** That means "not yet analysed"
   (UNKNOWN → WARN), not "clean" and not "dirty". Only an explicit `"1"`
   fails a security sub-check.
6. **DexScreener `pairs` can be `null`.** Fall back to the pair-address
   endpoint (`/pairs/bsc/{pair}`) when the token endpoint returns no pairs.
7. **One FAIL = GAGAL.** Do not add score-based overrides or exceptions to
   the verdict rule.
8. **No wallet, no signing, no transactions.** The app only reads public
   data. If a feature needs a wallet, it does not belong in MemeScope.
9. **Degrade, don't crash.** If one source fails or rate-limits, retry once,
   then continue with the remaining sources and mark the failed section
   clearly. A screening must never abort because one API is down.
10. **Keep the gate logic in one place.** `src/screener.py` is the single
    source of truth for the 8 gates. The frontend never re-implements a gate;
    it only renders what the backend returns.

## Environment variables

| Variable | Purpose | Required? |
|---|---|---|
| `CMC_API_KEY` | CoinMarketCap Pro API key | No — CMC section degrades to "not listed" without it |
| `LLM_ENDPOINT` | Optional LLM endpoint for the narrative tier | No — template narrative is the fallback |
| `PORT` | Backend listen port | No — default 8000 |

## Conventions

- Python: snake_case, stdlib only, type hints on public functions.
- JavaScript: plain functions, no modules/bundler, `const`/`let` only.
- All user-facing text: English (hackathon is international); the AI
  narrative may follow the user's language when known.
- Timestamps in reports: UTC, ISO format.
