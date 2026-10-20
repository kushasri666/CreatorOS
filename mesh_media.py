"""Opt-in Mesh-only speech and video endpoints; default locked, no automatic retries.

The user has requested no paid validation. Contract tests use MockTransport only.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
import wave

import httpx
import storage

BASE = "https://api.meshapi.ai/v1"
DIRECTORY = Path(__file__).resolve().parent / "data" / "mesh-media"


def configuration():
    return dict(enabled=os.getenv("MESH_ENABLE_MEDIA_PAID", "0") == "1",
        spend_cap_confirmed=os.getenv("MESH_MEDIA_SPEND_CAP_CONFIGURED", "0") == "1",
        video_model=os.getenv("MESH_VIDEO_MODEL", ""), speech_model=os.getenv("MESH_SPEECH_MODEL", ""),
        speech_voice=os.getenv("MESH_SPEECH_VOICE", ""), max_submissions_per_day=1,
        max_video_seconds=5, max_narration_characters=500,
        note="Paid media is separately locked. Configure a Mesh dashboard key spend cap and a compatible model before enabling. No price estimate is fabricated.")


def reserve(post_id, kind, payload):
    config = configuration()
    if os.getenv("MESH_ENABLE_PAID", "0") != "1" or not config["enabled"] or not config["spend_cap_confirmed"]:
        raise ValueError("Paid Mesh media is locked. Enable it only after configuring a provider-side spend cap.")
    if not os.getenv("MESH_API_KEY"):
        raise ValueError("Configure MESH_API_KEY locally")
    key = "media_request:" + hashlib.sha256(json.dumps([post_id, kind, payload], sort_keys=True).encode()).hexdigest()
    with storage.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM records WHERE id=?", (key,)).fetchone()
        if row:
            return json.loads(row[0]), False
        today = datetime.now(timezone.utc).date().isoformat()
        attempts = [json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind='mesh_media'")]
        if any(item["created_at"].startswith(today) for item in attempts):
            raise ValueError("One paid media submission per UTC day is permitted. Existing jobs can still be checked.")
        item = dict(id=key, post_id=post_id, kind=kind, status="submitting", created_at=storage.now(), payload=payload)
        db.execute("INSERT INTO records VALUES (?, 'mesh_media', ?)", (key, json.dumps(item)))
    return item, True


def submit(post, kind, text, include_audio=False, client=None):
    if post.get("status") not in ("approved", "scheduled", "ready_to_publish", "feedback_recorded"):
        raise ValueError("Approve content before submitting paid media")
    if kind not in ("video", "speech"):
        raise ValueError("Unsupported media kind")
    config = configuration()
    model = config["video_model"] if kind == "video" else config["speech_model"]
    if not model:
        raise ValueError("Select a compatible Mesh media model locally; there is no automatic expensive default")
    if kind == "speech":
        if not config["speech_voice"] or not 1 <= len(text) <= 500:
            raise ValueError("Configure a valid Mesh voice and keep narration between 1 and 500 characters")
        payload = dict(model=model, input=text, voice=config["speech_voice"], stream=False, response_format="wav_44100")
    else:
        if not 10 <= len(text) <= 1500:
            raise ValueError("Video prompt must contain 10–1500 characters")
        payload = dict(model=model, content=[{"type": "text", "text": text}], duration=5,
                       ratio="9:16", resolution="720p", generate_audio=include_audio)
    item, started = reserve(post["id"], kind, payload)
    if not started:
        return item
    owned = client is None
    client = client or httpx.Client(timeout=90, follow_redirects=False)
    try:
        # Exactly one POST. An ambiguous timeout stays blocked instead of retrying a charge.
        response = client.post(BASE+("/video/generations" if kind == "video" else "/audio/speech"),
            headers={"Authorization": "Bearer "+os.environ["MESH_API_KEY"]}, json=payload)
        response.raise_for_status()
        if kind == "video":
            result = response.json()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", result.get("id", "")):
                raise ValueError("Mesh returned no usable video task ID")
            item.update(status=result.get("status", "queued"), task_id=result["id"], unsupported_params=result.get("unsupported_params"))
        else:
            if len(response.content) > 20_000_000:
                raise ValueError("Speech exceeded the 20 MB download limit")
            with wave.open(io.BytesIO(response.content)) as audio:
                duration = audio.getnframes()/audio.getframerate()
            DIRECTORY.mkdir(parents=True, exist_ok=True)
            name = hashlib.sha256(item["id"].encode()).hexdigest()+".wav"
            (DIRECTORY/name).write_bytes(response.content)
            item.update(status="succeeded", file=name, duration_seconds=duration)
        storage.audit(post["id"], "mesh_media", {"reason": "Explicit paid media submission via Mesh only", "job_id": item["id"], "model": model, "kind": kind})
    except Exception as exc:
        item.update(status="submission_failed_or_unknown", error=type(exc).__name__,
                    note="No automatic retry. Check Mesh usage/tasks before any new submission.")
    finally:
        if owned:
            client.close()
    return storage.save("mesh_media", item, item["id"])


def poll(id, client=None):
    item = storage.get(id)
    if not item or item.get("kind") != "video" or not item.get("task_id"):
        raise ValueError("Video task not found")
    if item["status"] in ("succeeded", "failed", "expired") or item.get("next_poll", "") > storage.now():
        return item
    item["next_poll"] = (datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()
    storage.save("mesh_media", item, id)
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    try:
        response = client.get(BASE+"/video/generations/"+item["task_id"], headers={"Authorization": "Bearer "+os.environ["MESH_API_KEY"]})
        response.raise_for_status()
        data = response.json()
        item.update(status=data["status"], usage=data.get("usage"))
        if data["status"] == "succeeded":
            url = data.get("content", {}).get("video_url", "")
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.hostname in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("Invalid Mesh output URL")
            item["url"] = url
        elif data["status"] in ("failed", "expired"):
            item["error"] = data.get("error", {}).get("code", "provider_generation_failed")
    finally:
        if owned:
            client.close()
    return storage.save("mesh_media", item, id)
