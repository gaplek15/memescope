"""test_gates.py — Unit tests for the 8-gate screening engine.

No network calls. All inputs are canned normalised model dicts.
Run with:
    python3 -m pytest src/test_gates.py -v
    # or
    python3 src/test_gates.py
"""

import sys
import os
import unittest

# Ensure the src/ directory is on the path so `import screener` works whether
# tests are run from the project root or from inside src/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screener import (
    gate_market,
    gate_goplus,
    gate_owner_renounced,
    gate_lp_lock,
    gate_holder_concentration,
    gate_reputation,
    gate_sell_path,
    gate_survival,
    run_all_gates,
    compute_score,
    compute_verdict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(gate_fn, model: dict) -> str:
    """Call a gate function and return only its result string."""
    return gate_fn(model)["result"]


# ---------------------------------------------------------------------------
# Gate 1 — Market
# ---------------------------------------------------------------------------

class TestGateMarket(unittest.TestCase):

    PASS_MODEL = {
        "liquidity_usd": 25000,
        "volume_24h": 6000,
        "buys_1h": 50,
        "sells_1h": 20,
        "pair_age_hours": 10.0,
        "change_6h": -5.0,
    }

    def test_pass_all_conditions_met(self):
        r = gate_market(self.PASS_MODEL)
        self.assertEqual(r["result"], "PASS")
        self.assertEqual(r["gate"], 1)
        self.assertEqual(r["name"], "Market")

    def test_fail_low_liquidity(self):
        model = {**self.PASS_MODEL, "liquidity_usd": 10_000}
        self.assertEqual(_result(gate_market, model), "FAIL")

    def test_fail_low_volume(self):
        model = {**self.PASS_MODEL, "volume_24h": 1_000}
        self.assertEqual(_result(gate_market, model), "FAIL")

    def test_fail_buys_less_than_sells(self):
        model = {**self.PASS_MODEL, "buys_1h": 10, "sells_1h": 50}
        self.assertEqual(_result(gate_market, model), "FAIL")

    def test_fail_pair_too_young(self):
        model = {**self.PASS_MODEL, "pair_age_hours": 3.0}
        self.assertEqual(_result(gate_market, model), "FAIL")

    def test_result_has_required_keys(self):
        r = gate_market(self.PASS_MODEL)
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 2 — GoPlus security
# ---------------------------------------------------------------------------

class TestGateGoplus(unittest.TestCase):

    PASS_GP = {
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
    }

    def test_pass_all_clean(self):
        self.assertEqual(_result(gate_goplus, {"goplus": self.PASS_GP}), "PASS")

    def test_fail_honeypot(self):
        gp = {**self.PASS_GP, "is_honeypot": "1"}
        self.assertEqual(_result(gate_goplus, {"goplus": gp}), "FAIL")

    def test_warn_unknown_fields(self):
        gp = {
            **self.PASS_GP,
            "is_honeypot": None,
            "buy_tax": None,
            "sell_tax": None,
        }
        self.assertEqual(_result(gate_goplus, {"goplus": gp}), "WARN")

    def test_fail_no_goplus_data(self):
        self.assertEqual(_result(gate_goplus, {"goplus": {}}), "FAIL")

    def test_fail_missing_goplus_key(self):
        self.assertEqual(_result(gate_goplus, {}), "FAIL")

    def test_result_has_required_keys(self):
        r = gate_goplus({"goplus": self.PASS_GP})
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 3 — Owner renounced
# ---------------------------------------------------------------------------

class TestGateOwnerRenounced(unittest.TestCase):

    def test_pass_zero_address(self):
        model = {"goplus": {"owner_address": "0x0000000000000000000000000000000000000000"}}
        self.assertEqual(_result(gate_owner_renounced, model), "PASS")

    def test_pass_empty_address(self):
        model = {"goplus": {"owner_address": ""}}
        self.assertEqual(_result(gate_owner_renounced, model), "PASS")

    def test_fail_live_address(self):
        model = {"goplus": {"owner_address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12"}}
        self.assertEqual(_result(gate_owner_renounced, model), "FAIL")

    def test_warn_no_goplus_data(self):
        self.assertEqual(_result(gate_owner_renounced, {"goplus": {}}), "WARN")

    def test_warn_missing_goplus_key(self):
        self.assertEqual(_result(gate_owner_renounced, {}), "WARN")

    def test_result_has_required_keys(self):
        r = gate_owner_renounced({"goplus": {"owner_address": ""}})
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 4 — LP lock/burn
# ---------------------------------------------------------------------------

