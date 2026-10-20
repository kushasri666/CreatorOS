import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import storage
import video


class VideoTests(unittest.TestCase):
    def test_long_brand_and_tool_names_try_smaller_sharp_font(self):
        from PIL import ImageDraw
        text='LearnAIwithSachit: build with Snowflake/Databricks—straightforward AI tools.'
        canvas=video.scene_card(text,0,3,brand_name='LearnAIwithSachit')
        self.assertEqual(canvas.size,(720,1280))
        # This input really exercises the previous oversized-word failure.
        with self.assertRaises(ValueError):
            video.caption_lines(ImageDraw.Draw(canvas),text,video.font(66,True),590)

    def test_render_playable_video_captions_and_reuse_without_ai(self):
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                {"CREATOROS_DB": directory + "/test.db"}), patch.object(video, "OUTPUT", Path(directory)):
            post = storage.save("post", {"status": "approved", "slides": [
                "Start with one useful idea.", "Test it with your audience.", "Save what you learned."]})
            item, started = video.start(post, None, 2)
            self.assertTrue(started)
            video.render(item, post)
            saved = storage.get(item["id"])
            self.assertEqual(saved["status"], "ready", saved)
            self.assertEqual(saved["preview_frames"], 18)
            from PIL import Image, ImageStat
            with Image.open(video.output_path(item["id"], ".poster.jpg")) as poster:
                self.assertGreater(sum(ImageStat.Stat(poster).var), 100)
            self.assertTrue(video.output_path(item["id"], ".preview.webp").exists())
            reader = imageio_ffmpeg.read_frames(str(video.output_path(item["id"])))
            metadata = next(reader)
            self.assertEqual(metadata["size"], (720, 1280))
            self.assertEqual(metadata["audio_codec"], "aac")
            self.assertAlmostEqual(metadata["duration"], 6, delta=0.2)
            self.assertEqual(len(next(reader)), 720 * 1280 * 3)
            reader.close()
            captions = video.output_path(item["id"], ".vtt").read_text(encoding="utf-8")
            self.assertIn("00:00:04.000 --> 00:00:06.000", captions)
            again, started = video.start(post, None, 2)
            self.assertFalse(started)
            self.assertEqual(again["id"], item["id"])
            self.assertNotEqual(video.fingerprint(post, item["scenes"], 2, True),
                                video.fingerprint(post, item["scenes"], 2, False))

    def test_invalid_input_and_path_are_rejected(self):
        with self.assertRaises(ValueError):
            video.scenes_for({"slides": ["one"]})
        with self.assertRaises(ValueError):
            video.output_path("../outside")
        with self.assertRaises(ValueError):
            video.start({"status": "generating"}, ["one", "two", "three"], 4)
