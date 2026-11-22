"""quote.py — Reverse sell-quote for Gate 7.

Simulates selling $1 worth of a token to WBNB via the PancakeSwap V2 router
getAmountsOut eth_call on BSC. No third-party libraries; stdlib only.

Public function:
    get_sell_quote_usd(token_address, price_usd, liquidity_usd, bnb_price_usd)
        -> float | None

Gate 7 verdict (caller's responsibility, but documented here for reference):
    >= 0.50 USD received   → PASS
    < 0.50 USD received    → WARN if liquidity_usd >= 1_000, else FAIL
    None (quote failed)    → WARN if liquidity_usd >= 1_000, else FAIL

Degrade, don't crash (tech.md hard rule 9):
    Any exception → return None, log to stderr.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BSC_RPC = "https://bsc-dataseed.bnbchain.org"
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
PANCAKE_ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# PancakeSwap V2 Router getAmountsOut(uint256,address[]) selector
_SEL_GET_AMOUNTS_OUT = "d06ca61f"

# BNB/BUSD pair on DexScreener — used to fetch a live BNB price
_BNB_BUSD_PAIR_URL = (
    "https://api.dexscreener.com/latest/dex/pairs/bsc/"
    "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16"
)
_BNB_PRICE_FALLBACK = 600.0

_TIMEOUT = 20  # seconds per RPC / HTTP call


# ---------------------------------------------------------------------------
# ABI encoding helpers
# ---------------------------------------------------------------------------

def _encode_uint256(value: int) -> str:
    """Encode a uint256 as a 64-hex-char (32-byte) big-endian string."""
    return format(value & (2**256 - 1), "064x")


def _encode_address(address: str) -> str:
    """Left-pad an EVM address to 32 bytes (64 hex chars), no 0x prefix."""
    addr = address.lower().removeprefix("0x")
    return addr.zfill(64)


def _encode_get_amounts_out(amount_in_wei: int, token_address: str) -> str:
    """ABI-encode getAmountsOut(amount_in_wei, [token_address, WBNB_ADDRESS]).

    Layout (excluding the 4-byte selector):
        amountIn  : uint256   (32 bytes)
        offset    : uint256   (32 bytes) = 0x40 (64 decimal — two slots ahead)
        length    : uint256   (32 bytes) = 2
        path[0]   : address   (32 bytes, left-padded)
        path[1]   : address   (32 bytes, left-padded)

    Returns the full calldata as a hex string with "0x" prefix.
    """
    selector = _SEL_GET_AMOUNTS_OUT
    amount_in = _encode_uint256(amount_in_wei)
    offset = _encode_uint256(0x40)          # array starts at byte 64
    length = _encode_uint256(2)
    path0 = _encode_address(token_address)
    path1 = _encode_address(WBNB_ADDRESS)
    return "0x" + selector + amount_in + offset + length + path0 + path1


# ---------------------------------------------------------------------------
# Low-level JSON-RPC eth_call
# ---------------------------------------------------------------------------

def _eth_call(to: str, data: str) -> str | None:
    """POST a JSON-RPC eth_call to BSC_RPC.

    Returns the hex result string on success, or None on any failure.
    Retries once on transient network errors.
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }).encode("utf-8")

    for attempt in range(2):
        try:
            req = urllib.request.Request(
                BSC_RPC,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            if "error" in body:
                print(
                    f"[quote] eth_call RPC error for {to}: {body['error']}",
                    file=sys.stderr,
                )
                return None

            return body.get("result")

        except (URLError, OSError, json.JSONDecodeError, KeyError) as exc:
            if attempt == 0:
                print(
                    f"[quote] eth_call attempt 1 failed for {to}: {exc}; retrying…",
                    file=sys.stderr,
                )
                continue
            print(
                f"[quote] eth_call failed for {to} after retry: {exc}",
                file=sys.stderr,
            )
            return None

    return None


# ---------------------------------------------------------------------------
# BNB price helper
# ---------------------------------------------------------------------------

def _fetch_bnb_price_usd() -> float:
    """Fetch the current BNB price in USD from DexScreener.

    DexScreener's ``priceUsd`` is always the price of the pair's BASE token,
    so blindly taking ``pairs[0].priceUsd`` is wrong when the base token is
    the stablecoin side (that returns ~$1.00 instead of ~$540).  This function
    therefore only accepts a pair whose base token IS WBNB, and falls back to
    CoinGecko's simple price endpoint before the hard-coded fallback.

    Returns a float, or _BNB_PRICE_FALLBACK if every fetch fails.
    """
    # 1. DexScreener token endpoint for WBNB — pick a BSC pair whose base
    #    token is WBNB so priceUsd is really the BNB price.
    try:
        req = urllib.request.Request(
            "https://api.dexscreener.com/latest/dex/tokens/" + WBNB_ADDRESS,
            headers={"User-Agent": "MemeScope/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        for pair in body.get("pairs") or []:
            if pair.get("chainId") != "bsc":
                continue
            base = (pair.get("baseToken") or {}).get("address", "")
            if base.lower() == WBNB_ADDRESS.lower():
                raw = pair.get("priceUsd")
                if raw is not None:
                    price = float(raw)
                    if price > 0:
                        return price
    except (URLError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[quote] BNB price fetch (tokens) failed: {exc}", file=sys.stderr)

    # 2. Same check on the known WBNB/BUSD pair endpoint.
    try:
        req = urllib.request.Request(
            _BNB_BUSD_PAIR_URL,
            headers={"User-Agent": "MemeScope/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        for pair in body.get("pairs") or []:
            base = (pair.get("baseToken") or {}).get("address", "")
            if base.lower() == WBNB_ADDRESS.lower():
                raw = pair.get("priceUsd")
                if raw is not None:
                    price = float(raw)
                    if price > 0:
                        return price
    except (URLError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[quote] BNB price fetch (pair) failed: {exc}", file=sys.stderr)

    # 3. CoinGecko simple price (same source screen_strict.py uses).
    try:
        req = urllib.request.Request(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=binancecoin&vs_currencies=usd",
            headers={"User-Agent": "MemeScope/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        price = float((body.get("binancecoin") or {}).get("usd") or 0)
        if price > 0:
            return price
    except (URLError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[quote] BNB price fetch (coingecko) failed: {exc}", file=sys.stderr)

    return _BNB_PRICE_FALLBACK


# ---------------------------------------------------------------------------
# ABI decoding helpers
# ---------------------------------------------------------------------------

def _decode_amounts_out(hex_result: str) -> int | None:
    """Decode the second element (amounts[1]) from a getAmountsOut return value.

    ABI-encoded return layout (each slot = 32 bytes = 64 hex chars):
        slot 0: offset to the array data   (0x20)
        slot 1: array length               (2)
        slot 2: amounts[0]                 (token in)
        slot 3: amounts[1]                 (WBNB out)  ← we want this

    Strip the "0x" prefix before slicing; expect at least 256 hex chars (4 slots).
    """
    try:
        raw = hex_result.removeprefix("0x")
        if len(raw) < 256:
            print(
                f"[quote] getAmountsOut response too short ({len(raw)} hex chars)",
                file=sys.stderr,
            )
            return None
        # slot 3 starts at offset 192 (3 * 64) hex chars
        wbnb_out_hex = raw[192:256]
        return int(wbnb_out_hex, 16)
    except (ValueError, IndexError) as exc:
        print(f"[quote] could not decode getAmountsOut result: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def get_sell_quote_usd(
    token_address: str,
    price_usd: float,
    liquidity_usd: float,
    bnb_price_usd: float | None = None,
) -> float | None:
    """Simulate selling $1 worth of *token_address* to WBNB via PancakeSwap V2.

    Steps:
        1. Guard: price_usd <= 0 → return None immediately.
        2. Compute amountIn in wei: int(1.0 / price_usd * 1e18).
        3. ABI-encode getAmountsOut(amountIn, [token_address, WBNB]) and
           call PANCAKE_ROUTER_V2 via BSC JSON-RPC eth_call.
        4. Decode amounts[1] (WBNB output) from the hex response.
        5. Convert WBNB to USD using bnb_price_usd, or by fetching the BNB
           price from DexScreener, or the hard-coded fallback of 600.0.
        6. Router reverts or response invalid → return None.
        7. Return usd_received (float).

    Gate 7 uses the return value as follows (caller is responsible):
        >= 0.50 USD                        → PASS
        < 0.50 USD, liquidity_usd >= 1_000 → WARN (router limitation)
        < 0.50 USD, liquidity_usd <  1_000 → FAIL
        None,       liquidity_usd >= 1_000 → WARN
        None,       liquidity_usd <  1_000 → FAIL

    Any exception is caught; returns None and logs to stderr.
    """
    try:
        # 1. Guard
        if not price_usd or price_usd <= 0:
            return None

        # 2. Convert $1 to token wei units (assume 18 decimals)
        amount_in_tokens = 1.0 / price_usd
        amount_in_wei = int(amount_in_tokens * 1e18)
        if amount_in_wei <= 0:
            return None

        # 3. Build and execute the eth_call
        calldata = _encode_get_amounts_out(amount_in_wei, token_address)
        hex_result = _eth_call(PANCAKE_ROUTER_V2, calldata)

        if not hex_result or hex_result == "0x":
            # Router reverted (e.g. no liquidity path)
            print(
                f"[quote] getAmountsOut reverted for {token_address}",
                file=sys.stderr,
            )
            return None

        # 4. Decode WBNB output (amounts[1])
        wbnb_out_wei = _decode_amounts_out(hex_result)
        if wbnb_out_wei is None:
            return None

        # 5. Convert WBNB wei to USD
        bnb_price = bnb_price_usd if (bnb_price_usd is not None and bnb_price_usd > 0) \
            else _fetch_bnb_price_usd()

        wbnb_out = wbnb_out_wei / 1e18
        usd_received = wbnb_out * bnb_price

        return usd_received

    except Exception as exc:  # noqa: BLE001
        print(f"[quote] get_sell_quote_usd failed for {token_address}: {exc}", file=sys.stderr)
        return None
