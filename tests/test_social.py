import base64
from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import httpx
import main
import social
import social_auth
import storage


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CREATOROS_DB": self.temp.name+"/test.db",
            "CREATOROS_TOKEN_KEY": Fernet.generate_key().decode(), "MESH_ENABLE_PAID": "0"})
        self.env.start()
        self.client = TestClient(main.api)
        self.brand = storage.save("brand", {"kind": "brand", "name": "Test", "profile": {"tone": "precise"}, "version": 1})

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_examples_cover_six_platforms_and_never_pollute_live_data(self):
        with patch("workflow.OpenAI", side_effect=AssertionError("No AI")):
            for provider in social.PLATFORMS:
                response = self.client.get("/social/examples/"+provider)
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual(len(data["rows"]), 4)
                self.assertEqual(data["comparisons"][0]["learning"]["source"], "simulated")
        self.assertFalse(storage.listing("social_metric"))
        self.assertFalse(storage.listing("learning"))

    def test_provider_contracts_preserve_missing_metrics(self):
        def handler(request):
            url = str(request.url)
            if "graph.instagram.com" in url:
                data = {"data": [{"name": "reach", "values": [{"value": 100}]}]} if "/insights" in url else {"id": "123", "like_count": 5, "comments_count": 2}
            elif "graph.threads.net" in url:
                data = {"data": [{"name": "views", "values": [{"value": 200}]}, {"name": "likes", "values": [{"value": 10}]}]}
            elif "api.x.com" in url:
                data = {"data": {"id": "123", "public_metrics": {"like_count": 6, "impression_count": 300}}}
            elif "youtube/v3" in url:
                data = {"items": [{"id": "abcdefghijk", "snippet": {"channelId": "UC-test"}, "statistics": {"viewCount": "99"}}]}
            elif "youtubeanalytics" in url:
                names = ["views", "likes", "comments", "shares", "estimatedMinutesWatched", "averageViewDuration"]
                data = {"columnHeaders": [{"name": k} for k in names], "rows": [[200, 10, 3, 2, 50, 15]]}
            elif "linkedin" in url:
                data = {"elements": [{"count": 100, "metricType": request.url.params["queryType"], "targetEntity": {"share": "urn:li:share:123"}}]}
            else:
                raise AssertionError(url)
            return httpx.Response(200, json=data)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, patch.dict(os.environ, {"SOCIAL_ENABLE_PAID_X": "1"}):
            for provider, id in (("instagram", "123"), ("threads", "123"), ("x", "123"), ("youtube", "abcdefghijk"), ("linkedin", "urn:li:share:123")):
                values, window = social.fetch(provider, id, "test-only", client, {"allow_paid_reads": True, "account_id": "UC-test"})
                self.assertTrue(values)
                self.assertNotIn("saves", values)
            self.assertTrue(window)

    def test_telegram_uses_read_only_session_and_does_not_increment_views(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        client = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(), is_user_authorized=AsyncMock(return_value=True),
            get_entity=AsyncMock(return_value="channel"), get_permissions=AsyncMock(return_value=SimpleNamespace(is_admin=True, is_creator=False)),
            get_messages=AsyncMock(return_value=SimpleNamespace(reactions=None)))
        class CallableClient:
            def __getattr__(self, key): return getattr(client, key)
            async def __call__(self, request):
                self.assert_increment = request.increment
                return SimpleNamespace(views=[SimpleNamespace(views=10, forwards=2)])
        wrapper = CallableClient()
        import asyncio
        with patch("telethon.TelegramClient", return_value=wrapper), patch.dict(os.environ, {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "test-only"}):
            counts = asyncio.run(social.telegram_counts("123", {"account_id": "@testchannel"}))
        self.assertFalse(wrapper.assert_increment)
        self.assertEqual(counts["views"], 10)

    def test_x_is_locked_without_both_opt_ins(self):
        with patch.dict(os.environ, {"SOCIAL_ENABLE_PAID_X": "0"}), httpx.Client(transport=httpx.MockTransport(lambda r: self.fail("network"))) as client:
            with self.assertRaises(ValueError):
                social.fetch("x", "123", "test", client, {"allow_paid_reads": True})

    def test_evidence_learning_isolated_by_source_and_account(self):
        connection = social.connect("instagram", self.brand["id"], "123")
        published = (datetime.now(timezone.utc)-timedelta(days=12)).isoformat()
        for i, format in enumerate(("story", "story", "checklist", "checklist")):
            p = storage.save("post", {"kind": "post", "brand_id": self.brand["id"], "platform": "instagram"})
            tracking = social.track(connection, p, str(i+1), published, format)
            counts = {"views": 1000, "likes": 100 if format == "story" else 20, "comments": 10, "shares": 5}
            social.save_observation(connection, tracking, counts)
            social.save_observation(connection, tracking, counts)  # Same day does not multiply evidence.
        self.assertEqual(len(storage.listing("social_metric")), 4)
        social.learn_from_observations(self.brand["id"], "instagram")
        learning = storage.listing("learning")[0]
        self.assertIn("story", learning["rule"])
        self.assertEqual(len(learning["evidence_ids"]), 4)
        # Verify the persisted evidence reaches the next coordinator run, without AI.
        from offline import OfflineGateway
        with patch("main.gateway", return_value=OfflineGateway()):
            response = self.client.post("/generate", json={"brand_id": self.brand["id"],
                "platform": "instagram", "topic": "Useful coffee habits", "product_name": "Test coffee",
                "connection_id": connection["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(learning["id"], response.json()["used_learning_ids"])
        self.assertIn(learning["rule"], response.json()["strategy"]["reason"])
        self.assertEqual(social.dashboard("other-brand", "instagram")["rows"], [])
        # Same brand, different account cannot inherit a format comparison.
        other = social.connect("instagram", self.brand["id"], "456")
        p = storage.save("post", {"kind": "post", "brand_id": self.brand["id"], "platform": "instagram"})
        t = social.track(other, p, "99", published, "reel")
        social.save_observation(other, t, {"views": 100, "likes": 99}, source="simulated")
        social.learn_from_observations(self.brand["id"], "instagram")
        self.assertEqual(len(storage.listing("learning")), 1)

    def test_oauth_state_bound_to_browser_single_use_and_tokens_encrypted(self):
        connection = social.connect("youtube", self.brand["id"], "")
        env = {"YOUTUBE_CLIENT_ID": "test-id", "YOUTUBE_CLIENT_SECRET": "test-secret"}
        with patch.dict(os.environ, env):
            url, cookie = social_auth.begin(connection)
            params = parse_qs(urlparse(url).query)
            state = params["state"][0]
            self.assertIn("code_challenge", params)
            with self.assertRaises(ValueError):
                social_auth.consume_state("youtube", state, "wrong-browser")
            social_auth.consume_state("youtube", state, cookie)
            with self.assertRaises(ValueError):
                social_auth.consume_state("youtube", state, cookie)
            social_auth.persist_token(connection["id"], {"access_token": "private-test-token", "expires_in": 3600})
            self.assertNotIn("private-test-token", json.dumps(storage.listing("social_token")))
            self.assertEqual(social_auth.access_token(connection), "private-test-token")
            self.assertNotIn("private-test-token", self.client.get("/connections").text)
            social_auth.disconnect(connection["id"])
            self.assertFalse(storage.listing("social_token"))

    def test_api_auth_error_preserves_prior_evidence_and_daily_gate(self):
        connection = social.connect("threads", self.brand["id"], "")
        storage.save("social_connection", dict(connection, enabled=True), connection["id"])
        p = storage.save("post", {"kind": "post", "brand_id": self.brand["id"], "platform": "threads"})
        t = social.track(connection, p, "123", (datetime.now(timezone.utc)-timedelta(days=5)).isoformat(), "text")
        social.save_observation(connection, t, {"views": 10, "likes": 2})
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(401)
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "test-only"}), httpx.Client(transport=httpx.MockTransport(handler)) as client:
            self.assertEqual(social.sync(connection["id"], client)["status"], "reauthorize")
            social.sync(connection["id"], client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(storage.listing("social_metric")), 1)

    def test_discovery_is_bounded_and_deduplicated(self):
        connection = social.connect("threads", self.brand["id"], "")
        body = {"data": [{"id": "123", "text": "A real API-imported text fixture", "timestamp": "2026-10-01T10:00:00+00:00", "media_type": "TEXT_POST"}]}
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "test-only"}), httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))) as client:
            rows = social.discover(connection["id"], client)
            self.assertEqual(rows[0]["mode"], "imported_api")
            with self.assertRaises(ValueError):
                social.discover(connection["id"], client)
        self.assertEqual(len(storage.listing("post")), 1)
