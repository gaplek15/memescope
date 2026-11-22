"""
src/narrative.py — Plain-language risk narrative for MemeScope screening reports.

Two tiers:
  1. LLM tier   — POST to LLM_ENDPOINT (env var) if set; falls back on any error.
  2. Template tier — deterministic sentences built from gate results; always works.

Security contract:
  - The LLM prompt contains ONLY public gate numbers (names, results, details).
  - API keys, private keys, seed phrases, and wallet addresses are NEVER sent.

REQ-20: narrative based only on actual gate results.
REQ-21: residual-risk disclaimer even when all gates pass.
REQ-22: template narrative when LLM is unavailable (the default).
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional


_DISCLAIMER = (
    "LOLOS does not guarantee safety \u2014 a clean contract cannot predict "
    "the deployer\u2019s future decisions. "
    "Treat any amount invested as money you are prepared to lose."
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_narrative(
    gate_results: list[dict],
    verdict: str,
    score: int,
    token_name: str = "",
    token_symbol: str = "",
) -> str:
    """
    Generate a 3-6 sentence plain-language risk narrative based on gate results.

    1. Try the LLM tier first if LLM_ENDPOINT env var is set.
    2. Fall back to the template tier.

    Returns a string narrative. Never raises.
    """
    try:
        llm_text = _llm_narrative(
            gate_results=gate_results,
            verdict=verdict,
            score=score,
            token_name=token_name,
            token_symbol=token_symbol,
        )
        if llm_text:
            return llm_text
    except Exception:
        pass

    return _template_narrative(
        gate_results=gate_results,
        verdict=verdict,
        score=score,
    )


# ---------------------------------------------------------------------------
# Template tier
# ---------------------------------------------------------------------------


def _template_narrative(
    gate_results: list[dict],
    verdict: str,
    score: int,
) -> str:
    """
    Build a deterministic narrative from gate results.

    gate_results is a list of dicts, each expected to have at minimum:
        {
            "gate": int,          # 1-8
            "name": str,          # e.g. "Market"
            "result": str,        # "PASS", "FAIL", or "WARN"
            "detail": str,        # human-readable detail line
        }
    """
    failed = [g for g in gate_results if g.get("result") == "FAIL"]
    warned = [g for g in gate_results if g.get("result") == "WARN"]

    sentences: list[str] = []

    if failed:
        # Name the worst (first) failed gate prominently.
        first = failed[0]
        gate_num = first.get("gate", "?")
        gate_name = first.get("name", "Unknown")
        detail = first.get("detail", "").rstrip(".")
        sentences.append(
            f"Gate {gate_num} ({gate_name}) failed: {detail}."
        )
        for extra in failed[1:]:
            g_num = extra.get("gate", "?")
            g_name = extra.get("name", "Unknown")
            sentences.append(f"Gate {g_num} ({g_name}) also failed.")
        sentences.append(
            "This token does not pass the strict screening. "
            "Do not buy based solely on this report."
        )

    elif warned:
        warn_names = ", ".join(g.get("name", "Unknown") for g in warned)
        sentences.append(
            f"All 8 gates passed with {len(warned)} warning(s). "
            f"Warnings: {warn_names}."
        )
        sentences.append(f"Score: {score}/100.")
        sentences.append(_DISCLAIMER)

    else:
        # All clean.
        sentences.append(f"All 8 gates passed cleanly. Score: {score}/100.")
        sentences.append(
            "No mechanical traps were detected in the contract, liquidity, "
            "holder distribution, or sell path."
        )
        sentences.append(_DISCLAIMER)

    return " ".join(sentences)


# ---------------------------------------------------------------------------
# LLM tier
# ---------------------------------------------------------------------------


def _llm_narrative(
    gate_results: list[dict],
    verdict: str,
    score: int,
    token_name: str = "",
    token_symbol: str = "",
) -> Optional[str]:
    """
    POST gate results to the configured LLM endpoint and return the narrative.

    Returns None on any failure (not set, network error, bad JSON, timeout).
    NEVER sends API keys, private keys, seed phrases, or wallet addresses.
    Only public gate numbers/labels are included in the prompt.
    """
    endpoint = os.environ.get("LLM_ENDPOINT", "").strip()
    if not endpoint:
        return None

    # Build a gate summary from public information only.
    gate_lines: list[str] = []
    for g in gate_results:
        gate_num = g.get("gate", "?")
        gate_name = g.get("name", "Unknown")
        result = g.get("result", "UNKNOWN")
        detail = g.get("detail", "")
        line = f"{gate_num}. {gate_name}: {result}"
        if detail:
            line += f" ({detail})"
        gate_lines.append(line)

    gate_summary = "\n".join(gate_lines)
    name_sym = f"{token_name}/{token_symbol}".strip("/")

    prompt = (
        "You are a DeFi risk analyst. Based on these meme token screening "
        "results, write a 3-6 sentence plain-language risk narrative. "
        "Be direct about risks. Do not recommend buying or selling.\n\n"
        f"Token: {name_sym}\n"
        f"Verdict: {verdict}\n"
        f"Score: {score}/100\n"
        f"Gates:\n{gate_summary}"
    )

    payload = json.dumps({"prompt": prompt, "max_tokens": 200}).encode("utf-8")

    req = urllib.request.Request(
        url=endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None

    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    # Support several common LLM response shapes.
    if isinstance(body, dict):
        if "response" in body and isinstance(body["response"], str):
            return body["response"].strip() or None
        if "content" in body and isinstance(body["content"], str):
            return body["content"].strip() or None
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text") or first.get("message", {}).get("content", "")
                if isinstance(text, str) and text.strip():
                    return text.strip()

    return None
