#!/usr/bin/env python3
"""demo_screen.py — MemeScope prototype (concept validation, pre-Kiro).

Demonstrates the full screening flow for ONE example token using CANNED
data from the four sources (no network calls), so the concept can be
validated anywhere. The 8 gates here are the real gate logic, ported from
~/workspace/meme_watch/screen_strict.py and simplified to run over a
normalised token model — exactly as specified in
.kiro/specs/memescope/design.md.

Usage: python3 prototype/demo_screen.py [--fail-gate N]
  --fail-gate N  : force gate N to fail, to demo the GAGAL verdict.
"""
import argparse
import json

# ---------------------------------------------------------------------------
# Canned data from the four sources (example token: a BSC meme token that
# passes all gates in the default demo).
# ---------------------------------------------------------------------------
EXAMPLE_TOKEN = "0x1111111111111111111111111111111111111111"

CANNED_DEXSCREENER = {
    "pairAddress": "0x2222222222222222222222222222222222222222",
    "dexId": "pancakeswap",
    "liquidity": {"usd": 85400.0},
    "volume": {"h24": 31200.0},
    "txns": {"h1": {"buys": 42, "sells": 18}},
    "pairCreatedAt": 1763000000000,  # ~14 days before the demo date
    "priceUsd": "0.00001234",
    "priceChange": {"h6": -12.5},
}

CANNED_CMC = {
    "price": 0.00001234,
    "market_cap": 1234000.0,
    "volume_24h": 31200.0,
    "percent_change_24h": -8.2,
    "cmc_rank": 2841,
}

CANNED_GOPLUS = {
    "is_honeypot": "0",
    "cannot_buy": "0",
    "cannot_sell_all": "0",
    "buy_tax": "0",
    "sell_tax": "0",
    "is_proxy": "0",
    "hidden_owner": "0",
    "selfdestruct": "0",
    "owner_change_balance": "0",
    "is_mintable": "0",
    "transfer_pausable": "0",
    "is_blacklisted": "0",
    "slippage_modifiable": "0",
    "can_take_back_ownership": "0",
    "owner_address": "0x0000000000000000000000000000000000000000",
    "creator_address": "0x3333333333333333333333333333333333333333",
    "holder_count": 1842,
    "is_open_source": "1",
    # GoPlus `percent` is a FRACTION 0-1, not 0-100.
    "lp_holders": [
        {"is_locked": "1", "percent": 0.97,
         "locked_detail": [{"end_time": "2027-06-01T00:00:00Z"}]},
        {"is_locked": "0", "percent": 0.03},
    ],
    "holders": [
        {"is_locked": "0", "is_contract": "0", "percent": 0.021},
        {"is_locked": "0", "is_contract": "0", "percent": 0.018},
        {"is_locked": "0", "is_contract": "0", "percent": 0.015},
        {"is_locked": "0", "is_contract": "0", "percent": 0.012},
        {"is_locked": "0", "is_contract": "0", "percent": 0.010},
    ],
}

CANNED_ONCHAIN = {
    "lp_total_supply": 1000000,
    "lp_dead_balance": 0,          # 0% burned on-chain in this example
    "lock_end_days_out": 190,
}

CANNED_QUOTE = {"sell_1_usd_returns_usd": 0.94}

GATE_WEIGHTS = {
    "market": 15, "goplus": 20, "owner": 15, "lp": 20,
    "holders": 10, "reputation": 10, "sell_path": 5, "survival": 5,
}


def normalise():
    """Stitch the four sources into the single normalised token model."""
    import datetime
    age_h = (1764300000000 - CANNED_DEXSCREENER["pairCreatedAt"]) / 3_600_000
    g = CANNED_GOPLUS
    locked_pct = sum(float(x["percent"]) * 100
                     for x in g["lp_holders"] if x["is_locked"] == "1")
    burn_pct = (CANNED_ONCHAIN["lp_dead_balance"]
                / CANNED_ONCHAIN["lp_total_supply"] * 100)
    real = [h for h in g["holders"]
            if h["is_locked"] != "1" and h["is_contract"] != "1"]
    pcts = sorted((float(h["percent"]) * 100 for h in real), reverse=True)
    return {
        "address": EXAMPLE_TOKEN,
        "chain_id": 56,
        "name": "ExampleMeme", "symbol": "EXM",
        "price_usd": float(CANNED_DEXSCREENER["priceUsd"]),
        "market_cap": CANNED_CMC["market_cap"],
        "liquidity_usd": CANNED_DEXSCREENER["liquidity"]["usd"],
        "volume_24h": CANNED_DEXSCREENER["volume"]["h24"],
        "buys_1h": CANNED_DEXSCREENER["txns"]["h1"]["buys"],
        "sells_1h": CANNED_DEXSCREENER["txns"]["h1"]["sells"],
        "pair_age_hours": age_h,
        "change_6h": CANNED_DEXSCREENER["priceChange"]["h6"],
        "pair_address": CANNED_DEXSCREENER["pairAddress"],
        "dex": CANNED_DEXSCREENER["dexId"],
        "goplus": g,
        "lp_locked_pct": locked_pct,
        "lp_burned_pct": burn_pct,
        "top1_holder_pct": pcts[0] if pcts else 0,
        "top5_holder_pct": sum(pcts[:5]),
        "owner": g["owner_address"],
        "creator": g["creator_address"],
        "sell_quote_usd": CANNED_QUOTE["sell_1_usd_returns_usd"],
    }


