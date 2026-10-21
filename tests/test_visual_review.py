"""Generated-image publication gates: local SQLite and mocked HTTP only."""
import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from PIL import Image

import instagram_publish as ig
import social
import storage
import visual_review


class VisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, dict(CREATOROS_DB=str(Path(self.temp.name)/'review.db'),
            INSTAGRAM_ENABLE_PUBLISHING='1', INSTAGRAM_ACCESS_TOKEN='synthetic-test-token'))
        self.env.start()
        self.addCleanup(self.env.stop)
        brand = storage.save('brand', dict(name='Synthetic brand'))
        buffer = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(buffer, 'PNG')
        self.post = storage.save('post', dict(brand_id=brand['id'], platform='instagram',
            status='approved', mode='live_mesh', text='The exact reviewed caption.',
            image='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()))
        self.connection = social.connect('instagram', brand['id'], '123')
        self.connection = storage.save('social_connection', dict(self.connection,
            status='authorized_unverified'), self.connection['id'])
        app = FastAPI()
        app.include_router(ig.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def approve(self):
        return visual_review.record(self.post['id'], visual_review.signature(storage.get(self.post['id'])),
                                    True, 'Checked artwork and caption.', True)

    def prepare(self):
        return ig.prepare(self.post['id'], self.connection['id'], 'https://assets.example.com/reviewed.jpg')

    def test_generated_post_requires_review_before_delivery(self):
        result = visual_review.status(self.post)
        self.assertEqual(result['status'], 'required')
        self.assertTrue(result['required'])
        self.assertNotIn(self.post['image'], str(result))
        with self.assertRaisesRegex(ValueError, 'Review the generated image'):
            self.prepare()
        self.assertEqual(storage.listing('instagram_delivery'), [])

    def test_review_is_explicit_and_cannot_approve_an_unseen_changed_asset(self):
        fingerprint = visual_review.signature(self.post)
        response = self.client.post('/posts/'+self.post['id']+'/visual-review', json={
            'fingerprint':fingerprint, 'approved':True})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/posts/'+self.post['id']+'/visual-review', json={
            'fingerprint':fingerprint, 'approved':'yes', 'confirm_review':True})
        self.assertEqual(response.status_code, 422)
        storage.save('post', dict(self.post, text='New caption requiring review.'), self.post['id'])
        response = self.client.post('/posts/'+self.post['id']+'/visual-review', json={
            'fingerprint':fingerprint, 'approved':True, 'confirm_review':True})
        self.assertEqual(response.status_code, 422)
        self.assertIn('changed', response.json()['detail'])
        self.assertEqual(storage.listing('visual_review'), [])

    def test_approval_endpoint_returns_safe_status_and_authorizes_prepare(self):
        endpoint = '/posts/'+self.post['id']+'/visual-review'
        status = self.client.get(endpoint).json()
        response = self.client.post(endpoint, json=dict(fingerprint=status['fingerprint'],
            approved=True, confirm_review=True, note='Artwork is legible and relevant.'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'approved')
        self.assertNotIn('data:image', response.text)
        self.assertNotIn(self.post['text'], response.text)
        self.assertEqual(self.prepare()['status'], 'prepared')
        self.assertEqual(len([a for a in storage.listing('audit') if a['agent']=='visual_reviewer']), 1)

    def test_changed_asset_or_caption_invalidates_approval_before_network(self):
        for field, value in [('image', self.post['image']+'changed'), ('text', 'A changed caption.')]:
            with self.subTest(field=field):
                storage.save('post', self.post, self.post['id'])
                self.approve()
                job = self.prepare()
                changed = storage.save('post', dict(self.post, **{field:value}), self.post['id'])
                self.assertEqual(visual_review.status(changed)['status'], 'stale')
                with httpx.Client(transport=httpx.MockTransport(lambda _: self.fail('Review failure must not contact Instagram'))) as client:
                    with self.assertRaises(ValueError):
                        ig.stage(job['id'], client)
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_explicit_hold_blocks_staged_publication_without_provider_call(self):
        self.approve()
        job = self.prepare()
        storage.save('instagram_delivery', dict(job, status='ready', account_id='123',
            username='reviewed_account', container_id='456'), job['id'])
        result = visual_review.record(self.post['id'], visual_review.signature(self.post), False,
            'The illustration contains garbled lettering.', True)
        self.assertEqual(result['status'], 'held')
        self.assertIn('garbled lettering', result['message'])
        with httpx.Client(transport=httpx.MockTransport(lambda _: self.fail('Held visual must not contact Instagram'))) as client:
            with self.assertRaisesRegex(ValueError, 'garbled lettering'):
                ig.publish(job['id'], 'reviewed_account', True, client)
        self.assertEqual(storage.get(job['id'])['status'], 'ready')
        self.assertEqual(storage.get(self.post['id'])['status'], 'approved')

    def test_hold_requires_a_clear_reason(self):
        with self.assertRaisesRegex(ValueError, 'clear reason'):
            visual_review.record(self.post['id'], visual_review.signature(self.post), False, '', True)
        self.assertEqual(storage.listing('visual_review'), [])

    def test_generated_provenance_requires_review_but_legacy_manual_asset_does_not(self):
        manual = dict(self.post)
        manual.pop('mode')
        storage.save('post', manual, self.post['id'])
        self.assertFalse(visual_review.required(manual))
        self.assertEqual(self.prepare()['status'], 'prepared')
        for marker in [dict(image_origin='mesh_generated'), dict(image_review='required'),
                       dict(mode='live'), dict(visual=dict(image_origin='mesh_generated'))]:
            with self.subTest(marker=marker):
                marked = dict(manual, **marker)
                self.assertTrue(visual_review.required(marked))
                with self.assertRaises(ValueError):
                    visual_review.ensure_reviewed(marked)


if __name__=='__main__':
    unittest.main()
