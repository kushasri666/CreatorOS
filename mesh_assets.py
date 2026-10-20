"""Import a known Mesh image CDN response for durable local video use. No AI."""
import base64
import io
from urllib.parse import urlsplit
import httpx

LIMIT=30_000_000
HOSTS={'im.runware.ai','oaidalleapiprodscus.blob.core.windows.net'}


def materialize(url,client=None):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Image asset host is not on the trusted Mesh CDN list')
    owned=client is None
    client=client or httpx.Client(timeout=30,follow_redirects=False)
    try:
        with client.stream('GET',url,headers={'Accept':'image/*'}) as response:
            response.raise_for_status()
            if response.is_redirect:raise ValueError('Image asset redirects are not followed')
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>LIMIT:raise ValueError('Image asset exceeds the 30 MB limit')
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or max(image.size)>8192:raise ValueError('Unsupported image asset')
            mime={'PNG':'png','JPEG':'jpeg','WEBP':'webp'}[image.format]
            image.verify()
        return 'data:image/'+mime+';base64,'+base64.b64encode(raw).decode()
    finally:
        if owned:client.close()
