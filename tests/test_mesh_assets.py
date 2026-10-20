import io
import unittest
from unittest.mock import patch
import httpx
from PIL import Image
from mesh_assets import materialize


class MeshAssetTests(unittest.TestCase):
    def test_known_image_is_downloaded_without_credentials_and_made_durable(self):
        buf=io.BytesIO();Image.new('RGB',(32,32),'green').save(buf,'PNG')
        def handler(request):
            self.assertNotIn('authorization',request.headers)
            return httpx.Response(200,content=buf.getvalue())
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=materialize('https://im.runware.ai/example.png',client)
        self.assertTrue(result.startswith('data:image/png;base64,'))
    def test_unknown_hosts_redirects_and_invalid_bytes_are_rejected(self):
        for url in ['http://im.runware.ai/x','https://localhost/x','https://example.com/x','https://user:secret@im.runware.ai/x']:
            with self.assertRaises(ValueError):materialize(url)
        for response in [httpx.Response(302,headers={'location':'http://127.0.0.1/'}),httpx.Response(200,content=b'not an image')]:
            with httpx.Client(transport=httpx.MockTransport(lambda request,r=response:r)) as client:
                with self.assertRaises(Exception):materialize('https://im.runware.ai/x',client)
    def test_oversized_asset_is_rejected(self):
        with patch('mesh_assets.LIMIT',3),httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'1234'))) as client:
            with self.assertRaises(ValueError):materialize('https://im.runware.ai/x',client)
