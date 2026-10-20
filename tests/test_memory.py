"""Evidence consistency and correction tests: no model or provider calls."""
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
import memory
import storage
import social
from prompt_policy import compact_data


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = storage.database_override.set(self.temp.name+'/memory.db')
        self.brand = storage.save('brand', dict(version=1, profile={'tone':'warm'}))
        self.post = storage.save('post', dict(brand_id=self.brand['id'], platform='instagram', text='Original'))
        self.metric = storage.save('metric', dict(post_id=self.post['id'], brand_id=self.brand['id'],
            platform='instagram', input={'source':'manual'}, observed_at=storage.now(), rate=.1))
        self.lesson = storage.save('learning', dict(brand_id=self.brand['id'], platform='instagram',
            post_id=self.post['id'], source='manual', evidence_id=self.metric['id'], rule='Test a story', reason='Explore'))
        memory.inspect(self.lesson)

    def tearDown(self):
        storage.database_override.reset(self.token)
        self.temp.cleanup()

    def test_fresh_is_tentative_and_cache_metadata_is_stable(self):
        first = memory.inspect(self.lesson)
        second = memory.inspect(self.lesson)
        self.assertTrue(first['memory']['usable'])
        self.assertIn('tentative', first['memory']['reason'])
        self.assertEqual(compact_data('Strategist', {'learnings':[first]}), compact_data('Strategist', {'learnings':[second]}))
        self.assertEqual(len(storage.listing('audit')), 1)

    def test_changed_metrics_withheld_without_deletion(self):
        storage.save('metric', dict(self.metric, rate=.9), self.metric['id'])
        self.assertFalse(memory.inspect(self.lesson)['memory']['usable'])
        self.assertEqual(memory.retrieve(self.brand['id'], 'instagram'), [])
        self.assertIsNotNone(storage.get(self.lesson['id']))

    def test_changed_content_brand_and_claim_are_detected(self):
        for kind, original, changes in [('post',self.post,{'text':'Changed'}),
                                        ('brand',self.brand,{'version':2}),
                                        ('learning',self.lesson,{'rule':'Unsupported replacement'})]:
            with self.subTest(kind=kind):
                storage.save(kind, dict(original, **changes), original['id'])
                self.assertFalse(memory.inspect(storage.get(self.lesson['id']))['memory']['usable'])
                storage.save(kind, original, original['id'])

    def test_missing_evidence_retained_as_stale(self):
        with storage.connection() as db:
            db.execute('DELETE FROM records WHERE id=?',(self.metric['id'],))
        self.assertIn('missing', memory.inspect(self.lesson)['memory']['reason'])
        self.assertIsNotNone(storage.get(self.lesson['id']))

    def test_scope_mismatch_and_old_evidence_are_blocked(self):
        for changes in ({'brand_id':'other'}, {'platform':'linkedin'},
                        {'observed_at':(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()}):
            with self.subTest(changes=changes):
                storage.save('metric',dict(self.metric, **changes),self.metric['id'])
                self.assertFalse(memory.inspect(self.lesson)['memory']['usable'])
        storage.save('metric', self.metric, self.metric['id'])
        self.assertTrue(memory.inspect(self.lesson)['memory']['usable'])

    def test_correction_versions_and_refresh_idempotence(self):
        connection = social.connect('instagram',self.brand['id'],'123')
        published=(datetime.now(timezone.utc)-timedelta(days=12)).isoformat()
        for i, format in enumerate(('story','story','checklist','checklist')):
            post=storage.save('post',dict(brand_id=self.brand['id'],platform='instagram'))
            tracking=social.track(connection,post,str(i+1),published,format)
            social.save_observation(connection,tracking,{'views':1000,'likes':100 if format=='story' else 20,'comments':10,'shares':5})
        social.learn_from_observations(self.brand['id'],'instagram')
        lesson=next(r for r in storage.listing('learning') if r.get('method')=='deterministic_observation')
        self.assertIn('story',lesson['rule'])
        social.learn_from_observations(self.brand['id'],'instagram')
        self.assertEqual(storage.get('memory:'+lesson['id'])['version'],1)
        for row in storage.listing('social_metric'):
            row['counts']['likes']=500 if row['counts']['likes']==20 else 10
            # Rate is derived from counts by dashboard, not accepted from prose.
            storage.save('social_metric',row,row['id'])
        memory.review(self.brand['id'],'instagram',refresh=True)
        corrected=storage.get(lesson['id'])
        self.assertIn('checklist',corrected['rule'])
        self.assertEqual(storage.get('memory:'+lesson['id'])['version'],2)
        self.assertEqual(len(storage.listing('memory_revision')),1)
        self.assertTrue(memory.inspect(corrected)['memory']['usable'])
        with storage.connection() as db:
            db.execute("DELETE FROM records WHERE kind='social_metric'")
        memory.review(self.brand['id'],'instagram',refresh=True)
        self.assertFalse(memory.inspect(corrected)['memory']['usable'])
