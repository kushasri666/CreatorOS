import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from pydantic import BaseModel, Field, AwareDatetime
from typing import Literal
import storage as store
from workflow import gateway, learn_voice, run_pipeline
from insights import recommend, analytics
import linkedin
import social


@asynccontextmanager
async def lifespan(app):
    for item in store.listing("video"):
        if item.get("status") == "rendering":
            store.save("video", dict(item, status="failed", error="Rendering interrupted by server restart. Retry explicitly."), item["id"])
    async def worker():
        while True:
            for name, job in (("scheduler", store.tick), ("linkedin", linkedin.sync), ("social", social.tick)):
                try:
                    await asyncio.to_thread(job)
                except Exception as exc:
                    store.save("worker_health", {"job": name, "error": type(exc).__name__, "at": store.now()}, "worker_health:"+name)
            await asyncio.sleep(10)
    task = asyncio.create_task(worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


api = FastAPI(title="CreatorOS", lifespan=lifespan)
from social_routes import router as social_router
api.include_router(social_router)
from media_routes import router as media_router
api.include_router(media_router)
api.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")


class LinkedInTrackingRequest(BaseModel):
    urn: str = Field(max_length=100)


@api.get("/integrations/linkedin")
def linkedin_status():
    return linkedin.status()


@api.post("/posts/{post_id}/linkedin")
def linkedin_track(post_id: str, req: LinkedInTrackingRequest):
    try:
        return linkedin.track(require(post_id, "post"), req.urn)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@api.get("/integrations/linkedin/metrics")
def linkedin_metrics():
    return store.listing("linkedin_metric")


class BrandRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    samples: list[str] = Field(min_length=3, max_length=30)


class BriefRequest(BaseModel):
    brand_id: str
    topic: str = Field(min_length=3, max_length=2000)
    platform: Literal["linkedin", "x", "instagram", "youtube", "telegram", "threads"] = "linkedin"
    use_learnings: bool = True
    connection_id: str | None = None


class ScheduleRequest(BaseModel):
    scheduled_for: AwareDatetime


class MetricsRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    source: Literal["user_entered", "simulated"] = "user_entered"
    impressions: int = Field(gt=0)
    likes: int = Field(ge=0)
    comments: int = Field(ge=0)
    saves: int = Field(ge=0)
    window_hours: int = Field(gt=0, default=24)


def require(id, kind):
    value = store.get(id)
    if value is None or value.get("kind") != kind:
        raise HTTPException(404, f"{kind} not found")
    return value


@api.get("/", response_class=HTMLResponse)
def home():
    return Path(__file__).with_name("studio.html").read_text(encoding="utf-8")


@api.get("/state")
def state():
    return dict({k: store.listing(k) for k in ("brand", "post", "learning", "metric", "audit", "video")},
                mode=os.getenv("CREATOROS_MODE", "live"), paid_enabled=os.getenv("MESH_ENABLE_PAID", "0") == "1")


class VideoRequest(BaseModel):
    scenes: list[str] | None = Field(default=None, min_length=3, max_length=10)
    seconds_per_scene: int = Field(default=4, ge=2, le=6)
    music: bool = True


@api.post("/posts/{post_id}/video", status_code=202)
def create_video(post_id: str, req: VideoRequest, background: BackgroundTasks):
    import video
    post = require(post_id, "post")
    try:
        item, started = video.start(post, req.scenes, req.seconds_per_scene, req.music)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if started:
        background.add_task(video.render, item, post)
    return item


@api.get("/videos/{video_id}/{asset}")
def video_asset(video_id: str, asset: Literal["file", "captions", "preview", "poster"]):
    import video
    item = store.get(video_id)
    if not item or item.get("status") != "ready" or "renderer" not in item:
        raise HTTPException(404, "Ready video not found")
    suffix, mime = {"file": (".mp4", "video/mp4"), "captions": (".vtt", "text/vtt"),
                    "preview": (".preview.webp", "image/webp"), "poster": (".poster.jpg", "image/jpeg")}[asset]
    path = video.output_path(video_id, suffix)
    if not path.exists():
        raise HTTPException(404, "Video asset is no longer available")
    return FileResponse(path, media_type=mime,
                        filename=path.name if asset == "captions" else None)


@api.get("/videos/{video_id}/frames/{frame}")
def video_frame(video_id: str, frame: int):
    import video
    item = store.get(video_id)
    if not item or item.get("status") != "ready" or not 0 <= frame < item.get("preview_frames", 0):
        raise HTTPException(404, "Video frame not found")
    path = video.output_path(video_id).parent / video_id / f"{frame:03d}.jpg"
    if not path.exists():
        raise HTTPException(404, "Video frame unavailable")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@api.post("/brands")
def brand(req: BrandRequest):
    samples = [s.strip() for s in req.samples]
    if any(len(s) < 20 for s in samples) or len(set(samples)) < 3:
        raise HTTPException(422, "Provide three distinct samples of 20+ characters")
    client = gateway()
    usage = []
    client.observe = usage.append
    profile = learn_voice(client, samples)
    return store.save("brand", dict(kind="brand", name=req.name, samples=samples,
                                   profile=profile, version=1, usage=usage,
                                   mode=getattr(client, "mode", "test_double"), created_at=store.now()))


@api.post("/brands/samples")
def save_brand_samples(req: BrandRequest):
    samples = [s.strip() for s in req.samples]
    if any(len(s) < 20 for s in samples) or len(set(samples)) < 3:
        raise HTTPException(422, "Provide three distinct samples of 20+ characters")
    return store.save_brand_once(dict(kind="brand", name=req.name.strip(), samples=samples,
        profile={}, profile_status="pending", version=0, usage=[],
        mode="samples_only", created_at=store.now()))


@api.post("/brands/{brand_id}/learn")
def learn_saved_brand(brand_id: str):
    saved = require(brand_id, "brand")
    client = gateway()
    usage = []
    client.observe = usage.append
    profile = learn_voice(client, saved["samples"])
    return store.save("brand", dict(saved, profile=profile, profile_status="ready",
        version=saved.get("version", 0) + 1, usage=usage,
        mode=getattr(client, "mode", "test_double")), brand_id)


def create_post(req):
    brand = require(req.brand_id, "brand")
    if brand.get("profile_status") == "pending":
        raise HTTPException(422, "Brand samples saved. Learn its voice before generating content.")
    connections = [c for c in store.listing("social_connection") if c["brand_id"] == req.brand_id
                   and c["provider"] == req.platform and c["status"] != "disconnected"]
    connection_id = req.connection_id or (connections[0]["id"] if len(connections) == 1 else None)
    if connection_id and connection_id not in {c["id"] for c in connections}:
        raise HTTPException(422, "Generation connection must match the brand and platform")
    id = str(uuid4())
    post = store.save("post", dict(kind="post", brand_id=req.brand_id, brief=req.topic,
        platform=req.platform, voice=brand["profile"], voice_version=brand["version"],
        status="generating", learning_enabled=req.use_learnings, connection_id=connection_id,
        mode=os.getenv("CREATOROS_MODE", "live"), created_at=store.now()), id)
    return post


def execute(req, id):
    brand = require(req.brand_id, "brand")
    post = require(id, "post")
    learnings = [v for v in store.listing("learning") if
                 v["brand_id"] == req.brand_id and v["platform"] == req.platform
                 and (not v.get("connection_id") or v["connection_id"] == post.get("connection_id"))
                 and (v.get("method") != "deterministic_observation" or
                      v.get("updated_at", "") >= (datetime.now(timezone.utc)-timedelta(days=14)).isoformat())][:10] if req.use_learnings else []
    try:
        mesh = gateway()
        mesh.observe = lambda detail: store.audit(id, "mesh", detail)
        result = run_pipeline(mesh, req.topic, req.platform, brand["profile"], learnings,
                              lambda agent, detail: store.audit(id, agent, detail))
        result["schedule_recommendation"] = recommend(post)
        result["used_learning_ids"] = result["strategy"].get("applied_learning_ids", [])
        store.audit(id, "scheduler", result["schedule_recommendation"])
        return store.save("post", dict(post, **result,
                          status="approved" if result["approved"] else "needs_review"), id)
    except Exception as exc:
        store.save("post", dict(post, status="failed", error=type(exc).__name__), id)
        store.audit(id, "error", {"reason": str(exc) if isinstance(exc, ValueError)
                                 else type(exc).__name__})
        raise HTTPException(502, "Generation failed; inspect Mesh configuration and post audit") from exc


@api.post("/generate")
def generate(req: BriefRequest):
    post = create_post(req)
    return execute(req, post["id"])


@api.post("/runs", status_code=202)
def start_run(req: BriefRequest, tasks: BackgroundTasks):
    post = create_post(req)
    def work():
        try:
            execute(req, post["id"])
        except HTTPException:
            pass  # Failure and its audit trail were persisted by execute.
    tasks.add_task(work)
    return post


@api.get("/analytics/{brand_id}/{platform}")
def performance(brand_id: str, platform: str):
    require(brand_id, "brand")
    return analytics(brand_id, platform)


@api.get("/posts/{id}/slot")
def slot(id: str, timezone_name: str = "Asia/Kolkata"):
    try:
        return recommend(require(id, "post"), timezone_name)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, "Unknown timezone") from exc


