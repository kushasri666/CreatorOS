"""Real control flow under scripted responses; no quality/engagement claims."""
import unittest
from editorial_guidance import contract, inspect, regressions
from improvement import assess
from workflow import CRITERIA, run_pipeline
from tests.test_verification_loop import LiveFake


class EditorialGuidanceTests(unittest.TestCase):
    def test_policy_is_above_90_with_individual_weakness_floor(self):
        policy = contract("x")
        self.assertGreater(policy["target_editor_average"], 9)
        self.assertEqual(policy["max_characters"], 280)
        review = dict(scores=dict.fromkeys(CRITERIA, 9))
        self.assertFalse(assess(review, "Useful post", 280, 2, target_average=9.1, minimum_criterion=8)["ready"])
        review["scores"] = dict.fromkeys(CRITERIA, 10)
        review["scores"]["voice"] = 7
        self.assertFalse(assess(review, "Useful post", 280, 2, target_average=9.1, minimum_criterion=8)["ready"])

    def test_regression_detects_loss_of_a_good_hook(self):
        before = inspect("Your coffee ritual starts here. Save this guide.", [], "x")
        after = inspect("Update!", [], "x")
        self.assertIn("hook", regressions(before, after))

    def test_concrete_carousel_failures_and_unicode_limits(self):
        result = inspect("Coffee tips", ["Repeat"]*3, "instagram")
        self.assertFalse(result["checks"]["carousel"])
        self.assertFalse(inspect("☕"*281, [], "x")["checks"]["length"])

    def run_case(self, score=9.2, regress=False):
        gateway = LiveFake()
        original = gateway.ask
        gateway.requests=[]
        def ask(role, data):
            gateway.requests.append((role,data))
            result = original(role, data)
            if role.startswith("Writer"):
                result = dict(text="Your coffee ritual starts here. Save this guide." if gateway.writer == 1
                    else f"Update {gateway.writer}!" if regress else f"Your coffee ritual starts with fresh beans. Save this guide {gateway.writer}.", citations=[])
            if role.startswith("Editor"):
                rating=score[gateway.writer-1] if isinstance(score,list) else score
                result = dict(scores=dict.fromkeys(CRITERIA, rating), edits=["Keep a concrete opening"], reason="Scripted editor response")
            if role.startswith("Verifier"):
                result = dict(checks=[], conflicts=[])
            return result
        gateway.ask = ask
        events=[]
        result=run_pipeline(gateway,"Coffee habits","x",{},[],lambda a,d:events.append((a,d)),generate_image=False)
        return result, gateway, events

    def test_local_feedback_is_saved_and_reaches_agents_without_new_calls(self):
        result, gateway, events = self.run_case()
        self.assertTrue(result["approved"])
        self.assertEqual(gateway.call_count, 7)  # strategy, 2 writers, 2 editors, verifier, visual prompt
        self.assertEqual(len(result["editorial_checks"]), 2)
        self.assertTrue(any(a=="editorial_checks" for a,_ in events))
        writers=[data for role,data in gateway.requests if role.startswith("Writer")]
        editors=[data for role,data in gateway.requests if role.startswith("Editor")]
        self.assertIsNone(writers[0]["local_checks"])
        self.assertEqual(writers[1]["local_checks"],result["editorial_checks"][0])
        self.assertEqual(editors[1]["local_checks"],result["editorial_checks"][1])

    def test_targeted_third_revision_keeps_verification_within_cap(self):
        result,gateway,_=self.run_case(score=[8,9,9.2])
        self.assertTrue(result["approved"])
        self.assertEqual(len(result["drafts"]),3)
        self.assertEqual(gateway.verifier,1)
        self.assertEqual(gateway.call_count,9)

    def test_high_opinion_scores_do_not_override_a_local_regression(self):
        result, gateway, _ = self.run_case(score=10, regress=True)
        self.assertFalse(result["approved"])
        self.assertIn("hook", result["reviews"][1]["local_regressions"])
        self.assertIn("hook", result["reviews"][2]["local_regressions"])
        self.assertIsNone(result["visual"])
        self.assertLessEqual(gateway.call_count, 10)

    def test_nine_out_of_ten_is_held_not_relabelled_as_over_90(self):
        result, gateway, _ = self.run_case(score=9)
        self.assertFalse(result["approved"])
        self.assertIsNone(result["visual"])
        self.assertLessEqual(gateway.call_count, 10)