def run_gates(m, force_fail=None):
    """The 8 strict gates. Returns list of (name, result, detail).
    result: 'PASS' | 'FAIL' | 'WARN'."""
    g = m["goplus"]
    gates = []

    def add(name, ok, detail):
        if force_fail == len(gates) + 1:
            ok = False
            detail += "  [demo: forced fail]"
        gates.append((name, "PASS" if ok is True else "FAIL" if ok is False
                      else "WARN", detail))

    # 1. Market
    ok = (m["liquidity_usd"] >= 20000 and m["volume_24h"] >= 5000
          and m["buys_1h"] > m["sells_1h"] and m["pair_age_hours"] >= 6)
    add("1. Market", ok, f"liq ${m['liquidity_usd']:,.0f} | vol24 "
        f"${m['volume_24h']:,.0f} | buy {m['buys_1h']} vs sell {m['sells_1h']} "
        f"| age {m['pair_age_hours']:.0f}h")

    # 2. GoPlus security
    def bad(k):
        return g.get(k) == "1"
    sub = [
        ("honeypot", not bad("is_honeypot")),
        ("can buy", not bad("cannot_buy")),
        ("can sell all", not bad("cannot_sell_all")),
        ("tax <=5%", float(g["buy_tax"]) <= 5 and float(g["sell_tax"]) <= 5),
        ("not proxy", not bad("is_proxy")),
        ("no hidden owner", not bad("hidden_owner")),
        ("no selfdestruct", not bad("selfdestruct")),
        ("owner can't change balance", not bad("owner_change_balance")),
        ("not mintable", not bad("is_mintable")),
    ]
    failed_sub = [n for n, v in sub if not v]
    add("2. GoPlus security", not failed_sub,
        "all clean" if not failed_sub else f"dirty: {', '.join(failed_sub)}")

    # 3. Owner renounced
    add("3. Owner renounced",
        m["owner"].lower() in ("0x0000000000000000000000000000000000000000", ""),
        f"owner={m['owner']}")

    # 4. LP lock/burn
    lp_ok = ((m["lp_locked_pct"] + m["lp_burned_pct"]) >= 95
             and (m["lp_burned_pct"] > 0
                  or CANNED_ONCHAIN["lock_end_days_out"] > 90))
    add("4. LP lock/burn", lp_ok,
        f"locked {m['lp_locked_pct']:.0f}% | burned {m['lp_burned_pct']:.0f}% "
        f"| lock ends in {CANNED_ONCHAIN['lock_end_days_out']} days")

    # 5. Holder concentration
    add("5. Holder concentration",
        m["top1_holder_pct"] < 5 and m["top5_holder_pct"] < 15,
        f"top1 {m['top1_holder_pct']:.2f}% | top5 {m['top5_holder_pct']:.2f}% "
        f"| holders {g['holder_count']}")

    # 6. Reputation (canned: creator has 0 malicious contracts, no flags)
    add("6. Reputation", True,
        f"creator {m['creator'][:14]}... malicious=0 flags=[] (canned)")

    # 7. Sell path
    q = m["sell_quote_usd"]
    if q is None:
        add("7. Sell path", None, "quote unavailable")
    elif q >= 0.50:
        add("7. Sell path", True, f"sell $1 -> ${q:.2f}")
    elif m["liquidity_usd"] >= 1000:
        add("7. Sell path", None,
            f"quote failed but liq ${m['liquidity_usd']:,.0f} — verify on DEX")
    else:
        add("7. Sell path", False, f"sell $1 -> ${q:.2f}")

    # 8. Survival
    add("8. Survival", m["change_6h"] > -50, f"6h change {m['change_6h']}%")

    return gates


def score_and_verdict(gates):
    keys = ["market", "goplus", "owner", "lp",
            "holders", "reputation", "sell_path", "survival"]
    total = 0
    for (name, result, _), key in zip(gates, keys):
        w = GATE_WEIGHTS[key]
        if result == "PASS":
            total += w
        elif result == "WARN":
            total += w // 2
    verdict = "GAGAL" if any(r == "FAIL" for _, r, _ in gates) else "LOLOS"
    return total, verdict


def narrative(gates, verdict):
    failed = [n for n, r, _ in gates if r == "FAIL"]
    if failed:
        return (f"Risiko terbesar: {failed[0]} gagal. "
                "Token ini tidak lolos screening ketat — perlakukan sebagai "
                "lotre, bukan pick hasil screening.")
    return ("Semua 8 gate lolos dan tidak ada jebakan mekanis yang terdeteksi. "
            "Tetap ingat: kontrak yang bersih tidak bisa memprediksi keputusan "
            "deployer di masa depan. Anggap uang yang masuk sebagai uang yang "
            "siap hilang.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail-gate", type=int, default=None,
                    help="force gate N to fail (demo the GAGAL verdict)")
    args = ap.parse_args()

    print("=== MemeScope prototype — screening demo (canned data, no network) ===")
    print(f"Token: {EXAMPLE_TOKEN} (ExampleMeme / EXM, BSC)")
    print("Sources: CoinMarketCap + GoPlus + DexScreener + on-chain RPC")
    print("-" * 70)
    m = normalise()
    gates = run_gates(m, force_fail=args.fail_gate)
    for name, result, detail in gates:
        print(f"[{result}] {name}: {detail}")
    score, verdict = score_and_verdict(gates)
    print("-" * 70)
    print(f"SCORE: {score}/100   VERDICT: {verdict}")
    print(f"NARRATIVE: {narrative(gates, verdict)}")
    print("-" * 70)
    print("Disclaimer: LOLOS bukan jaminan aman. Jangan beli berdasarkan "
          "laporan ini saja.")
    report = {
        "token": m["address"], "name": m["name"], "symbol": m["symbol"],
        "score": score, "verdict": verdict,
        "gates": [{"name": n, "result": r, "detail": d}
                  for n, r, d in gates],
        "narrative": narrative(gates, verdict),
    }
    with open("prototype/demo_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Report JSON saved to prototype/demo_report.json")


if __name__ == "__main__":
    main()
