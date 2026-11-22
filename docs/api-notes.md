# MemeScope — API Notes

> Per-source endpoint notes and gotchas. Read this before implementing
> anything in `src/sources/`.
>
> Verified against the final implementation 2026-11-22 (Phase 2 smoke test
> + Phase 3 frontend). Where the implementation differs from the reference
> screener (`screen_strict.py`), the difference is noted inline.

## DexScreener (keyless, no auth)

- Token lookup: `GET https://api.dexscreener.com/latest/dex/tokens/{address}`
  - Response: `{ "pairs": [...] }` — pick the BSC pair (`chainId == "bsc"`)
    with the highest `liquidity.usd`.
  - **Gotcha:** `pairs` can be `null` for some tokens. Fall back to the
    pair-address endpoint (needs the pair address as a second CLI argument
    or from a previous lookup):
    `GET https://api.dexscreener.com/latest/dex/pairs/bsc/{pairAddress}`
- Fields used: `liquidity.usd`, `volume.h24`, `txns.h1.buys/sells`,
  `pairCreatedAt` (ms epoch), `priceUsd`, `priceChange.h6`,
  `pairAddress`, `dexId`.
- Pair age (hours) = `(now_ms - pairCreatedAt) / 3_600_000`.
- No API key, no rate-limit header documented; keep calls to one per
  screening and cache nothing server-side.

## GoPlus Security (keyless, no auth)

- Token security:
  `GET https://api.gopluslabs.io/api/v1/token_security/56?contract_addresses={address}`
  - Response: `{ "result": { "<lowercase address>": { ... } } }`.
  - **Gotcha 1:** `percent` in `lp_holders` and `holders` is a **fraction
    0–1, not 0–100**. Multiply by 100 before comparing with thresholds.
    (Misreading this cost a real rug on BCHN, 2026-11-06.)
  - **Gotcha 2:** fields can be `None` or `""` when the token has not been
    analysed yet. That is UNKNOWN (WARN), not clean and not dirty. Only an
    explicit `"1"` fails a security sub-check.
  - **Gotcha 3:** no data at all for the address = token not indexed =
    FAIL Gate 2 (unverified token).
  - Flags are strings `"1"` / `"0"`: `is_honeypot`, `cannot_buy`,
    `cannot_sell_all`, `is_proxy`, `hidden_owner`, `selfdestruct`,
    `owner_change_balance`, `is_mintable`, `transfer_pausable`,
    `is_blacklisted`, `slippage_modifiable`, `can_take_back_ownership`.
  - Taxes are strings that parse to float: `buy_tax`, `sell_tax`.
  - `lp_holders[]`: `{ is_locked: "1"/"0", percent, locked_detail: [{ end_time }] }`.
    Locked % = sum of `percent` where `is_locked == "1"`.
    Lock expiry check: any `end_time` more than 90 days in the future.
  - `holders[]`: `{ is_locked, is_contract, percent }`. Exclude locked and
    contract holders before computing top1 / top5.
- Address security:
  `GET https://api.gopluslabs.io/api/v1/address_security/{address}?chain_id=56`
  - Response: `{ "result": { "number_of_malicious_contracts_created": n,
    "cybercrime": "0"/"1", "phishing_activities": ..., "money_laundering": ...,
    "honeypot_related_address": ... } }`.
  - Used for Gate 6 on both owner and creator addresses.

## CoinMarketCap (keyed — backend only)

- Quotes: `GET https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbol}`
  (or `id=` when known). Header: `X-CMC_PRO_API_KEY: $CMC_API_KEY`.
- Fields used: `price`, `market_cap`, `volume_24h`, `percent_change_24h`,
  `cmc_rank`.
- **Token may not be listed.** A 400/404 or empty `data` means "not listed":
  mark the CMC section as such and continue with DexScreener data (REQ-06).
- **The key must never reach the browser.** All CMC calls go through
  `src/server.py`. Free Startup-tier key (hackathon grant) is rate-limited;
  one call per screening, retry once on 429.
- Sandbox/base URL: `https://sandbox-api.coinmarketcap.com` for testing
  without spending quota.

## BSC public JSON-RPC (keyless)

- Endpoint: `https://bsc-dataseed.bnbchain.org` (fallbacks: `bsc-rpc.publicnode.com`,
  `https://bsc.drpc.org`).
- `eth_call` with `balanceOf(address)` selector `0x70a08231` + 32-byte
  padded holder address, and `totalSupply()` selector `0x18160ddd`.
- Used for Gate 4: LP-token balance of the dead address
  `0x000000000000000000000000000000000000dEaD` divided by LP total supply
  = on-chain burn %.
- Results are hex uint256; parse with `int(hex, 16)`.
- Public nodes rate-limit `eth_getLogs` heavily — this project only uses
  `eth_call`, which is cheap.

## Reverse sell-quote (Gate 7)

- Purpose: prove a sell path exists and returns a sane amount.
- Method (implemented in `src/sources/quote.py`): PancakeSwap V2 router
  `getAmountsOut(uint256, address[])` via BSC JSON-RPC `eth_call`
  (selector `0xd06ca61f`), selling $1 of the token for WBNB, then
  converting WBNB → USD with a live BNB price. No `baw` dependency.
  `amountIn` assumes 18 decimals (standard for BSC meme tokens; a
  non-18-decimal token would misprice the quote — known limitation).
- Pass: received value ≥ $0.50. Fail: < $0.50 with a successful quote.
- **WARN case:** quote fails but pair liquidity ≥ $1,000 — the router may
  simply not support the token (seen before with ASI); advise the user to
  verify the sell path directly on the DEX instead of failing the gate.
- **Gotcha — BNB price (fixed 2026-11-22, human fix):** DexScreener's
  `priceUsd` is always the price of the pair's **base token**. Taking
  `pairs[0].priceUsd` from the WBNB/BUSD pair returns ~$1.00 (BUSD is the
  base token there), not ~$540 — that made every sell-quote ~$0.002 and
  Gate 7 could never PASS. The fix: only accept a pair whose
  `baseToken.address` is WBNB. Fallback chain:
  DexScreener WBNB token pairs → known WBNB/BUSD pair endpoint →
  CoinGecko simple price (`binancecoin`) → hard-coded 600.0.
