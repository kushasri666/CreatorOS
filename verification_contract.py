"""Resolve model-selected IDs to immutable exact text; no semantic verdict shortcuts."""
import re


def units(draft,slides,split_clauses=True):
    """Stable sentence/line units; repeated identical prose shares one review."""
    result={}
    for part in [draft,*slides]:
        if not isinstance(part,str):continue
        for line in part.splitlines():
            separator=r'(?<=[.!?])\s+'
            if split_clauses:separator+=r'|;\s+|,\s+(?:and|but|while)\s+|\s+(?:and|but|while)\s+(?=(?:it|they|this|that)\b)'
            for text in re.split(separator,line):
                text=text.strip()
                if text and text not in result.values():result['U'+str(len(result)+1)]=text
    return result


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
    for text in units(data.get('draft',''),data.get('slides',[])).values():
        if text not in candidates.values():candidates['C'+str(len(candidates)+1)]=text
    for part in parts:
        if not isinstance(part,str):continue
        # Whole-post/sentence/clause copies used to multiply the same assertion
        # in the prompt. Keep exact units plus useful short clauses; retain any
        # writer-cited whole passage above without synthesizing new claim text.
        for match in re.finditer(r'[^,;.!?\n]+',part):
            text=match.group().strip()
            if not text:continue
            if text not in candidates.values():candidates['C'+str(len(candidates)+1)]=text
    receipts={}
    for source in data.get('sources',[]):
        for text in segments(source['excerpt']):
            receipts['R'+str(len(receipts)+1)]=dict(source_id=source['source_id'],quote=text)
    return candidates,receipts


def resolve(result,candidates,receipts,coverage_units=None):
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
    resolved=dict(result,checks=checks,receipt_contract='exact-id-v1')
    if coverage_units is not None:
        coverage=[]
        for row in result.get('coverage',[]) if isinstance(result.get('coverage'),list) else []:
            if not isinstance(row,dict):coverage.append({});continue
            ids=row.get('candidate_ids')
            coverage.append(dict(unit_id=row.get('unit_id'),kind=row.get('kind'),reason=row.get('reason'),
                claims=[candidates.get(i,'') for i in ids] if isinstance(ids,list) and all(isinstance(i,str) for i in ids) else None))
        resolved.update(coverage=coverage,coverage_required=True,coverage_version='unit-v2')
    return resolved


def validate_coverage(result,checks,draft,slides):
    expected=units(draft,slides,split_clauses=result.get('coverage_version')=='unit-v2');rows=result.get('coverage')
    if not isinstance(rows,list):return False,'Missing sentence coverage manifest'
    ids=[r.get('unit_id') for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or len(set(i for i in ids if isinstance(i,str)))!=len(rows) or set(i for i in ids if isinstance(i,str))!=set(expected):
        return False,'Every sentence/line requires exactly one valid coverage classification'
    for row in rows:
        kind,claims=row.get('kind'),row.get('claims')
        if kind not in ('factual','mixed','nonfactual') or not isinstance(row.get('reason'),str) or not row['reason'].strip() or not isinstance(claims,list):
            return False,'Malformed coverage classification'
        if kind=='nonfactual':
            if claims:return False,'Nonfactual coverage cannot hide linked factual candidates'
            continue
        if not claims or any(not isinstance(c,str) or not c or (c not in expected[row['unit_id']] and expected[row['unit_id']] not in c) for c in claims):
            return False,'Factual coverage must link exact candidates in that unit'
        if any(not any(check['claim']==claim for check in checks) for claim in claims):
            return False,'Factual sentence was classified but its assertion was never checked'
    return True,'Every sentence/line was classified; semantic classification still depends on the model'


def canonical_claim(claim,parts):
    if any(claim in part for part in parts):return claim
    # Only remove fabricated terminal punctuation; never rewrite words or numbers.
    trimmed=claim.rstrip('.!?;:, \t\r\n')
    if len(trimmed)>=8 and trimmed!=claim and any(re.search(r'(?<!\w)'+re.escape(trimmed)+r'(?!\w)',part) for part in parts):return trimmed
    return claim
