# MemeScope — Requirements

> Kiroween 2026 · Category: **Frankenstein**
> MemeScope stitches four incompatible data sources into one screening report:
> CoinMarketCap (market data) + GoPlus (contract security) + DexScreener (DEX
> liquidity) + AI risk narrative (plain-language risk assessment of the 8 checks).
>
> This document uses EARS (Easy Approach to Requirements Syntax).

## Glossary

- **Token**: an ERC-20 / BEP-20 meme token identified by its contract address.
- **Gate**: one of the 8 strict checks. A gate returns PASS, FAIL, or WARN.
- **Verdict**: LOLOS (all gates PASS or WARN) or GAGAL (any gate FAIL).
- **Score**: 0–100, computed from the 8 gates (each gate weighted, see REQ-07).
- **Screening report**: the full output for one token — market snapshot, all 8
  gate results, score, verdict, AI narrative, and raw evidence links.

---

## 1. Token Input

### REQ-01 — Token address input
When the user enters a token contract address, the system shall validate that
it is a well-formed EVM address (0x + 40 hex characters) before any API call.

### REQ-02 — Chain selection
When the user enters a token address, the system shall screen it on BNB Chain
(chainId 56) by default, and shall support selecting a different EVM chain
when the user changes the chain selector.

### REQ-03 — Invalid input handling
When the user submits an invalid address, the system shall show a clear error
message and shall not make any external API call.

### REQ-04 — Example token
When the user clicks "Try an example", the system shall load a known example
token address so the screening flow can be demonstrated without typing.

## 2. Market Data (CoinMarketCap)

### REQ-05 — CMC market snapshot
When a screening starts, the system shall fetch the token's market snapshot
from the CoinMarketCap API (price, market cap, 24h volume, 24h change, rank)
when the token is listed on CMC.

### REQ-06 — Unlisted token fallback
When a token is not listed on CoinMarketCap, the system shall continue the
screening using DexScreener market data and shall mark the CMC section as
"not listed" instead of failing the whole screening.

## 3. The 8 Strict Gates

The gates below are the proven logic from `screen_strict.py` (built after 4
rugs in one afternoon, 2026-11-06). One FAIL = verdict GAGAL. No exceptions.

### REQ-07 — Gate 1: Market (DexScreener)
When market data is available, the system shall PASS Gate 1 only when
liquidity ≥ $20,000 AND 24h volume ≥ $5,000 AND 1h buys > 1h sells AND pair
age ≥ 6 hours.

### REQ-08 — Gate 2: GoPlus full security
When GoPlus returns security data for the token, the system shall PASS Gate 2
only when ALL of the following are clean: not a honeypot, can buy, can sell
all, buy tax ≤ 5% and sell tax ≤ 5%, not a proxy, no hidden owner, no
selfdestruct, owner cannot change balances, not mintable. When GoPlus has no
data for the token, the system shall FAIL Gate 2 (unverified token).

### REQ-09 — Gate 3: Owner renounced
When GoPlus returns an owner address, the system shall PASS Gate 3 only when
the owner is the zero address (or empty), i.e. ownership is renounced.

### REQ-10 — Gate 4: LP lock / burn
When LP holder data is available, the system shall PASS Gate 4 only when
(locked LP % + burned LP %) ≥ 95% AND (some LP is burned OR at least one lock
expires more than 90 days in the future). Burn % shall be verified on-chain
via the dead-address balance of the LP token contract.

### REQ-11 — Gate 5: Holder concentration
When holder data is available, the system shall PASS Gate 5 only when the
largest non-locked, non-contract holder owns < 5% AND the top 5 such holders
together own < 15%.

### REQ-12 — Gate 6: Deployer / owner reputation
When the owner or creator address is known, the system shall query GoPlus
address security and PASS Gate 6 only when the address created 0 malicious
contracts AND has no cybercrime / phishing / money-laundering /
honeypot-related flags.

### REQ-13 — Gate 7: Sell path (reverse quote)
When a price is available, the system shall simulate selling $1 worth of the
token and PASS Gate 7 only when the received value is ≥ $0.50. When the quote
fails but pair liquidity is ≥ $1,000, the system shall return WARN (router
limitation, not a token failure) and shall advise verifying the sell path
directly on the DEX.

