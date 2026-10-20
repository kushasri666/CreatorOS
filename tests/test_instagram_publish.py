import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from PIL import Image

import instagram_publish as ig
import social
import storage


class InstagramPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'CREATOROS_DB':self.temp.name+'/test.db',
            'INSTAGRAM_ENABLE_PUBLISHING':'1','INSTAGRAM_ACCESS_TOKEN':'test-only'})
        self.env.start()
        self.output=patch.object(ig,'OUTPUT',Path(self.temp.name)/'assets');self.output.start()
        b=storage.save('brand',{'name':'Test'})
        buffer=io.BytesIO();Image.new('RGB',(100,100),'purple').save(buffer,'PNG')
        self.post=storage.save('post',dict(brand_id=b['id'],platform='instagram',status='approved',
            text='A reviewed caption',image='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()))
        self.conn=social.connect('instagram',b['id'],'123')
        self.conn=storage.save('social_connection',dict(self.conn,status='authorized_unverified'),self.conn['id'])

    def tearDown(self):
        self.output.stop();self.env.stop();self.temp.cleanup()

    def job(self):
        return ig.prepare(self.post['id'],self.conn['id'],'https://assets.example.com/reviewed.jpg')

    def test_export_and_preparation_are_local_idempotent_and_do_not_publish(self):
        path=ig.jpeg(self.post)
        with Image.open(path) as image:
            self.assertEqual(image.format,'JPEG');self.assertEqual(image.size,(1080,1080))
        first=self.job();self.assertEqual(first['id'],self.job()['id'])
        self.assertEqual(first['status'],'prepared')
        self.assertEqual(len(storage.listing('instagram_delivery')),1)
        for url in ('http://assets.example.com/x.jpg','https://127.0.0.1/x.jpg','https://localhost/x.jpg','data:image/jpeg;base64,abc'):
            with self.assertRaises(ValueError):ig.public_url(url)

    def test_confirmed_flow_and_repeat_publish_do_not_duplicate(self):
        requests=[]
        def handler(req):
            requests.append(req)
            self.assertEqual(req.url.host,'graph.instagram.com')
            self.assertNotIn('access_token',str(req.url))
            if req.url.path.endswith('/me'):return httpx.Response(200,json={'id':'123','username':'reviewed_account'})
            if req.url.path.endswith('/media'):return httpx.Response(200,json={'id':'456'})
            if req.url.path.endswith('/456'):return httpx.Response(200,json={'status_code':'FINISHED'})
            if req.url.path.endswith('/media_publish'):return httpx.Response(200,json={'id':'789'})
            if req.url.path.endswith('/789'):return httpx.Response(200,json={'id':'789','like_count':12,'comments_count':2,'media_type':'IMAGE'})
            if req.url.path.endswith('/789/insights'):return httpx.Response(200,json={'data':[
                {'name':k,'values':[{'value':v}]} for k,v in dict(reach=100,saved=4,shares=1,views=150).items()]})
            raise AssertionError(str(req.url))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            job=ig.stage(self.job()['id'],client)
            self.assertEqual(job['status'],'container_created')
            job=ig.check(job['id'],client)
            with self.assertRaises(ValueError):ig.publish(job['id'],'wrong-account',True,client)
            with self.assertRaises(ValueError):ig.publish(job['id'],'reviewed_account',False,client)
            result=ig.publish(job['id'],'@reviewed_account',True,client)
            self.assertEqual(result['status'],'published')
            count=len(requests)
            self.assertEqual(ig.publish(job['id'],'reviewed_account',True,client)['external_id'],'789')
            self.assertEqual(len(requests),count)
            # Exercise the actual collector after the publishing adapter links
            # the returned media ID. Only the HTTP transport is mocked.
            storage.save('social_connection',dict(self.conn,enabled=True),self.conn['id'])
            self.assertEqual(social.sync(self.conn['id'],client)['status'],'verified')
            observations=storage.listing('social_metric')
            self.assertEqual(len(observations),1)
            self.assertEqual(observations[0]['external_id'],'789')
            self.assertEqual(observations[0]['counts']['likes'],12)
        self.assertEqual(sum(r.method=='POST' for r in requests),2)
        self.assertEqual(storage.get(self.post['id'])['status'],'published')
        self.assertEqual(len(storage.listing('social_track')),1)

    def test_disabled_publication_and_changed_post_block_network(self):
        job=self.job()
        with httpx.Client(transport=httpx.MockTransport(lambda _: self.fail('No network expected'))) as client:
            with patch.dict(os.environ,{'INSTAGRAM_ENABLE_PUBLISHING':'0'}):
                with self.assertRaises(ValueError):ig.stage(job['id'],client)
            storage.save('post',dict(self.post,text='Changed caption'),self.post['id'])
            with self.assertRaises(ValueError):ig.stage(job['id'],client)

    def test_uncertain_container_creation_is_never_automatically_retried(self):
        posts=[]
        def handler(req):
            if req.method=='GET':return httpx.Response(200,json={'id':'123','username':'reviewed_account'})
            posts.append(req)
            raise httpx.ReadTimeout('Test ambiguous outcome')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            job=self.job()
            with self.assertRaises(httpx.ReadTimeout):ig.stage(job['id'],client)
            self.assertEqual(storage.get(job['id'])['status'],'container_creation_unknown')
            with self.assertRaises(ValueError):ig.stage(job['id'],client)
        self.assertEqual(len(posts),1)
