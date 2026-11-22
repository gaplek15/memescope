"""
GoPlus Security API client.

Endpoints used:
  - Token security:  GET https://api.gopluslabs.io/api/v1/token_security/{chain_id}
                         ?contract_addresses={token_address}
  - Address security: GET https://api.gopluslabs.io/api/v1/address_security/{address}
                          ?chain_id={chain_id}

CRITICAL invariants (learned 2026-11-06):
  1. GoPlus `percent` fields in lp_holders and holders are FRACTIONS 0–1,
     NOT percentages 0–100.  Always multiply by 100 before comparisons.
  2. Fields can be None or "" — that means "not yet analysed" (treat as
     UNKNOWN / WARN in the screener).  Only an explicit "1" is a positive flag.
  3. `pairs` (and other list fields) can be absent or null; handle with .get().
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

_BASE = "https://api.gopluslabs.io/api/v1"
_TIMEOUT = 25  # seconds


def _get(url: str) -> dict | None:
    """
    Perform a GET request to `url` with a single retry on network error.

    Returns the parsed JSON body on success, or None on failure (error
    is printed to stderr).
    """
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                raw = resp.read()
                return json.loads(raw)
        except (urllib.error.URLError, OSError) as exc:
            if attempt == 0:
                print(
                    f"[goplus] network error on {url!r}: {exc} — retrying",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[goplus] network error on {url!r}: {exc} — giving up",
                    file=sys.stderr,
                )
        except Exception as exc:  # e.g. JSON decode error
            print(f"[goplus] unexpected error on {url!r}: {exc}", file=sys.stderr)
            return None
    return None


def fetch_token_security(token_address: str, chain_id: int = 56) -> dict | None:
    """
    Fetch GoPlus token security data for a single contract address.

    GET https://api.gopluslabs.io/api/v1/token_security/{chain_id}
        ?contract_addresses={token_address}

    Returns the token security dict (the value at result[token_address.lower()]),
    or None if the token is not found or the call fails.

    Retry once on network error. Timeout 25 seconds.
    """
    url = (
        f"{_BASE}/token_security/{chain_id}"
        f"?contract_addresses={token_address}"
    )
    body = _get(url)
    if body is None:
        return None

    result = body.get("result")
    if not result:
        print(
            f"[goplus] no result for token {token_address!r} on chain {chain_id}",
            file=sys.stderr,
        )
        return None

    # GoPlus returns the token data keyed by the lowercased address.
    key = token_address.lower()
    token_data = result.get(key)
    if token_data is None:
        # Try any key in result (some responses use checksummed addresses).
        for k, v in result.items():
            if k.lower() == key:
                token_data = v
                break

    if token_data is None:
        print(
            f"[goplus] token {token_address!r} not found in result keys: "
            f"{list(result.keys())}",
            file=sys.stderr,
        )
    return token_data


def fetch_address_security(address: str, chain_id: int = 56) -> dict | None:
    """
    Fetch GoPlus address security data for a wallet / contract address.

    GET https://api.gopluslabs.io/api/v1/address_security/{address}
        ?chain_id={chain_id}

    Returns the address security result dict, or None on failure.

    Retry once on network error. Timeout 25 seconds.
    """
    url = f"{_BASE}/address_security/{address}?chain_id={chain_id}"
    body = _get(url)
    if body is None:
        return None

    result = body.get("result")
    if result is None:
        print(
            f"[goplus] no result for address {address!r}",
            file=sys.stderr,
        )
    return result


def compute_lp_stats(token_data: dict) -> dict:
    """
    Compute LP lock / burn statistics from a raw GoPlus token security dict.

    Used by Gate 4 (LP lock/burn).

    CRITICAL: GoPlus `percent` in lp_holders is a FRACTION 0–1, NOT 0–100.
    Multiply by 100 to get the percentage.

    Returns:
    {
      "lp_locked_pct": float,     # sum of locked holder percents * 100
      "lp_lock_ends": list[str],  # ISO datetime strings from locked_detail[].end_time
    }
    """
    lp_holders: list = token_data.get("lp_holders") or []
    lp_locked_pct = 0.0
    lp_lock_ends: list[str] = []

    for holder in lp_holders:
        if not isinstance(holder, dict):
            continue

        # Only locked holders count toward lp_locked_pct.
        if holder.get("is_locked") == "1":
            raw_pct = holder.get("percent")
            if raw_pct is not None and raw_pct != "":
                try:
                    # percent is a fraction 0–1 — multiply by 100.
                    lp_locked_pct += float(raw_pct) * 100.0
                except (ValueError, TypeError):
                    pass

            # Collect lock expiry timestamps from locked_detail[].end_time.
            locked_detail: list = holder.get("locked_detail") or []
            for detail in locked_detail:
                if not isinstance(detail, dict):
                    continue
                end_time = detail.get("end_time")
                if end_time and end_time != "":
                    # Normalise to ISO format if it looks like a Unix timestamp.
                    iso = _normalise_timestamp(end_time)
                    if iso:
                        lp_lock_ends.append(iso)

    return {
        "lp_locked_pct": lp_locked_pct,
        "lp_lock_ends": lp_lock_ends,
    }


def compute_holder_stats(token_data: dict) -> dict:
    """
    Compute top-holder concentration statistics from a raw GoPlus token security dict.

    Used by Gate 5 (holder concentration).

    CRITICAL: GoPlus `percent` in holders is a FRACTION 0–1, NOT 0–100.
    Multiply by 100 to get the percentage.

    Real holders = those where is_locked != "1" AND is_contract != "1".

    Returns:
    {
      "top1_holder_pct": float,  # largest real holder %, or 0 if none
      "top5_holder_pct": float,  # top 5 real holders combined %, or 0 if none
    }
    """
    holders: list = token_data.get("holders") or []
    real_pcts: list[float] = []

    for holder in holders:
        if not isinstance(holder, dict):
            continue

        # Exclude locked and contract holders.
        if holder.get("is_locked") == "1":
            continue
        if holder.get("is_contract") == "1":
            continue

        raw_pct = holder.get("percent")
        if raw_pct is None or raw_pct == "":
            continue
        try:
            # percent is a fraction 0–1 — multiply by 100.
            real_pcts.append(float(raw_pct) * 100.0)
        except (ValueError, TypeError):
            pass

    if not real_pcts:
        return {"top1_holder_pct": 0.0, "top5_holder_pct": 0.0}

    real_pcts.sort(reverse=True)
    top1 = real_pcts[0]
    top5 = sum(real_pcts[:5])

    return {
        "top1_holder_pct": top1,
        "top5_holder_pct": top5,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_timestamp(value: str | int) -> str | None:
    """
    Convert a GoPlus end_time value to an ISO 8601 UTC string.

    GoPlus end_time is usually a Unix timestamp (int or numeric string).
    Returns None if conversion fails.
    """
    try:
        ts = int(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        pass

    # Already an ISO string — return as-is.
    if isinstance(value, str) and ("T" in value or "-" in value):
        return value

    return None
