"""screener.py — 8-gate engine for MemeScope.

Pure functions over the normalised token model dict (no print, no network,
no subprocess).  Each gate returns a dict with keys:
  name   : str          — human-readable gate name
  result : "PASS" | "FAIL" | "WARN"
  detail : str          — raw numbers that justify the result
  numbers: dict         — (optional) key metrics as typed values

Ported from ~/workspace/meme_watch/screen_strict.py with the following
adjustments:
  - No I/O: no print, no subprocess, no network calls.
  - Operates solely on the normalised token model (see design.md §2).
  - lp_locked_pct / lp_burned_pct / top1_holder_pct / top5_holder_pct
    are already percentage values (0–100) in the model; this module does
    NOT multiply them by 100 again (the sources layer already did that).
  - GoPlus None/"" == UNKNOWN → WARN (never FAIL). Only "1" fails.
  - One FAIL == GAGAL, no exceptions.
"""

from __future__ import annotations

import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Sentinel addresses
# ---------------------------------------------------------------------------
_ZERO = "0x0000000000000000000000000000000000000000"

# ---------------------------------------------------------------------------
# Gate weights for compute_score
# ---------------------------------------------------------------------------
_WEIGHTS: dict[int, int] = {
    1: 15,  # Market
    2: 20,  # GoPlus security
    3: 15,  # Owner renounced
    4: 20,  # LP lock/burn
    5: 10,  # Holder concentration
    6: 10,  # Reputation
    7: 5,   # Sell path
    8: 5,   # Survival
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gate(
    number: int,
    name: str,
    result: str,
    detail: str,
    numbers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a gate result dict."""
    out: dict[str, Any] = {
        "gate": number,
        "name": name,
        "result": result,
        "detail": detail,
    }
    if numbers is not None:
        out["numbers"] = numbers
    return out


def _goplus_flag(goplus: dict, key: str) -> bool | None:
    """Return True (safe), False (dangerous), or None (unknown) for a GoPlus flag.

    GoPlus uses string "1" for dangerous, "0" for safe, and None/"" for
    not-yet-analysed (UNKNOWN).  UNKNOWN maps to None so the caller can
    treat it as WARN rather than FAIL.
    """
    v = goplus.get(key)
    if v is None or v == "":
        return None   # UNKNOWN
    return v != "1"   # True == safe, False == dangerous


def _parse_tax(goplus: dict, key: str) -> float | None:
    """Parse a GoPlus tax field to float, returning None if unavailable."""
    v = goplus.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Gate 1 — Market (DexScreener)
# ---------------------------------------------------------------------------

def gate_market(model: dict) -> dict[str, Any]:
    """Gate 1: Market health from DexScreener data.

    PASS: liq >= $20k AND vol24 >= $5k AND buys_1h > sells_1h AND age >= 6h
    FAIL: any condition not met
    """
    liq: float = model.get("liquidity_usd") or 0.0
    vol24: float = model.get("volume_24h") or 0.0
    buys: int = model.get("buys_1h") or 0
    sells: int = model.get("sells_1h") or 0
    age: float = model.get("pair_age_hours") or 0.0
    change_6h = model.get("change_6h")

    cond_liq = liq >= 20_000
    cond_vol = vol24 >= 5_000
    cond_buys = buys > sells
    cond_age = age >= 6

    detail = (
        f"liq ${liq:,.0f} | vol24 ${vol24:,.0f} | "
        f"buys {buys} vs sells {sells} | "
        f"age {age:.1f}h | change_6h {change_6h}%"
    )
    numbers = {
        "liquidity_usd": liq,
        "volume_24h": vol24,
        "buys_1h": buys,
        "sells_1h": sells,
        "pair_age_hours": age,
        "change_6h": change_6h,
    }

    result = "PASS" if (cond_liq and cond_vol and cond_buys and cond_age) else "FAIL"
    return _gate(1, "Market", result, detail, numbers)


# ---------------------------------------------------------------------------
# Gate 2 — GoPlus security
# ---------------------------------------------------------------------------

def gate_goplus(model: dict) -> dict[str, Any]:
    """Gate 2: GoPlus token security sub-checks.

    If the GoPlus result is absent/empty → FAIL (unverified token).
    For each sub-check: "1" = FAIL, None/"" = UNKNOWN (WARN), "0" = PASS.
    Any FAIL sub-check → gate FAIL.
    No FAIL but at least one UNKNOWN → gate WARN.
    All clean → gate PASS.
    """
    goplus: dict = model.get("goplus") or {}

    if not goplus:
        return _gate(
            2, "GoPlus security", "FAIL",
            "No GoPlus data — token unverified or not yet indexed",
        )

    # Boolean flag sub-checks (invert: "1" is bad → safe == (val != "1"))
    bool_checks = [
        "is_honeypot",
        "cannot_buy",
        "cannot_sell_all",
        "is_proxy",
        "hidden_owner",
        "selfdestruct",
        "owner_change_balance",
        "is_mintable",
    ]

    sub_results: list[tuple[str, bool | None, str]] = []

    for key in bool_checks:
        safe = _goplus_flag(goplus, key)   # True=safe / False=dangerous / None=unknown
        raw = goplus.get(key)
        sub_results.append((key, safe, f"{key}={raw!r}"))

    # Tax sub-check
    buy_tax = _parse_tax(goplus, "buy_tax")
    sell_tax = _parse_tax(goplus, "sell_tax")
    if buy_tax is None or sell_tax is None:
        tax_safe: bool | None = None
    else:
        tax_safe = buy_tax <= 5.0 and sell_tax <= 5.0
    sub_results.append((
        "tax_lte_5pct",
        tax_safe,
        f"buy_tax={goplus.get('buy_tax')!r} sell_tax={goplus.get('sell_tax')!r}",
    ))

    any_fail = any(safe is False for _, safe, _ in sub_results)
    any_unknown = any(safe is None for _, safe, _ in sub_results)

    fail_details = [det for _, safe, det in sub_results if safe is False]
    unknown_details = [det for _, safe, det in sub_results if safe is None]

    if any_fail:
        result = "FAIL"
        detail_parts = ["FAIL: " + ", ".join(fail_details)]
        if unknown_details:
            detail_parts.append("UNKNOWN: " + ", ".join(unknown_details))
        detail = "; ".join(detail_parts)
    elif any_unknown:
        result = "WARN"
        detail = "UNKNOWN (not yet analysed): " + ", ".join(unknown_details)
    else:
        result = "PASS"
        detail = "All security sub-checks clean"

    numbers = {
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
    }
    return _gate(2, "GoPlus security", result, detail, numbers)


# ---------------------------------------------------------------------------
# Gate 3 — Owner renounced
# ---------------------------------------------------------------------------

def gate_owner_renounced(model: dict) -> dict[str, Any]:
    """Gate 3: Owner address must be zero / empty (renounced).

    PASS: owner == 0x0 or "" or None
    FAIL: owner is a live address
    WARN: no GoPlus data to check
    """
    goplus: dict = model.get("goplus") or {}

    if not goplus:
        return _gate(
            3, "Owner renounced", "WARN",
            "No GoPlus data — cannot verify owner address",
        )

    owner: str = (goplus.get("owner_address") or "").strip().lower()
    is_renounced = owner in ("", "0x", _ZERO.lower())

    detail = f"owner={goplus.get('owner_address')!r}"
    result = "PASS" if is_renounced else "FAIL"
    numbers = {"owner_address": goplus.get("owner_address")}
    return _gate(3, "Owner renounced", result, detail, numbers)


# ---------------------------------------------------------------------------
# Gate 4 — LP lock/burn
# ---------------------------------------------------------------------------

def gate_lp_lock(model: dict) -> dict[str, Any]:
    """Gate 4: LP tokens must be locked and/or burned.

    PASS: (locked_pct + burned_pct >= 95) AND (burned > 0 OR any lock ends > 90 days)
    FAIL: condition not met
    lp_locked_pct and lp_burned_pct are already 0–100 in the model.
    lp_lock_ends is a list of ISO datetime strings.
    """
    locked_pct: float = model.get("lp_locked_pct") or 0.0
    burned_pct: float = model.get("lp_burned_pct") or 0.0
    lock_ends: list[str] = model.get("lp_lock_ends") or []

    total_secured = locked_pct + burned_pct
    cond_total = total_secured >= 95.0
    cond_burn = burned_pct > 0

    # Check if any lock ends > 90 days from now (UTC)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cond_long_lock = False
    valid_ends: list[str] = []
    for end_str in lock_ends:
        if not end_str:
            continue
        try:
            end_dt = datetime.datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            # Ensure tz-aware for comparison
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
            days_left = (end_dt - now_utc).days
            valid_ends.append(f"{end_str} ({days_left}d)")
            if days_left > 90:
                cond_long_lock = True
        except (ValueError, OverflowError):
            valid_ends.append(f"{end_str} (unparseable)")

    cond_duration = cond_burn or cond_long_lock

    detail = (
        f"locked {locked_pct:.1f}% | burned {burned_pct:.1f}% | "
        f"total secured {total_secured:.1f}% | lock ends: {valid_ends or 'none'}"
    )
    numbers = {
        "lp_locked_pct": locked_pct,
        "lp_burned_pct": burned_pct,
        "total_secured_pct": total_secured,
        "long_lock": cond_long_lock,
    }

    result = "PASS" if (cond_total and cond_duration) else "FAIL"
    return _gate(4, "LP lock/burn", result, detail, numbers)


# ---------------------------------------------------------------------------
# Gate 5 — Holder concentration
# ---------------------------------------------------------------------------

def gate_holder_concentration(model: dict) -> dict[str, Any]:
    """Gate 5: No single or small group of holders dominates supply.

    PASS: top1_holder_pct < 5 AND top5_holder_pct < 15
    FAIL: either condition not met
    WARN: no holder data available (both zero and no GoPlus data)
    top1/top5 are already percentages 0–100 in the model.
    """
    top1: float = model.get("top1_holder_pct") or 0.0
    top5: float = model.get("top5_holder_pct") or 0.0
    goplus: dict = model.get("goplus") or {}

    # WARN when both are zero and there is no GoPlus data to trust
    no_data = top1 == 0.0 and top5 == 0.0 and not goplus
    if no_data:
        return _gate(
            5, "Holder concentration", "WARN",
            "No holder data available",
        )

    cond_top1 = top1 < 5.0
    cond_top5 = top5 < 15.0

    detail = f"top1 {top1:.2f}% | top5 {top5:.2f}%"
    numbers = {"top1_holder_pct": top1, "top5_holder_pct": top5}
    result = "PASS" if (cond_top1 and cond_top5) else "FAIL"
    return _gate(5, "Holder concentration", result, detail, numbers)


# ---------------------------------------------------------------------------
# Gate 6 — Reputation
# ---------------------------------------------------------------------------

_CRIME_FLAGS = (
    "cybercrime",
    "phishing_activities",
    "money_laundering",
    "honeypot_related_address",
)


def _check_reputation(rep: dict | None, label: str) -> tuple[str, str]:
    """Return (result, detail) for one address reputation dict.

    Reputation dicts come from GoPlus /address_security endpoint and are
    stored in model["owner_reputation"] / model["creator_reputation"].
    """
    if rep is None:
        return "WARN", f"{label}: no reputation data"

    malicious = int(rep.get("number_of_malicious_contracts_created") or 0)
    flags = [k for k in _CRIME_FLAGS if str(rep.get(k)) == "1"]

    if malicious > 0 or flags:
        return "FAIL", (
            f"{label}: malicious_contracts={malicious}"
            + (f" flags={flags}" if flags else "")
        )
    return "PASS", f"{label}: clean (malicious_contracts=0, no crime flags)"


def gate_reputation(model: dict) -> dict[str, Any]:
    """Gate 6: Owner and creator must have clean reputation records.

    FAIL if either has malicious contracts or known crime flags.
    WARN if reputation data is unavailable.
    PASS if both are clean.
    """
    owner_rep: dict | None = model.get("owner_reputation")
    creator_rep: dict | None = model.get("creator_reputation")

    owner_result, owner_detail = _check_reputation(owner_rep, "owner")
    creator_result, creator_detail = _check_reputation(creator_rep, "creator")

    detail = owner_detail + " | " + creator_detail

    if owner_result == "FAIL" or creator_result == "FAIL":
        result = "FAIL"
    elif owner_result == "WARN" or creator_result == "WARN":
        result = "WARN"
    else:
        result = "PASS"

    numbers = {
        "owner_malicious": int((owner_rep or {}).get("number_of_malicious_contracts_created") or 0),
        "creator_malicious": int((creator_rep or {}).get("number_of_malicious_contracts_created") or 0),
    }
    return _gate(6, "Reputation", result, detail, numbers)


# ---------------------------------------------------------------------------
# Gate 7 — Sell path
# ---------------------------------------------------------------------------

def gate_sell_path(model: dict) -> dict[str, Any]:
    """Gate 7: Selling $1 of token must return >= $0.50 USD equivalent.

    sell_quote_usd is the USD value received when selling $1 of token.

    PASS: sell_quote_usd >= 0.50
    WARN: sell_quote_usd < 0.50 but liq >= $1,000 (router limitation, not rug)
    WARN: sell_quote_usd is None but liq >= $1,000
    FAIL: sell_quote_usd < 0.50 and liq < $1,000
    FAIL: sell_quote_usd is None and liq < $1,000
    """
    quote: float | None = model.get("sell_quote_usd")
    liq: float = model.get("liquidity_usd") or 0.0

    numbers = {"sell_quote_usd": quote, "liquidity_usd": liq}

    if quote is not None:
        if quote >= 0.50:
            detail = f"sell $1 → ${quote:.2f} received"
            return _gate(7, "Sell path", "PASS", detail, numbers)
        # quote is set but below threshold
        if liq >= 1_000:
            detail = (
                f"sell $1 → ${quote:.2f} received (below $0.50 threshold); "
                f"liquidity ${liq:,.0f} present — possible router limitation; "
                "verify on-chain"
            )
            return _gate(7, "Sell path", "WARN", detail, numbers)
        detail = (
            f"sell $1 → ${quote:.2f} received (below $0.50 threshold); "
            f"liquidity ${liq:,.0f} — no viable sell path"
        )
        return _gate(7, "Sell path", "FAIL", detail, numbers)

    # quote is None
    if liq >= 1_000:
        detail = (
            f"sell quote unavailable; liquidity ${liq:,.0f} present — "
            "possible router limitation; verify on PancakeSwap directly"
        )
        return _gate(7, "Sell path", "WARN", detail, numbers)
    detail = (
        f"sell quote unavailable; liquidity ${liq:,.0f} — no viable sell path"
    )
    return _gate(7, "Sell path", "FAIL", detail, numbers)


# ---------------------------------------------------------------------------
# Gate 8 — Survival
# ---------------------------------------------------------------------------

def gate_survival(model: dict) -> dict[str, Any]:
    """Gate 8: Token must not be in free-fall over the past 6 hours.

    PASS: change_6h > -50%
    FAIL: change_6h <= -50%
    WARN: change_6h is None (data unavailable)
    """
    change_6h = model.get("change_6h")
    numbers = {"change_6h": change_6h}

    if change_6h is None:
        return _gate(
            8, "Survival", "WARN",
            "6h price change unavailable",
            numbers,
        )

    try:
        chg = float(change_6h)
    except (TypeError, ValueError):
        return _gate(
            8, "Survival", "WARN",
            f"6h price change could not be parsed: {change_6h!r}",
            numbers,
        )

    detail = f"6h change {chg:.2f}%"
    result = "PASS" if chg > -50 else "FAIL"
    return _gate(8, "Survival", result, detail, numbers)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_all_gates(model: dict) -> list[dict]:
    """Run all 8 gates against the normalised token model.

    Returns a list of 8 gate result dicts in gate order (1–8).
    """
    return [
        gate_market(model),
        gate_goplus(model),
        gate_owner_renounced(model),
        gate_lp_lock(model),
        gate_holder_concentration(model),
        gate_reputation(model),
        gate_sell_path(model),
        gate_survival(model),
    ]


def compute_score(gate_results: list[dict]) -> int:
    """Compute the 0–100 score from gate results.

    Weights: Market 15, GoPlus 20, Owner 15, LP 20, Holders 10,
             Reputation 10, Sell path 5, Survival 5.
    PASS = full weight, WARN = half weight (floor), FAIL = 0.
    """
    score = 0
    for gate_result in gate_results:
        gate_num: int = gate_result["gate"]
        weight = _WEIGHTS.get(gate_num, 0)
        result = gate_result["result"]
        if result == "PASS":
            score += weight
        elif result == "WARN":
            score += weight // 2
        # FAIL contributes 0
    return score


def compute_verdict(gate_results: list[dict]) -> str:
    """Return "GAGAL" if any gate FAILed, otherwise "LOLOS".

    One FAIL = GAGAL. No exceptions, no score overrides.
    """
    for gate_result in gate_results:
        if gate_result["result"] == "FAIL":
            return "GAGAL"
    return "LOLOS"