class TestGateLpLock(unittest.TestCase):

    def test_pass_burn_plus_lock_reaches_95(self):
        model = {
            "lp_locked_pct": 50.0,
            "lp_burned_pct": 50.0,
            "lp_lock_ends": [],
        }
        self.assertEqual(_result(gate_lp_lock, model), "PASS")

    def test_pass_long_lock_reaches_95(self):
        model = {
            "lp_locked_pct": 97.0,
            "lp_burned_pct": 0.0,
            "lp_lock_ends": ["2027-12-01T00:00:00Z"],
        }
        self.assertEqual(_result(gate_lp_lock, model), "PASS")

    def test_fail_only_50_percent_no_burn(self):
        model = {
            "lp_locked_pct": 50.0,
            "lp_burned_pct": 0.0,
            "lp_lock_ends": [],
        }
        self.assertEqual(_result(gate_lp_lock, model), "FAIL")

    def test_fail_locked_but_expired(self):
        # 97 % locked but the lock already expired → no valid long lock
        model = {
            "lp_locked_pct": 97.0,
            "lp_burned_pct": 0.0,
            "lp_lock_ends": ["2024-01-01T00:00:00Z"],
        }
        self.assertEqual(_result(gate_lp_lock, model), "FAIL")

    def test_result_has_required_keys(self):
        model = {"lp_locked_pct": 50.0, "lp_burned_pct": 50.0, "lp_lock_ends": []}
        r = gate_lp_lock(model)
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 5 — Holder concentration
# ---------------------------------------------------------------------------

class TestGateHolderConcentration(unittest.TestCase):

    def test_pass_low_concentration(self):
        model = {
            "top1_holder_pct": 3.0,
            "top5_holder_pct": 10.0,
            "goplus": {"holder_count": 1000},
        }
        self.assertEqual(_result(gate_holder_concentration, model), "PASS")

    def test_fail_top1_too_high(self):
        model = {
            "top1_holder_pct": 6.0,
            "top5_holder_pct": 12.0,
            "goplus": {"holder_count": 100},
        }
        self.assertEqual(_result(gate_holder_concentration, model), "FAIL")

    def test_fail_top5_too_high(self):
        model = {
            "top1_holder_pct": 3.0,
            "top5_holder_pct": 16.0,
            "goplus": {"holder_count": 100},
        }
        self.assertEqual(_result(gate_holder_concentration, model), "FAIL")

    def test_warn_no_data(self):
        model = {
            "top1_holder_pct": 0.0,
            "top5_holder_pct": 0.0,
            "goplus": {},
        }
        self.assertEqual(_result(gate_holder_concentration, model), "WARN")

    def test_result_has_required_keys(self):
        model = {
            "top1_holder_pct": 3.0,
            "top5_holder_pct": 10.0,
            "goplus": {"holder_count": 1000},
        }
        r = gate_holder_concentration(model)
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 6 — Reputation
# ---------------------------------------------------------------------------

class TestGateReputation(unittest.TestCase):

    CLEAN_REP = {
        "number_of_malicious_contracts_created": "0",
        "cybercrime": "0",
        "phishing_activities": "0",
        "money_laundering": "0",
        "honeypot_related_address": "0",
    }

    def test_pass_both_clean(self):
        model = {
            "owner_reputation": self.CLEAN_REP,
            "creator_reputation": self.CLEAN_REP,
        }
        self.assertEqual(_result(gate_reputation, model), "PASS")

    def test_fail_owner_malicious_contracts(self):
        model = {
            "owner_reputation": {"number_of_malicious_contracts_created": "3"},
            "creator_reputation": None,
        }
        self.assertEqual(_result(gate_reputation, model), "FAIL")

    def test_fail_owner_crime_flag(self):
        model = {
            "owner_reputation": {
                "number_of_malicious_contracts_created": "0",
                "honeypot_related_address": "1",
            },
            "creator_reputation": None,
        }
        self.assertEqual(_result(gate_reputation, model), "FAIL")

    def test_warn_no_data(self):
        model = {"owner_reputation": None, "creator_reputation": None}
        self.assertEqual(_result(gate_reputation, model), "WARN")

    def test_result_has_required_keys(self):
        model = {"owner_reputation": self.CLEAN_REP, "creator_reputation": self.CLEAN_REP}
        r = gate_reputation(model)
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 7 — Sell path
# ---------------------------------------------------------------------------

