"""Self-correcting evidence memory. Checks provenance, not the truth of model prose."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import storage

POLICY = "evidence-memory-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":" )).encode()).hexdigest()


def proof(item):
    ids = item.get("evidence_ids") or ([item["evidence_id"]] if item.get("evidence_id") else [])
    if not ids:
        return None,"No linked evidence",None
    evidence = {r["id"]:r for kind in ("metric","social_metric") for r in storage.listing(kind)}
    parts=[]
    oldest=None
    for id in ids:
        row=evidence.get(id)
        if not row:return None,"Linked evidence is missing or expired",None
        source=row.get("source") or row.get("input",{}).get("source")
        if row.get("brand_id")!=item["brand_id"] or row.get("platform")!=item["platform"] or source!=item.get("source"):
            return None,"Evidence brand, platform or source does not match",None
        if item.get("connection_id") and row.get("connection_id")!=item["connection_id"]:
            return None,"Evidence belongs to another account",None
        for key in ("window","age_bucket","formula"):
            if item.get(key) is not None and row.get(key)!=item[key]:return None,"Incompatible observation cohort",None
        at=row.get("collected_at") or row.get("observed_at")
        try:
            at=datetime.fromisoformat(at)
            if at.tzinfo is None:raise ValueError()
        except (ValueError,TypeError):return None,"Evidence timestamp is unavailable",None
        if at>datetime.now(timezone.utc)+timedelta(minutes=5):return None,"Evidence timestamp is in the future",None
        oldest=min(oldest,at) if oldest else at
        post=storage.get(row["post_id"])
        if not post or post.get("brand_id")!=item["brand_id"] or post.get("platform")!=item["platform"]:
            return None,"Source post is missing or incompatible",None
        # Exclude delivery status and backlinks so recording feedback does not invalidate itself.
        counters={k:row.get(k) for k in ("id","post_id","brand_id","platform","connection_id","source","input","counts","rate","baseline","window","age_bucket","formula","observed_at","collected_at")}
        content={k:post.get(k) for k in ("text","slides","voice_version","strategy")}
        parts.append(dict(evidence=counters,post_hash=digest(content)))
    connection=storage.get(item["connection_id"]) if item.get("connection_id") else None
    if item.get("connection_id") and (not connection or connection.get("status")=="disconnected"):
        return None,"Source account is disconnected or missing",oldest
    brand=storage.get(item["brand_id"])
    if not brand:return None,"Brand is missing",oldest
    return digest(dict(evidence=parts,brand_version=brand.get("version"),profile=brand.get("profile"))),None,oldest


def claim_hash(item):
    return digest({k:item.get(k) for k in ("rule","reason","source","method","confidence","direction","rate","baseline","evidence_ids","evidence_id","brand_id","platform","connection_id","window","age_bucket","formula")})


def anchor(item,version=1):
    fingerprint,error,_=proof(item)
    body=dict(learning_id=item["id"],version=version,policy=POLICY,proof_hash=fingerprint,
              claim_hash=claim_hash(item),registered_at=storage.now(),invalid_reason=None)
    evidence=storage.get(item.get("evidence_id",""))
    body['origin_post_id']=item.get('post_id') or (evidence or {}).get('post_id')
    if error:body["invalid_reason"]=error
    return storage.save("memory_state",body,"memory:"+item["id"])


def write_learning(body,id):
    """Archive a version receipt before replacing a deterministic, re-derived hypothesis."""
    candidate=dict(body,id=id)
    current_hash,error,_=proof(candidate)
    evidence=storage.get(candidate.get('evidence_id',''))
    with storage.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous=db.execute('SELECT body FROM records WHERE id=?',(id,)).fetchone()
        state=db.execute('SELECT body FROM records WHERE id=?',('memory:'+id,)).fetchone()
        previous=json.loads(previous[0]) if previous else None
        state=json.loads(state[0]) if state else None
        changed=not previous or not state or state.get("proof_hash")!=current_hash or state.get("claim_hash")!=claim_hash(candidate)
        if previous and not changed and not state.get("invalid_reason"):
            return previous,False
        version=(state.get("version",0) if state else 0)+1
        if previous:
            receipt=dict(id='memory_revision:'+id+':'+str(version-1),learning_id=id,version=version-1,
                         claim_hash=claim_hash(previous),superseded_at=storage.now())
            if previous.get("platform")!='youtube':receipt.update(rule=previous.get("rule"),reason=previous.get("reason"))
            db.execute("INSERT OR REPLACE INTO records VALUES (?,'memory_revision',?)",(receipt['id'],json.dumps(receipt)))
        state=dict(id='memory:'+id,learning_id=id,version=version,policy=POLICY,proof_hash=current_hash,
                   claim_hash=claim_hash(candidate),registered_at=storage.now(),invalid_reason=error,
                   origin_post_id=candidate.get('post_id') or (evidence or {}).get('post_id'))
        for kind,row in (('learning',candidate),('memory_state',state)):
            db.execute('INSERT INTO records VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(row['id'],kind,json.dumps(row)))
    return candidate,True


def invalidate(id,reason):
    item=storage.get(id)
    if not item:return
    state=storage.get("memory:"+id) or anchor(item)
    if state.get("invalid_reason")!=reason:
        storage.save("memory_state",dict(state,invalid_reason=reason),state["id"])


def inspect(item,record=True):
    state=storage.get("memory:"+item["id"])
    legacy=state is None
    state=state or anchor(item)
    current,error,oldest=proof(item)
    reason=error or state.get("invalid_reason")
    if not reason and state["claim_hash"]!=claim_hash(item):reason="Claim changed without a new evidence-grounded version"
    if not reason and state["proof_hash"]!=current:reason="Evidence, source content or brand version changed"
    now=datetime.now(timezone.utc)
    if not reason and (oldest is None or oldest < now-timedelta(days=14)):reason="Evidence is older than the 14-day freshness window"
    if not reason and oldest > now+timedelta(minutes=5):reason="Evidence timestamp is in the future"
    status="stale" if reason else "evidence_checked"
    note=reason or "Evidence references and versions match; the interpretation remains a tentative hypothesis, not a verified fact"
    check=dict(status=status,usable=not bool(reason),reason=note,version=state["version"],
               checked_at=storage.now(),legacy_anchor=legacy,policy=POLICY)
    if record and (state.get("last_status")!=status or state.get("last_reason")!=note):
        storage.save("memory_state",dict(state,last_status=status,last_reason=note,last_checked_at=check["checked_at"]),state["id"])
        post_id=item.get("post_id") or state.get('origin_post_id')
        if not post_id:
            ev=storage.get(item.get("evidence_id",""))
            post_id=ev.get("post_id") if ev else None
        storage.audit(post_id,"memory",dict(check,learning_id=item["id"]))
    return dict(item,memory=check)


def review(brand_id,platform,refresh=False):
    if refresh:
        from social import learn_from_observations
        learn_from_observations(brand_id,platform)
    return [inspect(item) for item in storage.listing("learning") if item.get("brand_id")==brand_id and item.get("platform")==platform]


def retrieve(brand_id,platform,connection_id=None):
    return [item for item in review(brand_id,platform,refresh=True) if item["memory"]["usable"]
            and (not item.get("connection_id") or item["connection_id"]==connection_id)][:10]
