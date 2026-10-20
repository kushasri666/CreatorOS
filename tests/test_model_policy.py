import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from model_policy import route, routes, image_model
from workflow import Mesh


class ModelPolicyTests(unittest.TestCase):
    def test_selected_models_are_in_checked_mesh_catalog_and_support_chat_json(self):
        catalog = json.loads(Path("docs/mesh-model-catalog-selection.json").read_text(encoding="utf-8"))
        models = {r["id"]: r for r in catalog["models"]}
        with patch.dict(os.environ, {}, clear=True):
            for selection in routes().values():
                row = models[selection["model"]]
                self.assertTrue(row["supports_completions_api"])
                self.assertTrue(row["supports_structured_output"])
            self.assertEqual(models[image_model()]["model_type"], "image")

    def test_explicit_agent_overrides_global_and_cap_is_preserved(self):
        with patch.dict(os.environ, {"MESH_TEXT_MODEL": "global/model",
                "MESH_WRITER_MODEL": "writer/model", "MESH_MAX_OUTPUT_TOKENS": "800"}, clear=True):
            self.assertEqual(route("Writer: create copy")["model"], "writer/model")
            self.assertEqual(route("Editor")["model"], "global/model")
            self.assertEqual(route("Writer")["max_tokens"], 800)
            self.assertEqual(route("Visual director")["max_tokens"], 400)

    def test_jev_cannot_silently_replace_a_text_agent(self):
        with patch.dict(os.environ, {"MESH_EDITOR_MODEL": "typesafe/jev-1.13"}, clear=True):
            with self.assertRaisesRegex(ValueError, "evaluation API"):
                route("Editor")

    def test_unrestricted_auto_routing_cannot_bypass_fixed_agent_selection(self):
        with patch.dict(os.environ, {"MESH_WRITER_MODEL": "auto"}, clear=True):
            with self.assertRaisesRegex(ValueError, "auto-routing is disabled"):
                route("Writer")

    def test_selected_route_and_token_limit_reach_sdk_without_extra_calls(self):
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"text":"A complete revised post.","citations":[]}'))]))
        mesh = Mesh.__new__(Mesh)
        mesh.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        mesh.metadata_only = False
        mesh.call_count = mesh.image_count = 0
        events = []
        mesh.observe = events.append
        with patch.dict(os.environ, {"MESH_CACHE_ENABLED": "0"}, clear=True):
            mesh.ask("Writer: write", {"platform": "linkedin"})
        self.assertEqual(create.call_args.kwargs["model"], "openai/gpt-4.1-mini")
        self.assertEqual(create.call_args.kwargs["max_tokens"], 1600)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(events[0]["requested_model"], "openai/gpt-4.1-mini")