class TestGateSellPath(unittest.TestCase):

    def test_pass_good_quote(self):
        model = {"sell_quote_usd": 0.90, "liquidity_usd": 50_000}
        self.assertEqual(_result(gate_sell_path, model), "PASS")

    def test_warn_low_quote_liq_ok(self):
        model = {"sell_quote_usd": 0.30, "liquidity_usd": 50_000}
        self.assertEqual(_result(gate_sell_path, model), "WARN")

    def test_fail_low_quote_low_liq(self):
        model = {"sell_quote_usd": 0.30, "liquidity_usd": 500}
        self.assertEqual(_result(gate_sell_path, model), "FAIL")

    def test_warn_no_quote_liq_ok(self):
        model = {"sell_quote_usd": None, "liquidity_usd": 50_000}
        self.assertEqual(_result(gate_sell_path, model), "WARN")

    def test_fail_no_quote_low_liq(self):
        model = {"sell_quote_usd": None, "liquidity_usd": 500}
        self.assertEqual(_result(gate_sell_path, model), "FAIL")

    def test_result_has_required_keys(self):
        r = gate_sell_path({"sell_quote_usd": 0.90, "liquidity_usd": 50_000})
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# Gate 8 — Survival
# ---------------------------------------------------------------------------

class TestGateSurvival(unittest.TestCase):

    def test_pass_moderate_dip(self):
        self.assertEqual(_result(gate_survival, {"change_6h": -20.0}), "PASS")

    def test_fail_severe_crash(self):
        self.assertEqual(_result(gate_survival, {"change_6h": -60.0}), "FAIL")

    def test_warn_no_data(self):
        self.assertEqual(_result(gate_survival, {"change_6h": None}), "WARN")

    def test_pass_positive_change(self):
        self.assertEqual(_result(gate_survival, {"change_6h": 10.0}), "PASS")

    def test_fail_exactly_minus_50(self):
        # Boundary: > -50 passes, <= -50 fails
        self.assertEqual(_result(gate_survival, {"change_6h": -50.0}), "FAIL")

    def test_result_has_required_keys(self):
        r = gate_survival({"change_6h": -20.0})
        for key in ("gate", "name", "result", "detail"):
            self.assertIn(key, r)


# ---------------------------------------------------------------------------
# run_all_gates
# ---------------------------------------------------------------------------

class TestRunAllGates(unittest.TestCase):
    """run_all_gates should return exactly 8 results, one per gate."""

    # Minimal model that gives all PASS results for a simple sanity check
    ALL_PASS_MODEL = {
        # Gate 1
        "liquidity_usd": 25_000,
        "volume_24h": 6_000,
        "buys_1h": 50,
        "sells_1h": 20,
        "pair_age_hours": 10.0,
        "change_6h": -5.0,
        # Gate 2 + 3
        "goplus": {
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
            "owner_address": "0x0000000000000000000000000000000000000000",
            "holder_count": 500,
        },
        # Gate 4
        "lp_locked_pct": 50.0,
        "lp_burned_pct": 50.0,
        "lp_lock_ends": [],
        # Gate 5
        "top1_holder_pct": 3.0,
        "top5_holder_pct": 10.0,
        # Gate 6
        "owner_reputation": {
            "number_of_malicious_contracts_created": "0",
            "cybercrime": "0",
            "phishing_activities": "0",
            "money_laundering": "0",
            "honeypot_related_address": "0",
        },
        "creator_reputation": {
            "number_of_malicious_contracts_created": "0",
            "cybercrime": "0",
            "phishing_activities": "0",
            "money_laundering": "0",
            "honeypot_related_address": "0",
        },
        # Gate 7
        "sell_quote_usd": 0.90,
        # Gate 8 reuses change_6h = -5.0 above
    }

    def test_returns_eight_results(self):
        results = run_all_gates(self.ALL_PASS_MODEL)
        self.assertEqual(len(results), 8)

    def test_gate_numbers_are_one_through_eight(self):
        results = run_all_gates(self.ALL_PASS_MODEL)
        gate_nums = [r["gate"] for r in results]
        self.assertEqual(gate_nums, list(range(1, 9)))

    def test_all_pass_model_gives_all_pass(self):
        results = run_all_gates(self.ALL_PASS_MODEL)
        for r in results:
            self.assertEqual(r["result"], "PASS", f"Gate {r['gate']} expected PASS, got {r['result']}")

    def test_each_result_has_required_keys(self):
        results = run_all_gates(self.ALL_PASS_MODEL)
        for r in results:
            for key in ("gate", "name", "result", "detail"):
                self.assertIn(key, r, f"Gate {r['gate']} missing key '{key}'")


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------

