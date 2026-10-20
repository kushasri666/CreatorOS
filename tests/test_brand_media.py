"""Real local file/SQLite uploads and ASGI round trips; no AI or provider calls."""
import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import httpx
import brand_media
import research
import storage


async def chunks(data):
    # Small chunks exercise headers split over transport boundaries.
    for start in range(0,len(data),3): yield data[start:start+3]


def wav_bytes():
    output=io.BytesIO()
    with wave.open(output,"wb") as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b"\0\0"*80)
    return output.getvalue()


class BrandMediaTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/"data";root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.override=storage.database_override.set(str(Path(self.temp.name)/"media.db"))
        self.folder=Path(self.temp.name)/"files"
        self.patch=patch.object(brand_media,"MEDIA_ROOT",self.folder);self.patch.start()
        self.brand=storage.save("brand",dict(kind="brand",name="Brew"))
        self.other=storage.save("brand",dict(kind="brand",name="Other"))

    def tearDown(self):
        self.patch.stop();storage.database_override.reset(self.override);self.temp.cleanup()

    def upload(self,filename="clip.wav",data=None,brand_id=None):
        return asyncio.run(brand_media.save_media(brand_id or self.brand["id"],filename,chunks(wav_bytes() if data is None else data)))

    def test_audio_is_stored_byte_for_byte_and_duplicate_reuses_one_record(self):
        doc,created=self.upload();again,recreated=self.upload(filename="same-audio.wav")
        self.assertTrue(created);self.assertFalse(recreated);self.assertEqual(doc["id"],again["id"])
        self.assertEqual(brand_media.media_path(doc).read_bytes(),wav_bytes())
        self.assertEqual(doc["media_type"],"audio")
        self.assertEqual(len(storage.listing("research_document")),1)
        self.assertFalse(list(self.folder.rglob("*.part")))

    def test_video_container_upload_has_video_metadata_and_is_brand_scoped(self):
        # This checks an MP4 signature, not codec decoding or playable frames.
        doc,_=self.upload("product.mp4",b"\x00\x00\x00\x18ftypisom"+b"\x00"*20)
        self.assertEqual(doc["mime_type"],"video/mp4")
        self.assertEqual(doc["media_type"],"video")
        with self.assertRaises(brand_media.UploadError) as failure:
            brand_media.get_media(self.other["id"],doc["id"])
        self.assertEqual(failure.exception.status,404)

    def test_bad_signature_path_and_unsupported_extension_are_rejected(self):
        for filename,data in (("fake.mp4",b"<html>not video</html>"),("../clip.wav",wav_bytes()),("payload.html",wav_bytes())):
            with self.assertRaises(brand_media.UploadError): self.upload(filename,data)
        self.assertEqual(storage.listing("research_document"),[])
        self.assertFalse(list(self.folder.rglob("*.part")))

    def test_limit_and_interrupted_stream_leave_no_file_or_record(self):
        with patch.object(brand_media,"MAX_MEDIA_BYTES",10):
            with self.assertRaises(brand_media.UploadError) as failure:self.upload()
        self.assertEqual(failure.exception.status,413)
        async def broken():
            yield b"RIFF"
            raise RuntimeError("transport disconnected")
        with self.assertRaises(RuntimeError):
            asyncio.run(brand_media.save_media(self.brand["id"],"broken.wav",broken()))
        self.assertFalse(list(self.folder.rglob("*.part")))
        self.assertEqual(storage.listing("research_document"),[])

    def test_shared_attachment_quota_allows_duplicates_but_rejects_new_media(self):
        doc,_=self.upload()
        for i in range(2):research.save_document(self.brand["id"],f"facts{i}.txt",f"Brew product facts {i}.")
        self.assertFalse(self.upload()[1])
        with self.assertRaises(brand_media.UploadError):self.upload("clip2.wav",wav_bytes()+b"different")
        self.assertEqual(len(storage.listing("research_document")),3)
        self.assertTrue(brand_media.media_path(doc).exists())

    def test_transcript_is_labeled_evidence_and_raw_media_is_not_invented_evidence(self):
        doc,_=self.upload()
        initial,warnings=research.gather("before",self.brand["id"],"Brew features",dict(name="Brew"))
        self.assertEqual(initial,[]);self.assertTrue(any("not analyzed" in w for w in warnings))
        updated=brand_media.save_transcript(self.brand["id"],doc["id"],"Brew has two modes.")
        sources,_=research.gather("after",self.brand["id"],"Brew features",dict(name="Brew"))
        self.assertEqual(sources[0]["source_type"],"user_media_transcript")
        self.assertEqual(sources[0]["excerpt"],"Brew has two modes.")
        self.assertEqual(sources[0]["transcript_origin"],"user_supplied")
        self.assertEqual(updated["sha256"],doc["sha256"])
        self.assertEqual(sources[0]["transcript_sha256"],updated["transcript_sha256"])
        with self.assertRaises(brand_media.UploadError):brand_media.save_transcript(self.other["id"],doc["id"],"Wrong brand")

    def test_http_upload_preview_range_and_notes_routes_do_not_call_mesh(self):
        import main
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.api),base_url="http://testserver") as client:
                base=f"/brands/{self.brand['id']}/research-media"
                response=await client.post(base,params={"filename":"sample.wav"},content=wav_bytes())
                self.assertEqual(response.status_code,200,response.text)
                doc=response.json();self.assertTrue(doc["created"])
                path=base+"/"+doc["id"]
                preview=await client.get(path+"/file",headers={"range":"bytes=0-15"})
                self.assertEqual(preview.status_code,206)
                self.assertEqual(preview.content,wav_bytes()[:16])
                self.assertIn("audio/wav",preview.headers["content-type"])
                update=await client.put(path+"/transcript",json={"text":"Brew has two modes."})
                self.assertEqual(update.status_code,200,update.text)
                notes=await client.get(path+"/transcript")
                self.assertEqual(notes.json()["text"],"Brew has two modes.")
                denied=await client.get(f"/brands/{self.other['id']}/research-media/{doc['id']}/file")
                self.assertEqual(denied.status_code,404)
        with patch("main.gateway",side_effect=AssertionError("Uploads must not use Mesh")):
            asyncio.run(exercise())


if __name__=="__main__":unittest.main()
