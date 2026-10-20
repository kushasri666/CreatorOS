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
import memory
import research
import brand_media
import self_evaluation
import followups
from reports import render_report
from agent_graph import definition as workflow_definition
from platform_formats import format_contract
from grounding import build_report
from run_audit import build_trail


@asynccontextmanager
async def lifespan(app):
    for turn in store.listing("followup_turn"):
        if turn.get("status")=="generating":
            store.save("followup_turn",dict(turn,status="failed",error_type="Interrupted",
                text="Follow-up interrupted by server restart. Earlier research is preserved; retry explicitly."),turn["id"])
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
from instagram_publish import router as instagram_publish_router
api.include_router(instagram_publish_router)
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
    product_name: str = Field(default="", max_length=120)
    product_url: str = Field(default="", max_length=500)
    product_details: str = Field(default="", max_length=3000)


class BriefRequest(BaseModel):
    brand_id: str
    topic: str = Field(min_length=3, max_length=2000)
    platform: Literal["linkedin", "x", "instagram", "youtube", "telegram", "threads"] = "linkedin"
    use_learnings: bool = True
    connection_id: str | None = None
    use_research: bool = True
    document_ids: list[str] = Field(default_factory=list, max_length=3)
    product_name: str = Field(default="", max_length=120)
    product_url: str = Field(default="", max_length=500)
    product_details: str = Field(default="", max_length=3000)


class ResearchDocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=12000)


class AdaptRequest(BaseModel):
    platform: Literal["linkedin", "x", "instagram", "youtube", "telegram", "threads"]
    connection_id: str | None = None
    use_learnings: bool = True


class MediaTranscriptRequest(BaseModel):
    text: str = Field(default="", max_length=12000)


class FollowupRequest(BaseModel):
    question: str = Field(default="Show the saved evidence",min_length=3,max_length=2000)
    mode: Literal["evidence","conflicts","mesh"] = "evidence"
    request_id: str = Field(min_length=8,max_length=80)


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
    documents=[{k:d.get(k) for k in ("id","brand_id","filename","sha256","created_at","media_type","mime_type","size_bytes","evidence_status","transcript_sha256")} for d in store.listing("research_document")]
    return dict({k: store.listing(k) for k in ("brand", "post", "learning", "metric", "audit", "video")},
                research_document=documents,
                mode=os.getenv("CREATOROS_MODE", "live"), paid_enabled=os.getenv("MESH_ENABLE_PAID", "0") == "1")


@api.get("/evaluation/grounding")
def grounding_evaluation():
    try:return self_evaluation.load_report()
    except FileNotFoundError as exc:
        raise HTTPException(404,"No recorded grounding evaluation. Run python scripts/evaluate_grounding.py locally; it uses no AI calls.") from exc


@api.get("/evaluation/grounding/questions")
def grounding_questions():
    return FileResponse(self_evaluation.QUESTIONS,media_type="application/json",filename="creatoros-grounding-questions.json")


@api.get("/evaluation/grounding/fixtures")
def grounding_fixtures():
    return FileResponse(self_evaluation.FIXTURES,media_type="application/json",filename="creatoros-authored-evaluation-fixtures.json")


@api.get("/posts/{id}/evidence-report")
def evidence_report(id: str):
    """Rebuild from saved evidence; existing/fixture posts are never implicitly verified."""
    post = require(id, "post")
    return dict(post_id=id, brand_id=post.get("brand_id"), **build_report(post))


@api.get("/workflow/definition")
def execution_definition():
    return workflow_definition()


@api.get("/posts/{id}/report",response_class=HTMLResponse)
def content_report(id:str,download:bool=False):
    post=require(id,"post")
    if not post.get("sources"):post=dict(post,sources=store.records_for_run("research_source",id))
    headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff",
        "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"}
    if download:headers["Content-Disposition"]='attachment; filename="creatoros-report.html"'
    return HTMLResponse(render_report(post),headers=headers)


@api.get("/posts/{id}/followups")
def list_followups(id:str):
    require(id,"post")
    return store.records_for_run("followup_turn",id)


