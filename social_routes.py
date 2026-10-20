"""Connection setup and evidence endpoints for the local CreatorOS application."""
from datetime import datetime, timedelta, timezone
from typing import Literal
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, AwareDatetime
import httpx
import storage
import social
import social_auth

router = APIRouter()
Platform = Literal["instagram", "youtube", "linkedin", "telegram", "threads", "x"]


def require(id, kind):
    value = storage.get(id)
    if not value or not any(v["id"] == id for v in storage.listing(kind)):
        raise HTTPException(404, f"{kind} not found")
    return value


class ConnectionRequest(BaseModel):
    provider: Platform
    brand_id: str
    account_id: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_@:-]*$")
    allow_paid_reads: bool = False


class EnabledRequest(BaseModel):
    enabled: bool


class LinkRequest(BaseModel):
    post_id: str
    external_id: str = Field(min_length=1, max_length=100)
    published_at: AwareDatetime
    format: str = Field(min_length=1, max_length=60)


class ImportedRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=10000)
    published_at: AwareDatetime
    format: str = Field(min_length=1, max_length=60)


@router.get("/connections")
def connections():
    return dict(platforms=social.SPECS, connections=storage.listing("social_connection"),
        configured={p: {"local_token": bool(os.getenv(p.upper()+"_ACCESS_TOKEN")),
            "oauth_app": bool(os.getenv(p.upper()+"_CLIENT_ID")),
            "encryption_key": bool(os.getenv("CREATOROS_TOKEN_KEY"))} for p in social.PLATFORMS},
        note="Configured is not connected. Verified means an actual metric collection succeeded. No credentials are returned.")


@router.post("/connections")
def create_connection(req: ConnectionRequest):
    require(req.brand_id, "brand")
    try:
        return social.connect(req.provider, req.brand_id, req.account_id, req.allow_paid_reads)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/connections/{id}/authorize")
def authorize(id: str):
    connection = require(id, "social_connection")
    try:
        url, nonce = social_auth.begin(connection)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    response = RedirectResponse(url, status_code=303)
    response.set_cookie("creatoros_oauth", nonce, max_age=600, httponly=True, samesite="lax",
                        secure=url.startswith("https:") and os.getenv("CREATOROS_HTTPS", "0") == "1", path="/connections/oauth")
    return response


@router.get("/connections/oauth/{provider}/callback", response_class=HTMLResponse)
def callback(provider: Platform, request: Request, state: str = "", code: str = "", error: str = ""):
    if error or not code or not state:
        raise HTTPException(400, "Authorization was denied or incomplete. Start again from Connections.")
    try:
        social_auth.finish(provider, code, state, request.cookies.get("creatoros_oauth"))
    except (ValueError, httpx.HTTPError):
        raise HTTPException(400, "Authorization failed. Check the app permissions and redirect URI; no credentials were saved in this response.") from None
    response = HTMLResponse('<h1>Account authorized</h1><p>Collection is still paused. Return to CreatorOS, link or discover posts, then enable collection.</p><a href="/">Return to CreatorOS</a>', headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
    response.delete_cookie("creatoros_oauth", path="/connections/oauth")
    return response


@router.post("/connections/{id}/enabled")
def enabled(id: str, req: EnabledRequest):
    connection = require(id, "social_connection")
    if req.enabled:
        if connection["provider"] == "x" and (not connection["allow_paid_reads"] or os.getenv("SOCIAL_ENABLE_PAID_X", "0") != "1"):
            raise HTTPException(422, "X API reads cost money. Both paid-read opt-ins must be configured explicitly.")
        try:
            social_auth.access_token(connection)
        except (ValueError, httpx.HTTPError) as exc:
            raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "Token refresh failed; reauthorize") from None
    return storage.save("social_connection", dict(connection, enabled=req.enabled,
        status="authorized_unverified" if req.enabled else "paused"), id)


@router.post("/connections/{id}/disconnect")
def disconnect(id: str):
    require(id, "social_connection")
    return social_auth.disconnect(id)


@router.post("/connections/{id}/sync", status_code=202)
def sync(id: str, background: BackgroundTasks):
    require(id, "social_connection")
    background.add_task(social.sync, id)
    return {"status": "queued", "note": "Daily request gate applies; enabling collection is required. No Mesh calls."}


@router.post("/connections/{id}/discover")
def discover(id: str):
    require(id, "social_connection")
    try:
        return {"posts": social.discover(id)}
    except (ValueError, KeyError, httpx.HTTPError, ImportError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "Discovery unavailable; check authorization and provider limits") from None


@router.post("/connections/{id}/posts")
def link(id: str, req: LinkRequest):
    connection = require(id, "social_connection")
    post = require(req.post_id, "post")
    if req.published_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Published time cannot be in the future")
    try:
        return social.track(connection, post, req.external_id, req.published_at.isoformat(), req.format)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/connections/{id}/import")
def import_post(id: str, req: ImportedRequest):
    connection = require(id, "social_connection")
    if req.published_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Published time cannot be in the future")
    try:
        social.validate_id(connection["provider"], req.external_id)
        # Reuse already linked media; repeated clicks cannot invent a new history.
        prior = next((t for t in storage.listing("social_track") if t["connection_id"] == id and t["external_id"] == req.external_id), None)
        if prior:
            return storage.get(prior["post_id"])
        post = storage.save("post", dict(kind="post", brand_id=connection["brand_id"], platform=connection["provider"],
            brief=req.text[:120], text=req.text, mode="user_imported", strategy={"format": req.format},
            published_at=req.published_at.isoformat(), status="published", created_at=storage.now()))
        social.track(connection, post, req.external_id, req.published_at.isoformat(), req.format)
        storage.audit(post["id"], "ingestion", {"reason": "User linked existing published content. Engagement must still be collected from its provider."})
        return post
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/social/analytics/{brand_id}/{platform}")
def analytics(brand_id: str, platform: Platform):
    require(brand_id, "brand")
    return social.dashboard(brand_id, platform)


@router.get("/social/examples/{platform}")
def examples(platform: Platform):
    import tempfile
    from pathlib import Path
    Path("data").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir="data") as directory:
        token = storage.database_override.set(str(Path(directory)/"example.db"))
        try:
            connection = {"id": "sample-connection", "provider": platform, "brand_id": "sample-brand"}
            now = datetime.now(timezone.utc)
            for i, (format, likes, comments, shares) in enumerate([
                ("story", 90, 18, 16), ("story", 100, 20, 18),
                ("checklist", 45, 6, 5), ("checklist", 50, 8, 6)]):
                tracking = {"id": f"sample:{i}", "post_id": f"sample:{i}", "external_id": f"sample:{i}",
                    "published_at": (now-timedelta(days=10+i)).isoformat(), "format": format}
                denominator = "impressions" if platform in ("linkedin", "x") else "views"
                counts = {denominator: 2000, "likes": likes, "comments": comments, "shares": shares}
                if platform == "telegram":
                    counts["reactions"] = counts.pop("likes")
                    counts.pop("comments")
                if platform == "youtube":
                    counts.update(estimatedMinutesWatched=500+i*20, averageViewDuration=15+i)
                social.save_observation(connection, tracking, counts, source="simulated")
            return dict(social.dashboard("sample-brand", platform), mode="simulated_example",
                next_brief="Use a story-led opening, then one actionable tip. Test it against a checklist; do not promise improved engagement.",
                note="Fictional examples for explaining analytics. They do not belong to your accounts and are never injected into live generation.")
        finally:
            storage.database_override.reset(token)
