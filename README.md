# MemeScope

> **Kiroween 2026 · Category: Frankenstein**
> One app, four incompatible data sources, one honest verdict.

MemeScope is a meme-coin screener for retail traders. Paste a token contract
address and it stitches together four data sources that were never designed
to work together:

| Source | What it contributes |
|---|---|
| **CoinMarketCap API** | Market data — price, market cap, 24h volume |
| **GoPlus Security API** | Contract security — honeypot, tax, owner, LP lock |
| **DexScreener API** | DEX liquidity, volume, pair age |
| **AI risk narrative** | Plain-language risk assessment of the results |

It then runs **8 strict gates** (ported from a screener built after 4 rugs
in one afternoon) and returns a score, a verdict (**LOLOS** / **GAGAL**),
and an AI risk narrative. One failed gate = GAGAL. No exceptions.

## The 8 gates

1. **Market** — liquidity ≥ $20k, 24h volume ≥ $5k, buys > sells (1h), age ≥ 6h
2. **GoPlus security** — no honeypot, can buy/sell all, tax ≤ 5%, no proxy /
   hidden owner / selfdestruct, owner can't change balances, not mintable
3. **Owner renounced** — owner is the zero address
4. **LP lock / burn** — locked + burned ≥ 95% (burn verified on-chain)
5. **Holder concentration** — top holder < 5%, top 5 < 15%
6. **Deployer / owner reputation** — 0 malicious contracts, no crime flags
7. **Sell path** — selling $1 of the token returns ≥ $0.50
8. **Survival** — 6h price change > −50%

## Honest warning

A LOLOS verdict means **no mechanical trap was found** — not that the token
is safe, and never a recommendation to buy. A rug is the deployer's decision;
no screener can predict it. Any money put in should be treated as money you
are prepared to lose.

## Run it

```bash
# Backend (Python 3, stdlib only — no pip install needed)
python3 src/server.py          # listens on http://localhost:8000

# Frontend
# Open web/index.html in a browser (or serve the web/ folder statically).
```

Optional environment variables:

| Variable | Purpose |
|---|---|
| `CMC_API_KEY` | CoinMarketCap Pro API key. Without it, the CMC section shows "not listed" and screening continues with DexScreener data. |
| `LLM_ENDPOINT` | Optional LLM endpoint for the narrative tier. Without it, a template narrative is used. |
| `PORT` | Backend port (default 8000). |

## Project layout

```
.kiro/            Kiro specs, steering, hooks (required by Kiroween)
src/              Python backend — 8-gate engine + one module per data source
web/              Static frontend — dashboard, report, leaderboard
prototype/        Concept validation (pre-Kiro demo)
docs/             Per-source API notes
```

See `.kiro/specs/memescope/design.md` for the architecture and
`.kiro/specs/memescope/requirements.md` for the full requirements.

## Hackathon

- Event: [Kiroween 2026](https://kiroween.devpost.com/) (Devpost)
- Category: **Frankenstein** — stitch together a chimera of technologies
- Submission deadline: 4 Dec 2026, 14:00 PT
- Built with [Kiro](https://kiro.dev) — see `.kiro/` for specs, steering,
  and hooks.

## License

MIT — see [LICENSE](LICENSE).
