"""Run-history persistence and retrieval audits with local SQLite and mocked HTTP."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
import research
import storage
from run_audit import build_trail


class RunAuditTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "data"
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.override = storage.database_override.set(str(Path(self.temp.name) / "audit.db"))
        self.brand = storage.save("brand", dict(kind="brand", name="Brew"))
        self.post = storage.save("post", dict(kind="post", brand_id=self.brand["id"],
            brief="Brew features", platform="instagram", text="", status="generating", mode="live_mesh"))
        self.product = dict(name="Brew", url="https://brand.example/", details="Brew has two modes.")
        self.dns = patch("research.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 0))])
        self.dns.start()

    def tearDown(self):
        self.dns.stop()
        storage.database_override.reset(self.override)
        self.temp.cleanup()

    def events(self):
        return storage.records_for_run("audit", self.post["id"])

    def test_records_actual_questions_page_urls_document_query_and_skips(self):
        doc, _ = research.save_document(self.brand["id"], "brew.md", "Brew has two modes and a quiet motor.")
        seen = []
        def respond(request):
            seen.append(str(request.url))
            return httpx.Response(200, headers={"content-type":"text/html"}, text="<title>Brew</title><p>Brew has two modes.</p>")
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            sources, _ = research.gather(self.post["id"], self.brand["id"], "Brew features", self.product, client=client)
        events = self.events()
        plan = next(e["detail"] for e in events if e["agent"] == "research_plan")
        self.assertEqual([q["id"] for q in plan["questions"]], ["Q-product", "Q-documents", "Q-performance"])
        attempts = [e["detail"] for e in events if e["agent"] == "research_attempt"]
        pages = [a for a in attempts if a["action"] == "official_page_fetch"]
        self.assertEqual(seen, ["https://brand.example/"])
        self.assertEqual([a["status"] for a in pages], ["started", "retrieved"])
        self.assertEqual(pages[0]["attempt_id"], pages[1]["attempt_id"])
        self.assertEqual(pages[0]["url"], seen[0])
        lookup = next(a for a in attempts if a["action"] == "document_excerpt_lookup")
        self.assertEqual(lookup["document_id"], doc["id"])
        self.assertEqual(lookup["query"], "Brew Brew features")
        self.assertTrue(any(a["status"] == "skipped" for a in attempts))
        self.assertEqual(len(sources), 3)
        self.assertTrue(all(isinstance(s["excerpt"], str) for s in sources))
        self.assertIn("Brew has two modes.", next(s["excerpt"] for s in sources if s["source_type"] == "official_product_page"))

    def test_http_failure_remains_recorded_without_successful_source(self):
        with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(503))) as client:
            sources, warnings = research.gather(self.post["id"], self.brand["id"], "Brew features", self.product, client=client)
        attempts = [e["detail"] for e in self.events() if e["agent"] == "research_attempt"]
        failed = next(a for a in attempts if a["action"] == "official_page_fetch" and a["status"] == "failed")
        self.assertEqual(failed["http_status"], 503)
        self.assertFalse(any(s["source_type"] == "official_product_page" for s in sources))
        self.assertTrue(warnings)

    def test_retry_logs_thin_claim_questions_and_real_bounded_attempts(self):
        def respond(request):
            text = '<p>Brew product overview.</p><a href="/features">Brew features</a>' if request.url.path == "/" else '<p>Brew has two modes.</p>'
            return httpx.Response(200, headers={"content-type":"text/html"}, text=text)
        initial = [dict(source_id="S1", source_type="official_product_page", title="Brew", url="https://brand.example/", excerpt="Brew product overview.")]
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            extra, _ = research.gather_more(self.post["id"], self.brand["id"], "Brew features", self.product,
                ["Brew has two modes."], initial, client=client)
        trail = build_trail(self.post, self.events(), storage.records_for_run("research_source", self.post["id"]))
        self.assertEqual(trail["questions"][0]["id"], "Q-retry-1")
        self.assertIn("Brew has two modes.", trail["questions"][0]["question"])
        web = [s for s in trail["searches"] if s["action"] == "official_page_fetch" and s["status"] == "started"]
        self.assertEqual(len(web), 2)
        self.assertTrue(all(s["phase"] == "verification_retry" for s in web))
        self.assertEqual(extra[0]["source_id"], "S2")

    def test_export_keeps_rejections_after_correction_and_preserves_insertion_order(self):
        rejected = storage.audit(self.post["id"], "verification", dict(version=1, draft_version=2,
            checks=[dict(claim="Brew keeps coffee fresh for 30 days.", source_ids=[], verdict="unsupported", reason="No duration evidence.")]))
        passed = storage.audit(self.post["id"], "verification", dict(version=2, draft_version=3,
            checks=[dict(claim="Brew has two modes.", source_ids=["S1"], verdict="supported", reason="Product facts directly support it.")]))
        storage.audit("different-post", "verification", dict(checks=[]))
        trail = build_trail(self.post, self.events(), [])
        self.assertEqual([e["id"] for e in trail["timeline"]], [rejected["id"], passed["id"]])
        self.assertEqual(trail["rejected_claims"][0]["reason"], "No duration evidence.")
        self.assertEqual(trail["passed_claims"][0]["draft_version"], 3)
        self.assertEqual(trail["timeline"][1]["sequence"], 2)

    def test_failed_run_export_recovers_saved_evidence_and_never_invents_old_queries(self):
        storage.save("research_source", dict(post_id=self.post["id"], source_id="S1", source_type="user_product_facts",
            title="Brew facts", excerpt="Brew has two modes."))
        storage.audit(self.post["id"], "run_failed", dict(reason="Writer failed after retrieval."))
        post = dict(self.post, status="failed")
        trail = build_trail(post, self.events(), storage.records_for_run("research_source", post["id"]))
        self.assertEqual(trail["status"], "failed")
        self.assertEqual(trail["sources"][0]["source_id"], "S1")
        self.assertEqual(trail["questions"], [])
        self.assertEqual(trail["searches"], [])
        self.assertFalse(trail["grounded_report"]["passed"])

    def test_account_lookup_records_filters_without_connection_credentials(self):
        connection = storage.save("social_connection", dict(brand_id=self.brand["id"], provider="instagram", enabled=True,
            account_id="account1", encrypted_token="do-not-log-this"))
        research.gather(self.post["id"], self.brand["id"], "Brew features", dict(name="Brew"), platform="instagram")
        attempts = [e["detail"] for e in self.events() if e["agent"] == "research_attempt"]
        lookup = next(a for a in attempts if a["action"] == "stored_provider_observation_lookup")
        self.assertEqual(lookup["filters"]["connection_ids"], [connection["id"]])
        self.assertEqual(lookup["status"], "no_evidence")
        self.assertNotIn("do-not-log-this", json.dumps(self.events()))

    def test_api_exports_only_the_requested_runs_persisted_events_without_ai(self):
        import main
        event = storage.audit(self.post["id"], "run_failed", dict(reason="Example failure"))
        storage.audit("another-run", "run_completed", dict(reason="Other brand's run"))
        with patch("main.gateway", side_effect=AssertionError("Audit export must never call AI")):
            exported = main.audit_trail(self.post["id"])
        self.assertEqual(exported["post_id"], self.post["id"])
        self.assertEqual([e["id"] for e in exported["timeline"]], [event["id"]])


if __name__ == "__main__":
    unittest.main()
