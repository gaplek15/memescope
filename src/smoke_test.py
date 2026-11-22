#!/usr/bin/env python3
"""smoke_test.py — Task 19: Live end-to-end smoke test.

Screens one real BSC token (CAKE) directly via the pipeline components
(no HTTP server).  Asserts that all 8 gates return a valid result
(PASS / FAIL / WARN) and that no exception escapes.

Exit 0 on success, exit 1 on assertion failure.
"""

import sys
import os

# Allow running from the workspace root or from src/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Test target
# ---------------------------------------------------------------------------

CAKE_ADDRESS = "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
CHAIN_ID = 56

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from sources.dexscreener import fetch_pair, normalise_pair
from sources.goplus import (
    fetch_token_security,
    fetch_address_security,
    compute_lp_stats,
    compute_holder_stats,
)
from sources.onchain import burn_percent
from sources.cmc import fetch_quote        # returns None without CMC_API_KEY
from sources.quote import get_sell_quote_usd
from screener import run_all_gates, compute_score, compute_verdict
from narrative import generate_narrative

_ZERO = "0x0000000000000000000000000000000000000000"
_VALID_RESULTS = {"PASS", "FAIL", "WARN"}


def _log(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_model(address: str, chain_id: int = 56) -> dict:
    """Build the normalised token model from live sources.

    Mirrors server.screen_token() but without the HTTP layer.
    Every source failure is caught and degraded to None / defaults.
    """
    # --- DexScreener (required for Gate 1 / 8) ---
    pair_raw = fetch_pair(address)
    if not pair_raw:
        print(f"[smoke] WARN: DexScreener returned no pair for {address}", file=sys.stderr)
        pair = {
            "pair_address": "", "dex": "", "liquidity_usd": 0.0,
            "volume_24h": 0.0, "buys_1h": 0, "sells_1h": 0,
            "pair_age_hours": 0.0, "change_6h": None,
            "price_usd": 0.0, "name": "", "symbol": "",
        }
    else:
        pair = normalise_pair(pair_raw)

    # --- CoinMarketCap (optional; None without CMC_API_KEY) ---
    cmc = None
    try:
        cmc = fetch_quote(address, chain_id)
    except Exception as exc:
        _log(f"CMC degraded: {exc}")

    # --- GoPlus token security (Gates 2–6) ---
    gp_token = None
    try:
        gp_token = fetch_token_security(address, chain_id)
    except Exception as exc:
        _log(f"GoPlus token security degraded: {exc}")

    # --- On-chain LP burn percent (Gate 4) ---
    lp_burn_pct = 0.0
    if gp_token and pair.get("pair_address"):
        try:
            lp_burn_pct = burn_percent(pair["pair_address"])
        except Exception as exc:
            _log(f"on-chain burn_percent degraded: {exc}")

    # --- LP lock / holder stats (Gates 4, 5) ---
    lp_stats = {"lp_locked_pct": 0.0, "lp_lock_ends": []}
    holder_stats = {"top1_holder_pct": 0.0, "top5_holder_pct": 0.0}
    if gp_token:
        try:
            lp_stats = compute_lp_stats(gp_token)
        except Exception as exc:
            _log(f"compute_lp_stats degraded: {exc}")
        try:
            holder_stats = compute_holder_stats(gp_token)
        except Exception as exc:
            _log(f"compute_holder_stats degraded: {exc}")

    # --- GoPlus address security for owner / creator (Gate 6) ---
    owner_addr = (gp_token or {}).get("owner_address", "")
    creator_addr = (gp_token or {}).get("creator_address", "")
    owner_rep = None
    creator_rep = None
    if owner_addr and owner_addr.lower() not in ("", _ZERO.lower()):
        try:
            owner_rep = fetch_address_security(owner_addr, chain_id)
        except Exception as exc:
            _log(f"GoPlus owner address security degraded: {exc}")
    if creator_addr and creator_addr.lower() not in ("", _ZERO.lower()):
        try:
            creator_rep = fetch_address_security(creator_addr, chain_id)
        except Exception as exc:
            _log(f"GoPlus creator address security degraded: {exc}")

    # --- Reverse sell quote (Gate 7) ---
    sell_quote = None
    try:
        sell_quote = get_sell_quote_usd(
            address,
            pair.get("price_usd", 0.0),
            pair.get("liquidity_usd", 0.0),
        )
    except Exception as exc:
        _log(f"sell quote degraded: {exc}")

    # --- Assemble normalised token model ---
    return {
        "address": address,
        "chain_id": chain_id,
        "name": pair.get("name") or (cmc or {}).get("name") or "",
        "symbol": pair.get("symbol") or (cmc or {}).get("symbol") or "",
        "price_usd": pair.get("price_usd", 0.0),
        "market_cap": (cmc or {}).get("market_cap"),
        "liquidity_usd": pair.get("liquidity_usd", 0.0),
        "volume_24h": pair.get("volume_24h", 0.0),
        "buys_1h": pair.get("buys_1h", 0),
        "sells_1h": pair.get("sells_1h", 0),
        "pair_age_hours": pair.get("pair_age_hours", 0.0),
        "change_6h": pair.get("change_6h"),
        "pair_address": pair.get("pair_address", ""),
        "dex": pair.get("dex", ""),
        "goplus": gp_token or {},
        "lp_locked_pct": lp_stats["lp_locked_pct"],
        "lp_burned_pct": lp_burn_pct,
        "lp_lock_ends": lp_stats["lp_lock_ends"],
        "top1_holder_pct": holder_stats["top1_holder_pct"],
        "top5_holder_pct": holder_stats["top5_holder_pct"],
        "owner": owner_addr,
        "creator": creator_addr,
        "owner_reputation": owner_rep,
        "creator_reputation": creator_rep,
        "sell_quote_usd": sell_quote,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print(f"MemeScope smoke test — CAKE ({CAKE_ADDRESS})")
    print("=" * 60)

    # Build model
    print("\n[1/3] Fetching data from all sources…")
    model = build_model(CAKE_ADDRESS, CHAIN_ID)

    name = model.get("name") or "CAKE"
    symbol = model.get("symbol") or "CAKE"
    print(f"      Token: {name} ({symbol})")
    print(f"      Price: ${model.get('price_usd', 0):.4f}")
    print(f"      Liquidity: ${model.get('liquidity_usd', 0):,.0f}")
    mc = model.get("market_cap")
    cmc_str = "not listed (no API key)" if mc is None else f"${mc:,.0f}"
    print(f"      CMC: {cmc_str}")

    # Run gates
    print("\n[2/3] Running all 8 gates…")
    gates = run_all_gates(model)
    score = compute_score(gates)
    verdict = compute_verdict(gates)
    narrative = generate_narrative(gates, verdict, score, name, symbol)

    print("\n  Gate results:")
    print(f"  {'#':<4} {'Name':<24} {'Result':<6}  Detail")
    print(f"  {'-'*4} {'-'*24} {'-'*6}  {'-'*40}")
    for g in gates:
        print(f"  {g['gate']:<4} {g['name']:<24} {g['result']:<6}  {g['detail']}")

    print(f"\n  Score  : {score}/100")
    print(f"  Verdict: {verdict}")
    print(f"\n  Narrative:\n  {narrative}")

    # Assertions
    print("\n[3/3] Assertions…")
    failures: list[str] = []

    if len(gates) != 8:
        failures.append(f"Expected 8 gates, got {len(gates)}")

    for g in gates:
        r = g.get("result")
        if r not in _VALID_RESULTS:
            failures.append(
                f"Gate {g['gate']} ({g['name']}) has invalid result: {r!r}"
            )

    if failures:
        print("\n  ASSERTION FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\n[FAIL] Smoke test FAILED.\n")
        return 1

    print(f"  ✓ All {len(gates)} gates present")
    print(f"  ✓ All results are in {_VALID_RESULTS}")
    print(f"  ✓ Verdict is {verdict!r}")
    print(f"  ✓ Score is {score}/100")
    print(f"\n[PASS] Smoke test passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
