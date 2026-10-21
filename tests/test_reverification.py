"""Isolated source-recheck regressions using scripted agents, never real AI."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import reverification
import storage


CLAIM = "Brew Mini includes a cleaning brush."


class ScriptedSourceRecheck:
    """One verifier response to exercise production persistence and gates."""
    mode = "live_mesh"

    def __init__(self, response=None, on_ask=None):
        self.call_count = 0
        self.requests = []
        self.on_ask = on_ask
        self.response = response if response is not None else dict(checks=[dict(
            claim=CLAIM, source_ids=["S1"], verdict="supported",
            reason="Scripted verdict; not measured model performance.",
            evidence=[dict(source_id="S1", quote=CLAIM)])], conflicts=[])

    def ask(self, role, data):
        if not role.startswith("Verifier:"):
            raise AssertionError("A targeted source recheck may invoke only the verifier")
        self.call_count += 1
        self.requests.append((role, copy.deepcopy(data)))
        if self.on_ask:
            self.on_ask()
        return copy.deepcopy(self.response)


class SourceReverificationTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).parents[1] / "data" / "evaluation-test-tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="reverification-", dir=temp_root)
        self.token = storage.database_override.set(str(Path(self.temp.name) / "isolated.db"))
        self.environment = patch.dict(os.environ, {"MESH_ENABLE_PAID": "0", "CREATOROS_MODE": "live"})
        self.environment.start()
        prior = dict(status="complete", passed=False, checks=[dict(claim=CLAIM,
            source_ids=["S1"], verdict="thin", reason="Earlier failed review retained as audit history.")])
        self.post = storage.save("post", dict(status="needs_review", approved=False,
            brand_id="synthetic-recheck-brand", platform="linkedin", text=CLAIM, slides=[],
            citations=[dict(claim=CLAIM, source_ids=["S1"])],
            sources=[dict(source_id="S1", title="Synthetic package contents", source_type="user_product_facts", excerpt=CLAIM)],
            drafts=[CLAIM],slide_versions=[[]],selected_draft_index=0,
            assessments=[dict(ready=True, action="accept", version=2)],
            verification=copy.deepcopy(prior), verification_history=[copy.deepcopy(prior)],
            evidence_review=dict(conflicts=[])), "synthetic-source-recheck-post")

    def tearDown(self):
        self.environment.stop()
        storage.database_override.reset(self.token)
        self.temp.cleanup()

    def test_same_request_replays_after_approval_without_another_mesh_call(self):
        mesh = ScriptedSourceRecheck()
        factory = Mock(return_value=mesh)
        first = reverification.recheck(self.post["id"], "request-idempotent-1", factory)
        self.assertEqual(first["status"], "completed")
        self.assertTrue(first["approved"])
        self.assertEqual(storage.get(self.post["id"])["status"], "approved")
        repeated = reverification.recheck(self.post["id"], "request-idempotent-1", factory)
        self.assertEqual(repeated, first)
        self.assertEqual(mesh.call_count, 1)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(len(storage.listing("verification_recheck")), 1)

    def test_new_recheck_requires_review_state_before_constructing_mesh(self):
        factory = Mock(side_effect=AssertionError("Unexpected paid client construction"))
        for status in ("approved", "scheduled", "ready_to_publish", "published", "generating", "failed"):
            with self.subTest(status=status):
                storage.save("post", dict(self.post, status=status), self.post["id"])
                with self.assertRaises(ValueError):
                    reverification.recheck(self.post["id"], "request-other-state-" + status, factory)
        factory.assert_not_called()
        self.assertEqual(storage.listing("verification_recheck"), [])

    def test_changed_caption_during_response_withholds_result_without_overwriting(self):
        changed_caption = "Brew Mini is awaiting a different review."
        def change_caption():
            current = storage.get(self.post["id"])
            storage.save("post", dict(current, text=changed_caption), current["id"])
        mesh = ScriptedSourceRecheck(on_ask=change_caption)
        operation = reverification.recheck(self.post["id"], "request-stale-caption", lambda: mesh)
        self.assertEqual(operation["status"], "stale")
        self.assertEqual(mesh.call_count, 1)
        saved = storage.get(self.post["id"])
        self.assertEqual(saved["text"], changed_caption)
        self.assertFalse(saved["approved"])
        self.assertEqual(saved["verification_history"], self.post["verification_history"])
        self.assertEqual(saved["verification"], self.post["verification"])
        self.assertEqual(storage.records_for_run("audit", self.post["id"])[-1]["detail"]["status"], "stale")

    def test_editorial_hold_added_during_response_cannot_be_overwritten(self):
        new_assessment = dict(ready=False, action="needs_review", version=3,
                              reason="Editorial approval revoked during source review.")
        def revoke_editorial_approval():
            current = storage.get(self.post["id"])
            current["assessments"].append(copy.deepcopy(new_assessment))
            storage.save("post", current, current["id"])
        mesh = ScriptedSourceRecheck(on_ask=revoke_editorial_approval)
        operation = reverification.recheck(self.post["id"], "request-editor-race", lambda: mesh)
        saved = storage.get(self.post["id"])
        self.assertEqual(operation["status"], "stale")
        self.assertEqual(mesh.call_count, 1)
        self.assertEqual(saved["assessments"][-1], new_assessment)
        self.assertFalse(saved["approved"])
        self.assertEqual(saved["status"], "needs_review")
        self.assertEqual(saved["verification"], self.post["verification"])
        self.assertEqual(saved["verification_history"], self.post["verification_history"])
        self.assertNotIn("grounded_report", saved)

    def test_status_change_during_response_cannot_be_replaced_with_approval(self):
        def change_status():
            current = storage.get(self.post["id"])
            storage.save("post", dict(current, status="failed"), current["id"])
        mesh = ScriptedSourceRecheck(on_ask=change_status)
        operation = reverification.recheck(self.post["id"], "request-status-race", lambda: mesh)
        saved = storage.get(self.post["id"])
        self.assertEqual(operation["status"], "stale")
        self.assertEqual(mesh.call_count, 1)
        self.assertEqual(saved["status"], "failed")
        self.assertFalse(saved["approved"])
        self.assertEqual(saved["verification"], self.post["verification"])
        self.assertEqual(saved["verification_history"], self.post["verification_history"])

    def test_supported_source_cannot_bypass_an_editorial_hold(self):
        self.post["assessments"] = [dict(ready=True, version=2), dict(ready=False, version=3)]
        storage.save("post", self.post, self.post["id"])
        mesh = ScriptedSourceRecheck()
        operation = reverification.recheck(self.post["id"], "request-editor-held", lambda: mesh)
        saved = storage.get(self.post["id"])
        self.assertTrue(saved["verification"]["passed"])
        self.assertTrue(saved["grounded_report"]["passed"])
        self.assertFalse(operation["editorial_ready"])
        self.assertFalse(operation["approved"])
        self.assertFalse(saved["approved"])
        self.assertEqual(saved["status"], "needs_review")

    def test_supported_recheck_preserves_prior_failed_verification_and_audit(self):
        mesh = ScriptedSourceRecheck()
        operation = reverification.recheck(self.post["id"], "request-preserve-history", lambda: mesh)
        saved = storage.get(self.post["id"])
        self.assertTrue(saved["verification"]["passed"])
        self.assertTrue(saved["grounded_report"]["passed"])
        self.assertEqual(len(saved["verification_history"]), 2)
        self.assertEqual(saved["verification_history"][0], self.post["verification_history"][0])
        self.assertFalse(saved["verification_history"][0]["passed"])
        self.assertEqual(saved["verification_history"][-1]["recheck_id"], operation["id"])
        audits = storage.records_for_run("audit", self.post["id"])
        self.assertEqual(audits[-1]["agent"], "source_recheck")
        self.assertEqual(audits[-1]["detail"]["recheck_id"], operation["id"])
        self.assertEqual(operation["ai_calls"], 1)
        self.assertEqual(len(mesh.requests), 1)
        self.assertEqual(mesh.requests[0][1]["sources"][0]["excerpt"], CLAIM)

    def test_malformed_verifier_reply_never_promotes_the_post(self):
        mesh = ScriptedSourceRecheck(dict(checks="not a check array", conflicts=[]))
        operation = reverification.recheck(self.post["id"], "request-malformed-reply", lambda: mesh)
        self.assertEqual(operation["status"], "needs_review")
        self.assertFalse(operation["approved"])
        saved = storage.get(self.post["id"])
        self.assertFalse(saved["approved"])
        self.assertEqual(saved["status"], "needs_review")
        self.assertFalse(saved["verification"]["passed"])
        self.assertEqual(saved["verification"]["status"], "invalid_verifier_output")
        self.assertEqual(mesh.call_count, 1)

    def test_missing_source_evidence_blocks_before_factory_or_paid_reservation(self):
        storage.save("post", dict(self.post, sources=[]), self.post["id"])
        factory = Mock(side_effect=AssertionError("A mesh client must never be constructed"))
        with self.assertRaises(ValueError):
            reverification.recheck(self.post["id"], "request-no-evidence", factory)
        factory.assert_not_called()
        self.assertEqual(storage.listing("verification_recheck"), [])

    def test_paid_lock_factory_failure_is_recorded_without_changing_post(self):
        factory = Mock(side_effect=ValueError("Paid Mesh calls are disabled."))
        with self.assertRaisesRegex(ValueError, "Paid Mesh calls are disabled"):
            reverification.recheck(self.post["id"], "request-paid-lock", factory)
        self.assertEqual(factory.call_count, 1)
        operations = storage.listing("verification_recheck")
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["status"], "failed")
        self.assertEqual(operations[0]["ai_calls"], 0)
        self.assertEqual(operations[0]["error_type"], "ValueError")
        self.assertEqual(storage.get(self.post["id"]), self.post)
        # Explicit request replay surfaces its recorded failure; it never silently
        # retries a paid operation when the same request is submitted twice.
        repeated = reverification.recheck(self.post["id"], "request-paid-lock", factory)
        self.assertEqual(repeated["status"], "failed")
        self.assertEqual(factory.call_count, 1)

    def test_same_request_cannot_reuse_results_after_evidence_changes(self):
        mesh = ScriptedSourceRecheck()
        factory = Mock(return_value=mesh)
        reverification.recheck(self.post["id"], "request-snapshot-guard", factory)
        changed = storage.get(self.post["id"])
        changed["sources"][0]["excerpt"] += " Source version changed."
        storage.save("post", changed, changed["id"])
        with self.assertRaises(ValueError):
            reverification.recheck(self.post["id"], "request-snapshot-guard", factory)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(mesh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
