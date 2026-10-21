"""Provider doubles and real SQLite; no Mesh or provider network calls."""
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from unittest.mock import patch

import httpx
import insights
import social
import storage


NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class FormatSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = storage.database_override.set(self.temp.name + "/studio.db")
        self.clock = patch("insights.datetime", FrozenDateTime)
        self.clock.start()
        self.brand = storage.save("brand", dict(kind="brand", name="Synthetic timing fixture"))
        self.connection = social.connect("instagram", self.brand["id"], "123")
        self.target = dict(brand_id=self.brand["id"], platform="instagram",
            connection_id=self.connection["id"], strategy={"format": "carousel"})

    def tearDown(self):
        self.clock.stop()
        storage.database_override.reset(self.override)
        self.temp.cleanup()

    def import_instagram(self, data):
        fresh = storage.get(self.connection["id"])
        storage.save("social_connection", dict(fresh, next_discovery=""), fresh["id"])
        with patch("social_auth.access_token", return_value="test-only"), httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": data}))) as client:
            return social.discover(self.connection["id"], client)

    def seed_timing(self, connection=None, format="carousel"):
        connection = connection or self.connection
        rows = []
        for i, (published, likes) in enumerate((("2026-10-19T03:30:00+00:00", 30),
                ("2026-10-19T03:45:00+00:00", 30), ("2026-10-20T04:30:00+00:00", 10),
                ("2026-10-20T04:45:00+00:00", 10))):
            post = storage.save("post", dict(kind="post", brand_id=connection["brand_id"],
                platform=connection["provider"], mode="imported_api", published_at=published,
                scheduled_for="2030-01-01T19:00:00+00:00", strategy={"format": format}))
            tracking = social.track(connection, post, str(1000 + len(storage.listing("post"))), published, format)
            row = social.save_observation(connection, tracking, {"views": 100, "likes": likes})
            rows.append(storage.save("social_metric", dict(row, collected_at=NOW.isoformat(), age_bucket="0–2d"), row["id"]))
        return rows

    def test_instagram_feed_preserves_carousel_photo_reel_and_unknown(self):
        cases = [("CAROUSEL_ALBUM", "FEED", "carousel"), ("IMAGE", "FEED", "single_image"),
            ("VIDEO", "REELS", "reel"), ("VIDEO", "FEED", "video"),
            ("IMAGE", "STORY", "story"), (None, "FEED", "unknown")]
        data = [dict(id=str(i + 1), caption="Synthetic own media", timestamp="2026-10-19T10:00:00Z",
            media_type=kind, media_product_type=product) for i, (kind, product, _) in enumerate(cases)]
        posts = self.import_instagram(data)
        self.assertEqual([p["strategy"]["format"] for p in posts], [c[2] for c in cases])
        self.assertEqual({t["format"] for t in storage.listing("social_track")}, {c[2] for c in cases})

    def test_discovery_refresh_corrects_existing_format_and_tracking(self):
        data = [dict(id="55", caption="First title", timestamp="2026-10-19T10:00:00Z",
            media_type="IMAGE", media_product_type="FEED")]
        first = self.import_instagram(data)[0]
        storage.save("post", dict(first, strategy={"format": "FEED", "reason": "Retain unrelated history"}), first["id"])
        data[0].update(caption="Refreshed title", media_type="CAROUSEL_ALBUM", timestamp="2026-10-19T10:05:00Z")
        updated = self.import_instagram(data)[0]
        self.assertEqual(updated["id"], first["id"])
        self.assertEqual(updated["strategy"]["format"], "carousel")
        self.assertEqual(updated["strategy"]["reason"], "Retain unrelated history")
        tracking = storage.listing("social_track")
        self.assertEqual(len(tracking), 1)
        self.assertEqual(tracking[0]["format"], "carousel")
        self.assertEqual(tracking[0]["published_at"], "2026-10-19T10:05:00+00:00")
        self.assertEqual(tracking[0]["published_at_source"], "api_metadata")

    def test_youtube_does_not_invent_shorts_classification_from_title(self):
        connection = social.connect("youtube", self.brand["id"], "UC-fixture")
        def handler(request):
            body = {"items": [{"id": "UC-fixture", "contentDetails": {"relatedPlaylists": {"uploads": "UU-fixture"}}}]} \
                if request.url.path.endswith("channels") else {"items": [{"contentDetails": {"videoId": "abcdefghijk"},
                "snippet": {"title": "A short #shorts", "publishedAt": "2026-10-19T10:00:00Z"}}]}
            return httpx.Response(200, json=body)
        with patch("social_auth.access_token", return_value="test-only"), httpx.Client(transport=httpx.MockTransport(handler)) as client:
            post = social.discover(connection["id"], client)[0]
        self.assertEqual(post["strategy"]["format"], "video")

    def test_api_timing_uses_actual_publication_timezone_and_returns_comparison_receipts(self):
        rows = self.seed_timing()
        answer = insights.recommend(self.target, "Asia/Kolkata")
        self.assertEqual(answer["basis"], "api_observational_metrics")
        self.assertTrue(answer["local_time"].startswith("2026-10-26T09:00:00"))
        self.assertEqual(answer["api_evidence"]["comparable_posts"], 4)
        self.assertEqual(set(answer["evidence_ids"]), {r["id"] for r in rows[:2]})
        self.assertEqual(set(answer["api_evidence"]["comparison_evidence_ids"]), {r["id"] for r in rows})
        self.assertIn("not causal", answer["reason"])

    def test_account_brand_platform_source_and_format_are_never_pooled(self):
        self.seed_timing()
        other = social.connect("instagram", self.brand["id"], "456")
        self.seed_timing(other)
        answer = insights.recommend(self.target)
        self.assertEqual(answer["api_evidence"]["comparable_posts"], 4)
        unscoped = dict(self.target, connection_id=None)
        self.assertEqual(insights.recommend(unscoped)["basis"], "heuristic")
        self.assertEqual(insights.recommend(dict(self.target, platform="threads"))["basis"], "heuristic")
        self.assertEqual(insights.recommend(dict(self.target, brand_id="unrelated"))["basis"], "heuristic")
        self.assertEqual(insights.recommend(dict(self.target, strategy={"format": "single_image"}))["basis"], "heuristic")

    def test_latest_snapshot_per_post_cannot_inflate_minimum_evidence(self):
        rows = self.seed_timing()
        old = rows[0]
        storage.save("social_metric", dict(old, collected_at=(NOW-timedelta(hours=1)).isoformat()), old["id"])
        latest = storage.save("social_metric", dict(old, collected_at=NOW.isoformat()))
        answer = insights.recommend(self.target)
        self.assertEqual(answer["api_evidence"]["comparable_posts"], 4)
        self.assertIn(latest["id"], answer["evidence_ids"])
        self.assertNotIn(old["id"], answer["evidence_ids"])

    def test_mixed_reporting_cohorts_cannot_manufacture_time_comparison(self):
        rows = self.seed_timing()
        for field, changed in (("window", "range:other"), ("formula", "(likes+shares)/views"),
                ("age_bucket", "3–7d"), ("source", "simulated"), ("account_id", "different")):
            with self.subTest(field=field):
                for row in rows[2:]:
                    storage.save("social_metric", dict(row, **{field: changed}), row["id"])
                self.assertEqual(insights.recommend(self.target)["basis"], "heuristic")
                for row in rows[2:]:
                    storage.save("social_metric", row, row["id"])

    def test_missing_old_or_untrusted_publication_metadata_is_explicit(self):
        rows = self.seed_timing()
        cases = ({"published_at_source": "user_supplied"}, {"published_at_source": "unknown"},
            {"account_id": None}, {"collected_at": (NOW-timedelta(days=15)).isoformat()},
            {"published_at": "2026-10-19T10:00:00"}, {"rate": float("nan")})
        for change in cases:
            with self.subTest(change=change):
                for row in rows:
                    storage.save("social_metric", dict(row, **change), row["id"])
                answer = insights.recommend(self.target)
                self.assertEqual(answer["basis"], "heuristic")
                self.assertEqual(answer["api_evidence"]["status"], "insufficient_evidence")
                self.assertIn("provider publication timestamps", answer["reason"])
        # Restore one post per slot only: two posts are still insufficient.
        for row in rows[:1] + rows[2:3]:
            storage.save("social_metric", row, row["id"])
        self.assertEqual(insights.recommend(self.target)["basis"], "heuristic")

    def test_legacy_manual_and_simulated_recommendations_keep_explicit_labels(self):
        post = storage.save("post", dict(kind="post", brand_id=self.brand["id"], platform="instagram",
            scheduled_for="2026-10-19T03:30:00+00:00"))
        metric = dict(brand_id=self.brand["id"], platform="instagram", post_id=post["id"], rate=.2,
            input={"window_hours": 24, "source": "simulated"})
        storage.save("metric", metric)
        self.assertEqual(insights.recommend(self.target)["basis"], "simulated_metrics")
        storage.save("metric", dict(metric, input={"window_hours": 24, "source": "user_entered"}))
        answer = insights.recommend(self.target)
        self.assertEqual(answer["basis"], "observed_metrics")
        self.assertIn("API timing evidence not used", answer["reason"])


if __name__ == "__main__":
    unittest.main()
