"""Arithmetic and anti-gaming checks for the frozen semantic challenge set."""
import json
import unittest

import semantic_evaluation as evaluation


class SemanticEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = evaluation.load_cases()

    def raw_gold_prediction(self, case):
        """Test-only oracle used to test scorer arithmetic, never live prompts."""
        by_id = {s["source_id"]: s for s in case["sources"]}
        checks = []
        for gold in case["gold"]:
            if gold["label"] == "nonfactual":
                continue
            supported = gold["label"] == "supported"
            ids = gold["source_ids"] if supported else next(
                (c["source_ids"] for c in case["citations"] if c["claim"] == gold["claim"]), [])
            checks.append(dict(claim=gold["claim"], source_ids=ids,
                verdict="supported" if supported else "unsupported",
                reason="Test-only oracle, not a model result.",
                evidence=[dict(source_id=sid, quote=by_id[sid]["excerpt"]) for sid in ids] if supported else []))
        return dict(checks=checks, conflicts=[])

    def validated_gold(self):
        return evaluation.validate_predictions(self.cases,
            {c["id"]: self.raw_gold_prediction(c) for c in self.cases})

    def test_frozen_gold_denominators_and_fingerprint(self):
        report = evaluation.evaluate_named({"oracle_arithmetic_only": self.validated_gold()})
        self.assertEqual(report["dataset_sha256"], "07e3d0b52f2ca1297464dd9957c6514e490f7d88ab8b72e21320512feda29702")
        result = report["phases"]["oracle_arithmetic_only"]
        self.assertEqual(result["case_count"], 12)
        self.assertEqual(result["counts"]["factual_assertions"], 18)
        self.assertEqual(result["counts"]["supported_gold"], 11)
        self.assertEqual(result["counts"]["unsupported_gold"], 7)
        self.assertEqual(result["metrics"]["factual_decision_accuracy"], evaluation.ratio(18, 18))
        self.assertEqual(result["metrics"]["supported_precision"], evaluation.ratio(11, 11))
        self.assertEqual(result["case_false_approvals"], 0)
        self.assertEqual(result["case_false_rejections"], 0)

    def test_gold_and_decoys_are_never_exported_to_model(self):
        for case in self.cases:
            packet = evaluation.model_input(case)
            self.assertEqual(set(packet), {"draft", "slides", "sources", "writer_citations"})
            for hidden in ("gold", "expected_pass", "category", "absent_decoys", "label"):
                self.assertNotIn(hidden, packet)
            packet["sources"][0]["excerpt"] = "changed copy"
            self.assertNotEqual(case["sources"][0]["excerpt"], "changed copy")

    def test_quoted_irrelevant_evidence_is_a_semantic_false_approval(self):
        case = next(c for c in self.cases if c["id"] == "irrelevant-quote-benefit")
        raw = dict(checks=[dict(claim=case["draft"], source_ids=["S1"], verdict="supported",
            reason="Incorrect model entailment despite a real quote.",
            evidence=[dict(source_id="S1", quote=case["sources"][0]["excerpt"])])])
        validated = evaluation.validate_predictions([case], {case["id"]: raw})
        # Receipts validate provenance; the gold scorer independently catches
        # unsupported meaning instead of calling the validator an oracle.
        self.assertTrue(validated[case["id"]]["passed"])
        report = evaluation.evaluate([case], validated)
        self.assertEqual(report["counts"]["false_support"], 1)
        self.assertEqual(report["metrics"]["false_approval_rate"], evaluation.ratio(1, 1))
        self.assertEqual(report["case_false_approvals"], 1)

    def test_empty_refusal_is_not_perfect_and_missing_claims_are_errors(self):
        raw = {c["id"]: dict(checks=[], conflicts=[]) for c in self.cases}
        report = evaluation.evaluate(self.cases, evaluation.validate_predictions(self.cases, raw))
        self.assertEqual(report["metrics"]["supported_recall"], evaluation.ratio(0, 11))
        self.assertLess(report["metrics"]["factual_decision_accuracy"]["value"], 1)
        self.assertGreater(report["counts"]["missed_factual_assertions"], 0)
        self.assertEqual(report["counts"]["correct_withholding"], 0)
        self.assertEqual(report["counts"]["missed_factual_assertions"], 18)

    def test_uncited_nonnumeric_claim_omission_cannot_count_as_safe_withholding(self):
        case = next(c for c in self.cases if c["id"] == "uncited-nonnumeric-assertion")
        raw = self.raw_gold_prediction(case)
        raw["checks"] = raw["checks"][:1]
        validated = evaluation.validate_predictions([case], {case["id"]: raw})
        report = evaluation.evaluate([case], validated)
        self.assertEqual(report["counts"]["missed_factual_assertions"], 1)
        self.assertEqual(report["counts"]["correct_withholding"], 0)
        self.assertEqual(report["metrics"]["factual_decision_accuracy"], evaluation.ratio(1, 2))

    def test_absent_claim_is_rejected_by_actual_validator_and_reported(self):
        case = next(c for c in self.cases if c["id"] == "source-fact-absent-from-draft")
        raw = self.raw_gold_prediction(case)
        raw["checks"].append(dict(claim=case["absent_decoys"][0], source_ids=["S1"],
            verdict="supported", reason="Fact exists only in the source.",
            evidence=[dict(source_id="S1", quote=case["sources"][0]["excerpt"])]))
        validated = evaluation.validate_predictions([case], {case["id"]: raw})
        self.assertFalse(validated[case["id"]]["passed"])
        report = evaluation.evaluate([case], validated)
        self.assertEqual(report["counts"]["absent_claim_checks"], 1)
        self.assertEqual(report["counts"]["unscored_checks"], 1)

    def test_overlapping_whole_draft_is_unscored_not_silently_full_credit(self):
        case = next(c for c in self.cases if c["id"] == "literal-product-facts")
        direct_result = dict(status="complete", passed=True, checks=[dict(claim=case["draft"],
            source_ids=["S1"], verdict="supported", reason="One overlapping check")])
        report = evaluation.evaluate([case], {case["id"]: direct_result})
        self.assertEqual(report["counts"]["missed_factual_assertions"], 2)
        self.assertEqual(report["counts"]["unscored_supported_checks"], 1)
        self.assertEqual(report["metrics"]["supported_precision"], evaluation.ratio(0, 1))

    def test_nonfactual_rejection_is_visible_separately_from_factual_accuracy(self):
        case = next(c for c in self.cases if c["id"] == "cta-and-imagined-aspiration")
        raw = self.raw_gold_prediction(case)
        raw["checks"].append(dict(claim="Imagine a calmer morning ritual.", source_ids=[],
            verdict="unsupported", reason="Unnecessary factuality check of an aspiration."))
        report = evaluation.evaluate([case], evaluation.validate_predictions([case], {case["id"]: raw}))
        self.assertEqual(report["counts"]["nonfactual_rejections"], 1)
        self.assertEqual(report["case_false_rejections"], 1)
        self.assertEqual(report["metrics"]["factual_decision_accuracy"], evaluation.ratio(1, 1))

    def test_missing_phase_cases_reduce_coverage_unknown_cases_are_rejected(self):
        report = evaluation.evaluate(self.cases, {})
        self.assertEqual(report["counts"]["missed_factual_assertions"], 18)
        self.assertEqual(report["metrics"]["factual_decision_accuracy"], evaluation.ratio(0, 18))
        self.assertIsNone(report["metrics"]["supported_precision"]["value"])
        with self.assertRaises(ValueError):
            evaluation.evaluate(self.cases, {"invented-case": {}})
        with self.assertRaises(ValueError):
            evaluation.validate_predictions(self.cases, {"invented-case": {}})

    def test_full_pipeline_conflict_policy_withholds_a_quoted_disputed_value(self):
        case = next(c for c in self.cases if c["id"] == "unqualified-source-conflict")
        raw = dict(checks=[dict(claim=case["draft"], source_ids=["S1", "S2"],
            verdict="supported", reason="Incorrectly approved contradictory quotes.",
            evidence=[dict(source_id=s["source_id"], quote=s["excerpt"]) for s in case["sources"]])], conflicts=[])
        validated = evaluation.validate_predictions([case], {case["id"]: raw})
        self.assertFalse(validated[case["id"]]["passed"])
        self.assertEqual(validated[case["id"]]["checks"][0]["verdict"], "thin")
        self.assertTrue(validated[case["id"]]["conflicts"])
        report = evaluation.evaluate([case], validated)
        self.assertEqual(report["counts"]["correct_withholding"], 1)

    def test_invalid_conflict_evidence_is_not_silently_ignored(self):
        case = next(c for c in self.cases if c["id"] == "literal-product-facts")
        raw = self.raw_gold_prediction(case)
        raw["conflicts"] = [dict(subject="invented dispute", reason="no source receipts", evidence=[])]
        validated = evaluation.validate_predictions([case], {case["id"]: raw})
        self.assertFalse(validated[case["id"]]["passed"])
        self.assertEqual(validated[case["id"]]["status"], "invalid_conflict_output")
        self.assertEqual(evaluation.evaluate([case], validated)["invalid_or_missing_cases"], 1)

    def test_named_phases_keep_raw_counts_and_same_fixed_denominators(self):
        report = evaluation.evaluate_named({"before": {}, "after": self.validated_gold()})
        before = report["phases"]["before"]
        after = report["phases"]["after"]
        self.assertEqual(before["counts"]["factual_assertions"], after["counts"]["factual_assertions"])
        self.assertEqual(before["metrics"]["supported_recall"]["denominator"], 11)
        self.assertEqual(after["metrics"]["supported_recall"]["denominator"], 11)
        self.assertIn("retrospective", json.dumps(report["limitations"]))


if __name__ == "__main__":
    unittest.main()
