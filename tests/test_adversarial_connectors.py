"""Adversarial delivery/collector journeys: real SQLite, HTTP transports only mocked.

No credentials, public social writes or AI requests are used in these tests.
"""
import base64
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import httpx
from PIL import Image

import instagram_publish as ig
import main
import social
import social_auth
import storage


class AdversarialConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            'CREATOROS_DB': str(Path(self.temp.name) / 'adversarial.db'),
            'CREATOROS_MODE': 'offline', 'MESH_ENABLE_PAID': '0',
            'CREATOROS_TOKEN_KEY': Fernet.generate_key().decode(),
            'INSTAGRAM_ENABLE_PUBLISHING': '1',
            'INSTAGRAM_ACCESS_TOKEN': 'offline-test-token',
            'THREADS_ACCESS_TOKEN': 'offline-test-token',
            'X_ACCESS_TOKEN': 'offline-test-token',
            'SOCIAL_ENABLE_PAID_X': '1',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.out = patch.object(ig, 'OUTPUT', Path(self.temp.name) / 'assets')
        self.out.start()
        self.addCleanup(self.out.stop)
        # Fail closed if any test accidentally enters generation.
        self.ai = patch('workflow.OpenAI', side_effect=AssertionError('No Mesh calls in offline adversarial tests'))
        self.ai.start()
        self.addCleanup(self.ai.stop)
        self.brand = storage.save('brand', {'name': 'Adversarial test brand', 'profile': {}})
        self.other_brand = storage.save('brand', {'name': 'Separate private brand', 'profile': {}})
        picture = io.BytesIO()
        Image.new('RGB', (32, 32), 'blue').save(picture, 'PNG')
        self.post = storage.save('post', {
            'brand_id': self.brand['id'], 'platform': 'instagram', 'status': 'approved',
            'text': 'Reviewed test caption.',
            'image': 'data:image/png;base64,' + base64.b64encode(picture.getvalue()).decode(),
        })
        self.connection = social.connect('instagram', self.brand['id'], '123')
        self.connection = storage.save('social_connection',
            dict(self.connection, status='authorized_unverified'), self.connection['id'])
        self.client = TestClient(main.api)

    def prepare(self):
        return ig.prepare(self.post['id'], self.connection['id'], 'https://assets.example.com/reviewed.jpg')

    def ready_delivery(self):
        def handler(request):
            if request.url.path.endswith('/me'):
                return httpx.Response(200, json={'id': '123', 'username': 'reviewed_account'})
            if request.url.path.endswith('/media'):
                return httpx.Response(200, json={'id': '456'})
            if request.url.path.endswith('/456'):
                return httpx.Response(200, json={'status_code': 'FINISHED'})
            raise AssertionError('Unexpected setup request')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            delivery = ig.stage(self.prepare()['id'], client)
            return ig.check(delivery['id'], client)

    def published_at(self):
        return (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    def test_wrong_brand_or_platform_preparation_has_no_delivery_side_effect(self):
        wrong_brand = social.connect('instagram', self.other_brand['id'], '789')
        wrong_platform = social.connect('threads', self.brand['id'], '123')
        for connection in (wrong_brand, wrong_platform):
            with self.subTest(connection=connection['provider']):
                response = self.client.post('/posts/' + self.post['id'] + '/instagram/delivery', json={
                    'connection_id': connection['id'], 'image_url': 'https://assets.example.com/reviewed.jpg'})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(storage.listing('instagram_delivery'), [])

    def test_staging_wrong_identity_never_creates_remote_container(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'id': '999', 'username': 'another_account'})
        delivery = self.prepare()
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError):
                ig.stage(delivery['id'], client)
        self.assertEqual([request.method for request in calls], ['GET'])
        self.assertEqual(storage.get(delivery['id'])['status'], 'prepared')

    def test_connection_account_change_after_staging_blocks_publish_before_network(self):
        delivery = self.ready_delivery()
        storage.save('social_connection', dict(self.connection, account_id='999'), self.connection['id'])
        with httpx.Client(transport=httpx.MockTransport(lambda _: self.fail('Changed account must not reach provider'))) as client:
            with self.assertRaises(ValueError):
                ig.publish(delivery['id'], 'reviewed_account', True, client)
        self.assertEqual(storage.get(delivery['id'])['status'], 'ready')
        self.assertEqual(storage.get(self.post['id'])['status'], 'approved')

    def test_publication_read_timeout_locks_delivery_and_preserves_approval(self):
        delivery = self.ready_delivery()
        calls = []
        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout('Ambiguous publication result', request=request)
        with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                ig.publish(delivery['id'], 'reviewed_account', True, client)
            self.assertEqual(storage.get(delivery['id'])['status'], 'publication_unknown')
            with self.assertRaises(ValueError):
                ig.publish(delivery['id'], 'reviewed_account', True, client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(storage.get(self.post['id'])['status'], 'approved')
        self.assertEqual(storage.listing('social_track'), [])

    def test_malformed_publication_success_is_not_accepted_or_retried(self):
        delivery = self.ready_delivery()
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'id': '<invalid-id>', 'error': 'Incomplete success'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError):
                ig.publish(delivery['id'], 'reviewed_account', True, client)
            with self.assertRaises(ValueError):
                ig.publish(delivery['id'], 'reviewed_account', True, client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(storage.get(delivery['id'])['status'], 'publication_unknown')
        self.assertFalse(storage.listing('social_metric'))

    def test_bookkeeping_failure_after_remote_success_cannot_duplicate_publication(self):
        delivery = self.ready_delivery()
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'id': '789'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with patch('social.track', side_effect=ValueError('Bookkeeping failed')):
                with self.assertRaises(ValueError):
                    ig.publish(delivery['id'], 'reviewed_account', True, client)
            repeated = ig.publish(delivery['id'], 'reviewed_account', True, client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(repeated['status'], 'published')
        self.assertEqual(storage.get(self.post['id'])['instagram_media_id'], '789')

    def test_revoked_approval_is_not_restored_by_due_scheduler_job(self):
        due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        storage.queue(self.post['id'], due)
        storage.save('post', dict(storage.get(self.post['id']), status='needs_review'), self.post['id'])
        storage.tick()
        self.assertEqual(storage.get(self.post['id'])['status'], 'needs_review')
        self.assertEqual(storage.tick(), 0)
        self.assertFalse(any(a['agent'] == 'scheduler' and
            a['detail'].get('reason') == 'Scheduled time reached; manual publishing handoff ready'
            for a in storage.listing('audit')))

    def test_x_foreign_author_metrics_do_not_enter_brand_evidence(self):
        connection = social.connect('x', self.brand['id'], '123', True)
        storage.save('social_connection', dict(connection, enabled=True), connection['id'])
        post = storage.save('post', {'brand_id': self.brand['id'], 'platform': 'x'})
        social.track(connection, post, '456', self.published_at(), 'text')
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            'data': {'id': '456', 'author_id': '999',
                'public_metrics': {'like_count': 10, 'impression_count': 100}}}))) as client:
            result = social.sync(connection['id'], client)
        self.assertNotEqual(result['status'], 'verified')
        self.assertEqual(storage.listing('social_metric'), [])
        self.assertEqual(social.dashboard(self.brand['id'], 'x')['rows'], [])

    def test_x_selected_handle_resolves_identity_then_collects_owned_post(self):
        for handle in ('reviewed_account', '@Reviewed_Account'):
            with self.subTest(handle=handle):
                connection = social.connect('x', self.brand['id'], handle, True)
                storage.save('social_connection', dict(connection, enabled=True), connection['id'])
                post = storage.save('post', {'brand_id': self.brand['id'], 'platform': 'x'})
                social.track(connection, post, '456', self.published_at(), 'text')
                calls = []
                def handler(request):
                    calls.append(request.url.path)
                    self.assertEqual(request.url.host, 'api.x.com')
                    if request.url.path == '/2/users/me':
                        return httpx.Response(200, json={'data': {'id': '123', 'username': 'reviewed_account'}})
                    if request.url.path == '/2/tweets/456':
                        return httpx.Response(200, json={'data': {'id': '456', 'author_id': '123',
                            'public_metrics': {'like_count': 10, 'impression_count': 100}}})
                    raise AssertionError('Unexpected identity request')
                with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                    result = social.sync(connection['id'], client)
                self.assertEqual(result['status'], 'verified')
                own_metrics = [row for row in storage.listing('social_metric') if row['connection_id'] == connection['id']]
                self.assertEqual(len(own_metrics), 1)
                self.assertEqual(own_metrics[0]['counts'], {'likes': 10, 'impressions': 100})
                self.assertEqual(calls.count('/2/users/me'), 1)
                self.assertEqual(calls.count('/2/tweets/456'), 1)

    def test_x_wrong_selected_handle_rejects_authenticated_users_metrics(self):
        connection = social.connect('x', self.brand['id'], '@different_account', True)
        storage.save('social_connection', dict(connection, enabled=True), connection['id'])
        post = storage.save('post', {'brand_id': self.brand['id'], 'platform': 'x'})
        social.track(connection, post, '456', self.published_at(), 'text')
        def handler(request):
            if request.url.path == '/2/users/me':
                return httpx.Response(200, json={'data': {'id': '123', 'username': 'reviewed_account'}})
            if request.url.path == '/2/tweets/456':
                return httpx.Response(200, json={'data': {'id': '456', 'author_id': '123',
                    'public_metrics': {'like_count': 10, 'impression_count': 100}}})
            raise AssertionError('Unexpected identity request')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = social.sync(connection['id'], client)
        self.assertNotEqual(result['status'], 'verified')
        self.assertEqual(storage.listing('social_metric'), [])
        self.assertEqual(storage.listing('learning'), [])

    def test_x_missing_author_id_is_not_treated_as_ownership(self):
        connection = social.connect('x', self.brand['id'], '123', True)
        storage.save('social_connection', dict(connection, enabled=True), connection['id'])
        post = storage.save('post', {'brand_id': self.brand['id'], 'platform': 'x'})
        social.track(connection, post, '456', self.published_at(), 'text')
        calls = []
        def handler(request):
            calls.append(request.url.path)
            self.assertEqual(request.url.path, '/2/tweets/456', 'Numeric account ID needs no identity read')
            return httpx.Response(200, json={'data': {'id': '456',
                'public_metrics': {'like_count': 10, 'impression_count': 100}}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = social.sync(connection['id'], client)
        self.assertEqual(calls, ['/2/tweets/456'])
        self.assertNotEqual(result['status'], 'verified')
        self.assertEqual(storage.listing('social_metric'), [])

    def test_partial_collector_timeout_retains_valid_evidence_without_zero_padding(self):
        connection = social.connect('threads', self.brand['id'], '123')
        storage.save('social_connection', dict(connection, enabled=True), connection['id'])
        for external_id in ('1', '2'):
            post = storage.save('post', {'brand_id': self.brand['id'], 'platform': 'threads'})
            social.track(connection, post, external_id, self.published_at(), 'text')
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, json={'data': [
                    {'name': 'views', 'values': [{'value': 100}]},
                    {'name': 'likes', 'values': [{'value': 7}]}]})
            raise httpx.ReadTimeout('Provider unavailable', request=request)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = social.sync(connection['id'], client)
            social.sync(connection['id'], client)
        self.assertEqual(len(calls), 2, 'The daily gate must prevent retry storms')
        self.assertNotEqual(result['status'], 'verified')
        metrics = storage.listing('social_metric')
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]['counts'], {'views': 100, 'likes': 7})
        self.assertNotIn('comments', metrics[0]['counts'])
        self.assertEqual(social.dashboard(self.other_brand['id'], 'threads')['rows'], [])

    def test_invalid_provider_counters_fail_closed_without_new_evidence(self):
        connection = social.connect('threads', self.brand['id'], '123')
        post = storage.save('post', {'brand_id': self.brand['id'], 'platform': 'threads'})
        tracking = social.track(connection, post, '1', self.published_at(), 'text')
        original = social.save_observation(connection, tracking, {'views': 100, 'likes': 7})
        for value in (-1, float('nan'), float('inf'), '999', True):
            with self.subTest(counter=repr(value)):
                with self.assertRaises(ValueError):
                    social.save_observation(connection, tracking, {'views': 100, 'likes': value})
        self.assertEqual(storage.listing('social_metric'), [original])

    def test_rotated_token_key_never_leaks_ciphertext_or_token_to_connection_response(self):
        social_auth.persist_token(self.connection['id'], {'access_token': 'secret-test-sentinel', 'expires_in': 3600})
        before = storage.listing('social_token')
        with patch.dict(os.environ, {'CREATOROS_TOKEN_KEY': Fernet.generate_key().decode()}):
            with httpx.Client(transport=httpx.MockTransport(lambda _: self.fail('Broken token cannot reach provider'))) as client:
                storage.save('social_connection', dict(self.connection, enabled=True), self.connection['id'])
                result = social.sync(self.connection['id'], client)
            response = self.client.get('/connections')
        self.assertEqual(result['status'], 'setup_required')
        serialized = response.text + json.dumps(result)
        self.assertNotIn('secret-test-sentinel', serialized)
        self.assertNotIn(before[0]['encrypted'], serialized)
        self.assertEqual(storage.listing('social_token'), before)
        self.assertEqual(storage.listing('social_metric'), [])
