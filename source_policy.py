"""Visible provenance weights and conservative, zero-call contradiction checks."""
import hashlib
import re

QUALITY = {
    "social_account_metrics": (0.95,"primary_observation","Authenticated provider observations; limited to that account and reporting window."),
    "official_product_page": (0.90,"configured_primary","Brand-supplied official product URL; ownership and claims are not independently certified."),
    "primary_source": (0.90,"primary","Explicit primary-source provenance; still inspect the actual evidence."),
    "user_product_facts": (0.75,"owner_supplied","Approved facts supplied by the brand owner, not independent confirmation."),
    "user_document": (0.65,"uploaded","Uploaded document with recorded hash; authority is not independently verified."),
    "user_media_transcript": (0.55,"supplied_notes","User-supplied transcript/notes; raw audio/video has not been analyzed."),
    "third_party_blog": (0.30,"secondary","Secondary commentary; prefer a primary source for the same claim."),
}


def quality(source):
    score,tier,reason=QUALITY.get(source.get("source_type"),(0.25,"unknown","Unknown provenance; do not assume authority."))
    if source.get("is_current") is False:
        score=max(0,score-0.25);reason+=" Explicitly marked non-current; retain it for disagreement history."
    return dict(score=score,tier=tier,reason=reason,
        scope="account_and_window_only" if source.get("source_type")=="social_account_metrics" else "source_claims_only",
        caution="Provenance weight is not a probability of truth and never resolves a contradiction by itself.")


def _entity(text):
    text=re.sub(r"\b(?:current|archived|old|new|specifications?|specs?|20\d{2})\b","",text.casefold())
    return " ".join(text.split()).strip(" :")


def _numeric_facts(source):
    text=source.get("excerpt","")
    pattern=r"(?P<entity>[A-Za-z][A-Za-z0-9 '-]{1,65}?)\s+(?:has|features|offers|supports|specification:)\s*(?P<value>\d+(?:\.\d+)?)\s+(?P<attribute>(?:(?:grind|power|brew)\s+)?(?:modes?|settings?|hours?|minutes?|grams?|ml))\b"
    for match in re.finditer(pattern,text,re.I):
        entity=_entity(match["entity"])
        if entity:
            yield dict(entity=entity,attribute=match["attribute"].casefold().rstrip("s"),value=match["value"],quote=match.group(0),source_id=source["source_id"])
    # Handles "Current 2026 ModeCup specification: 6 modes" without pretending
    # to compare unrelated numbers such as price, date, reach and impressions.


def _make_conflict(rows,reason,method,sources,subject=None):
    ids=sorted({r["source_id"] for r in rows})
    key=repr(sorted((r["source_id"],r["quote"]) for r in rows))
    preferred=max(ids,key=lambda sid:(quality(sources[sid])["score"],sid))
    return dict(id="conflict-"+hashlib.sha256(key.encode()).hexdigest()[:12],source_ids=ids,
        subject=subject or (rows[0].get("entity","")+" "+rows[0].get("attribute","")).strip(),
        evidence=rows,reason=reason,method=method,status="unresolved",preferred_source_id=preferred,
        preference_reason="Highest provenance score is shown as a review hint; disagreement remains unresolved.")


def review_sources(sources,semantic_conflicts=()):
    indexed={s["source_id"]:s for s in sources}
    groups={}
    for source in sources:
        for row in _numeric_facts(source):groups.setdefault((row["entity"],row["attribute"]),[]).append(row)
    conflicts=[]
    for (entity,attribute),rows in groups.items():
        if len({r["source_id"] for r in rows})>1 and len({r["value"] for r in rows})>1:
            conflicts.append(_make_conflict(rows,f"Sources disagree on {entity} {attribute}: "+", ".join(sorted({r["value"] for r in rows})),"deterministic_numeric",indexed))
    for conflict in semantic_conflicts:
        if all(sid in indexed for sid in conflict.get("source_ids",[])):
            conflicts.append(conflict)
    unique={c["id"]:c for c in conflicts}
    return dict(policy_version="provenance-v1",sources=[dict(source_id=s["source_id"],**quality(s)) for s in sources],
        conflicts=list(unique.values()),limitations=["Local numeric checks cover only explicit comparable statements; semantic disagreements are also requested from the Mesh verifier.",
            "Scores prioritize provenance rather than establish truth. A blog cannot become primary merely by sounding confident."])


def validate_semantic_conflicts(raw,sources):
    if not isinstance(raw,list):return [],"Verifier conflicts must be a list"
    indexed={s["source_id"]:s for s in sources};valid=[]
    for item in raw:
        if not isinstance(item,dict) or not isinstance(item.get("reason"),str) or not isinstance(item.get("subject"),str):
            return [],"Malformed source conflict"
        evidence=item.get("evidence",[])
        if not isinstance(evidence,list) or len(evidence)<2:return [],"A conflict needs quotations from two sources"
        for row in evidence:
            if not isinstance(row,dict) or row.get("source_id") not in indexed or not isinstance(row.get("quote"),str) or not row["quote"].strip() or row["quote"] not in indexed[row["source_id"]].get("excerpt",""):
                return [],"Conflict evidence did not match saved source quotations"
        ids={r["source_id"] for r in evidence}
        if len(ids)<2:return [],"A cross-source conflict requires distinct sources"
        valid.append(_make_conflict(evidence,item["reason"],"mesh_verifier",indexed,subject=item["subject"]))
    return valid,None


def blocking_conflicts(claim,source_ids,conflicts):
    # Attribution makes a statement about what a source says, rather than silently
    # declaring one disputed product value to be the established truth.
    attributed=bool(re.search(r"\b(?:according to|reports?|states?|lists?|specifications?|sources? disagree|conflicting)\b",claim,re.I))
    if attributed:return []
    result=[]
    for conflict in conflicts:
        if not set(source_ids)&set(conflict["source_ids"]):continue
        if conflict["method"]=="deterministic_numeric":
            sample=conflict["evidence"][0]
            if sample["entity"] not in claim.casefold() or sample["attribute"] not in claim.casefold():continue
        result.append(conflict["id"])
    return result
