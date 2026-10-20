"""Separately gated paid Mesh media; browsing this UI makes no inference calls."""
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal
import httpx
import mesh_media
import storage

router = APIRouter()


class MediaRequest(BaseModel):
    kind: Literal["video", "speech"]
    text: str = Field(min_length=1, max_length=1500)
    include_audio: bool = False
    confirm_paid: bool = False


@router.get("/posts/{post_id}/media")
def media_status(post_id: str):
    if not storage.get(post_id):
        raise HTTPException(404, "Post not found")
    return dict(configuration=mesh_media.configuration(),
                jobs=[v for v in storage.listing("mesh_media") if v["post_id"] == post_id])


@router.post("/posts/{post_id}/media")
def create_media(post_id: str, req: MediaRequest):
    post = storage.get(post_id)
    if not post or post.get("kind") != "post":
        raise HTTPException(404, "Post not found")
    if not req.confirm_paid:
        raise HTTPException(422, "Explicit paid-media confirmation is required")
    try:
        return mesh_media.submit(post, req.kind, req.text, req.include_audio)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/media/jobs/{id}")
def media_job(id: str):
    item = storage.get(id)
    if not item or not id.startswith("media_request:"):
        raise HTTPException(404, "Media job not found")
    try:
        return mesh_media.poll(id) if item["kind"] == "video" and item.get("task_id") else item
    except (ValueError, httpx.HTTPError):
        raise HTTPException(502, "Mesh status check failed; no generation was retried") from None


@router.get("/media/speech/{id}")
def speech_file(id: str):
    item = storage.get(id)
    name = item.get("file", "") if item else ""
    if not item or item.get("status") != "succeeded" or item.get("kind") != "speech" or not re.fullmatch(r"[a-f0-9]{64}\.wav", name):
        raise HTTPException(404, "Ready narration not found")
    path = mesh_media.DIRECTORY/name
    if not path.exists():
        raise HTTPException(404, "Narration file unavailable")
    return FileResponse(path, media_type="audio/wav", filename="creatoros-narration.wav")
