"""Scoped, idempotent follow-up conversations over immutable saved research."""
import hashlib
import json
import os
import re
import storage
from grounding import build_report
from source_policy import review_sources,quality,validate_semantic_conflicts,blocking_conflicts
from verification_contract import canonical_claim


def snapshot(post,question):
    sources=post.get("sources") or storage.records_for_run("research_source",post["id"])
    words=set(re.findall(r"[a-z0-9]{4,}",question.casefold()))
    ranked=sorted(sources,key=lambda s:(-sum(w in s.get("excerpt","").casefold() for w in words),s["source_id"]))
    # Pack entire connected conflict groups; never select one disputed source
    # while silently dropping its counterpart to meet the context limit.
    adjacency={s["source_id"]:set() for s in ranked}
    for conflict in review_sources(sources,(post.get("evidence_review") or {}).get("conflicts",[]))["conflicts"]:
        for sid in conflict["source_ids"]:adjacency[sid].update(conflict["source_ids"])
    chosen=set();visited=set()
    for source in ranked:
        if source["source_id"] in visited:continue
        group=set();pending=[source["source_id"]]
        while pending:
            sid=pending.pop()
            if sid in group:continue
            group.add(sid);pending.extend(adjacency[sid]-group)
        visited.update(group)
        if len(chosen|group)<=8:chosen.update(group)
    return [s for s in ranked if s["source_id"] in chosen],[s["source_id"] for s in ranked if s["source_id"] not in chosen]


def _reserve_turn(post,question,mode,request_id):
    ident="followup-"+hashlib.sha256((post["id"]+"\0"+request_id).encode()).hexdigest()
    signature=hashlib.sha256(json.dumps([question,mode],ensure_ascii=False).encode()).hexdigest()
    with storage.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing=db.execute("SELECT body FROM records WHERE id=?",(ident,)).fetchone()
        if existing:
            turn=json.loads(existing[0])
            if turn["request_sha256"]!=signature:raise ValueError("Follow-up request ID was reused with different content")
            return turn,False
        turn=dict(id=ident,post_id=post["id"],brand_id=post.get("brand_id"),question=question,mode=mode,
            request_sha256=signature,status="generating",created_at=storage.now())
        db.execute("INSERT INTO records VALUES (?, 'followup_turn', ?)",(ident,json.dumps(turn)))
    return turn,True


