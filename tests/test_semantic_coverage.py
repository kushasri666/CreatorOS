"""Offline coverage-contract regressions; fixture verdicts are not AI results."""
import copy
import unittest

from verification_contract import packet, resolve, units
from workflow import _validate_verifier_result


class SemanticCoverageTests(unittest.TestCase):
    def setup_contract(self, draft, excerpt="Brew Mini includes a cleaning brush.", slides=None):
        self.draft = draft
        self.slides = slides or []
        self.sources = [dict(source_id="S1", source_type="user_product_facts", excerpt=excerpt)]
        self.candidates, self.receipts = packet(dict(draft=draft, slides=self.slides, sources=self.sources))
        self.coverage_units = units(draft, self.slides)

    def candidate(self, claim):
        return next(cid for cid, text in self.candidates.items() if text == claim)

    def row(self, unit_id, kind, claims=()):
        return dict(unit_id=unit_id, kind=kind,
                    candidate_ids=[self.candidate(c) for c in claims],
                    reason="Fixture classification to exercise the coverage contract.")

    def check(self, claim, verdict="supported"):
        return dict(candidate_id=self.candidate(claim), source_ids=["S1"], verdict=verdict,
            reason="Fixture semantic verdict; no inference was run.",
            evidence=[dict(receipt_id=next(iter(self.receipts)))] if verdict == "supported" else [])

    def validate(self, checks, coverage):
        resolved = resolve(dict(checks=checks, coverage=coverage, conflicts=[]),
            self.candidates, self.receipts, self.coverage_units)
        return _validate_verifier_result(resolved, self.draft, self.slides, [], self.sources)

    def test_every_unit_required_before_approval(self):
        fact = "Brew Mini includes a cleaning brush."
        self.setup_contract(fact + " Save this guide.")
        checks = [self.check(fact)]
        complete = [self.row("U1", "factual", [fact]), self.row("U2", "nonfactual")]
        self.assertTrue(self.validate(checks, complete)["passed"])
        missing = self.validate(checks, complete[:1])
        self.assertFalse(missing["passed"])
        self.assertFalse(missing["coverage_passed"])
        self.assertIn("Every sentence/line", missing["reason"])

    def test_unknown_duplicate_unit_ids_and_unknown_candidates_reject(self):
        fact = "Brew Mini includes a cleaning brush."
        self.setup_contract(fact + " Save this guide.")
        checks = [self.check(fact)]
        valid = [self.row("U1", "factual", [fact]), self.row("U2", "nonfactual")]
        unknown_unit = copy.deepcopy(valid)
        unknown_unit[1]["unit_id"] = "U999"
        duplicate_unit = copy.deepcopy(valid)
        duplicate_unit[1]["unit_id"] = "U1"
        unknown_candidate = copy.deepcopy(valid)
        unknown_candidate[0]["candidate_ids"] = ["C999"]
        malformed_candidate = copy.deepcopy(valid)
        malformed_candidate[0]["candidate_ids"] = [None]
        for bad in (unknown_unit, duplicate_unit, unknown_candidate, malformed_candidate):
            with self.subTest(coverage=bad):
                result = self.validate(checks, bad)
                self.assertFalse(result["passed"])
                self.assertFalse(result["coverage_passed"])

    def test_manifest_factual_nonnumeric_capability_cannot_be_left_unchecked(self):
        fact = "Brew Mini includes a cleaning brush."
        unverified = "Brew Mini is waterproof."
        self.setup_contract(fact + " " + unverified)
        coverage = [self.row("U1", "factual", [fact]), self.row("U2", "factual", [unverified])]
        result = self.validate([self.check(fact)], coverage)
        self.assertFalse(result["passed"])
        self.assertFalse(result["coverage_passed"])
        self.assertIn("never checked", result["reason"])
        checked = self.validate([self.check(fact), self.check(unverified, "unsupported")], coverage)
        self.assertTrue(checked["coverage_passed"])
        self.assertFalse(checked["passed"])

    def test_pure_cta_needs_no_receipt_and_cannot_link_a_hidden_fact(self):
        fact = "Brew Mini includes a cleaning brush."
        self.setup_contract(fact + " Save this guide.")
        coverage = [self.row("U1", "factual", [fact]), self.row("U2", "nonfactual")]
        result = self.validate([self.check(fact)], coverage)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["checks"]), 1)
        self.assertEqual(result["coverage"][1]["claims"], [])
        coverage[1]["candidate_ids"] = [self.candidate(fact)]
        self.assertFalse(self.validate([self.check(fact)], coverage)["coverage_passed"])

    def test_mixed_factual_clause_and_cta_share_one_verified_assertion(self):
        claim = "Brew Mini includes a cleaning brush"
        self.setup_contract(claim + ", so save this guide.")
        self.assertEqual(len(self.coverage_units), 1)
        mixed = self.row("U1", "mixed", [claim])
        result = self.validate([self.check(claim)], [mixed])
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks"][0]["claim"], claim)
        self.assertEqual(result["checks"][0]["evidence"][0]["quote"], self.sources[0]["excerpt"])
        unrelated = self.row("U1", "mixed", ["so save this guide"])
        self.assertFalse(self.validate([self.check(claim)], [unrelated])["coverage_passed"])

    def test_repeated_identical_caption_and_slide_units_deduplicate(self):
        fact = "Brew Mini includes a cleaning brush."
        self.setup_contract(fact + " " + fact, slides=[fact, fact])
        self.assertEqual(self.coverage_units, {"U1": fact})
        result = self.validate([self.check(fact)], [self.row("U1", "factual", [fact])])
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["checks"]), 1)

    def test_source_paraphrase_is_an_exact_draft_candidate_with_real_receipt(self):
        claim = "A cleaning brush comes with Brew Mini."
        self.setup_contract(claim)
        result = self.validate([self.check(claim)], [self.row("U1", "factual", [claim])])
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks"][0]["claim"], claim)
        self.assertNotEqual(claim, result["checks"][0]["evidence"][0]["quote"])
        # This exercises exact IDs and receipt integrity. The supplied supported
        # verdict is a fixture; the test does not prove general entailment.


if __name__ == "__main__":
    unittest.main()
