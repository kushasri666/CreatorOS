"""Reproduce recorded synthetic model replies without constructing an AI client."""
import copy
import json
import unittest
from unittest.mock import patch

import semantic_evaluation
from scripts import evaluate_semantic as replay


class RecordedSemanticReplayTests(unittest.TestCase):
    def setUp(self):
        self.artifact = json.loads(replay.PREDICTIONS.read_text(encoding="utf-8"))
        self.cases = semantic_evaluation.load_cases()

    def test_public_replies_reproduce_current_scores_without_ai_client(self):
        with patch("workflow.Mesh", side_effect=AssertionError("Offline replay must not construct a client")):
            result = replay.evaluate()
        self.assertEqual(result["ai_calls"], 0)
        self.assertEqual(result["validation_cost_usd"], 0)
        self.assertEqual(result, json.loads(replay.OUTPUT.read_text(encoding="utf-8")))
        phases = result["current_policy_replay"]["phases"]
        self.assertEqual(phases["before"]["metrics"]["factual_decision_accuracy"], semantic_evaluation.ratio(12, 18))
        self.assertEqual(phases["after"]["metrics"]["factual_decision_accuracy"], semantic_evaluation.ratio(18, 18))
        self.assertEqual(phases["reference"]["metrics"]["factual_decision_accuracy"], semantic_evaluation.ratio(17, 18))

    def test_original_sixteen_of_eighteen_remains_distinct_from_policy_replay(self):
        result = replay.evaluate()
        initial = result["historical_initial"]["phases"]["after"]
        current = result["current_policy_replay"]["phases"]["after"]
        self.assertEqual(initial["metrics"]["factual_decision_accuracy"], semantic_evaluation.ratio(16, 18))
        self.assertNotEqual(initial["metrics"], current["metrics"])
        self.assertIn("identical stored model replies", result["interpretation"])
        self.assertIn("not recomputed", result["historical_initial"]["treatment"])

    def test_null_schema_failures_remain_in_every_phase_denominator(self):
        before = self.artifact["phases"]["before"]["predictions"]
        self.assertEqual(len(before), 12)
        self.assertEqual(sum(value is None for value in before.values()), 4)
        dropped_failure = copy.deepcopy(self.artifact)
        missing_id = next(case_id for case_id, result in before.items() if result is None)
        del dropped_failure["phases"]["before"]["predictions"][missing_id]
        with self.assertRaisesRegex(ValueError, "retain every case"):
            replay.validate_artifact(dropped_failure, self.cases)

    def test_changed_gold_or_replaced_phase_is_rejected_before_scoring(self):
        changed_gold = copy.deepcopy(self.artifact)
        changed_gold["gold_file_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "gold changed"):
            replay.validate_artifact(changed_gold, self.cases)
        missing_reference = copy.deepcopy(self.artifact)
        del missing_reference["phases"]["reference"]
        with self.assertRaisesRegex(ValueError, "reference phases"):
            replay.validate_artifact(missing_reference, self.cases)

    def test_one_pass_holdout_reproduces_invalid_manifests_as_safe_holds(self):
        with patch("workflow.Mesh", side_effect=AssertionError("Holdout replay must not construct a client")):
            result = replay.evaluate_holdout()
        self.assertEqual(result, json.loads(replay.HOLDOUT_OUTPUT.read_text(encoding="utf-8")))
        scored = result["results"]
        self.assertEqual(scored["metrics"]["factual_decision_accuracy"], semantic_evaluation.ratio(16, 16))
        self.assertEqual(scored["invalid_or_missing_cases"], 3)
        invalid = [case for case in scored["cases"] if case["invalid_or_missing"]]
        self.assertEqual(len(invalid), 3)
        self.assertTrue(all(not case["actual_pass"] and not case["expected_pass"] for case in invalid))
        self.assertEqual(scored["case_false_approvals"], 0)
        self.assertEqual(scored["case_false_rejections"], 0)

    def test_holdout_scope_and_original_hash_remain_distinct_from_diagnostics(self):
        result = replay.evaluate()
        holdout = result["untuned_holdout_replay"]
        self.assertEqual(holdout["dataset_id"], "creatoros-semantic-verifier-holdout-v1")
        self.assertEqual(holdout["results"]["case_count"], 8)
        self.assertEqual(holdout["gold_sha256"], "5f182ad083eee168b4f62cf348981d261e014817365ae9779336aa150f53d448")
        self.assertIn("eight-case", holdout["scope"])
        self.assertIn("run once", holdout["scope"])
        self.assertNotEqual(holdout["dataset_id"], result["current_policy_replay"]["dataset_id"])


if __name__ == "__main__":
    unittest.main()
