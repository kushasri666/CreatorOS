"""Mock provider + scripted agents: end-to-end wiring proof, NOT live model efficacy."""
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from unittest.mock import patch
import httpx
from fastapi import BackgroundTasks, HTTPException

import main
import memory
import social
import storage
from workflow import run_pipeline, CRITERIA
from platform_formats import FORMATS
from prompt_policy import compact_data


class AdaptiveFixture:
    mode="offline_fixture"
    def __init__(self):self.drafts=0;self.calls=[]
    def ask(self,role,data):
        self.calls.append((role,data))
        if role.startswith("Strategist"):
            learned=data["learnings"]
            experiment=learned[0]["experiment"] if learned else {}
            return dict(angle=experiment.get("preferred_format","baseline"),format=data["format_contract"]["format"],
                applied_learning_ids=[l["id"] for l in learned],reason="Scripted response to the actual derived experiment")
        if role.startswith("Writer"):
            self.drafts+=1
            angle=data["strategy"]["angle"]
            return dict(text=f"Our coffee guide explores {angle} ideas. Save this guide {self.drafts}.",
                slides=[f"Explore coffee ideas with {angle}","Try one small brewing change",f"Save version {self.drafts}"],citations=[])
        if role.startswith("Editor"):return dict(scores=dict.fromkeys(CRITERIA,9.2),edits=[],reason="Scripted passing review")
        if role.startswith("Visual"):return dict(prompt="Coffee illustration",reason="Fixture prompt only")
        raise AssertionError(role)


class FeedbackCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.token=storage.database_override.set(self.temp.name+'/test.db')
        self.env=patch.dict(os.environ,{"MESH_ENABLE_PAID":"0","INSTAGRAM_ACCESS_TOKEN":"test-only","CREATOROS_MODE":"offline"})
        self.env.start()
        self.brand=storage.save('brand',dict(kind='brand',name='Fixture brand',profile={'tone':'clear'},version=1))
        self.connection=social.connect('instagram',self.brand['id'],'123')
    def tearDown(self):
        self.env.stop();storage.database_override.reset(self.token);self.temp.cleanup()

    def observations(self,invert=False):
        published=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
        def handler(request):
            identifier=request.url.path.split('/')[-2] if request.url.path.endswith('/insights') else request.url.path.split('/')[-1]
            if request.url.path.endswith('/insights'):
                return httpx.Response(200,json={'data':[{'name':k,'values':[{'value':v}]} for k,v in dict(views=100,reach=100,saved=0,shares=0).items()]})
            higher=(int(identifier)<102) != invert
            return httpx.Response(200,json=dict(id=identifier,like_count=20 if higher else 2,comments_count=0,media_type='IMAGE'))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            for i in range(4):
                external=str(100+i)
                post=storage.get('fixture-post-'+external) or storage.save('post',dict(brand_id=self.brand['id'],platform='instagram',text='Mock provider content '+external), 'fixture-post-'+external)
                tracking=social.track(self.connection,post,external,published,'carousel' if i<2 else 'single_image')
                counts,window=social.fetch('instagram',external,'test-only',client,self.connection)
                social.save_observation(self.connection,tracking,counts,window)
        social.learn_from_observations(self.brand['id'],'instagram')

    def generate(self,learned=True):
        lessons=memory.retrieve(self.brand['id'],'instagram',self.connection['id']) if learned else []
        gateway=AdaptiveFixture()
        result=run_pipeline(gateway,'Better home coffee','instagram',self.brand['profile'],lessons,lambda *_:None,generate_image=False)
        return result,gateway

    def test_provider_metrics_change_next_draft_and_changed_winner_changes_it_again(self):
        self.observations()
        baseline,_=self.generate(False)
        learned,gateway=self.generate()
        self.assertNotEqual(baseline['text'],learned['text'])
        self.assertEqual(learned['strategy']['angle'],'carousel')
        self.assertTrue(learned['strategy']['applied_learning_ids'])
        lesson=memory.retrieve(self.brand['id'],'instagram',self.connection['id'])[0]
        self.assertEqual(lesson['experiment']['preferred_posts'],2)
        self.assertAlmostEqual(lesson['experiment']['preferred_mean_rate'],.2)
        self.assertEqual(lesson['source'],'api')  # synthetic transport, isolated test DB only
        compact=compact_data('Strategist: choose',gateway.calls[0][1])
        self.assertEqual(compact['learnings'][0]['experiment']['preferred_format'],'carousel')
        self.observations(invert=True)
        changed,_=self.generate()
        self.assertEqual(changed['strategy']['angle'],'single_image')
        self.assertNotEqual(changed['text'],learned['text'])
        self.assertTrue(storage.listing('memory_revision'))

    def test_experiment_tampering_is_detected_and_other_accounts_do_not_reuse_it(self):
        self.observations()
        lesson=memory.retrieve(self.brand['id'],'instagram',self.connection['id'])[0]
        changed=dict(lesson,experiment=dict(lesson['experiment'],preferred_format='invented'))
        self.assertFalse(memory.inspect(changed)['memory']['usable'])
        self.assertEqual(memory.retrieve(self.brand['id'],'instagram','unrelated-account'),[])
        self.assertEqual(memory.retrieve(self.brand['id'],'youtube',self.connection['id']),[])

    def test_adaptation_plan_is_free_and_one_idea_has_six_native_formats(self):
        source=storage.save('post',dict(kind='post',brand_id=self.brand['id'],brief='Better home coffee',platform='instagram',status='approved'))
        plan=main.adaptation_plan(source['id'])
        self.assertEqual(plan['ai_calls'],0)
        self.assertEqual(set(plan['platforms']),set(FORMATS))
        self.assertEqual(len({v['format'] for v in plan['platforms'].values()}),6)
        tasks=BackgroundTasks()
        with patch('main.gateway',side_effect=AssertionError('Queue creation must not call AI')):
            post=main.adapt_post(source['id'],main.AdaptRequest(platform='youtube'),tasks)
        self.assertEqual(post['adaptation_of'],source['id'])
        self.assertEqual(post['brief'],source['brief'])
        self.assertEqual(post['brand_id'],source['brand_id'])
        self.assertEqual(post['platform'],'youtube')
        self.assertEqual(len(tasks.tasks),1)
        with self.assertRaises(HTTPException):main.adapt_post(source['id'],main.AdaptRequest(platform='instagram'),BackgroundTasks())

    def test_same_idea_pipeline_receives_native_format_in_each_agent(self):
        for platform in FORMATS:
            gateway=AdaptiveFixture()
            result=run_pipeline(gateway,'Better home coffee',platform,self.brand['profile'],[],lambda *_:None,generate_image=False)
            self.assertEqual(result['format_contract']['format'],FORMATS[platform]['format'])
            for role,data in gateway.calls:
                if role.startswith(('Strategist','Writer','Editor')):
                    self.assertEqual(data['brief'],'Better home coffee')
                    self.assertEqual(data['format_contract']['platform'],platform)
