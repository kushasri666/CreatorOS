"""Evaluation arithmetic and anti-gaming checks; stdlib only, no model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import self_evaluation as evaluation


class SelfEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.dataset=json.loads(evaluation.QUESTIONS.read_text(encoding="utf-8"))
        self.predictions=json.loads(evaluation.FIXTURES.read_text(encoding="utf-8"))

    def test_fixed_stress_set_is_reproducible_and_all_claims_are_annotated(self):
        result=evaluation.evaluate()
        self.assertEqual((result["case_count"],result["question_count"]),(16,24))
        self.assertEqual(result["before"]["metrics"]["grounded_claim_fraction"],evaluation.ratio(10,22))
        self.assertEqual(result["after"]["metrics"]["grounded_claim_fraction"],evaluation.ratio(10,16))
        self.assertEqual(result["after"]["metrics"]["required_fact_completeness"],evaluation.ratio(10,18))
        self.assertEqual(result["after"]["unscored_claims"],0)
        self.assertEqual(result["ai_calls"],0)

    def test_empty_report_cannot_game_completeness_or_get_a_perfect_claim_rate(self):
        case=self.dataset["cases"][-1];prediction=self.predictions["cases"][-1]
        scored=evaluation.score_case(case,prediction)
        self.assertIsNone(scored["metrics"]["grounded_claim_fraction"]["value"])
        self.assertEqual(scored["metrics"]["required_fact_completeness"]["value"],0)
        self.assertEqual(scored["metrics"]["question_completeness"]["value"],0)

    def test_real_quote_for_unsupported_claim_is_not_grounded(self):
        case=self.dataset["cases"][0];prediction=self.predictions["cases"][0]
        filtered,_=evaluation.filter_prediction(prediction,case["sources"])
        scored=evaluation.score_case(case,filtered)
        self.assertTrue(scored["claims"][-1]["citation_integrity"])
        self.assertFalse(scored["claims"][-1]["grounded"])
        self.assertEqual(scored["unsupported_claims"],1)

    def test_missing_premise_source_is_not_full_support(self):
        case=self.dataset["cases"][13];prediction=self.predictions["cases"][13]
        scored=evaluation.score_case(case,prediction)
        self.assertTrue(scored["claims"][0]["citation_integrity"])
        self.assertEqual(scored["metrics"]["grounded_claim_fraction"]["value"],0)

    def test_unseen_wording_is_unscored_not_falsely_called_hallucinated(self):
        prediction=copy.deepcopy(self.predictions["cases"][0]);prediction["claims"]=prediction["claims"][:1]
        prediction["claims"][0]["text"]="Twelve adjustable grind levels are available."
        prediction["text"]=prediction["claims"][0]["text"]
        scored=evaluation.score_case(self.dataset["cases"][0],prediction)
        self.assertEqual(scored["unscored_claims"],1)
        self.assertEqual(scored["unsupported_claims"],0)
        self.assertEqual(scored["metrics"]["grounded_claim_fraction"]["value"],0)

    def test_abstention_plus_invented_answer_does_not_count_as_correct_abstention(self):
        case=self.dataset["cases"][1];prediction=copy.deepcopy(self.predictions["cases"][1])
        prediction["abstentions"]=[dict(question_id="Q2",reason="Need testing")]
        scored=evaluation.score_case(case,prediction)
        self.assertEqual(scored["metrics"]["abstention_accuracy"]["value"],0)

    def test_missing_cases_and_duplicate_claims_are_rejected(self):
        predictions=copy.deepcopy(self.predictions);predictions["cases"].pop()
        with self.assertRaises(ValueError):evaluation.validate_dataset(self.dataset,predictions)
        predictions=copy.deepcopy(self.predictions);predictions["cases"][0]["claims"].append(predictions["cases"][0]["claims"][0])
        with self.assertRaises(ValueError):evaluation.validate_dataset(self.dataset,predictions)

    def test_gold_free_inputs_never_export_answer_labels(self):
        exported=evaluation.export_prompts()
        self.assertEqual(len(exported["cases"]),16)
        for case in exported["cases"]:
            self.assertNotIn("facts",case);self.assertNotIn("unsupported_claims",case)
            for question in case["questions"]:
                self.assertEqual(set(question),{"id","question"})

    def test_whole_dataset_empty_predictions_get_zero_answerable_fact_coverage(self):
        rows=[]
        for case,prediction in zip(self.dataset["cases"],self.predictions["cases"]):
            scored=evaluation.score_case(case,dict(prediction,claims=[],text="",abstentions=[]))
            rows.append(dict(after=scored))
        total=evaluation.summarize(rows,"after")
        self.assertIsNone(total["metrics"]["grounded_claim_fraction"]["value"])
        self.assertEqual(total["metrics"]["required_fact_completeness"],evaluation.ratio(0,18))

    def test_fingerprints_reproduce_across_windows_and_linux_line_endings(self):
        root=Path(__file__).resolve().parents[1]/"data";root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            windows=Path(temp)/"windows.txt";linux=Path(temp)/"linux.txt"
            windows.write_bytes(b"example\r\nsecond line\r\n");linux.write_bytes(b"example\nsecond line\n")
            self.assertEqual(evaluation.fingerprint(windows),evaluation.fingerprint(linux))


if __name__=="__main__":unittest.main()
