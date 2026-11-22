#!/usr/bin/env python3
"""MemeScope backend — stdlib HTTP server, POST /api/screen.

Usage:
    python3 src/server.py

Environment variables:
    PORT          — listen port (default 8000)
    CMC_API_KEY   — CoinMarketCap Pro key (optional; CMC section degrades
                    to "not listed" when absent)
    LLM_ENDPOINT  — optional LLM endpoint for the narrative tier
"""

import sys
import os

# Add src/ to sys.path so "from sources.X import …" resolves from server.py's
# own directory regardless of where the user runs the command from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import datetime
import re
import concurrent.futures
from http.server import HTTPServer, BaseHTTPRequestHandler

from sources.dexscreener import fetch_pair, normalise_pair
from sources.goplus import (
    fetch_token_security,
    fetch_address_security,
    compute_lp_stats,
    compute_holder_stats,
)
from sources.onchain import burn_percent
from sources.cmc import fetch_quote
from sources.quote import get_sell_quote_usd
from screener import run_all_gates, compute_score, compute_verdict
from narrative import generate_narrative

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("PORT", "8000"))

_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ZERO = "0x0000000000000000000000000000000000000000"

# ---------------------------------------------------------------------------
# Screening pipeline
# ---------------------------------------------------------------------------


def screen_token(address: str, chain_id: int = 56) -> dict:
    """Full screening pipeline for one token address.

    Returns a report dict on success, or {"error": "…"} on input failure.
    Individual source failures degrade gracefully — they never abort the
    whole screening (REQ-09, tech-rule #9).

    Args:
        address:  EVM contract address (0x + 40 hex chars).
        chain_id: EVM chain identifier, default 56 (BNB Chain).

    Returns:
        dict containing the full report or an error entry.
    """
    # 1. Validate address before any network call (REQ-01, REQ-03)
    if not _EVM_ADDRESS_RE.match(address):
        return {"error": "Invalid EVM address — expected 0x followed by 40 hex characters"}

    # 2. DexScreener: fetch the best pair for this token (Gate 1, Gate 8)
    pair_raw = fetch_pair(address)
    if not pair_raw:
        return {"error": "Token not found on DexScreener (no BSC pairs found)"}
    pair = normalise_pair(pair_raw)

    # 3. CoinMarketCap — optional; degrades to None when unlisted or key absent
    # (REQ-05, REQ-06, REQ-31)
    cmc = None
    try:
        cmc = fetch_quote(address, chain_id)
    except Exception as exc:
        _log(f"CMC degraded: {exc}")

    # 4. GoPlus token security (Gates 2, 3, 4, 5, 6)
    gp_token = None
    try:
        gp_token = fetch_token_security(address, chain_id)
    except Exception as exc:
        _log(f"GoPlus token security degraded: {exc}")

    # 5. On-chain LP burn percent (Gate 4)
    lp_burn_pct = 0.0
    if gp_token and pair.get("pair_address"):
        try:
            lp_burn_pct = burn_percent(pair["pair_address"])
        except Exception as exc:
            _log(f"on-chain burn_percent degraded: {exc}")

    # 6. LP lock stats and holder concentration stats (Gates 4, 5)
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

    # 7. Owner / creator reputation via GoPlus address security (Gate 6)
    owner_addr = (gp_token or {}).get("owner_address", "")
    creator_addr = (gp_token or {}).get("creator_address", "")
    owner_rep = None
    creator_rep = None
    if owner_addr and owner_addr.lower() != _ZERO.lower():
        try:
            owner_rep = fetch_address_security(owner_addr, chain_id)
        except Exception as exc:
            _log(f"GoPlus owner address security degraded: {exc}")
    if creator_addr and creator_addr.lower() != _ZERO.lower():
        try:
            creator_rep = fetch_address_security(creator_addr, chain_id)
        except Exception as exc:
            _log(f"GoPlus creator address security degraded: {exc}")

    # 8. Reverse sell quote (Gate 7)
    sell_quote = None
    try:
        sell_quote = get_sell_quote_usd(
            address,
            pair.get("price_usd", 0.0),
            pair.get("liquidity_usd", 0.0),
        )
    except Exception as exc:
        _log(f"sell quote degraded: {exc}")

    # 9. Build the normalised token model (design.md §2)
    model = {
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

    # 10. Gates → score → verdict → narrative (REQ-16, REQ-17, REQ-20..22)
    gates = run_all_gates(model)
    score = compute_score(gates)
    verdict = compute_verdict(gates)
    narrative = generate_narrative(gates, verdict, score, model["name"], model["symbol"])

    return {
        "address": address,
        "chain_id": chain_id,
        "name": model["name"],
        "symbol": model["symbol"],
        "price_usd": model["price_usd"],
        "market_cap": model["market_cap"],
        "liquidity_usd": model["liquidity_usd"],
        "volume_24h": model["volume_24h"],
        "pair_address": model["pair_address"],
        "dex": model["dex"],
        "cmc_listed": cmc is not None,
        "gates": gates,
        "score": score,
        "verdict": verdict,
        "narrative": narrative,
        "screened_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class ScreenHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler: OPTIONS (CORS preflight) + POST /api/screen."""

    def do_OPTIONS(self) -> None:  # CORS preflight
        self.send_response(204)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/api/screen":
            self.send_error(404, "Not Found")
            return

        # Read and parse request body
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._json_response(400, {"error": "Invalid JSON in request body"})
            return

        address = str(req.get("address", "")).strip()
        chain_id = int(req.get("chain_id", 56))

        # Enforce a 60-second timeout for the entire screening (REQ-33)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(screen_token, address, chain_id)
            try:
                result = future.result(timeout=60)
            except concurrent.futures.TimeoutError:
                result = {"error": "Screening timed out (60 s). Try again."}
            except Exception as exc:
                result = {"error": f"Screening failed: {exc}"}

        status = 400 if "error" in result else 200
        self._json_response(status, result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_cors_headers(self) -> None:
        """Add CORS headers required for local development (REQ-30 safe)."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, status: int, data: dict) -> None:
        payload = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self._add_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        # Route the default access log to stderr (avoids mixing with stdout)
        print(f"[{self.address_string()}] {fmt % args}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _log(message: str) -> None:
    """Write a timestamped diagnostic to stderr (never to stdout)."""
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    print(f"[{ts}] {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ScreenHandler)
    _log(f"MemeScope backend listening on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("Shutting down.")
        server.server_close()
