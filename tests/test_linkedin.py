import os
import tempfile
import unittest
from unittest.mock import patch
import httpx
import linkedin
import storage


class LinkedInTests(unittest.TestCase):
    def test_collection_is_bounded_and_preserves_lifetime_evidence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "CREATOROS_DB": directory + "/test.db", "LINKEDIN_ACCESS_TOKEN": "test-only",
            "LINKEDIN_AUTO_SYNC": "1"}):
            post = storage.save("post", {"platform": "linkedin"})
            urn = "urn:li:share:123"
            linkedin.track(post, urn)
            calls = []
            def handler(request):
                calls.append(request)
                self.assertIn("entity=(share:urn%3Ali%3Ashare%3A123)", str(request.url))
                query = request.url.params["queryType"]
                return httpx.Response(200, json={"elements": [{"count": 100,
                    "metricType": query, "targetEntity": {"share": urn}}]})
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                self.assertEqual(linkedin.sync(client)["updated"], 1)
                linkedin.sync(client)
            self.assertEqual(len(calls), 4)
            row = storage.listing("linkedin_metric")[0]
            self.assertEqual(row["observation_basis"], "lifetime")
            self.assertEqual(row["engagement_rate"], 3)
            self.assertFalse(storage.listing("metric"))

    def test_missing_and_forbidden_metrics_are_not_zero(self):
        for response in (httpx.Response(200, json={"elements": []}), httpx.Response(403)):
            with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
                with self.assertRaises((ValueError, httpx.HTTPStatusError)):
                    linkedin.fetch(client, "test-only", "urn:li:share:123")

    def test_disabled_collector_does_not_call_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "CREATOROS_DB": directory + "/test.db", "LINKEDIN_AUTO_SYNC": "0"}):
            with patch("linkedin.httpx.Client", side_effect=AssertionError("network")):
                self.assertFalse(linkedin.sync()["collection_enabled"])
