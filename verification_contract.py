"""Resolve model-selected IDs to immutable exact text; no semantic verdict shortcuts."""
import re


def segments(text):
    values=[text.strip()]
    # Both sentences and clauses: a factual clause need not inherit adjacent
    # motivational prose. Every value must still be an exact source substring.
    for pattern in (r'[^.!?\n]+(?:[.!?]+|$)',r'[^,;.!?\n]+'):
        values.extend(m.group().strip() for m in re.finditer(pattern,text))
    return list(dict.fromkeys(v for v in values if v))


def packet(data):
    candidates={}
    parts=[data.get('draft',''),*data.get('slides',[])]
    for citation in data.get('writer_citations',[]):
        claim=citation.get('claim') if isinstance(citation,dict) else None
        if isinstance(claim,str) and any(claim in part for part in parts if isinstance(part,str)) and claim not in candidates.values():
            candidates['C'+str(len(candidates)+1)]=claim
    for part in parts:
        if not isinstance(part,str):continue
        for text in segments(part):
            if text not in candidates.values():candidates['C'+str(len(candidates)+1)]=text
    receipts={}
    for source in data.get('sources',[]):
        for text in segments(source['excerpt']):
            receipts['R'+str(len(receipts)+1)]=dict(source_id=source['source_id'],quote=text)
    return candidates,receipts


def resolve(result,candidates,receipts):
    if not isinstance(result.get('checks'),list):raise ValueError('Verifier checks must be a list')
    checks=[]
    for raw in result['checks']:
        if not isinstance(raw,dict):checks.append(raw);continue
        claim=candidates.get(raw.get('candidate_id'),'')
        evidence=[]
        for entry in raw.get('evidence',[]) if isinstance(raw.get('evidence'),list) else []:
            receipt=receipts.get(entry.get('receipt_id')) if isinstance(entry,dict) else None
            evidence.append(dict(receipt) if receipt else dict(source_id='',quote=''))
        checks.append(dict(claim=claim,source_ids=raw.get('source_ids'),verdict=raw.get('verdict'),reason=raw.get('reason'),evidence=evidence))
    return dict(result,checks=checks,receipt_contract='exact-id-v1')


def canonical_claim(claim,parts):
    if any(claim in part for part in parts):return claim
    # Only remove fabricated terminal punctuation; never rewrite words or numbers.
    trimmed=claim.rstrip('.!?;:, \t\r\n')
    if len(trimmed)>=8 and trimmed!=claim and any(re.search(r'(?<!\w)'+re.escape(trimmed)+r'(?!\w)',part) for part in parts):return trimmed
    return claim
