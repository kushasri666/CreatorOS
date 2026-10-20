"""Contract tests use explicit deterministic doubles, never real AI calls."""
import os
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from types import SimpleNamespace
from fastapi.testclient import TestClient
import main
import storage
from workflow import Mesh, CRITERIA


class ScriptedMesh:
    mode = "offline_fixture"  # Contract fixtures do not claim to execute live source verification.
    calls = []
    unchanged = False
    invalid = False
    low = False

    def ask(self, role, data):
        self.calls.append((role, data))
        if role.startswith("Brand analyst"):
            return {"tone": "playful" if "coffee" in data["samples"][0] else "precise",
                    "evidence": data["samples"]}
        if role.startswith("Strategist"):
            learned = data["learnings"]
            return {"angle": "practical checklist" if learned else "overview",
                    "reason": "Testing a feedback hypothesis" if learned else "Explore initial angle",
                    "applied_learning_ids": [l["id"] for l in learned]}
        if role.startswith("Writer"):
            if not data["previous_draft"] or self.unchanged:
                return {"text": "AI safety matters. Learn more."}
            return {"text": "Your next AI release needs a safety check.\n\n"
                "1. Test failure cases.\n2. Assign a reviewer.\n3. Document a rollback.\n\n"
                + ("Try this checklist. " if data["learnings"] else "")
                + ("Brew a safer launch. " if data["voice"]["tone"] == "playful" else "Review the evidence. ")
                + ("What would you change?" if self.low and data["previous_draft"] != "AI safety matters. Learn more."
                   else "Which check would your team add?")}
        if role.startswith("Editor"):
            if self.invalid:
                return {"scores": {"hook": "great"}, "edits": []}
            return {"scores": dict.fromkeys(CRITERIA, 5 if self.low or len(data["draft"]) < 80 else 9),
                    "edits": ["Add three concrete steps and a specific audience question"],
                    "reason": "Actionability and CTA need specificity"}
        if role.startswith("Visual director"):
            return {"prompt": "Editorial illustration of a team reviewing AI release safety checks",
                    "reason": "Matches the actionable release checklist"}
        if role.startswith("Learning analyst"):
            return {"rule": "Test practical checklists with a question CTA", "reason":
                    "Exploratory normalized engagement evidence; not a causal conclusion"}
        raise AssertionError(role)

    def image(self, prompt):
        return "https://example.test/test-double.png"


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CREATOROS_DB": self.temp.name + "/test.db",
                                          "CREATOROS_MODE": "offline", "MESH_ENABLE_PAID": "0"})
        self.env.start()
        self.mock = patch("main.gateway", ScriptedMesh)
        self.mock.start()
        ScriptedMesh.calls = []
        ScriptedMesh.unchanged = ScriptedMesh.invalid = ScriptedMesh.low = False
        self.client = TestClient(main.api)

    def tearDown(self):
        self.mock.stop()
        self.env.stop()
        self.temp.cleanup()

    def brand(self, coffee=True):
        samples = [f"{'coffee' if coffee else 'Research'} sample {i}: we explain practical ideas with care." for i in range(3)]
        r = self.client.post("/brands", json={"name": "Brew" if coffee else "Lab", "samples": samples})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def generate(self, brand):
        return self.client.post("/generate", json={"brand_id": brand["id"], "topic": "AI safety", "platform": "linkedin"})

    def ready(self, post):
        due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        storage.queue(post["id"], due)
        self.assertEqual(storage.tick(), 1)
        self.assertEqual(storage.tick(), 0)

    def test_recorded_grounding_evaluation_endpoint_is_labeled_and_uses_no_ai(self):
        response=self.client.get("/evaluation/grounding")
        self.assertEqual(response.status_code,200,response.text)
        report=response.json()
        self.assertEqual(report["question_count"],24)
        self.assertTrue(report["prediction_origin"]["not_model_generated"])
        self.assertTrue(report["artifact_matches_current_code"])
        self.assertEqual(report["ai_calls"],0)
        self.assertEqual(ScriptedMesh.calls,[])

    def test_full_loop_and_brand_isolation(self):
        brand = self.brand()
        post = self.generate(brand).json()
        self.assertEqual(post["status"], "approved")
        self.assertNotEqual(post["drafts"][0], post["drafts"][1])
        self.ready(post)
        metrics = dict(event_id="24h", source="simulated", impressions=1000, likes=30, comments=8, saves=10)
        path = "/posts/" + post["id"] + "/metrics"
        first = self.client.post(path, json=metrics)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), self.client.post(path, json=metrics).json())
        self.assertEqual(len(storage.listing("learning")), 1)
        self.assertEqual(self.client.post(path, json=dict(metrics, likes=50)).status_code, 409)
        next_post = self.generate(brand).json()
        self.assertEqual(next_post["strategy"]["angle"], "practical checklist")
        self.assertTrue(next_post["strategy"]["applied_learning_ids"])
        other = self.generate(self.brand(False)).json()
        self.assertEqual(other["strategy"]["angle"], "overview")
        self.assertNotEqual(other["text"], next_post["text"])

    def test_validation_and_schedule(self):
        self.assertEqual(self.client.post("/brands", json={"name": "x", "samples": ["x"]}).status_code, 422)
        post = self.generate(self.brand()).json()
        path = "/posts/" + post["id"] + "/schedule"
        self.assertEqual(self.client.post(path, json={"scheduled_for": "2030-01-01T12:00:00"}).status_code, 422)
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.assertEqual(self.client.post(path, json={"scheduled_for": future}).status_code, 200)
        self.assertEqual(storage.tick(), 0)
        self.assertEqual(storage.get(post["id"])["status"], "scheduled")

    def test_bounded_low_quality(self):
        ScriptedMesh.low = True
        post = self.generate(self.brand()).json()
        self.assertEqual(post["status"], "needs_review")
        self.assertEqual(len(post["drafts"]), 3)
        self.assertEqual(self.client.post('/posts/'+post['id']+'/schedule', json={
            "scheduled_for": (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}).status_code, 409)

    def test_negative_feedback_and_source_isolation(self):
        brand = self.brand()
        post = self.generate(brand).json()
        self.ready(post)
        data = dict(event_id="first", source="simulated", impressions=100, likes=20, comments=5, saves=5)
        self.client.post('/posts/'+post['id']+'/metrics', json=data)
        second = self.generate(brand).json()
        self.ready(second)
        r = self.client.post('/posts/'+second['id']+'/metrics', json=dict(data, likes=1, comments=0, saves=0))
        self.assertAlmostEqual(r.json()["baseline"], .45)
        self.assertEqual(storage.listing("learning")[0]["direction"], "avoid_or_test")
        r = self.client.post('/posts/'+second['id']+'/metrics', json=dict(data, event_id="actual", source="user_entered"))
        self.assertIsNone(r.json()["baseline"])

    def test_invalid_review(self):
        ScriptedMesh.invalid = True
        r = self.generate(self.brand())
        self.assertEqual(r.status_code, 502)
        self.assertTrue(any(a["agent"] == "error" for a in storage.listing("audit")))

    def test_valid_metrics_survive_optional_learner_failure_without_retry(self):
        post=self.generate(self.brand()).json();self.ready(post)
        class BrokenLearner:
            mode='offline_fixture'
            calls=0
            def ask(self,*args):
                self.calls+=1
                raise ValueError('Malformed hypothesis')
        learner=BrokenLearner()
        data=dict(event_id='learner-failure',source='simulated',impressions=100,likes=10,comments=2,saves=3)
        with patch('main.gateway',return_value=learner):
            first=self.client.post('/posts/'+post['id']+'/metrics',json=data)
            second=self.client.post('/posts/'+post['id']+'/metrics',json=data)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['id'],second.json()['id'])
        self.assertEqual(learner.calls,1)
        lesson=storage.get(first.json()['learning_id'])
        self.assertEqual(lesson['method'],'deterministic_metric_fallback')
        self.assertEqual(lesson['mode'],'deterministic_evidence_fallback')
        self.assertEqual(lesson['source'],'simulated')
        self.assertAlmostEqual(first.json()['rate'],.23)

    def test_unchanged_revision_rejected(self):
        ScriptedMesh.unchanged = True
        self.assertEqual(self.generate(self.brand()).status_code, 502)

    def test_mesh_recovers_missing_writer_field(self):
        def response(text):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
        with patch.dict(os.environ, {"MESH_API_KEY": "test-only", "MESH_ENABLE_PAID": "1", "MESH_FORMAT_RETRIES": "1"}), patch("workflow.OpenAI") as client:
            client.return_value.chat.completions.create.side_effect = [
                response('{"post": "wrong field"}'), response('{"text": "corrected schema", "citations": []}')]
            result = Mesh().ask("Writer: return text.", {"brief": "AI safety"})
            self.assertEqual(result["text"], "corrected schema")
            self.assertEqual(client.call_args.kwargs["base_url"], "https://api.meshapi.ai/v1")

    def test_paid_calls_are_locked_and_metadata_cannot_generate(self):
        with patch.dict(os.environ, {"MESH_ENABLE_PAID": "0", "MESH_API_KEY": "test-only"}), patch("workflow.OpenAI") as client:
            with self.assertRaises(ValueError):
                Mesh()
            client.assert_not_called()
            metadata = Mesh(metadata_only=True)
            with self.assertRaises(ValueError):
                metadata.image("Test")
            client.return_value.images.generate.assert_not_called()

    def test_call_budget_prevents_extra_requests(self):
        with patch.dict(os.environ, {"MESH_ENABLE_PAID": "1", "MESH_API_KEY": "test-only", "MESH_MAX_CALLS": "1"}), patch("workflow.OpenAI") as client:
            mesh = Mesh()
            mesh.reserve()
            with self.assertRaises(ValueError):
                mesh.image("Test")
            client.return_value.images.generate.assert_not_called()

    def test_default_gateway_never_silently_uses_fixtures(self):
        from workflow import gateway
        with patch.dict(os.environ, {"MESH_ENABLE_PAID": "0"}), patch("workflow.OpenAI") as network:
            os.environ.pop("CREATOROS_MODE", None)
            with self.assertRaises(ValueError):
                gateway()
            network.assert_not_called()

    def test_recorded_evaluation_uses_real_dataset_without_api_calls(self):
        from evaluate import evaluate_recorded
        with patch("evaluate.Mesh") as network, redirect_stdout(io.StringIO()):
            result = evaluate_recorded(self.temp.name + '/scores.json')
        network.assert_not_called()
        self.assertEqual(result['mode'], 'recorded_live_rescore')
        self.assertEqual(result['n'], 8)
        self.assertEqual(result['mean_before'], 1.5)
        self.assertEqual(result['mean_after'], 1.625)

    def test_offline_scenario_and_scheduler_evidence(self):
        with patch("main.gateway", __import__('offline').OfflineGateway), patch("workflow.OpenAI") as network:
            scenario = self.client.post('/demo/coffee').json()
            bid = scenario['brand']['id']
            self.assertEqual(len(storage.listing('metric')), 6)
            self.client.post('/demo/coffee')
            self.assertEqual(len(storage.listing('metric')), 6)
            req = dict(brand_id=bid, topic=scenario['brief'], platform='instagram')
            p = self.client.post('/generate', json=req).json()
            self.assertEqual(p['mode'], 'offline_fixture')
            self.assertGreaterEqual(len(p['slides']), 6)
            self.assertEqual(p['schedule_recommendation']['basis'], 'simulated_metrics')
            baseline = self.client.post('/generate', json=dict(req, use_learnings=False)).json()
            self.assertEqual(baseline['used_learning_ids'], [])
            self.assertNotEqual(p['text'], baseline['text'])
            analytics = self.client.get('/analytics/'+bid+'/instagram').json()
            self.assertEqual(len(analytics['rows']), 6)
            self.assertEqual(self.client.get('/posts/'+p['id']+'/slot?timezone_name=invalid').status_code, 422)
            network.assert_not_called()

    def test_background_run_returns_id_and_persisted_trace(self):
        b = self.brand()
        response = self.client.post('/runs', json=dict(brand_id=b['id'], topic='A practical launch checklist', platform='linkedin'))
        self.assertEqual(response.status_code, 202)
        p = storage.get(response.json()['id'])
        self.assertEqual(p['status'], 'approved')
        trace = [a for a in storage.listing('audit') if a['post_id'] == p['id']]
        self.assertTrue(any(a['agent'] == 'agent_start' for a in trace))
        self.assertTrue(any(a['agent'] == 'scheduler' for a in trace))

    def test_scheduler_prefers_observed_evidence_and_analytics_deduplicates_snapshots(self):
        p = self.generate(self.brand()).json()
        self.ready(p)
        path = '/posts/'+p['id']+'/metrics'
        data = dict(event_id='observed1', source='user_entered', impressions=1000, likes=40, comments=10, saves=20)
        first = self.client.post(path, json=data).json()
        latest = self.client.post(path, json=dict(data,event_id='observed2',likes=45)).json()
        recommendation = self.client.get('/posts/'+p['id']+'/slot?timezone_name=UTC').json()
        self.assertEqual(recommendation['basis'], 'observed_metrics')
        self.assertEqual(recommendation['evidence_ids'], [latest['id']])
        rows = self.client.get('/analytics/'+p['brand_id']+'/linkedin').json()['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['input']['likes'], 45)
        other = self.generate(storage.get(p['brand_id'])).json()
        self.ready(other)
        comparison = self.client.post('/posts/'+other['id']+'/metrics', json=dict(data,event_id='second-post')).json()
        self.assertAlmostEqual(comparison['baseline'], latest['rate'])


if __name__ == "__main__":
    unittest.main()