@api.post("/posts/{id}/followups")
def content_followup(id:str,req:FollowupRequest):
    post=require(id,"post")
    if post.get("status")=="generating":raise HTTPException(409,"Wait for the current content run before asking a follow-up.")
    try:return followups.answer(post,req.question.strip(),req.mode,req.request_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc


@api.get("/posts/{id}/audit-trail")
def audit_trail(id: str):
    post = require(id, "post")
    return build_trail(post, store.records_for_run("audit", id),
                       store.records_for_run("research_source", id))


@api.get('/memory/{brand_id}/{platform}')
def memory_status(brand_id:str, platform:Literal['instagram','linkedin','youtube','telegram','threads','x']):
    require(brand_id,'brand')
    items=memory.review(brand_id,platform)
    ids={item['id'] for item in items}
    return dict(items=items,revisions=[r for r in store.listing('memory_revision') if r['learning_id'] in ids],
                note='Evidence checked means references and versions match, not proven truth or engagement uplift. Stale lessons are withheld. No AI or provider calls.')


@api.post('/memory/{brand_id}/{platform}/refresh')
def refresh_memory(brand_id:str, platform:Literal['instagram','linkedin','youtube','telegram','threads','x']):
    require(brand_id,'brand')
    memory.review(brand_id,platform,refresh=True)
    return memory_status(brand_id,platform)


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
                                   product_name=req.product_name.strip(), product_url=req.product_url.strip(),
                                   product_details=req.product_details.strip(),
                                   profile=profile, version=1, usage=usage,
                                   mode=getattr(client, "mode", "test_double"), created_at=store.now()))


