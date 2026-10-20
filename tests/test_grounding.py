"""Evidence integrity checks with synthetic source excerpts; no paid calls."""
import copy
import unittest
from grounding import build_report
from workflow import _validate_verifier_result


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.claim = "The grinder has 12 settings."
        self.source = dict(source_id="S1", id="source:test", source_type="official_product_page",
            title="Grinder specifications", url="https://brand.example/grinder", retrieved_at="2026-10-20T00:00:00Z",
            excerpt="Grinder specifications. The grinder has 12 settings. Available in black.")
        self.check = dict(claim=self.claim, source_ids=["S1"], verdict="supported",
            reason="Specifications directly state this feature.", evidence=[dict(source_id="S1", quote=self.claim)])

    def validate(self, check):
        return _validate_verifier_result(dict(checks=[check]), self.claim, [],
            [dict(claim=self.claim, source_ids=["S1"])], [self.source])

    def post(self):
        return dict(text=self.claim, slides=[], sources=[self.source], verification=self.validate(self.check))

    def test_report_carries_verbatim_quote_url_timestamp_and_snapshot_hash(self):
        report = build_report(self.post())
        self.assertTrue(report["passed"])
        self.assertEqual(report["claims"][0]["source_ids"], ["S1"])
        receipt = report["claims"][0]["evidence"][0]
        self.assertEqual(receipt["quote"], self.claim)
        self.assertEqual(self.source["excerpt"][receipt["quote_start"]:][:len(self.claim)], self.claim)
        self.assertEqual(report["sources"][0]["url"], self.source["url"])
        self.assertEqual(report["sources"][0]["retrieved_at"], self.source["retrieved_at"])
        self.assertEqual(receipt["excerpt_sha256"], report["sources"][0]["excerpt_sha256"])

    def test_invented_or_paraphrased_quotation_blocks_approval(self):
        check = copy.deepcopy(self.check)
        check["evidence"][0]["quote"] = "The grinder offers 12 adjustable settings."
        self.assertFalse(self.validate(check)["passed"])

    def test_supported_claim_without_quote_is_rejected(self):
        check = copy.deepcopy(self.check)
        check.pop("evidence")
        self.assertFalse(self.validate(check)["passed"])

    def test_quote_from_a_different_source_is_rejected(self):
        check = copy.deepcopy(self.check)
        check["evidence"][0]["source_id"] = "S99"
        self.assertFalse(self.validate(check)["passed"])

    def test_omitted_cited_claim_and_malformed_check_fail_closed(self):
        for checks in ([], [None]):
            result = _validate_verifier_result(dict(checks=checks), self.claim, [],
                [dict(claim=self.claim, source_ids=["S1"])], [self.source])
            self.assertFalse(result["passed"])

    def test_mutated_source_cannot_reuse_a_verified_receipt(self):
        post = self.post()
        post["sources"][0] = dict(self.source, excerpt=self.source["excerpt"] + " Later update.")
        report = build_report(post)
        self.assertFalse(report["passed"])
        self.assertFalse(report["claims"])

    def test_appending_uncited_content_invalidates_saved_report(self):
        post = self.post()
        post["grounded_report"] = build_report(post)
        post["text"] += " It also reduces energy use by 90%."
        report = build_report(post)
        self.assertFalse(report["passed"])
        self.assertTrue(report["content_changed_since_verification"])

    def test_fixture_or_legacy_post_never_inherits_verified_status(self):
        self.assertFalse(build_report(dict(text="A fictional sample post."))["passed"])


if __name__ == "__main__":
    unittest.main()