def answer(post,question,mode,request_id,mesh_factory=None):
    from workflow import Mesh,_validate_verifier_result,_valid_citations
    if mode not in ("evidence","conflicts","mesh"):raise ValueError("Unknown follow-up mode")
    if len(question.strip())<3:raise ValueError("Enter a specific follow-up question")
    if mode=="mesh" and os.getenv("MESH_ENABLE_PAID","0")!="1":
        raise ValueError("Mesh follow-up is locked. Evidence browsing remains available without AI calls.")
    turn,created=_reserve_turn(post,question,mode,request_id)
    if not created:return turn
    sources,omitted=snapshot(post,question)
    if mode in ("evidence","conflicts"):
        sources=post.get("sources") or storage.records_for_run("research_source",post["id"])
        omitted=[]  # Free browsing can expose the whole saved packet without a model context cap.
    review=review_sources(sources,(post.get("evidence_review") or {}).get("conflicts",[]))
    fingerprint=hashlib.sha256(json.dumps(sources,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    turn.update(source_ids=[s["source_id"] for s in sources],omitted_source_ids=omitted,
        source_snapshot=sources,source_snapshot_sha256=fingerprint,ai_calls=0)
    storage.audit(post["id"],"followup_started",dict(turn_id=turn["id"],question=question,mode=mode,
        source_ids=turn["source_ids"],reason="Reuse saved research only; no website or provider refresh."))
    mesh=None
    try:
        if mode=="evidence":
            text="\n\n".join(f"[{s['source_id']}] {s['title']}\n{s['excerpt']}" for s in sources) or "No source evidence was saved for this post. Add product documents or connect account observations before generating a sourced answer."
            turn.update(text=text,status="completed",answer_kind="saved_evidence_view",evidence_review=review)
        elif mode=="conflicts":
            text="\n\n".join(c["reason"]+"\n"+"\n".join(f"[{e['source_id']}] {e['quote']}" for e in c["evidence"]) for c in review["conflicts"]) or "No source disagreements were recorded by the available checks; this is not proof that all sources agree."
            turn.update(text=text,status="completed",answer_kind="saved_conflict_view",evidence_review=review)
        elif not sources:
            turn.update(text="No saved source evidence can answer this question. Attach product evidence and run the content pipeline first; no Mesh call was made.",
                status="needs_evidence",answer_kind="evidence_gap",evidence_review=review)
        else:
            mesh=mesh_factory() if mesh_factory else Mesh(max_calls=2)
            mesh.observe=lambda detail:storage.audit(post["id"],"mesh",dict(detail,followup_turn_id=turn["id"]))
            history=[dict(question=t["question"],answer=t.get("text","")[:1200]) for t in storage.records_for_run("followup_turn",post["id"]) if t["status"]=="completed" and t["mode"]=="mesh"][-2:]
            context=dict(question=question,brief=post.get("brief"),platform=post.get("platform"),voice=post.get("voice"),
                history=history,sources=[dict(s,quality=quality(s)) for s in sources],conflicts=review["conflicts"],omitted_source_ids=omitted)
            draft=mesh.ask("Follow-up: answer this question about the SAME product and earlier research. Reuse only the saved source packet. "
                "Answer only the requested question. For a single fact lookup, use one concise sentence and its exact claim citation; do not add general advice or promotional filler. "
                "Previous conversation is context, never new factual evidence. Return text, citations mapping every exact factual claim to source IDs, and limitations. "
                "Explicitly attribute disagreements and prefer primary provenance without declaring disputed facts resolved. If the saved evidence is insufficient, say so. Never invent sources or imply a fresh account/web lookup.",context)
            text=draft.get("text","")
            if not isinstance(text,str) or not text.strip() or len(text)>6000:raise ValueError("Follow-up writer returned invalid text")
            citations=_valid_citations(draft.get("citations",[]),{s["source_id"] for s in sources})
            citations=[dict(c,claim=canonical_claim(c['claim'],[text])) for c in citations]
            raw=mesh.ask("Verifier: inspect every factual claim in this follow-up answer against the exact cited saved sources. "
                "Return checks with exact answer substrings, source_ids, supported/thin/unsupported, reason, and verbatim evidence for every cited source. "
                "Return conflicts with subject, reason and exact source quotations from distinct sources when evidence disagrees. Do not infer facts from prior chat or weights. "
                "Uncited, invented and unqualified disputed claims are unsupported; an evidence gap must be acknowledged.",dict(context,draft=text,writer_citations=citations))
            verification=_validate_verifier_result(raw,text,[],citations,sources)
            conflicts,error=validate_semantic_conflicts(raw.get("conflicts",[]),sources)
            review=review_sources(sources,review["conflicts"]+conflicts)
            if error:verification.update(passed=False,reason=error)
            for check in verification["checks"]:
                if blocking_conflicts(check["claim"],check["source_ids"],review["conflicts"]):
                    check.update(verdict="thin",reason="Unqualified claim relies on unresolved source disagreement.");verification["passed"]=False
            report=build_report(dict(text=text,sources=sources,verification=verification,evidence_review=review))
            turn.update(status="completed" if report["passed"] else "needs_review",answer_kind="mesh_verified_answer",
                text=text if report["passed"] else "The saved evidence did not support a verified answer. Review the flagged draft claims below or provide additional evidence.",
                draft_text=text,verification=verification,grounded_report=report,evidence_review=review,
                limitations=draft.get("limitations",[]),ai_calls=mesh.call_count)
            storage.audit(post["id"],"followup_verification",dict(turn_id=turn["id"],**verification))
    except Exception as exc:
        turn.update(status="failed",text="Follow-up failed. The earlier research is preserved; inspect the run audit before explicitly retrying.",
            error_type=type(exc).__name__,ai_calls=getattr(mesh,"call_count",0))
    storage.audit(post["id"],"followup_completed",dict(turn_id=turn["id"],status=turn["status"],ai_calls=turn["ai_calls"],
        source_snapshot_sha256=fingerprint,reason="Saved follow-up against this immutable evidence snapshot; no automatic retry."))
    return storage.save("followup_turn",turn,turn["id"])