@api.post("/demo/{scenario}")
def sample_scenario(scenario: str):
    if os.getenv("CREATOROS_MODE", "live") != "offline":
        raise HTTPException(409, "Sample scenarios are available in offline mode only")
    from demo import seed
    try:
        return seed(scenario)
    except KeyError as exc:
        raise HTTPException(404, "Unknown sample scenario") from exc


@api.get("/examples/{scenario}")
def preview_example(scenario: str):
    """Isolated, explicitly scripted preview. No live gateway or persistent user data."""
    import tempfile
    from demo import seed, SCENARIOS
    from offline import OfflineGateway
    if scenario not in SCENARIOS:
        raise HTTPException(404, "Unknown sample scenario")
    Path("data").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir="data") as directory:
        token = store.database_override.set(str(Path(directory) / "preview.db"))
        try:
            sample = seed(scenario)
            brand = sample["brand"]
            post = store.save("post", dict(kind="post", brand_id=brand["id"],
                brief=sample["brief"], platform=sample["platform"], voice=brand["profile"],
                voice_version=1, mode="offline_fixture", learning_enabled=True))
            result = run_pipeline(OfflineGateway(), sample["brief"], sample["platform"],
                brand["profile"], store.listing("learning"),
                lambda agent, detail: store.audit(post["id"], agent, detail))
            store.save("post", dict(post, **result, status="approved",
                schedule_recommendation=recommend(post)), post["id"])
            return dict(state={**{k: store.listing(k) for k in
                ("brand", "post", "learning", "metric", "audit")},
                "mode": "offline", "paid_enabled": False, "preview": True},
                post_id=post["id"], **sample)
        finally:
            store.database_override.reset(token)


