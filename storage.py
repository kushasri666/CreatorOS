"""SQLite records and atomic, restart-safe publication handoff queue."""
import json
import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

database_override = ContextVar("database_override", default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    mode = os.getenv("CREATOROS_MODE", "live")
    path = Path(database_override.get() or os.getenv("CREATOROS_DB") or f"data/creatoros-{mode}.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, body TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS jobs (post_id TEXT PRIMARY KEY, due TEXT, status TEXT)")
    try:
        with db:
            yield db
    finally:
        db.close()


def save(kind, body, id=None):
    id = id or str(uuid4())
    body = dict(body, id=id)
    with connection() as db:
        db.execute("INSERT INTO records VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                   (id, kind, json.dumps(body)))
    return body


def get(id):
    with connection() as db:
        row = db.execute("SELECT body FROM records WHERE id=?", (id,)).fetchone()
    return json.loads(row[0]) if row else None


def save_brand_once(body):
    """Identical sample submissions reuse a brand, even with concurrent clicks."""
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        for row in db.execute("SELECT body FROM records WHERE kind='brand'"):
            existing = json.loads(row[0])
            if (existing["name"].strip().casefold() == body["name"].strip().casefold()
                    and existing.get("samples") == body["samples"]):
                return dict(existing, already_exists=True)
        body = dict(body, id=str(uuid4()))
        db.execute("INSERT INTO records VALUES (?, 'brand', ?)", (body["id"], json.dumps(body)))
        return dict(body, already_exists=False)


def listing(kind):
    with connection() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind=? ORDER BY rowid DESC", (kind,))]


def audit(post_id, agent, detail):
    return save("audit", dict(post_id=post_id, agent=agent, detail=detail, at=now()))


def records_for_run(kind, post_id):
    """Return persisted run records in insertion order, including equal timestamps."""
    with connection() as db:
        rows = db.execute("SELECT body FROM records WHERE kind=? AND json_extract(body, '$.post_id')=? ORDER BY rowid",
                          (kind, post_id)).fetchall()
    return [json.loads(row[0]) for row in rows]


def queue(post_id, due):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM records WHERE id=?", (post_id,)).fetchone()
        post = json.loads(row[0])
        if post["status"] not in ("approved", "scheduled"):
            raise ValueError("Post is no longer schedulable")
        post.update(status="scheduled", scheduled_for=due)
        db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(post), post_id))
        db.execute("INSERT INTO jobs VALUES (?, ?, 'queued') ON CONFLICT(post_id) DO UPDATE SET due=excluded.due,status='queued'",
                   (post_id, due))


def feedback(key, metric, learning):
    """One atomic evidence/learning commit; retrying the same event cannot multiply learning."""
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM records WHERE id=?", (key,)).fetchone()
        if row:
            previous = json.loads(row[0])
            if previous["input"] != metric["input"]:
                raise ValueError("Event ID already used with different metrics")
            return previous
        learning = dict(learning, id="learning:" + key)
        metric = dict(metric, id=key, learning_id=learning["id"])
        for kind, body in (("metric", metric), ("learning", learning)):
            db.execute("INSERT INTO records VALUES (?, ?, ?)", (body["id"], kind, json.dumps(body)))
        row = db.execute("SELECT body FROM records WHERE id=?", (metric["post_id"],)).fetchone()
        post = json.loads(row[0])
        post["status"] = "feedback_recorded"
        db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(post), post["id"]))
        event = dict(id=str(uuid4()), post_id=post["id"], agent="learner", at=now(), detail=learning)
        db.execute("INSERT INTO records VALUES (?, 'audit', ?)", (event["id"], json.dumps(event)))
        return metric


def tick():
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        jobs = db.execute("SELECT post_id FROM jobs WHERE status='queued' AND due<=?", (now(),)).fetchall()
        completed=0
        for job in jobs:
            row = db.execute("SELECT body FROM records WHERE id=?", (job[0],)).fetchone()
            if not row:
                db.execute("UPDATE jobs SET status='cancelled' WHERE post_id=?",(job[0],))
                continue
            post = json.loads(row[0])
            if post.get('status')!='scheduled' or post.get('approved') is False:
                db.execute("UPDATE jobs SET status='cancelled' WHERE post_id=?",(job[0],))
                event=dict(id=str(uuid4()),post_id=job[0],agent='scheduler',at=now(),
                    detail={'reason':'Queued handoff cancelled because approval or scheduled state was revoked.'})
                db.execute("INSERT INTO records VALUES (?, 'audit', ?)",(event['id'],json.dumps(event)))
                continue
            post["status"] = "ready_to_publish"
            completed+=1
            db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(post), job[0]))
            db.execute("UPDATE jobs SET status='completed' WHERE post_id=?", (job[0],))
            event = dict(id=str(uuid4()), post_id=job[0], agent="scheduler", at=now(),
                         detail={"reason": "Scheduled time reached; manual publishing handoff ready"})
            db.execute("INSERT INTO records VALUES (?, 'audit', ?)", (event["id"], json.dumps(event)))
    return completed
