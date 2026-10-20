import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from workflow import Mesh


class WriterSchemaTests(unittest.TestCase):
    def test_instagram_schema_explicitly_allows_slides(self):
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps({"text": "Caption",
                "slides": ["Hook", "Useful idea", "Call to action"], "citations": []})))]))
        mesh = Mesh.__new__(Mesh)
        mesh.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        mesh.metadata_only = False
        mesh.call_count = mesh.image_count = 0
        mesh.observe = lambda event: None
        with patch.dict("os.environ", {"MESH_FORMAT_RETRIES": "0", "MESH_CACHE_ENABLED": "0"}):
            result = mesh.ask("Writer: return caption and slides", {"platform": "instagram"})
        schema_text = create.call_args.kwargs["messages"][0]["content"]
        self.assertIn('"slides"', schema_text)
        self.assertEqual(len(result["slides"]), 3)
        self.assertEqual(create.call_count, 1)