@api.post("/posts/{id}/schedule")
def schedule(id: str, req: ScheduleRequest):
    post = require(id, "post")
    if post["status"] not in ("approved", "scheduled"):
        raise HTTPException(409, "Only approved content can be scheduled")
    due = req.scheduled_for.astimezone(timezone.utc)
    if due <= datetime.now(timezone.utc):
        raise HTTPException(422, "Schedule must be in the future")
    try:
        store.queue(id, due.isoformat())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    store.audit(id, "scheduler", {"reason": "User selected publication handoff time", "due": due.isoformat()})
    return store.get(id)


@api.post("/posts/{id}/metrics")
def metrics(id: str, req: MetricsRequest):
    post = require(id, "post")
    if post["status"] not in ("ready_to_publish", "feedback_recorded"):
        raise HTTPException(409, "Wait for the scheduled handoff before entering metrics")
    key = "metric:" + id + ":" + req.event_id
    previous = store.get(key)
    if previous:
        if previous["input"] != req.model_dump():
            raise HTTPException(409, "Event ID already used with different metrics")
        return previous
    rate = (req.likes + 2 * req.comments + 3 * req.saves) / req.impressions
    peers = [m for m in store.listing("metric") if m["brand_id"] == post["brand_id"]
             and m["post_id"] != id
             and m["platform"] == post["platform"] and m["input"]["source"] == req.source
             and m["input"]["window_hours"] == req.window_hours]
    latest_per_post = {}
    for metric in peers:
        latest_per_post.setdefault(metric["post_id"], metric)
    peers = list(latest_per_post.values())
    baseline = sum(m["rate"] for m in peers) / len(peers) if peers else None
    direction = "explore" if baseline is None else ("repeat" if rate > baseline else "avoid_or_test")
    learner = gateway()
    learner.observe = lambda detail: store.audit(id, "mesh", detail)
    hypothesis = learner.ask("Learning analyst: return rule and reason. Suggest a specific future "
        "hook/format/CTA change using the normalized engagement comparison. Never infer causation. "
        "First observation is exploratory; below-baseline output should change future approach. "
        "Simulated metrics are simulated evidence only.", dict(strategy=post["strategy"],
        text=post["text"], rate=rate, baseline=baseline, direction=direction, metrics=req.model_dump()))
    learning = dict(hypothesis, kind="learning", brand_id=post["brand_id"],
        platform=post["platform"], post_id=id, evidence_id=key, source=req.source,
        confidence="tentative", direction=direction, rate=rate, baseline=baseline,
        mode=getattr(learner, "mode", "test_double"))
    metric = dict(kind="metric", post_id=id, brand_id=post["brand_id"],
        platform=post["platform"], input=req.model_dump(), rate=rate, baseline=baseline,
        observed_at=store.now())
    try:
        return store.feedback(key, metric, learning)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
