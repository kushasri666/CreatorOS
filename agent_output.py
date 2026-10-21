"""Strict structural contracts for model replies; no factuality shortcuts."""
import json
import math


def parse(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Ambiguous duplicate JSON key')
            result[key]=value
        return result
    def constant(_):raise ValueError('Nonfinite JSON number')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=constant)


def valid(role,result,data):
    if not isinstance(result,dict):return False
    role=role.split(':')[0]
    def strings(key):return isinstance(result.get(key),list) and all(isinstance(v,str) for v in result[key])
    def texts(*keys):return all(isinstance(result.get(k),str) and result[k].strip() for k in keys)
    def citations():
        rows=result.get('citations')
        return isinstance(rows,list) and all(isinstance(c,dict) and isinstance(c.get('claim'),str) and c['claim'].strip()
            and isinstance(c.get('source_ids'),list) and c['source_ids'] and all(isinstance(s,str) and s for s in c['source_ids']) for c in rows)
    if role=='Brand analyst':return texts('tone','structure','cta_habits') and all(strings(k) for k in ('vocabulary','avoid','evidence'))
    if role=='Strategist':return texts('angle','hook','audience','format','cta','reason') and strings('applied_learning_ids') and strings('source_ids')
    if role in ('Writer','Follow-up'):
        okay=texts('text') and citations()
        if role=='Follow-up':return okay and strings('limitations')
        return okay and (data.get('platform')!='instagram' or strings('slides') and 3<=len(result['slides'])<=10 and all(s.strip() for s in result['slides']))
    if role=='Editor':
        scores=result.get('scores')
        return isinstance(scores,dict) and set(scores)=={'hook','clarity','voice','platform','cta'} and all(
            type(v) in (int,float) and math.isfinite(v) and 0<=v<=10 for v in scores.values()) and strings('edits') and texts('reason')
    if role=='Verifier':return isinstance(result.get('checks'),list) and isinstance(result.get('conflicts'),list) and (
        not result.get('coverage_required') or isinstance(result.get('coverage'),list))
    if role=='Visual director':return texts('prompt','reason')
    if role=='Learning analyst':return texts('rule','reason')
    return False
