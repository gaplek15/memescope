"""
src/sources/onchain.py — BSC JSON-RPC eth_call helpers.

Provides balanceOf, totalSupply, and burn_percent (Gate 4: LP lock/burn
on-chain verification via the dead address balance of the LP token contract).

BSC public RPC is keyless. No pip dependencies — stdlib only.
"""

import json
import sys
import urllib.request
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BSC_RPC = "https://bsc-dataseed.bnbchain.org"
DEAD_ADDRESS = "0x000000000000000000000000000000000000dEaD"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Function selectors (first 4 bytes of keccak256 of the ABI signature)
_SEL_BALANCE_OF = "0x70a08231"   # balanceOf(address)
_SEL_TOTAL_SUPPLY = "0x18160ddd"  # totalSupply()

_TIMEOUT = 20  # seconds per RPC call


# ---------------------------------------------------------------------------
# Low-level JSON-RPC helper
# ---------------------------------------------------------------------------

def eth_call(to: str, data: str, rpc_url: str = BSC_RPC) -> str | None:
    """
    Make a JSON-RPC eth_call to the BSC public node.

    POST to rpc_url with body:
        {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
         "params": [{"to": to, "data": data}, "latest"]}

    Returns the hex result string (e.g. "0x000...001"), or None on failure.
    Timeout: 20 seconds. Retries once on network error.
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
                rpc_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            if "error" in body:
                print(
                    f"[onchain] eth_call RPC error for {to}: {body['error']}",
                    file=sys.stderr,
                )
                return None

            return body.get("result")

        except (URLError, OSError, json.JSONDecodeError, KeyError) as exc:
            if attempt == 0:
                # Retry once on transient network errors
                print(
                    f"[onchain] eth_call attempt {attempt + 1} failed for {to}: {exc}; retrying…",
                    file=sys.stderr,
                )
                continue
            print(
                f"[onchain] eth_call failed for {to} after retry: {exc}",
                file=sys.stderr,
            )
            return None

    return None


# ---------------------------------------------------------------------------
# ABI-encoded call helpers
# ---------------------------------------------------------------------------

def _encode_address(address: str) -> str:
    """Zero-pad an EVM address to 32 bytes (64 hex chars), no 0x prefix."""
    # Strip leading 0x if present, lowercase, left-pad with zeros to 64 chars
    addr = address.lower().removeprefix("0x")
    return addr.zfill(64)


def balance_of(token_contract: str, holder_address: str) -> int | None:
    """
    Call balanceOf(holder_address) on token_contract.

    ABI-encoded call: 0x70a08231 + holder_address zero-padded to 32 bytes.
    Returns the balance as an integer, or None if the call fails.
    """
    data = _SEL_BALANCE_OF + _encode_address(holder_address)
    result = eth_call(token_contract, data)
    if result is None or result == "0x":
        return None
    try:
        return int(result, 16)
    except ValueError as exc:
        print(
            f"[onchain] balance_of: could not parse result '{result}': {exc}",
            file=sys.stderr,
        )
        return None


def total_supply(token_contract: str) -> int | None:
    """
    Call totalSupply() on token_contract.

    ABI-encoded call: 0x18160ddd
    Returns total supply as an integer, or None if the call fails.
    """
    result = eth_call(token_contract, _SEL_TOTAL_SUPPLY)
    if result is None or result == "0x":
        return None
    try:
        return int(result, 16)
    except ValueError as exc:
        print(
            f"[onchain] total_supply: could not parse result '{result}': {exc}",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------------
# Gate 4 helper
# ---------------------------------------------------------------------------

def burn_percent(lp_token_address: str) -> float:
    """
    Compute the percentage of LP tokens burned (held by the dead address).

    Steps:
      1. dead_bal = balance_of(lp_token_address, DEAD_ADDRESS)
      2. ts       = total_supply(lp_token_address)
      3. If both are available and ts > 0: return dead_bal / ts * 100
      4. Otherwise return 0.0

    Used for Gate 4 (LP lock/burn on-chain verification).
    """
    dead_bal = balance_of(lp_token_address, DEAD_ADDRESS)
    ts = total_supply(lp_token_address)

    if dead_bal is None or ts is None:
        print(
            f"[onchain] burn_percent: could not fetch data for {lp_token_address}, returning 0.0",
            file=sys.stderr,
        )
        return 0.0

    if ts == 0:
        print(
            f"[onchain] burn_percent: totalSupply is 0 for {lp_token_address}, returning 0.0",
            file=sys.stderr,
        )
        return 0.0

    return dead_bal / ts * 100
