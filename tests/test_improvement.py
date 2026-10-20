"""Outer-loop decisions use offline contracts, never paid inference."""
import unittest
from improvement import assess
from workflow import CRITERIA, run_pipeline


class TrajectoryGateway:
    mode = "offline_fixture"

    def __init__(self, scores):
        self.scores = iter(scores)
        self.calls = []
        self.drafts = 0
        self.strategies = 0

    def ask(self, role, data):
        self.calls.append((role, data))
        if role.startswith("Strategist"):
            self.strategies += 1
            return dict(angle=f"angle {self.strategies}", applied_learning_ids=["evidence-1", "invented"])
        if role.startswith("Writer"):
            self.drafts += 1
            return dict(text=f"Practical draft {self.drafts}. Test one useful change. What worked?")
        if role.startswith("Editor"):
            return dict(scores=dict.fromkeys(CRITERIA, next(self.scores)),
                        edits=["Use a concrete hook"], reason="Targeted critique")
        if role.startswith("Visual"):
            return dict(prompt="An editorial scene", reason="Matches the selected draft")
        raise AssertionError(role)

    def image(self, prompt):
        self.calls.append(("Image", prompt))
        return "https://example.test/fixture.png"


class ImprovementTests(unittest.TestCase):
    def run_case(self, scores):
        gateway = TrajectoryGateway(scores)
        events = []
        result = run_pipeline(gateway, "Useful habits", "linkedin", {"tone": "precise"},
            [{"id": "evidence-1", "rule": "Test a checklist"}], lambda a, d: events.append((a, d)))
        return result, gateway, events

    def test_recovery_replans_once_and_preserves_context_within_ten_calls(self):
        result, gateway, events = self.run_case([6, 5, 9])
        self.assertEqual([a["action"] for a in result["assessments"]], ["refine", "restart", "accept"])
        self.assertEqual(gateway.strategies, 2)
        self.assertEqual(len(gateway.calls), 10)
        self.assertTrue(result["approved"])
        restart = [data for role, data in gateway.calls if role.startswith("Strategist")][-1]
        self.assertEqual(restart["brief"], "Useful habits")
        self.assertEqual(restart["voice"], {"tone": "precise"})
        self.assertIn("previous_draft", restart)
        self.assertEqual(result["strategy"]["applied_learning_ids"], ["evidence-1"])
        self.assertEqual(len([a for a, _ in events if a == "improvement"]), 3)

    def test_low_quality_stops_and_does_not_spend_on_visual(self):
        result, gateway, _ = self.run_case([5, 5, 4])
        self.assertFalse(result["approved"])
        self.assertEqual(result["assessments"][-1]["action"], "needs_review")
        self.assertEqual(result["selected_draft_index"], 1)
        self.assertEqual(result["text"], result["drafts"][1])
        self.assertEqual(result["strategy"]["angle"], "angle 1")
        self.assertIsNone(result["image"])
        self.assertFalse(any(role.startswith("Visual") for role, _ in gateway.calls))

    def test_good_revision_adds_no_extra_agent_calls(self):
        result, gateway, _ = self.run_case([8, 9])
        self.assertTrue(result["approved"])
        self.assertEqual(len(gateway.calls), 7)
        self.assertEqual(gateway.strategies, 1)

    def test_average_does_not_hide_weak_criterion_or_length_violation(self):
        review = {"scores": dict.fromkeys(CRITERIA, 10)}
        review["scores"]["voice"] = 4
        decision = assess(review, "text", 280, 2)
        self.assertFalse(decision["ready"])
        self.assertGreater(decision["confidence_score"], .8)
        self.assertFalse(assess({"scores": dict.fromkeys(CRITERIA, 9)}, "x"*281, 280, 2)["ready"])
        self.assertEqual(assess({"scores": dict.fromkeys(CRITERIA, 9)}, "text", 280, 1)["action"], "refine")
