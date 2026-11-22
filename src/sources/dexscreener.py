"""dexscreener.py — DexScreener pairs client for MemeScope.

Provides two public functions:
  fetch_pair(token_address, pair_hint) -> dict | None
  normalise_pair(pair) -> dict

No third-party libraries; uses only the stdlib (urllib.request, json, time).

API notes (from docs/api-notes.md):
  Token endpoint: GET https://api.dexscreener.com/latest/dex/tokens/{address}
    Response: { "pairs": [...] | null }
    chainId == "bsc" for BSC pairs; sort by liquidity.usd descending.

  Pair endpoint (fallback): GET https://api.dexscreener.com/latest/dex/pairs/bsc/{pairAddress}
    Response: { "pairs": [...] | null }

  Fields used:
    liquidity.usd, volume.h24, txns.h1.buys/sells,
    pairCreatedAt (ms epoch), priceUsd, priceChange.h6,
    pairAddress, dexId, baseToken.{name,symbol}

Degrade, don't crash (tech.md hard rule 9):
  Any network error, non-200, or malformed JSON → return None, log to stderr.

Retry logic (REQ-32):
  Retry once after a short delay on network error or non-200.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.dexscreener.com/latest/dex"
_TIMEOUT = 25        # seconds per request
_RETRY_DELAY = 2.0   # seconds to wait before the single retry


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

def _get_json(url: str) -> Any:
    """Fetch *url* and return the parsed JSON body.

    Retries once after _RETRY_DELAY seconds on network error or non-200.
    Returns None (and logs to stderr) on any failure after the retry.
    """
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MemeScope/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(
                        url, resp.status, f"HTTP {resp.status}", {}, None
                    )
                body = resp.read()
                return json.loads(body)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            if attempt == 0:
                print(
                    f"[dexscreener] attempt 1 failed for {url}: {exc}; retrying…",
                    file=sys.stderr,
                )
                time.sleep(_RETRY_DELAY)
            else:
                print(
                    f"[dexscreener] attempt 2 failed for {url}: {exc}; giving up",
                    file=sys.stderr,
                )
                return None
        except (json.JSONDecodeError, ValueError) as exc:
            print(
                f"[dexscreener] malformed JSON from {url}: {exc}",
                file=sys.stderr,
            )
            return None
    return None  # unreachable, but satisfies type checkers


# ---------------------------------------------------------------------------
# Internal pair helpers
# ---------------------------------------------------------------------------

def _best_bsc_pair(pairs: list[dict]) -> dict | None:
    """Return the BSC pair with the highest liquidity.usd, or None."""
    bsc_pairs = [p for p in pairs if p.get("chainId") == "bsc"]
    if not bsc_pairs:
        return None

    def _liq(p: dict) -> float:
        try:
            return float((p.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    return max(bsc_pairs, key=_liq)


def _pairs_from_response(data: Any) -> list[dict]:
    """Extract the pairs list from a DexScreener response dict.

    Returns an empty list when pairs is absent, null, or not a list.
    """
    if not isinstance(data, dict):
        return []
    pairs = data.get("pairs")
    if not isinstance(pairs, list):
        return []
    return pairs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_pair(
    token_address: str,
    pair_hint: str | None = None,
) -> dict | None:
    """Fetch the best BSC pair for the given token address.

    Strategy:
    1. GET /tokens/{token_address}
       — Filter pairs where chainId == "bsc"
       — Sort by liquidity.usd descending
       — If at least one BSC pair found, return the best one
    2. If pairs is null/empty AND pair_hint is provided:
       GET /pairs/bsc/{pair_hint}
       — Return the first pair from the result
    3. If still no pair: return None

    Returns the raw DexScreener pair dict, or None.
    Retries once on network error or non-200 (REQ-32).
    Timeout: 25 seconds per request.
    """
    if not token_address:
        print("[dexscreener] fetch_pair called with empty token_address", file=sys.stderr)
        return None

    # Step 1 — token endpoint
    token_url = f"{_BASE_URL}/tokens/{token_address}"
    data = _get_json(token_url)
    if data is not None:
        pairs = _pairs_from_response(data)
        best = _best_bsc_pair(pairs)
        if best is not None:
            return best

    # Step 2 — pair-address fallback
    if pair_hint:
        pair_url = f"{_BASE_URL}/pairs/bsc/{pair_hint}"
        pair_data = _get_json(pair_url)
        if pair_data is not None:
            fallback_pairs = _pairs_from_response(pair_data)
            if fallback_pairs:
                return fallback_pairs[0]

    # Step 3 — no pair found
    return None


def normalise_pair(pair: dict) -> dict:
    """Extract the fields needed by the screener from a raw DexScreener pair.

    Returns:
    {
      "pair_address": str,
      "dex": str,              # e.g. "pancakeswap"
      "liquidity_usd": float,
      "volume_24h": float,
      "buys_1h": int,
      "sells_1h": int,
      "pair_age_hours": float,
      "change_6h": float | None,
      "price_usd": float,
      "name": str,             # baseToken.name
      "symbol": str,           # baseToken.symbol
    }

    Missing or malformed fields default to 0 / None, not exceptions.
    """
    # --- liquidity ---
    try:
        liquidity_usd = float((pair.get("liquidity") or {}).get("usd") or 0)
    except (TypeError, ValueError):
        liquidity_usd = 0.0

    # --- volume ---
    try:
        volume_24h = float((pair.get("volume") or {}).get("h24") or 0)
    except (TypeError, ValueError):
        volume_24h = 0.0

    # --- transaction counts ---
    txns_h1 = (pair.get("txns") or {}).get("h1") or {}
    try:
        buys_1h = int(txns_h1.get("buys") or 0)
    except (TypeError, ValueError):
        buys_1h = 0
    try:
        sells_1h = int(txns_h1.get("sells") or 0)
    except (TypeError, ValueError):
        sells_1h = 0

    # --- pair age ---
    try:
        created_at_ms = float(pair.get("pairCreatedAt") or 0)
        now_ms = time.time() * 1_000
        pair_age_hours = (now_ms - created_at_ms) / 3_600_000
        if pair_age_hours < 0:
            pair_age_hours = 0.0
    except (TypeError, ValueError):
        pair_age_hours = 0.0

    # --- 6h price change ---
    try:
        raw_change_6h = (pair.get("priceChange") or {}).get("h6")
        change_6h: float | None = float(raw_change_6h) if raw_change_6h is not None else None
    except (TypeError, ValueError):
        change_6h = None

    # --- price ---
    try:
        price_usd = float(pair.get("priceUsd") or 0)
    except (TypeError, ValueError):
        price_usd = 0.0

    # --- base token metadata ---
    base_token = pair.get("baseToken") or {}
    name: str = str(base_token.get("name") or "")
    symbol: str = str(base_token.get("symbol") or "")

    return {
        "pair_address": str(pair.get("pairAddress") or ""),
        "dex": str(pair.get("dexId") or ""),
        "liquidity_usd": liquidity_usd,
        "volume_24h": volume_24h,
        "buys_1h": buys_1h,
        "sells_1h": sells_1h,
        "pair_age_hours": pair_age_hours,
        "change_6h": change_6h,
        "price_usd": price_usd,
        "name": name,
        "symbol": symbol,
    }
