"""Hostile SDK responses at the real Mesh parser boundary; no inference/network."""
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import storage
from workflow import Mesh


class AdversarialGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.token=storage.database_override.set(self.temp.name+'/test.db')
        self.env=patch.dict(os.environ,dict(MESH_ENABLE_PAID='0',MESH_CACHE_ENABLED='1',MESH_FORMAT_RETRIES='0'))
        self.env.start()
    def tearDown(self):
        self.env.stop();storage.database_override.reset(self.token);self.temp.cleanup()

    def mesh(self,raw,finish='stop'):
        create=Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish,message=SimpleNamespace(content=raw))]))
        mesh=Mesh.__new__(Mesh)
        mesh.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        mesh.metadata_only=False;mesh.call_count=mesh.image_count=0;mesh.observe=lambda _:None
        return mesh,create

    def test_length_finish_never_becomes_valid_cached_content(self):
        mesh,create=self.mesh('{"text":"This looks complete but output was cut off.","citations":[]}',finish='length')
        with self.assertRaises(ValueError):mesh.ask('Writer: produce content',dict(platform='linkedin'))
        self.assertEqual(create.call_count,1)
        self.assertFalse(storage.listing('mesh_cache'))

    def test_invalid_field_types_are_not_cached_as_agent_success(self):
        cases=[('Writer',dict(text='A draft',citations='S1')),
            ('Visual director',dict(prompt=None,reason='A reason')),
            ('Learning analyst',dict(rule=[],reason='A reason')),
            ('Brand analyst',dict(tone=[],vocabulary=[],structure='Short',cta_habits='Ask',avoid=[],evidence=[])),
            ('Strategist',dict(angle=[],hook='Hook',audience='People',format='post',cta='Save',reason='Evidence',applied_learning_ids=[],source_ids=[])),
            ('Follow-up',dict(text='An answer',citations=[],limitations='No limitations'))]
        for role,result in cases:
            with self.subTest(role=role):
                mesh,create=self.mesh(json.dumps(result))
                with self.assertRaises(ValueError):mesh.ask(role+': produce structured result',dict(platform='linkedin'))
                self.assertEqual(create.call_count,1)
                self.assertFalse(storage.listing('mesh_cache'))

    def test_ambiguous_json_duplicate_keys_are_rejected(self):
        mesh,create=self.mesh('{"text":"One claim","text":"Conflicting claim","citations":[]}')
        with self.assertRaises(ValueError):mesh.ask('Writer: produce content',dict(platform='linkedin'))
        self.assertFalse(storage.listing('mesh_cache'))

    def test_nonfinite_scores_are_rejected_before_cache(self):
        mesh,create=self.mesh('{"scores":{"hook":NaN,"clarity":10,"voice":10,"platform":10,"cta":10},"edits":[],"reason":"Great"}')
        with self.assertRaises(ValueError):mesh.ask('Editor: review',dict(platform='linkedin'))
        self.assertFalse(storage.listing('mesh_cache'))

    def test_corrupt_cache_is_ignored_and_fresh_valid_result_replaces_it(self):
        mesh,create=self.mesh('{"text":"A valid complete draft","citations":[]}')
        role='Writer: produce content';data=dict(platform='linkedin')
        mesh.ask(role,data)
        cached=storage.listing('mesh_cache')[0]
        storage.save('mesh_cache',dict(cached,result=dict(text='Injected incomplete record',citations='wrong-type')),cached['id'])
        result=mesh.ask(role,data)
        self.assertEqual(result['text'],'A valid complete draft')
        self.assertEqual(create.call_count,2)

    def test_network_failure_is_not_retried_or_cached(self):
        import httpx
        mesh,create=self.mesh('{}')
        create.side_effect=httpx.ReadTimeout('Synthetic uncertain response')
        with self.assertRaises(httpx.ReadTimeout):mesh.ask('Writer: produce content',dict(platform='linkedin'))
        self.assertEqual(create.call_count,1)
        self.assertEqual(mesh.call_count,1)
        self.assertFalse(storage.listing('mesh_cache'))
