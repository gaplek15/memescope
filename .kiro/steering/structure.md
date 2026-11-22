# MemeScope — Structure Steering

> Canonical directory layout. New files go in the place below that matches
> their role. Do not invent new top-level folders without updating this file.

```
memescope/
├── .kiro/                          # Kiro configuration (MUST be committed)
│   ├── specs/memescope/
│   │   ├── requirements.md         # EARS requirements (REQ-01..33)
│   │   ├── design.md               # Architecture + data flow + gates
│   │   └── tasks.md                # Numbered implementation tasks
│   ├── steering/
│   │   ├── product.md              # Vision, users, principles
│   │   ├── tech.md                 # Stack + hard rules
│   │   └── structure.md            # This file
│   └── hooks/
│       ├── pre-commit-secret-scan.sh    # Secret scanner (git hook)
│       └── pre-commit-secret-scan.json  # Kiro hook definition
├── src/                            # Python backend (stdlib only)
│   ├── server.py                   # HTTP server, POST /api/screen
│   ├── screener.py                 # 8-gate engine (single source of truth)
│   ├── narrative.py                # AI risk narrative (template + LLM tier)
│   ├── test_gates.py               # Gate unit tests (no network)
│   └── sources/                    # One module per data source
│       ├── __init__.py
│       ├── cmc.py                  # CoinMarketCap (keyed, via env var)
│       ├── goplus.py               # GoPlus token + address security
│       ├── dexscreener.py          # DexScreener pairs
│       ├── onchain.py              # BSC eth_call helpers
│       └── quote.py                # Reverse sell-quote
├── web/                            # Static frontend (no build step)
│   ├── index.html                  # Dashboard (single page)
│   ├── app.js                      # Frontend logic
│   └── style.css                   # Dark theme, mobile-first
├── prototype/                      # Concept validation (pre-Kiro)
│   ├── demo.html                   # Static demo page, 1 example token
│   └── demo_screen.py              # CLI demo of the screening flow
├── docs/
│   └── api-notes.md                # Per-source API notes + gotchas
├── README.md                       # Project overview + how to run
├── LICENSE                         # MIT
└── .gitignore                      # NEVER ignores .kiro/
```

## Placement rules

- **Gate logic** → `src/screener.py` only. Never duplicate a gate in the
  frontend or in a prototype.
- **One data source = one module** under `src/sources/`. A module may only
  talk to its own API.
- **Secrets** → environment variables only. Never in `src/`, `web/`,
  `docs/`, tests, or comments.
- **Demo/prototype files** → `prototype/` only. They are concept validation
  and are not part of the shipped app.
- **Kiro config** → `.kiro/` only. Specs, steering, and hooks live here and
  are committed to the repo.
