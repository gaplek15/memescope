# MemeScope — Product Steering

> This file guides every implementation decision. When in doubt, re-read this
> before writing code.

## Vision

Retail meme-coin traders lose money to rugs they could have spotted in 60
seconds. The data that exposes a rug already exists — it is just scattered
across four incompatible sources (CoinMarketCap, GoPlus, DexScreener, and
the chain itself). MemeScope stitches those sources into one screening
report and one honest verdict, so a trader can check a token *before*
buying instead of learning about the rug afterwards.

## Target user

- A retail trader who buys small-cap meme coins on BNB Chain (and other EVM
  chains later).
- Not a developer. They can paste a contract address and read a verdict.
- They have been rugged before, or have watched someone get rugged.
- They trade from a phone as often as from a desktop.

## Principles

1. **Honest about risk, always.** A LOLOS verdict means "no mechanical trap
   was found", never "this is safe" and never "you should buy". Every LOLOS
   report carries the residual-risk disclaimer. A rug is the deployer's
   decision — no screener can predict it.
2. **Show the numbers, not just the verdict.** Every gate shows the raw
   figures behind its decision, with a link to the source. If a user cannot
   re-verify a gate by hand, the gate is not done.
3. **One FAIL = GAGAL. No exceptions.** The 8 gates are hard gates. There is
   no "overall score saves a failed gate" logic, no override, no "but the
   chart looks good".
4. **No buy/sell/hold advice, ever.** MemeScope reports facts. It never
   recommends an action.
5. **Free and keyless where possible.** The core screening must work with
   public, keyless APIs. A keyed API (CoinMarketCap) is an enhancement, never
   a hard dependency — its absence degrades the report, it never blocks it.
6. **Read-only.** MemeScope never connects a wallet, never signs anything,
   never moves funds. It reads public data only.

## What MemeScope is NOT

- Not a trading bot, not a signal service, not a "gem finder".
- Not a guarantee. A token that passes all 8 gates can still rug.
- Not a replacement for the user's own judgement.

## Success criteria (for the hackathon)

- A user can paste a token address and get a full report in under 60 seconds.
- Every gate result is verifiable against its linked source.
- The demo video shows the whole flow end-to-end on a real token.
- The Frankenstein story is visible in the product: four incompatible
  sources, one report.