### REQ-14 — Gate 8: Survival
When 6-hour price change is available, the system shall PASS Gate 8 only when
the 6h change is greater than −50%.

### REQ-15 — Gate result transparency
When a screening finishes, the system shall show every gate's result (PASS /
FAIL / WARN) together with the raw numbers that decided it, so any user can
re-verify each gate by hand.

## 4. Score and Verdict

### REQ-16 — Score computation
When all gates have run, the system shall compute a score from 0 to 100:
each PASS contributes its weight, each WARN contributes half its weight, each
FAIL contributes 0. Gate weights: Market 15, GoPlus 20, Owner 15, LP 20,
Holders 10, Reputation 10, Sell path 5, Survival 5.

### REQ-17 — Verdict rule
When any gate FAILs, the system shall set the verdict to GAGAL regardless of
the score. When no gate FAILs, the system shall set the verdict to LOLOS.

### REQ-18 — Verdict disclaimer
When a verdict of LOLOS is shown, the system shall always display the
disclaimer that LOLOS is not a guarantee of safety and that any money put in
should be treated as money the user is prepared to lose.

### REQ-19 — No buy recommendation
When a screening report is shown, the system shall never present the result
as a recommendation to buy, sell, or hold. It shall present facts and a
verdict only.

## 5. AI Risk Narrative

### REQ-20 — Narrative generation
When a screening finishes, the system shall generate a short plain-language
narrative (3–6 sentences) explaining the biggest risk found, in the user's
language, based only on the actual gate results.

### REQ-21 — Narrative honesty
When all gates pass, the narrative shall still state the residual risk
(rug risk can never be reduced to zero; a clean contract does not predict
the deployer's future decisions). When a gate fails, the narrative shall name
the failed gate first.

### REQ-22 — Narrative fallback
When the AI narrative service is unavailable, the system shall show a
template narrative built from the gate results instead of failing the
screening.

## 6. Leaderboard

### REQ-23 — Passed-token leaderboard
When at least one token has passed screening, the system shall show a
leaderboard of passed tokens ranked by score (highest first), with token
name, score, verdict, liquidity, and screening time.

### REQ-24 — Leaderboard persistence
When the app reloads, the leaderboard shall be restored from local storage
(browser localStorage) so previous screenings are not lost.

### REQ-25 — No failed tokens on the leaderboard
When a token's verdict is GAGAL, the system shall never add it to the
leaderboard.

## 7. Dashboard UI

### REQ-26 — Single-page dashboard
When the user opens the app, the system shall show a single-page dashboard
with: a token input form, a screening progress indicator, the report view,
and the leaderboard.

### REQ-27 — Progress feedback
When a screening is running, the system shall show which data source is
currently being queried (CMC → DexScreener → GoPlus → on-chain → quote →
narrative) so the user sees progress instead of a blank wait.

### REQ-28 — Evidence links
When a report is shown, every data point shall link to its source
(DexScreener pair page, GoPlus token page, BscScan contract page) so the user
can verify independently.

### REQ-29 — Mobile usable
When the app is opened on a phone-sized screen, the dashboard shall remain
fully usable (input, report, and leaderboard stacked vertically).

## 8. Non-functional

### REQ-30 — No secrets in the repo
When the app is built, no API key, seed phrase, private key, or credential
shall be committed to the repository. Public APIs that need no key shall be
preferred; any key that is needed shall be read from an environment variable
at runtime.

### REQ-31 — Free public APIs only
When the app calls an external API, it shall use a free, keyless public
endpoint where one exists (DexScreener, GoPlus token security) and shall
degrade gracefully when a keyed API (CoinMarketCap) is unavailable.

### REQ-32 — Rate-limit tolerance
When an upstream API returns a rate-limit error, the system shall retry once
after a short delay and then continue with the remaining sources instead of
aborting the screening.

### REQ-33 — Response time
When a screening is started for a token with data on all four sources, the
system shall finish within 60 seconds under normal network conditions.
