"""Official read-only social adapters and normalized evidence. No AI calls.

Tokens are loaded server-side; API responses never include credentials. All network
hosts are fixed in code. Missing counters remain missing, never invented zeros.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import threading
import math

import httpx
import storage

PLATFORMS = ("instagram", "youtube", "linkedin", "telegram", "threads", "x")
SPECS = {
    "instagram": {"account": "Creator or Business (professional account)", "cost": "Professional account conversion is free; API permissions and app review still required.",
        "scopes": "instagram_business_basic instagram_business_manage_insights", "setup": "Instagram Login; personal Instagram insights are not available through this API.",
        "docs": "https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/insights"},
    "youtube": {"account": "Normal Google account with a YouTube channel", "cost": "No paid channel tier required; API quotas and OAuth verification apply.",
        "scopes": "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly",
        "setup": "Enable YouTube Data and Analytics APIs in your Google project, then authorize read access.",
        "docs": "https://developers.google.com/youtube/analytics/reference/reports/query"},
    "linkedin": {"account": "Personal LinkedIn profile", "cost": "Premium is not a substitute for approved developer permissions.",
        "scopes": "r_member_postAnalytics", "setup": "Approved analytics permission required; register published share/ugcPost URNs. Full personal post discovery requires restricted read permissions.",
        "docs": "https://learn.microsoft.com/en-us/linkedin/marketing/community-management/members/post-statistics"},
    "telegram": {"account": "Normal Telegram user administering a channel", "cost": "No Telegram Premium required for this connector.",
        "scopes": "MTProto user session; channel administrator", "setup": "Run scripts/connect_telegram.py locally. Bot API alone cannot retrieve historical channel post views. Sessions are credentials: keep them local.",
        "docs": "https://core.telegram.org/method/messages.getMessagesViews"},
    "threads": {"account": "Normal Threads profile", "cost": "No professional account tier required; app review and quotas apply.",
        "scopes": "threads_basic threads_manage_insights", "setup": "Create a Meta app with Threads API and authorize your profile.",
        "docs": "https://www.postman.com/meta/threads/request/ndeeu6p/get-post-insights"},
    "x": {"account": "Normal X account plus a funded developer app", "cost": "API reads are paid. Professional/Premium account status does not remove API charges.",
        "scopes": "tweet.read users.read offline.access", "setup": "Explicit paid-read opt-in required. Configure spending limits in the X developer console.",
        "docs": "https://docs.x.com/x-api/getting-started/pricing"},
}
SYNC_LOCK = threading.Lock()


def number(value):
    if type(value) not in (int, float) or value < 0 or not math.isfinite(value):
        raise ValueError("Invalid metric counter")
    return value


def graph_counts(response):
    result = {}
    for row in response.get("data", []):
        if row.get("values") and len(row["values"]) == 1:
            value = row["values"][0].get("value")
        else:
            value = row.get("total_value", {}).get("value")
        if value is not None:
            result[row["name"]] = number(value)
    return result


def get(client, url, token, params=None, headers=None):
    result = client.get(url, params=params, headers={"Authorization": "Bearer " + token, **(headers or {})})
    result.raise_for_status()
    return result.json()


def fetch(provider, external_id, token, client, connection):
    """One bounded collection; no automatic retries or arbitrary URLs."""
    if provider == "linkedin":
        import linkedin
        return linkedin.fetch(client, token, external_id), "lifetime"
    if provider == "instagram":
        version = os.getenv("INSTAGRAM_API_VERSION", "v24.0")
        if not re.fullmatch(r"v[0-9]+\.0", version):
            raise ValueError("Invalid Instagram API version")
        base = f"https://graph.instagram.com/{version}/{external_id}"
        info = get(client, base, token, {"fields": "id,like_count,comments_count,media_type"})
        if str(info.get("id")) != external_id:
            raise ValueError("Instagram returned a different media ID")
        stats = graph_counts(get(client, base + "/insights", token, {"metric": "reach,saved,shares,views"}))
        return {k: v for k, v in {"likes": info.get("like_count"), "comments": info.get("comments_count"),
            "reach": stats.get("reach"), "saves": stats.get("saved"), "shares": stats.get("shares"),
            "views": stats.get("views")}.items() if v is not None}, "lifetime"
    if provider == "threads":
        stats = graph_counts(get(client, f"https://graph.threads.net/v1.0/{external_id}/insights", token,
            {"metric": "views,likes,replies,reposts,quotes,shares"}))
        return {({"replies": "comments", "reposts": "reposts"}.get(k, k)): v for k, v in stats.items()}, "lifetime"
    if provider == "x":
        if not connection.get("allow_paid_reads") or os.getenv("SOCIAL_ENABLE_PAID_X", "0") != "1":
            raise ValueError("Paid X reads are disabled; both connection and environment opt-in are required")
        data = get(client, f"https://api.x.com/2/tweets/{external_id}", token,
                   {"tweet.fields": "public_metrics,author_id"}).get("data", {})
        if str(data.get("id")) != external_id:
            raise ValueError("X returned no matching post")
        metrics = data.get("public_metrics", {})
        mapping = {"like_count": "likes", "reply_count": "comments", "retweet_count": "reposts",
                   "quote_count": "quotes", "bookmark_count": "saves", "impression_count": "impressions"}
        return {v: number(metrics[k]) for k, v in mapping.items() if k in metrics}, "lifetime"
    if provider == "youtube":
        info = get(client, "https://www.googleapis.com/youtube/v3/videos", token,
                   {"part": "statistics,snippet", "id": external_id}).get("items", [])
        if len(info) != 1 or info[0]["id"] != external_id:
            raise ValueError("YouTube returned no matching video")
        if connection.get("account_id") and info[0]["snippet"]["channelId"] != connection["account_id"]:
            raise ValueError("Video does not belong to this channel")
        end = (datetime.now(timezone.utc)-timedelta(days=1)).date()
        start = end-timedelta(days=27)
        metrics = ["views", "likes", "comments", "shares", "estimatedMinutesWatched", "averageViewDuration"]
        report = get(client, "https://youtubeanalytics.googleapis.com/v2/reports", token,
            {"ids": "channel==MINE", "startDate": str(start), "endDate": str(end),
             "metrics": ",".join(metrics), "filters": "video=="+external_id})
        if len(report.get("rows", [])) != 1:
            raise ValueError("YouTube analytics is not available for this reporting range yet")
        columns = [h["name"] for h in report["columnHeaders"]]
        row = report["rows"][0]
        if len(row) != len(columns) or set(columns) != set(metrics):
            raise ValueError("Unexpected YouTube report columns")
        return {k: number(v) for k, v in zip(columns, row)}, f"range:{start}:{end} (provider reporting lag applies)"
    if provider == "telegram":
        return asyncio.run(telegram_counts(external_id, connection)), "lifetime"
    raise ValueError("Unsupported platform")


async def telegram_counts(external_id, connection):
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetMessagesViewsRequest
    session = os.getenv("TELEGRAM_SESSION_PATH", "data/telegram")
    client = TelegramClient(session, int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise ValueError("Telegram session is not authorized. Run the local setup script.")
        channel = await client.get_entity(connection["account_id"])
        permission = await client.get_permissions(channel, "me")
        if not (permission.is_admin or permission.is_creator):
            raise ValueError("The Telegram user must administer the selected channel")
        result = await client(GetMessagesViewsRequest(peer=channel, id=[int(external_id)], increment=False))
        if len(result.views) != 1:
            raise ValueError("Telegram returned no matching message")
        counter = result.views[0]
        values = {"views": counter.views, "shares": counter.forwards}
        message = await client.get_messages(channel, ids=int(external_id))
        if message and message.reactions:
            values["reactions"] = sum(r.count for r in message.reactions.results)
        return {k: number(v) for k, v in values.items() if v is not None}
    finally:
        await client.disconnect()


def validate_id(provider, id):
    pattern = r"urn:li:(share|ugcPost):[0-9]+" if provider == "linkedin" else r"[A-Za-z0-9_-]{11}" if provider == "youtube" else r"[0-9]+"
    if not re.fullmatch(pattern, id):
        raise ValueError("Use the platform's exact media/post ID (not a URL)")


def connect(provider, brand_id, account_id, allow_paid_reads=False):
    if provider not in PLATFORMS:
        raise ValueError("Unsupported platform")
    if provider == "telegram" and not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", account_id):
        raise ValueError("Use your public Telegram channel handle, for example @yourchannel")
    for connection in storage.listing("social_connection"):
        if connection["provider"] == provider and connection["brand_id"] == brand_id and connection["account_id"] == account_id:
            connection["allow_paid_reads"] = allow_paid_reads
            if connection.get("status") == "disconnected":
                connection.update(enabled=False, status="not_authorized")
            return storage.save("social_connection", connection, connection["id"])
    return storage.save("social_connection", {"provider": provider, "brand_id": brand_id, "account_id": account_id,
        "allow_paid_reads": allow_paid_reads, "enabled": False, "status": "not_authorized", "created_at": storage.now()})


def track(connection, post, external_id, published_at, format):
    validate_id(connection["provider"], external_id)
    if post["brand_id"] != connection["brand_id"] or post["platform"] != connection["provider"]:
        raise ValueError("Post and connection must have the same brand and platform")
    key = "social_track:" + hashlib.sha256((connection["id"] + ":" + external_id).encode()).hexdigest()
    previous = storage.get(key)
    if previous and previous["post_id"] != post["id"]:
        raise ValueError("External media ID is already linked to another post")
    return storage.save("social_track", {"connection_id": connection["id"], "post_id": post["id"],
        "external_id": external_id, "published_at": published_at, "format": format}, key)


def save_observation(connection, tracking, counts, window="lifetime", source="api"):
    counts = {k: number(v) for k, v in counts.items() if v is not None}
    at = datetime.now(timezone.utc)
    published = datetime.fromisoformat(tracking["published_at"])
    age = (at-published).total_seconds()/86400
    if age < -5/1440:
        raise ValueError("Publication time is in the future")
    age_bucket = "0–2d" if age < 3 else "3–7d" if age < 8 else "8–30d" if age < 31 else "31d+"
    denominator = next((k for k in ("impressions", "views", "reach") if counts.get(k, 0) > 0), None)
    numerator = [k for k in ("likes", "reactions", "comments", "shares", "reposts", "quotes", "saves") if k in counts]
    formula = "("+"+".join(numerator) + ")/" + str(denominator)
    rate = sum(counts[k] for k in numerator)/counts[denominator] if denominator and numerator else None
    key = "social_metric:" + hashlib.sha256((tracking["id"] + at.date().isoformat() + source).encode()).hexdigest()
    return storage.save("social_metric", {"brand_id": connection["brand_id"], "platform": connection["provider"],
        "connection_id": connection["id"], "post_id": tracking["post_id"], "format": tracking["format"],
        "external_id": tracking["external_id"], "counts": counts, "source": source, "window": window,
        "age_bucket": age_bucket, "published_at": tracking["published_at"], "collected_at": at.isoformat(),
        "denominator": denominator, "formula": formula, "rate": rate}, key)


def dashboard(brand_id, platform):
    rows, seen, groups = [], set(), {}
    for row in storage.listing("social_metric"):
        if row["brand_id"] != brand_id or row["platform"] != platform:
            continue
        key = (row["connection_id"], row["post_id"], row["source"], row["window"], row["age_bucket"], row["formula"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if row["rate"] is not None:
            cohort = (row["source"], row["window"], row["age_bucket"], row["formula"], row["connection_id"])
            groups.setdefault(cohort, {}).setdefault(row["format"], []).append(row)
    comparisons = []
    for cohort, formats in groups.items():
        entries = [dict(format=f, n=len(v), mean_rate=sum(r["rate"] for r in v)/len(v), evidence_ids=[r["id"] for r in v]) for f, v in formats.items()]
        entries.sort(key=lambda e: e["mean_rate"], reverse=True)
        eligible = [e for e in entries if e["n"] >= 2]
        learning = None
        if len(eligible) >= 2:
            best, worst = eligible[0], eligible[-1]
            if best["mean_rate"] > worst["mean_rate"]:
                learning = dict(rule=f"Test another {best['format']} post; compare it with {worst['format']}.",
                    reason=f"Observed mean interaction rate {best['mean_rate']:.2%} vs {worst['mean_rate']:.2%}; {best['n']} and {worst['n']} posts. Association, not causation.",
                    evidence_ids=best["evidence_ids"] + worst["evidence_ids"], source=cohort[0],
                    experiment=dict(preferred_format=best["format"],comparison_format=worst["format"],
                        preferred_mean_rate=best["mean_rate"],comparison_mean_rate=worst["mean_rate"],
                        preferred_posts=best["n"],comparison_posts=worst["n"],
                        interpretation="Tentative observational format test; not causal uplift"))
        comparisons.append(dict(source=cohort[0], window=cohort[1], age_bucket=cohort[2], formula=cohort[3], connection_id=cohort[4], formats=entries, learning=learning))
    return dict(rows=rows, comparisons=comparisons, note="Compare within a platform, source, window, age bucket and formula. Missing values are unavailable, not zero. No cross-platform leaderboard.")


def learn_from_observations(brand_id, platform):
    import memory
    active=set()
    for comparison in dashboard(brand_id, platform)["comparisons"]:
        insight = comparison["learning"]
        if not insight or insight["source"] != "api":
            continue
        key = "social_learning:" + hashlib.sha256(json.dumps([brand_id, platform, comparison["source"], comparison["window"], comparison["age_bucket"], comparison["formula"], comparison["connection_id"]]).encode()).hexdigest()
        active.add(key)
        item,changed = memory.write_learning(dict(insight, brand_id=brand_id, platform=platform,
            connection_id=comparison["connection_id"],
            evidence_id=insight["evidence_ids"][0], confidence="tentative", method="deterministic_observation",
            window=comparison["window"], age_bucket=comparison["age_bucket"], formula=comparison["formula"], updated_at=storage.now()), key)
        if not changed:continue
        for id in insight["evidence_ids"]:
            evidence = storage.get(id)
            storage.audit(evidence["post_id"], "learner", {"reason": item["reason"], "rule": item["rule"], "learning_id": item["id"], "evidence_ids": insight["evidence_ids"]})
    for old in storage.listing("learning"):
        if old.get("brand_id")==brand_id and old.get("platform")==platform and old.get("method")=="deterministic_observation" and old['id'] not in active:
            memory.invalidate(old['id'],"Current comparable observations no longer support this experiment")


def sync(connection_id, client=None):
    from social_auth import access_token
    connection = storage.get(connection_id)
    if not connection or not connection.get("enabled"):
        return {"status": "disabled"}
    if connection.get("next_sync", "") > storage.now():
        return connection
    if not SYNC_LOCK.acquire(blocking=False):
        return {"status": "busy"}
    owned = client is None
    client = client or httpx.Client(timeout=25, follow_redirects=False)
    try:
        due = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        connection.update(next_sync=due, status="collecting", last_sync=storage.now())
        storage.save("social_connection", connection, connection_id)
        token = access_token(connection)
        tracked = [t for t in storage.listing("social_track") if t["connection_id"] == connection_id]
        # Rotate oldest/unobserved posts; never let the newest items starve older ones.
        recent = {m["post_id"]: m["collected_at"] for m in reversed(storage.listing("social_metric"))}
        tracked.sort(key=lambda t: recent.get(t["post_id"], ""))
        for tracking in tracked[:3]:
            counts, window = fetch(connection["provider"], tracking["external_id"], token, client, connection)
            observation = save_observation(connection, tracking, counts, window)
            storage.audit(tracking["post_id"], "collector", {"reason": "Official API observation collected", "metric_id": observation["id"], "source": "api"})
        learn_from_observations(connection["brand_id"], connection["provider"])
        connection.update(status="verified" if tracked else "authorized_no_posts", last_error=None)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        connection.update(status="reauthorize" if code == 401 else "permission_required" if code == 403 else "rate_limited" if code == 429 else "api_error",
            last_error=f"Provider HTTP {code}; existing evidence preserved")
    except (ValueError, KeyError, TypeError, httpx.HTTPError, ImportError) as exc:
        connection.update(status="setup_required", last_error=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
    except Exception as exc:
        connection.update(status="collector_error", last_error=type(exc).__name__ + "; existing evidence preserved")
    finally:
        if owned:
            client.close()
        SYNC_LOCK.release()
    return storage.save("social_connection", connection, connection_id)


def tick():
    expire_youtube_data()
    for connection in storage.listing("social_connection"):
        if connection.get("enabled") and connection.get("next_sync", "") <= storage.now():
            if connection["provider"] != "linkedin" and connection.get("next_discovery", "") <= storage.now():
                try:
                    discover(connection["id"])
                except Exception as exc:
                    fresh = storage.get(connection["id"])
                    storage.save("social_connection", dict(fresh, last_discovery_error=type(exc).__name__), connection["id"])
            sync(connection["id"])


def discover(connection_id, client=None):
    """Import at most ten recent own posts. LinkedIn personal history is restricted."""
    from social_auth import access_token
    connection = storage.get(connection_id)
    if not connection:
        raise ValueError("Connection not found")
    provider = connection["provider"]
    if provider == "linkedin":
        raise ValueError("Personal LinkedIn discovery requires closed r_member_social access. Link known share/ugcPost URNs instead.")
    if connection.get("next_discovery", "") > storage.now():
        raise ValueError("Discovery already ran today. Existing posts remain available; retry tomorrow.")
    token = access_token(connection)
    if provider == "x" and (not connection.get("allow_paid_reads") or os.getenv("SOCIAL_ENABLE_PAID_X", "0") != "1"):
        raise ValueError("Paid X reads are disabled")
    connection["next_discovery"] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    storage.save("social_connection", connection, connection_id)
    owned = client is None
    client = client or httpx.Client(timeout=25, follow_redirects=False)
    try:
        if provider == "instagram":
            version = os.getenv("INSTAGRAM_API_VERSION", "v24.0")
            if not re.fullmatch(r"v[0-9]+\.0", version):
                raise ValueError("Invalid Instagram API version")
            account = connection["account_id"] or "me"
            data = get(client, f"https://graph.instagram.com/{version}/{account}/media", token,
                {"fields": "id,caption,timestamp,media_type,media_product_type", "limit": 10})
            rows = [dict(id=r["id"], text=r.get("caption", ""), date=r["timestamp"],
                format=r.get("media_product_type") or r.get("media_type", "post")) for r in data.get("data", [])]
        elif provider == "threads":
            data = get(client, "https://graph.threads.net/v1.0/me/threads", token,
                {"fields": "id,text,timestamp,media_type", "limit": 10})
            rows = [dict(id=r["id"], text=r.get("text", ""), date=r["timestamp"], format=r.get("media_type", "text")) for r in data.get("data", [])]
        elif provider == "youtube":
            channels = get(client, "https://www.googleapis.com/youtube/v3/channels", token,
                {"part": "contentDetails", "mine": "true"}).get("items", [])
            if not channels:
                raise ValueError("No YouTube channel available to this account")
            channel = next((r for r in channels if not connection["account_id"] or r["id"] == connection["account_id"]), None)
            if not channel:
                raise ValueError("Selected YouTube channel is not authorized")
            data = get(client, "https://www.googleapis.com/youtube/v3/playlistItems", token,
                {"part": "snippet,contentDetails", "playlistId": channel["contentDetails"]["relatedPlaylists"]["uploads"], "maxResults": 10})
            rows = [dict(id=r["contentDetails"]["videoId"], text=r["snippet"]["title"],
                date=r["contentDetails"].get("videoPublishedAt", r["snippet"]["publishedAt"]), format="video") for r in data.get("items", [])]
        elif provider == "x":
            me = get(client, "https://api.x.com/2/users/me", token)["data"]
            if connection["account_id"] and connection["account_id"] not in (str(me["id"]), me.get("username")):
                raise ValueError("X account does not match the authenticated user")
            data = get(client, f"https://api.x.com/2/users/{me['id']}/tweets", token,
                {"max_results": 5, "tweet.fields": "created_at", "exclude": "retweets,replies"})
            rows = [dict(id=r["id"], text=r["text"], date=r["created_at"], format="text") for r in data.get("data", [])]
        elif provider == "telegram":
            rows = asyncio.run(telegram_recent(connection))
        else:
            raise ValueError("Unsupported discovery provider")
        imported = []
        for row in rows[:10]:
            validate_id(provider, str(row["id"]))
            published = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            if published.tzinfo is None:
                raise ValueError("Provider returned a date without a timezone")
            key = "imported:"+hashlib.sha256((connection_id+":"+str(row["id"])).encode()).hexdigest()
            previous = storage.get(key)
            if previous:
                previous.update(text=row["text"], brief=row["text"][:120] or "Imported media",
                                metadata_verified_at=storage.now(), metadata_expired=False)
                imported.append(storage.save("post", previous, key))
                continue
            post = storage.save("post", dict(kind="post", brand_id=connection["brand_id"], platform=provider,
                brief=row["text"][:120] or "Imported media", text=row["text"], status="published",
                published_at=published.isoformat(), strategy={"format": row["format"]}, mode="imported_api",
                created_at=storage.now(), metadata_verified_at=storage.now(), external_id=str(row["id"])), key)
            track(connection, post, str(row["id"]), published.isoformat(), row["format"])
            storage.audit(post["id"], "ingestion", {"reason": "Imported from the authorized provider API; no AI generation", "platform": provider})
            imported.append(post)
        return imported
    finally:
        if owned:
            client.close()


async def telegram_recent(connection):
    from telethon import TelegramClient
    client = TelegramClient(os.getenv("TELEGRAM_SESSION_PATH", "data/telegram"), int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise ValueError("Authorize the local Telegram session first")
        channel = await client.get_entity(connection["account_id"])
        permissions = await client.get_permissions(channel, "me")
        if not (permissions.is_admin or permissions.is_creator):
            raise ValueError("You must administer the channel")
        return [dict(id=str(m.id), text=m.message or "", date=m.date.isoformat(),
                     format="video" if m.video else "photo" if m.photo else "text")
                async for m in client.iter_messages(channel, limit=10) if m.message or m.media]
    finally:
        await client.disconnect()


def expire_youtube_data():
    """Refreshable YouTube API data is not retained indefinitely without verification."""
    cutoff = (datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
    with storage.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        records = [(row["id"], row["kind"], json.loads(row["body"]))
                   for row in db.execute("SELECT id,kind,body FROM records")]
        removed = set()
        for id, kind, value in records:
            if kind == "social_metric" and value.get("platform") == "youtube" and value.get("source") == "api" and value["collected_at"] < cutoff:
                db.execute("DELETE FROM records WHERE id=?", (id,))
                removed.add(id)
            if kind == "post" and value.get("platform") == "youtube" and value.get("mode") == "imported_api" and value.get("metadata_verified_at", value.get("created_at", "")) < cutoff:
                value.update(text="", brief="YouTube metadata refresh required", metadata_expired=True)
                db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(value), id))
        for id, kind, value in records:
            if kind == "learning" and any(e in removed for e in value.get("evidence_ids", [])):
                value.update(rule="Expired YouTube memory; refresh required",reason="Source data expired under retention policy")
                db.execute("UPDATE records SET body=? WHERE id=?",(json.dumps(value),id))
