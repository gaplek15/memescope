"""
CoinMarketCap client for MemeScope.

Fetches the latest market quote for a token by its contract address.
Key is read exclusively from the CMC_API_KEY environment variable —
it is never written into this file or any other file.

Hardcoded API key → never.  If you need to run against the sandbox,
set CMC_API_KEY to a sandbox key and change CMC_BASE_URL.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

CMC_BASE_URL = "https://pro-api.coinmarketcap.com"

# Timeout for every HTTP call, in seconds (REQ-33: 60 s total; allow 20 per step).
_REQUEST_TIMEOUT = 20


def _get_key() -> Optional[str]:
    """Return the CMC API key from the environment, or None if absent."""
    return os.environ.get("CMC_API_KEY") or None


def _make_request(url: str, key: str) -> Optional[dict]:
    """
    Perform a single GET request to the CMC API.

    Returns the parsed JSON body, or None when the HTTP status indicates
    the token is not listed (400, 404) or when any error occurs.
    Does NOT retry — the caller is responsible for retrying.
    """
    req = urllib.request.Request(
        url,
        headers={"X-CMC_PRO_API_KEY": key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):
            # Token not listed — treat as a normal "not found", not an error.
            return None
        # 429 rate-limit and other HTTP errors bubble up so the caller can retry.
        raise
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"CMC request failed: {exc}") from exc


def _request_with_retry(url: str, key: str) -> Optional[dict]:
    """
    Call _make_request; retry once on network/transient errors (REQ-32).

    Returns the parsed JSON body or None (token not listed).
    On both attempts failing, logs to stderr and returns None.
    """
    for attempt in range(2):
        try:
            return _make_request(url, key)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                return None
            if attempt == 0:
                # Brief back-off before the single retry (rate-limit or transient).
                time.sleep(1)
                continue
            print(
                f"[cmc] HTTP {exc.code} after retry, skipping CMC section.",
                file=sys.stderr,
            )
            return None
        except RuntimeError as exc:
            if attempt == 0:
                time.sleep(1)
                continue
            print(f"[cmc] {exc} — skipping CMC section.", file=sys.stderr)
            return None
    return None  # unreachable, but satisfies the type-checker


def _extract_first_entry(body: dict) -> Optional[dict]:
    """
    Pull the first token entry out of the CMC quotes/latest response body.

    The v2 endpoint keyed by address returns:
        { "data": { "<cmc_id>": { ... } }, "status": { ... } }
    """
    data = body.get("data") if isinstance(body, dict) else None
    if not data:
        return None
    # `data` is a dict of one or more CMC-id → token-info mappings.
    first_id = next(iter(data), None)
    if first_id is None:
        return None
    return data[first_id]


def _normalise(entry: dict) -> Optional[dict]:
    """
    Map a raw CMC token entry to the flat dict the screener expects.

    Returns None when the entry is malformed or missing required fields.
    """
    try:
        quote_usd = entry["quote"]["USD"]
        return {
            "price": float(quote_usd.get("price") or 0),
            "market_cap": _float_or_none(quote_usd.get("market_cap")),
            "volume_24h": _float_or_none(quote_usd.get("volume_24h")),
            "percent_change_24h": _float_or_none(quote_usd.get("percent_change_24h")),
            "cmc_rank": _int_or_none(entry.get("cmc_rank")),
            "name": str(entry.get("name") or ""),
            "symbol": str(entry.get("symbol") or ""),
        }
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[cmc] Unexpected response shape: {exc}", file=sys.stderr)
        return None


def _float_or_none(value: object) -> Optional[float]:
    """Return float(value) or None when value is None / falsy."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> Optional[int]:
    """Return int(value) or None when value is None / falsy."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_quote(token_address: str, chain_id: int = 56) -> Optional[dict]:
    """
    Fetch the latest market quote for a token from CoinMarketCap.

    Steps:
    1. Read the API key from CMC_API_KEY.  No key → return None immediately.
    2. Query /v2/cryptocurrency/quotes/latest?address=<token_address>&convert=USD.
    3. On 400/404 (token not listed) → return None gracefully.
    4. Retry once on network or transient server errors (REQ-32).
    5. On both attempts failing → log to stderr, return None.

    Returns a dict on success:
        {
            "price":               float,
            "market_cap":          float | None,
            "volume_24h":          float | None,
            "percent_change_24h":  float | None,
            "cmc_rank":            int   | None,
            "name":                str,
            "symbol":              str,
        }

    Returns None when: key is absent, token not listed, or API error.
    The chain_id parameter is accepted for API compatibility but not used in
    the CMC v2 address lookup (CMC resolves the chain internally).
    """
    key = _get_key()
    if not key:
        # No key — degrade silently; screening continues without CMC data (REQ-06).
        return None

    # Primary lookup: by contract address (v2 endpoint).
    url = (
        f"{CMC_BASE_URL}/v2/cryptocurrency/quotes/latest"
        f"?address={token_address}&convert=USD"
    )
    body = _request_with_retry(url, key)
    if body is None:
        return None

    entry = _extract_first_entry(body)
    if entry is None:
        return None

    return _normalise(entry)
