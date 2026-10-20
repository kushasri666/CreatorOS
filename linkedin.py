"""Read-only personal LinkedIn analytics. Never invokes an LLM.

Requires a locally configured OAuth token with r_member_postAnalytics.
Post discovery is deliberately separate: register known share/ugcPost URNs.
"""
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
import storage as store

LOCK = threading.Lock()
METRICS = {"IMPRESSION": "impressions", "REACTION": "reactions",
           "COMMENT": "comments", "RESHARE": "shares"}


def status():
    return {"configured": bool(os.getenv("LINKEDIN_ACCESS_TOKEN")),
            "collection_enabled": os.getenv("LINKEDIN_AUTO_SYNC", "0") == "1",
            "required_permission": "r_member_postAnalytics",
            "tracked_posts": len(store.listing("linkedin_tracking")),
            "last_sync": store.get("linkedin_sync_status")}


def track(post, urn):
    if post.get("platform") != "linkedin":
        raise ValueError("Only LinkedIn posts can be linked")
    if not re.fullmatch(r"urn:li:(share|ugcPost):[0-9]+", urn):
        raise ValueError("Use the exact urn:li:share:NUMBER or urn:li:ugcPost:NUMBER")
    if any(t["urn"] == urn and t["post_id"] != post["id"]
           for t in store.listing("linkedin_tracking")):
        raise ValueError("This LinkedIn post is already linked")
    value = store.save("linkedin_tracking", {"post_id": post["id"], "urn": urn,
                       "next_sync": store.now()}, "linkedin_tracking:" + post["id"])
    store.audit(post["id"], "linkedin", {"event": "post_linked", "urn": urn})
    return value


def fetch(client, token, urn):
    version = os.getenv("LINKEDIN_API_VERSION", "202609")
    if not re.fullmatch(r"20[0-9]{4}", version):
        raise ValueError("Invalid LinkedIn API version")
    tag = "ugc" if ":ugcPost:" in urn else "share"
    entity = f"({tag}:{quote(urn, safe='')})"
    counts = {}
    for query, name in METRICS.items():
        # Preserve Rest.li delimiters and encode the URN exactly once.
        url = ("https://api.linkedin.com/rest/memberCreatorPostAnalytics"
               f"?q=entity&entity={entity}&queryType={query}&aggregation=TOTAL")
        response = client.get(url, headers={"Authorization": "Bearer " + token,
            "Linkedin-Version": version, "X-Restli-Protocol-Version": "2.0.0"})
        response.raise_for_status()
        elements = response.json().get("elements", [])
        if len(elements) != 1:
            raise ValueError("Missing or ambiguous lifetime metric; not treated as zero")
        row = elements[0]
        target = row.get("targetEntity")
        if isinstance(target, dict):
            target = target.get(tag)
        if target != urn or row.get("metricType") != query or row.get("dateRange"):
            raise ValueError("Unexpected LinkedIn metric identity or window")
        count = row.get("count")
        if type(count) is not int or count < 0:
            raise ValueError("Invalid metric count")
        counts[name] = count
    return counts


def sync(client=None):
    """At most three due posts per daily run, four requests each; no retries.

    Single-process local deployment only. HTTP errors never overwrite evidence.
    """
    token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    if not token or os.getenv("LINKEDIN_AUTO_SYNC", "0") != "1":
        return status()
    if not LOCK.acquire(blocking=False):
        return {"status": "busy"}
    owned = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=False)
    try:
        now = datetime.now(timezone.utc)
        gate = store.get("linkedin_sync_status")
        if gate and gate.get("next_sync", "") > now.isoformat():
            return gate
        next_sync = (now + timedelta(days=1)).isoformat()
        # Persist before network access, so restart/error cannot cause a retry storm.
        result = {"at": now.isoformat(), "next_sync": next_sync, "updated": 0,
                  "status": "collecting"}
        store.save("linkedin_status", result, "linkedin_sync_status")
        due = sorted(store.listing("linkedin_tracking"), key=lambda t: t["next_sync"])
        for tracking in [t for t in due if t["next_sync"] <= now.isoformat()][:3]:
            try:
                counts = fetch(client, token, tracking["urn"])
                metric = dict(counts, post_id=tracking["post_id"], urn=tracking["urn"],
                    source="linkedin_api", observation_basis="lifetime", collected_at=store.now())
                metric["engagement_rate"] = ((counts["reactions"] + counts["comments"] + counts["shares"])
                    / counts["impressions"] if counts["impressions"] else None)
                store.save("linkedin_metric", metric,
                    f"linkedin_metric:{tracking['post_id']}:{now.date().isoformat()}")
                store.audit(tracking["post_id"], "linkedin", {"event": "metrics_collected", **metric})
                store.save("linkedin_tracking", dict(tracking, next_sync=next_sync), tracking["id"])
                result["updated"] += 1
            except httpx.HTTPStatusError as exc:
                result.update(status="api_error", http_status=exc.response.status_code)
                break  # Includes revoked tokens, missing permissions, and rate limits.
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                result.update(status="invalid_or_unavailable_response")
                break
        else:
            result["status"] = "complete"
        return store.save("linkedin_status", result, "linkedin_sync_status")
    finally:
        if owned:
            client.close()
        LOCK.release()