@api.post("/brands/samples")
def save_brand_samples(req: BrandRequest):
    samples = [s.strip() for s in req.samples]
    if any(len(s) < 20 for s in samples) or len(set(samples)) < 3:
        raise HTTPException(422, "Provide three distinct samples of 20+ characters")
    return store.save_brand_once(dict(kind="brand", name=req.name.strip(), samples=samples,
        product_name=req.product_name.strip(), product_url=req.product_url.strip(),
        product_details=req.product_details.strip(),
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


@api.post("/brands/{brand_id}/research-documents")
def research_document(brand_id: str, req: ResearchDocumentRequest):
    try:
        document, created = research.save_document(brand_id, req.filename, req.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return dict(id=document["id"], filename=document["filename"], brand_id=brand_id,
        sha256=document["sha256"], created=created,
        note="Stored locally for this brand. It is treated as untrusted evidence, not as instructions.")


@api.post("/brands/{brand_id}/research-media")
async def upload_brand_media(brand_id: str, filename: str, request: Request):
    require(brand_id, "brand")
    try:
        length=request.headers.get("content-length")
        if length and (not length.isdigit() or int(length)>brand_media.MAX_MEDIA_BYTES):
            raise brand_media.UploadError("Media exceeds the 50 MiB upload limit",413)
        doc,created=await brand_media.save_media(brand_id,filename,request.stream())
    except brand_media.UploadError as exc:
        raise HTTPException(exc.status,str(exc)) from exc
    return dict(id=doc["id"],filename=doc["filename"],brand_id=brand_id,created=created,
        media_type=doc["media_type"],evidence_status=doc["evidence_status"],
        note="Media saved locally. Add a transcript or notes to use it as content evidence; no automatic transcription or AI call ran.")


@api.get("/brands/{brand_id}/research-media/{document_id}/file")
def brand_media_file(brand_id:str,document_id:str):
    try:
        doc=brand_media.get_media(brand_id,document_id)
        path=brand_media.media_path(doc)
    except brand_media.UploadError as exc:
        raise HTTPException(exc.status,str(exc)) from exc
    return FileResponse(path,media_type=doc["mime_type"],filename=doc["filename"],content_disposition_type="inline",
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@api.get("/brands/{brand_id}/research-media/{document_id}/transcript")
def brand_media_transcript(brand_id:str,document_id:str):
    try:doc=brand_media.get_media(brand_id,document_id)
    except brand_media.UploadError as exc:raise HTTPException(exc.status,str(exc)) from exc
    return dict(text=doc.get("text",""),origin="user_supplied",evidence_status=doc["evidence_status"])


@api.put("/brands/{brand_id}/research-media/{document_id}/transcript")
def update_brand_media_transcript(brand_id:str,document_id:str,req:MediaTranscriptRequest):
    try:doc=brand_media.save_transcript(brand_id,document_id,req.text)
    except brand_media.UploadError as exc:raise HTTPException(exc.status,str(exc)) from exc
    return dict(id=doc["id"],evidence_status=doc["evidence_status"],
        note="Saved user-supplied transcript/notes. Future content runs can cite this text; no AI call ran.")


def create_post(req):
    brand = require(req.brand_id, "brand")
    if brand.get("profile_status") == "pending":
        raise HTTPException(422, "Brand samples saved. Learn its voice before generating content.")
    docs={d["id"] for d in store.listing("research_document") if d.get("brand_id")==req.brand_id}
    if any(id not in docs for id in req.document_ids):
        raise HTTPException(422,"Selected research documents must belong to this brand")
    product = {
        "name": req.product_name.strip() or brand.get("product_name", "").strip(),
        "url": req.product_url.strip() or brand.get("product_url", "").strip(),
        "details": req.product_details.strip() or brand.get("product_details", "").strip(),
    }
    if os.getenv("CREATOROS_MODE", "live") == "live" and not product["name"]:
        raise HTTPException(422, "Name the product or service this post should promote. Add its product page or key facts for product-specific content.")
    connections = [c for c in store.listing("social_connection") if c["brand_id"] == req.brand_id
                   and c["provider"] == req.platform and c["status"] != "disconnected"]
    connection_id = req.connection_id or (connections[0]["id"] if len(connections) == 1 else None)
    if connection_id and connection_id not in {c["id"] for c in connections}:
        raise HTTPException(422, "Generation connection must match the brand and platform")
    id = str(uuid4())
    post = store.save("post", dict(kind="post", brand_id=req.brand_id, brief=req.topic,
        platform=req.platform, voice=brand["profile"], voice_version=brand["version"],
        use_research=req.use_research, document_ids=req.document_ids, product=product,
        status="generating", learning_enabled=req.use_learnings, connection_id=connection_id,
        mode=os.getenv("CREATOROS_MODE", "live"), created_at=store.now()), id)
    return post


def execute(req, id):
    brand = require(req.brand_id, "brand")
    post = require(id, "post")
    store.audit(id,"run_started",dict(brief=req.topic,platform=req.platform,brand_id=req.brand_id,
        reason="Started this content run; subsequent questions, retrievals and verdicts belong to this post ID."))
    try:
        learnings = memory.retrieve(req.brand_id,req.platform,post.get("connection_id")) if req.use_learnings else []
        mesh = gateway()
        mesh.observe = lambda detail: store.audit(id, "mesh", detail)
        retrieve_more = None
        retrieve_initial = None
        sources=[];warnings=[]
        if getattr(mesh,"mode","") == "live_mesh":
            product_evidence=post.get("product",{}) if req.use_research else dict(post.get("product",{}),url="")
            def retrieve_initial():
                try:
                    found,notes = research.gather(id,req.brand_id,req.topic,product_evidence,req.document_ids,
                        req.platform if req.use_research else None,connection_id=post.get("connection_id"))
                except ValueError as exc:raise HTTPException(422,str(exc)) from exc
                if not req.use_research:
                    notes.append("Connected-account metric collection was not requested for this run; saved brand documents remain included.")
                return found,notes
            def retrieve_more(claims, existing_sources):
                return research.gather_more(id,req.brand_id,req.topic,product_evidence,claims,existing_sources,
                    platform=req.platform if req.use_research else None,connection_id=post.get("connection_id"))
        else:
            sources=[]; warnings=["Offline mode does not fetch provider metrics, product pages, or attach uploaded documents to an AI call."]
        result = run_pipeline(mesh, req.topic, req.platform, brand["profile"], learnings,
                              lambda agent, detail: store.audit(id, agent, detail),
                              sources=sources,research_warnings=warnings,product=post.get("product",{}),
                              research_more=retrieve_more,research_initial=retrieve_initial)
        result["schedule_recommendation"] = recommend(post)
        result["used_learning_ids"] = result["strategy"].get("applied_learning_ids", [])
        store.audit(id, "scheduler", result["schedule_recommendation"])
        saved=store.save("post", dict(post, **result,
                          status="approved" if result["approved"] else "needs_review"), id)
        store.audit(id,"run_completed",dict(status=saved["status"],selected_draft_version=result["selected_draft_index"]+1,
            source_ids=[s["source_id"] for s in result.get("sources",[])],
            reason="Run completed; quality and evidence gates determined the final approval state."))
        return saved
    except HTTPException:
        store.save("post",dict(post,status="failed",error="research_input_invalid"),id)
        store.audit(id,"run_failed",dict(reason="Research input validation failed; prior decisions and retrieval attempts remain recorded."))
        raise
    except Exception as exc:
        store.save("post", dict(post, status="failed", error=type(exc).__name__), id)
        store.audit(id, "error", {"reason": str(exc) if isinstance(exc, ValueError)
                                 else type(exc).__name__})
        store.audit(id,"run_failed",dict(error_type=type(exc).__name__,reason="Run failed; all earlier recorded steps remain available in this run's audit trail."))
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


@api.get("/posts/{id}/adaptation-plan")
def adaptation_plan(id: str):
    post=require(id,"post")
    return dict(source_post_id=id,brand_id=post["brand_id"],idea=post["brief"],ai_calls=0,
        platforms={p:format_contract(p) for p in ("linkedin","x","instagram","youtube","telegram","threads")},
        note="Plan only. Starting one adaptation runs its own Mesh pipeline and budget; no publishing is triggered.")


@api.post("/posts/{id}/adapt",status_code=202)
def adapt_post(id: str,req: AdaptRequest,tasks: BackgroundTasks):
    source=require(id,"post")
    if source.get("status") in ("generating","failed"):
        raise HTTPException(409,"Finish or review the source run before adapting its idea")
    if req.platform==source["platform"]:
        raise HTTPException(422,"Choose a different target platform for this adaptation")
    product=source.get("product",{})
    brief=BriefRequest(brand_id=source["brand_id"],topic=source["brief"],platform=req.platform,
        use_learnings=req.use_learnings,connection_id=req.connection_id,use_research=source.get("use_research",True),
        document_ids=source.get("document_ids",[]),product_name=product.get("name",""),
        product_url=product.get("url",""),product_details=product.get("details",""))
    post=start_run(brief,tasks)
    post=store.save("post",dict(post,adaptation_of=id,source_platform=source["platform"],
        adaptation_policy="Same brief and brand; fresh native format, evidence retrieval and independent checks"),post["id"])
    store.audit(post["id"],"adaptation",dict(source_post_id=id,source_platform=source["platform"],
        target_platform=req.platform,reason="Adapt the idea with native formatting; source post copy is not treated as factual evidence."))
    return post


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
                brand["profile"], memory.retrieve(brand['id'],sample['platform']),
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
        "Simulated metrics are simulated evidence only. Do not attribute performance to tone, "
        "vocabulary, CTA or another feature unless supplied data isolates that feature. "
        "A baseline comparison alone does not explain why a post performed differently. "
        "Frame untested explanations only as future experiments.", dict(strategy=post["strategy"],
        text=post["text"], rate=rate, baseline=baseline, direction=direction, metrics=req.model_dump()))
    learning = dict(hypothesis, kind="learning", brand_id=post["brand_id"],
        platform=post["platform"], post_id=id, evidence_id=key, source=req.source,
        confidence="tentative", direction=direction, rate=rate, baseline=baseline,
        mode=getattr(learner, "mode", "test_double"))
    metric = dict(kind="metric", post_id=id, brand_id=post["brand_id"],
        platform=post["platform"], input=req.model_dump(), rate=rate, baseline=baseline,
        observed_at=store.now())
    try:
        saved = store.feedback(key, metric, learning)
        memory.inspect(store.get(saved['learning_id']))
        return saved
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
