import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

import httpx
import mesh_media
from prompt_policy import compact_data
import storage
from workflow import Mesh


class PromptMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CREATOROS_DB": self.temp.name+"/test.db", "MESH_CACHE_ENABLED": "1",
            "MESH_ENABLE_PAID": "0", "MESH_ENABLE_MEDIA_PAID": "0", "MESH_API_KEY": "test-only"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_compaction_preserves_publishable_content_and_all_voice_rules(self):
        data = dict(platform="instagram", brief="Exact user brief", limits={"instagram": 2200, "x": 280},
            voice=dict(tone="precise", vocabulary=["check"], structure="short", cta_habits="ask", avoid=["fabrication"], evidence=["Old sample"]),
            previous_draft="Do not shorten my draft", editor_feedback={"edits": ["Specific CTA"]},
            learnings=[{"id": str(i), "rule": "rule", "reason": "evidence", "raw_counter": 100} for i in range(5)])
        compact = compact_data("Writer", data)
        for key in ("brief", "previous_draft", "editor_feedback"):
            self.assertEqual(compact[key], data[key])
        self.assertEqual(compact["voice"]["avoid"], ["fabrication"])
        self.assertEqual(len(compact["learnings"]), 5)
        self.assertNotIn("raw_counter", compact["learnings"][0])
        self.assertIn("evidence", data["voice"])

    def test_identical_validated_request_is_cached_without_a_second_call(self):
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"text":"Full publishable copy","citations":[]}'))]))
        mesh = Mesh.__new__(Mesh)
        mesh.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        mesh.metadata_only = False
        mesh.call_count = mesh.image_count = 0
        events = []
        mesh.observe = events.append
        first = mesh.ask("Writer: return text", {"platform": "linkedin"})
        second = mesh.ask("Writer: return text", {"platform": "linkedin"})
        self.assertEqual(first, second)
        self.assertEqual(create.call_count, 1)
        self.assertTrue(events[-1]["cached"])
        mesh.metadata_only = True
        with self.assertRaises(ValueError):
            mesh.ask("Writer: return text", {"platform": "linkedin"})

    def test_paid_media_locked_by_default_and_never_calls_network(self):
        post = {"id": "p", "status": "approved"}
        with patch.dict(os.environ, {"MESH_VIDEO_MODEL": "test/model"}), httpx.Client(transport=httpx.MockTransport(lambda r: self.fail("network"))) as client:
            with self.assertRaises(ValueError):
                mesh_media.submit(post, "video", "A gentle product demonstration", client=client)

    def test_video_submission_and_poll_are_bounded_mesh_only(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "api.meshapi.ai")
            if request.method == "POST":
                self.assertEqual(json.loads(request.content)["duration"], 5)
                return httpx.Response(200, json={"id": "t-test", "status": "queued"})
            return httpx.Response(200, json={"id": "t-test", "status": "succeeded", "content": {"video_url": "https://cdn.example.com/output.mp4"}})
        env = {"MESH_ENABLE_PAID": "1", "MESH_ENABLE_MEDIA_PAID": "1", "MESH_MEDIA_SPEND_CAP_CONFIGURED": "1", "MESH_VIDEO_MODEL": "test/model"}
        with patch.dict(os.environ, env), httpx.Client(transport=httpx.MockTransport(handler)) as client:
            post = {"id": "p", "status": "approved"}
            result = mesh_media.submit(post, "video", "A gentle product demonstration", client=client)
            again = mesh_media.submit(post, "video", "A gentle product demonstration", client=client)
            self.assertEqual(result["id"], again["id"])
            with self.assertRaises(ValueError):
                mesh_media.submit(post, "video", "A completely different demonstration", client=client)
            self.assertEqual(mesh_media.poll(result["id"], client)["status"], "succeeded")
            self.assertEqual(len(calls), 2)

    def test_speech_wav_export_is_a_real_audio_asset(self):
        stream = io.BytesIO()
        with wave.open(stream, "wb") as audio:
            audio.setparams((1, 2, 8000, 8000, "NONE", "none"))
            audio.writeframes(b"\x01\x00"*8000)
        env = {"MESH_ENABLE_PAID": "1", "MESH_ENABLE_MEDIA_PAID": "1", "MESH_MEDIA_SPEND_CAP_CONFIGURED": "1",
               "MESH_SPEECH_MODEL": "test/voice", "MESH_SPEECH_VOICE": "test-voice"}
        with patch.dict(os.environ, env), patch.object(mesh_media, "DIRECTORY", Path(self.temp.name)), httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=stream.getvalue(), headers={"Content-Type": "audio/wav"}))) as client:
            result = mesh_media.submit({"id": "p", "status": "approved"}, "speech", "A calmer introduction.", client=client)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["duration_seconds"], 1)
            self.assertTrue((Path(self.temp.name)/result["file"]).exists())
