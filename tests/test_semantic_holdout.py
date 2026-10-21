"""Holdout integrity and prompt isolation only; no oracle model-score claims."""
import collections
import hashlib
import json
from pathlib import Path
import unittest

import semantic_evaluation as evaluation


HOLDOUT = Path(__file__).parents[1] / "evals" / "semantic" / "holdout.json"


class SemanticHoldoutIntegrityTests(unittest.TestCase):
    def test_fixed_holdout_loads_with_balanced_pass_hold_and_exact_annotations(self):
        cases = evaluation.load_cases(HOLDOUT)
        self.assertEqual(len(cases), 8)
        self.assertEqual(sum(case["expected_pass"] for case in cases), 4)
        labels = collections.Counter(gold["label"] for case in cases for gold in case["gold"])
        self.assertEqual(labels, {"supported": 12, "unsupported": 4, "nonfactual": 2})
        self.assertEqual(len({case["category"] for case in cases}), 8)

    def test_frozen_preinference_fingerprints_and_json_roundtrip(self):
        self.assertEqual(hashlib.sha256(HOLDOUT.read_bytes()).hexdigest(),
            "5f182ad083eee168b4f62cf348981d261e014817365ae9779336aa150f53d448")
        cases = evaluation.load_cases(HOLDOUT)
        canonical = json.dumps(cases, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(),
            "9610de0f78b9b02f3c82d55bcfe6bee0a414442aa45cf07bf35712057ff3a724")
        self.assertEqual(cases, json.loads(json.dumps(cases, ensure_ascii=False)))

    def test_holdout_gold_and_expected_decisions_do_not_reach_model(self):
        for case in evaluation.load_cases(HOLDOUT):
            with self.subTest(case=case["id"]):
                packet = evaluation.model_input(case)
                self.assertEqual(set(packet), {"draft", "slides", "writer_citations", "sources"})
                self.assertNotIn("gold", packet)
                self.assertNotIn("expected_pass", packet)
                self.assertNotIn("category", packet)
                self.assertEqual(packet, json.loads(json.dumps(packet, ensure_ascii=False)))


if __name__ == "__main__":
    unittest.main()
