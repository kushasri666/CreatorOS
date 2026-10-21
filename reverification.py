"""Idempotent one-call source recheck of an existing reviewed draft; no rewrite."""
import hashlib
import json
from uuid import uuid4
import storage
from grounding import build_report
from verification_service import verify_draft


def fingerprint(post):
    fields=('text','slides','sources','citations','assessments','brand_id','voice_version',
        'selected_draft_index','drafts','slide_versions','reviews','editorial_checks',
        'platform','brief','voice','mode','evidence_review','verification','verification_history',
        'grounded_report','status','approved')
    return hashlib.sha256(json.dumps({key:post.get(key) for key in fields},
        sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def editorial_lineage(post):
    """A source verdict cannot approve wording the selected editor never saw."""
    index=post.get('selected_draft_index')
    drafts=post.get('drafts');versions=post.get('slide_versions');assessments=post.get('assessments')
    if (type(index) is not int or index<0 or not isinstance(drafts,list) or not isinstance(versions,list)
            or not isinstance(assessments,list) or index>=min(len(drafts),len(versions),len(assessments))):
        return False,'Missing selected editorial lineage; a source-only recheck cannot create editorial approval.'
    if drafts[index]!=post.get('text') or versions[index]!=post.get('slides',[]):
        return False,'The saved caption/slides differ from the selected editorial draft; obtain a fresh editor review.'
    if not isinstance(assessments[index],dict) or assessments[index].get('ready') is not True:
        return False,'The selected draft has not passed editorial review.'
    # A later explicit hold/revocation remains effective even if an older
    # selected draft originally passed. A source recheck must not clear it.
    if not isinstance(assessments[-1],dict) or assessments[-1].get('ready') is not True:
        return False,'A later editorial hold remains unresolved.'
    return True,'Selected caption and slides match a passing editorial assessment with no later hold.'


def recheck(post_id,request_id,mesh_factory=None):
    if not isinstance(request_id,str) or not 8<=len(request_id)<=80:raise ValueError('A request ID of 8–80 characters is required')
    key='verification_recheck:'+hashlib.sha256((post_id+':'+request_id).encode()).hexdigest()
    with storage.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT body FROM records WHERE id=? AND kind='post'",(post_id,)).fetchone()
        post=json.loads(row[0]) if row else None
        if not post or not post.get('text') or not post.get('sources'):
            raise ValueError('Select a completed draft with saved source evidence before rechecking')
        snapshot=fingerprint(post)
        existing=db.execute("SELECT body FROM records WHERE id=? AND kind='verification_recheck'",(key,)).fetchone()
        if existing:
            prior=json.loads(existing[0])
            # Applying our source result legitimately updates conflicts, report,
            # history and approval fields. Replay only the exact input or exact
            # saved output, never unrelated changes made after completion.
            allowed={prior['input_sha256']}
            if prior.get('output_sha256'):allowed.add(prior['output_sha256'])
            if snapshot not in allowed:raise ValueError('The saved content/evidence changed; use a new explicit request ID')
            return prior
        if post.get('status')!='needs_review':raise ValueError('Only a draft held for review can start a new source recheck')
        if db.execute("SELECT 1 FROM records WHERE kind='verification_recheck' AND json_extract(body,'$.post_id')=? AND json_extract(body,'$.status')='checking'",(post_id,)).fetchone():
            raise ValueError('A source recheck for this post is already running')
        operation=dict(id=key,post_id=post_id,status='checking',input_sha256=snapshot,created_at=storage.now(),ai_calls=0)
        db.execute("INSERT INTO records VALUES (?,'verification_recheck',?)",(key,json.dumps(operation)))
    mesh=None
    try:
        from workflow import Mesh
        mesh=mesh_factory() if mesh_factory else Mesh(max_calls=1)
        mesh.observe=lambda detail:storage.audit(post_id,'mesh',dict(detail,recheck_id=key))
        result,review,_=verify_draft(mesh,post['text'],post.get('slides',[]),post.get('citations',[]),post['sources'],
            (post.get('evidence_review') or {}).get('conflicts',[]))
        checked=dict(post,verification=result,evidence_review=review)
        report=build_report(checked)
        # Source rechecks can never stand in for a successful editorial review.
        editorial_ready,editorial_reason=editorial_lineage(post)
        approved=editorial_ready and report['passed']
        with storage.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current=json.loads(db.execute('SELECT body FROM records WHERE id=?',(post_id,)).fetchone()[0])
            if fingerprint(current)!=snapshot or current.get('status')!='needs_review':
                operation.update(status='stale',reason='Content/evidence changed during recheck; result was not applied.')
            else:
                history=[*current.get('verification_history',[]),dict(result,recheck_id=key)]
                current.update(verification=result,evidence_review=review,grounded_report=report,verification_history=history,
                    approved=approved,status='approved' if approved else 'needs_review')
                db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(current),post_id))
                operation.update(status='completed' if approved else 'needs_review',approved=approved,
                    editorial_ready=editorial_ready,editorial_reason=editorial_reason,verification=result,
                    output_sha256=fingerprint(current))
            operation['ai_calls']=mesh.call_count
            db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(operation),key))
            event=dict(id=str(uuid4()),post_id=post_id,agent='source_recheck',at=storage.now(),detail=dict(
                recheck_id=key,status=operation['status'],approved=operation.get('approved',False),source_ids=[s['source_id'] for s in post['sources']],
                reason='Rechecked saved final wording once; prior failed judgments retained. Editorial approval is independently required.'))
            db.execute("INSERT INTO records VALUES (?, 'audit', ?)",(event['id'],json.dumps(event)))
        return operation
    except Exception as exc:
        storage.save('verification_recheck',dict(operation,status='failed',error_type=type(exc).__name__,
            ai_calls=getattr(mesh,'call_count',0)),key)
        raise