class TestComputeScore(unittest.TestCase):
    """Score: PASS=full weight, WARN=half weight (floor), FAIL=0.
    Weights: 1→15, 2→20, 3→15, 4→20, 5→10, 6→10, 7→5, 8→5. Total=100.
    """

    def _make_results(self, result: str) -> list[dict]:
        """Build 8 gate result dicts all set to `result`."""
        return [
            {"gate": i, "name": f"Gate{i}", "result": result, "detail": ""}
            for i in range(1, 9)
        ]

    def test_all_pass_scores_100(self):
        self.assertEqual(compute_score(self._make_results("PASS")), 100)

    def test_all_fail_scores_0(self):
        self.assertEqual(compute_score(self._make_results("FAIL")), 0)

    def test_all_warn_scores_half(self):
        # Half-weight (floor): 7+10+7+10+5+5+2+2 = 48
        expected = 7 + 10 + 7 + 10 + 5 + 5 + 2 + 2
        self.assertEqual(compute_score(self._make_results("WARN")), expected)

    def test_mixed_pass_and_fail(self):
        # Gate 1 PASS (15), Gate 2 FAIL (0), rest PASS (65) → 80
        results = self._make_results("PASS")
        results[1] = {"gate": 2, "name": "GoPlus security", "result": "FAIL", "detail": ""}
        self.assertEqual(compute_score(results), 80)

    def test_single_warn_gate(self):
        # Only gate 4 (weight 20) is WARN → 10; rest PASS → 90 → total 90
        results = self._make_results("PASS")
        results[3] = {"gate": 4, "name": "LP lock/burn", "result": "WARN", "detail": ""}
        self.assertEqual(compute_score(results), 90)

    def test_empty_list_scores_0(self):
        self.assertEqual(compute_score([]), 0)


# ---------------------------------------------------------------------------
# compute_verdict
# ---------------------------------------------------------------------------

class TestComputeVerdict(unittest.TestCase):

    def _gates(self, results: list[str]) -> list[dict]:
        return [
            {"gate": i + 1, "name": f"Gate{i+1}", "result": r, "detail": ""}
            for i, r in enumerate(results)
        ]

    def test_all_pass_gives_lolos(self):
        self.assertEqual(compute_verdict(self._gates(["PASS"] * 8)), "LOLOS")

    def test_all_warn_gives_lolos(self):
        self.assertEqual(compute_verdict(self._gates(["WARN"] * 8)), "LOLOS")

    def test_mixed_pass_warn_gives_lolos(self):
        results = ["PASS", "WARN", "PASS", "WARN", "PASS", "PASS", "WARN", "PASS"]
        self.assertEqual(compute_verdict(self._gates(results)), "LOLOS")

    def test_one_fail_gives_gagal(self):
        results = ["PASS"] * 7 + ["FAIL"]
        self.assertEqual(compute_verdict(self._gates(results)), "GAGAL")

    def test_multiple_fails_gives_gagal(self):
        results = ["FAIL", "FAIL", "PASS", "PASS", "FAIL", "PASS", "PASS", "PASS"]
        self.assertEqual(compute_verdict(self._gates(results)), "GAGAL")

    def test_first_gate_fail_gives_gagal(self):
        results = ["FAIL"] + ["PASS"] * 7
        self.assertEqual(compute_verdict(self._gates(results)), "GAGAL")

    def test_empty_list_gives_lolos(self):
        # No FAILs → LOLOS
        self.assertEqual(compute_verdict([]), "LOLOS")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
