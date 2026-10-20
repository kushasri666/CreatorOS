"""Independent failure-mode tests for editorial proxies; no provider dependencies."""
import json
import unittest

from content_quality import POLICIES, score
from scripts.evaluate_content import evaluate, OUTPUT


class ContentQualityTests(unittest.TestCase):
    def setUp(self):
        self.requirements = dict(concepts=[["coffee"], ["beans"]], cta_terms=["save", "?"], voice_terms=["fresh"])
        self.text = "Fresh coffee starts with your beans. " * 9 + "Save this guide."

    def test_platform_length_is_not_a_global_tweet_limit(self):
        self.assertGreater(len(self.text), 280)
        self.assertFalse(score({"text": self.text}, "x", self.requirements)["checks"]["length"]["passed"])
        self.assertTrue(score({"text": self.text}, "linkedin", self.requirements)["checks"]["length"]["passed"])

    def test_empty_posts_never_get_free_length_points(self):
        for platform in POLICIES:
            with self.subTest(platform=platform):
                self.assertEqual(score({"text": ""}, platform, self.requirements)["passed"], 0)

    def test_numbered_lists_and_question_ctas_are_not_required(self):
        result = score({"text": "Fresh coffee starts with better beans. Save this guide."}, "x", self.requirements)
        self.assertEqual(result["score_100"], 100)

    def test_off_topic_keyword_absence_loses_brief_and_voice_points(self):
        result = score({"text": "An exciting launch is happening today. Save this update."}, "x", self.requirements)
        self.assertFalse(result["checks"]["brief_coverage"]["passed"])
        self.assertFalse(result["checks"]["voice_cues"]["passed"])

    def test_duplicate_or_overloaded_carousel_slides_fail(self):
        requirements = dict(self.requirements, slide_count=3)
        draft = {"text": "Fresh coffee beans for tomorrow. Save this guide.", "slides": ["same slide"]*3}
        self.assertFalse(score(draft, "instagram", requirements)["checks"]["carousel_structure"]["passed"])
        draft["slides"] = ["fresh beans", "coffee "*36, "Save this"]
        self.assertFalse(score(draft, "instagram", requirements)["checks"]["carousel_structure"]["passed"])

    def test_script_requires_both_length_and_visual_direction(self):
        requirements = dict(self.requirements, format="short_script")
        text = "Fresh coffee beans make a daily habit. "*8 + "Save this."
        self.assertFalse(score({"text": text}, "youtube", requirements)["checks"]["script_format"]["passed"])
        self.assertTrue(score({"text": "[Visual: mug] " + text}, "youtube", requirements)["checks"]["script_format"]["passed"])

    def test_score_arithmetic_and_cohort_separation(self):
        result = evaluate()
        self.assertEqual(result["cohorts"]["recorded_mesh"]["overall"]["n"], 10)
        self.assertEqual(result["cohorts"]["authored_regression"]["overall"]["n"], 12)
        self.assertEqual(len(result["memory_pairs"]), 4)
        for row in result["rows"]:
            for stage in ("before", "after"):
                s = row[stage]
                self.assertEqual(s["passed"], sum(c["passed"] for c in s["checks"].values()))
                self.assertEqual(s["score_100"], round(100*s["passed"]/s["total"], 3))

    def test_authored_cases_include_detectable_regressions_for_every_platform(self):
        rows = [r for r in evaluate()["rows"] if r["origin"] == "authored_regression"]
        for platform in POLICIES:
            selected = [r for r in rows if r["platform"] == platform]
            self.assertTrue(any(r["delta"] < 0 for r in selected))
            self.assertTrue(any(r["delta"] > 0 for r in selected))

    def test_recorded_scores_and_fingerprints_reproduce(self):
        self.assertEqual(json.loads(OUTPUT.read_text(encoding="utf-8")), json.loads(json.dumps(evaluate())))

    def test_unknown_platform_and_malformed_slides_are_rejected(self):
        with self.assertRaises(ValueError): score({"text": "hi"}, "unknown", self.requirements)
        with self.assertRaises(ValueError): score({"text": "hi", "slides": [None]}, "instagram", self.requirements)
