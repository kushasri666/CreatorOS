"""Explicitly authorized saved-brand validation, carrying ALL prior spending forward."""
import argparse
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validation_budget import BASE,Budget,save

DIRECTORY=ROOT/'data/saved-brand-validation-075'
LEDGER=DIRECTORY/'ledger.json'
PARENT=ROOT/'data/live-validation-075/ledger.json'
REPORT=DIRECTORY/'report.json'
CASES=[dict(name='LearnAIwithSachit',platform='linkedin',
    topic='Introduce LearnAIwithSachit to professionals who want to learn AI tools by building, deploying and fixing bugs. Explain the hands-on approach and tracking resource expenditure in one page. Invite the reader to start learning by building. Use only the saved brand samples; do not invent courses, pricing, a community, outcomes, statistics or guarantees.',
    concepts=[['AI'],['build','building'],['deploy','deploying'],['resource','expenditure']],cta=['learn','build']),
    dict(name='Content Tracker AI',platform='instagram',
    topic='Create a concise Instagram carousel introducing Content Tracker AI to content creators. Explain the feedback loop: review historical audience engagement, use it to inform the next content idea, and generate the next post. Invite creators to review their past content. Present higher performance as a goal, never a guaranteed or measured result. Use only saved brand samples; do not invent automatic platform integrations, real-time analytics, publishing access, pricing or statistics.',
    concepts=[['AI'],['engagement'],['content'],['feedback','historical']],cta=['review','content'])]


def outcome(result):
    """A function returning normally is not proof that its operation succeeded."""
    if not isinstance(result,dict) or not result:return 'failed'
    if result.get('approved') is False:return 'needs_review'
    for key in ('status','video_status'):
        if key in result and result[key] not in ('approved','scheduled','ready_to_publish','feedback_recorded',
                'ready','verified','completed','published'):
            return 'needs_review' if result[key]=='needs_review' else 'failed'
    if 'scheduling_status' in result and result['scheduling_status'] not in ('ready_to_publish','feedback_recorded'):
        return 'failed'
    if result.get('video_status')=='ready' and (type(result.get('bytes')) is not int or result['bytes']<=0):return 'failed'
    return 'passed'


def main(execute=False,repair=False,finish=False):
    if not execute:raise SystemExit('Requires --execute; shared cumulative cap remains $0.70, below $0.75')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.update(CREATOROS_MODE='live',CREATOROS_DB=str(DIRECTORY/'studio.db'),MESH_ENABLE_PAID='1',
        MESH_CACHE_ENABLED='1',MESH_FORMAT_RETRIES='0',MESH_MAX_CALLS='10',MESH_MAX_OUTPUT_TOKENS='1600',
        MESH_WRITER_MODEL='openai/gpt-4.1',MESH_EDITOR_MODEL='openai/gpt-4.1',MESH_VERIFIER_MODEL='openai/gpt-4.1',
        MESH_STRATEGIST_MODEL='google/gemini-2.5-flash-lite',MESH_VISUAL_MODEL='google/gemini-2.5-flash-lite',
        MESH_LEARNER_MODEL='openai/gpt-4.1-mini',MESH_IMAGE_MODEL='alibaba/z-image-turbo',
        MESH_ENABLE_MEDIA_PAID='0',LINKEDIN_AUTO_SYNC='0',SOCIAL_ENABLE_PAID_X='0',INSTAGRAM_ENABLE_PUBLISHING='0')
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    if LEDGER.exists():
        ledger=json.loads(LEDGER.read_text(encoding='utf-8'))
        if ledger.get('saved_brands_finalized') and not (repair or finish):
            print('Saved brands already finalized; no inference.');return
    else:
        ledger=json.loads(PARENT.read_text(encoding='utf-8'))
        if not ledger.get('finalized'):raise ValueError('Prior validation must be reconciled first')
        ledger['parent_ledger_sha256']=hashlib.sha256(PARENT.read_bytes()).hexdigest()
        ledger['prior_cost_usd']=ledger['reconciled_request_cost_usd']
        ledger['prior_request_count']=len(ledger['calls'])
        ledger['saved_brand_steps']={}
        ledger['continuation_authorization']='User requested both saved brands, combined with prior spend below $0.75'
        ledger['continuation_started_at']=datetime.now(timezone.utc).isoformat()
        save(LEDGER,ledger)
    import httpx
    from openai import OpenAI as RealOpenAI
    import main as app,storage,video
    from content_quality import score
    with httpx.Client(headers={'Authorization':'Bearer '+os.environ['MESH_API_KEY']},timeout=45,follow_redirects=False) as metadata:
        # Fresh official pricing is read without inference. Old prices are retained
        # for old completed receipts; permitted current models must still exist.
        catalog=metadata.get(BASE+'/models').raise_for_status().json()
        rows=catalog if isinstance(catalog,list) else catalog['data']
        current={r['id']:r['pricing'] for r in rows}
        for model in ('openai/gpt-4.1','openai/gpt-4.1-mini','google/gemini-2.5-flash-lite','alibaba/z-image-turbo'):
            if current.get(model)!=ledger['prices'][model]:raise ValueError('Pricing changed; review bounds before spending')
        # Explicitly bounded extension: original 78 calls and one image INCLUDED.
        # Dollar cap, original starting balance and unresolved reservations persist.
        guard=Budget(LEDGER,ledger,metadata,call_limit=130,image_limit=3)
        with httpx.Client(event_hooks={'request':[guard.before],'response':[guard.after]},timeout=120,follow_redirects=False) as inference:
            def sdk(**kwargs):return RealOpenAI(**kwargs,http_client=inference)
            def step(key,fn):
                if finish:key='finish:'+key
                elif repair:key='repair:'+key
                if key in ledger['saved_brand_steps']:return ledger['saved_brand_steps'][key].get('result')
                ledger['saved_brand_steps'][key]=dict(status='in_progress');save(LEDGER,ledger)
                print('STEP',key,flush=True)
                try:
                    result=fn();entry=dict(status=outcome(result),result=result)
                except Exception as exc:
                    entry=dict(status='failed',error_type=type(exc).__name__)
                ledger['saved_brand_steps'][key]=entry;save(LEDGER,ledger)
                print('RESULT',key,entry['status'],flush=True)
                return entry.get('result')
            with patch.object(app.workflow if hasattr(app,'workflow') else sys.modules['workflow'],'OpenAI',side_effect=sdk):
                pending=[]
                for case in CASES:
                    name=case['name']
                    # Read customer records without copying accounts, tokens, metrics,
                    # generated claims or cache entries into the isolated experiment.
                    with sqlite3.connect('file:'+(ROOT/'data/creatoros-live.db').as_posix()+'?mode=ro',uri=True) as source:
                        brands=[json.loads(r[0]) for r in source.execute("SELECT body FROM records WHERE kind='brand'")]
                        brand=next(b for b in brands if b['name'].casefold()==name.casefold())
                        docs=[json.loads(r[0]) for r in source.execute("SELECT body FROM records WHERE kind='research_document'")]
                    if not storage.get(brand['id']):storage.save('brand',brand,brand['id'])
                    selected=[d for d in docs if d.get('brand_id')==brand['id']]
                    for doc in selected:
                        if not storage.get(doc['id']):storage.save('research_document',doc,doc['id'])
                    facts='\n'.join(brand['samples'])
                    request=app.BriefRequest(brand_id=brand['id'],platform=case['platform'],topic=case['topic'],
                        product_name=name,product_details=facts,use_research=False,use_learnings=False,
                        document_ids=[d['id'] for d in selected[:3]])
                    if repair:
                        guidance=('Keep the caption to 60–90 words in 3–4 short paragraphs. ' if case['platform']=='linkedin' else
                            'Keep the caption to 35–55 words and exactly four slides of at most 12 words each. ')
                        request=request.model_copy(update=dict(topic=case['topic']+' '+guidance+
                            'Keep the hook on its own first line. Use only 2–3 distinct product facts. Avoid abstract benefits, superiority, professional-grade outcomes, or claims of guaranteed improvement. '
                            'Each citation claim MUST be copied from your own caption or slide, never copied from a source unless that exact passage also appears in your final content. '
                            'Reuse the same factual wording across caption and slides. Preserve these length limits during revision.'))
                    def generate(learned=False,request=request,name=name):
                        req=request.model_copy(update=dict(use_learnings=learned))
                        post=app.create_post(req)
                        # Only the first run per brand requests an image. Learned
                        # comparison exercises writing/verification without another image.
                        real=app.run_pipeline
                        def pipeline(*args,**kwargs):
                            kwargs['generate_image']=not learned
                            return real(*args,**kwargs)
                        try:
                            with patch.object(app,'run_pipeline',side_effect=pipeline):app.execute(req,post['id'])
                        finally:save(DIRECTORY/(name+('-learned' if learned else '')+'.json'),storage.get(post['id']))
                        return storage.get(post['id'])
                    if finish:
                        prior=(ledger['saved_brand_steps'].get('repair:'+name+':pipeline') or {}).get('result') or {}
                        core=storage.get(prior['id']) if prior.get('id') else None
                        if core:request=request.model_copy(update=dict(topic=core['brief']))
                    else:core=step(name+':pipeline',generate)
                    if not core or not core.get('approved'):continue
                    if finish and not core.get('image'):
                        def visual():
                            import workflow
                            mesh=workflow.Mesh(max_calls=2)
                            prompt=mesh.ask('Visual director: return prompt and reason for an editorial image matching this product and its saved approved content. No rendered text, no unsupported outcome promises.',
                                dict(platform=case['platform'],voice=core['voice'],text=core['text'],product=dict(name=name)))
                            image=mesh.image(prompt['prompt'])
                            saved=storage.save('post',dict(core,image=image,visual=prompt),core['id'])
                            return dict(post_id=saved['id'],image_generated=True)
                        step(name+':missing_visual',visual)
                        core=storage.get(core['id'])
                    def media():
                        due=datetime.now(timezone.utc)+timedelta(seconds=1)
                        if storage.get(core['id'])['status'] in ('approved','scheduled'):
                            app.schedule(core['id'],app.ScheduleRequest(scheduled_for=due))
                        item,started=video.start(storage.get(core['id']),core.get('slides') or None,2,True)
                        if started:video.render(item,storage.get(core['id']))
                        storage.tick()
                        return dict(video_status=storage.get(item['id'])['status'],video_id=item['id'],
                            file=str(video.output_path(item['id'])),bytes=video.output_path(item['id']).stat().st_size,
                            scheduling_status=storage.get(core['id'])['status'],
                            report_bytes=len(app.content_report(core['id']).body),audit_events=len(app.audit_trail(core['id']).get('timeline',[])))
                    assets=step(name+':local_media_queue_and_report',media)
                    if storage.get(core['id'])['status']=='ready_to_publish':
                        step(name+':simulated_feedback',lambda:app.metrics(core['id'],app.MetricsRequest(
                            event_id='saved-brand-validation-1',source='simulated',impressions=1000,likes=40,comments=8,saves=15)))
                        earlier=(ledger['saved_brand_steps'].get('repair:'+name+':with_learning') or {}).get('result') or {}
                        if not (finish and earlier.get('text')):
                            pending.append((name,lambda learned,req=request,g=generate:g(learned,request=req)))
                # Validate both primary posts before spending on either comparison.
                for name,generate in pending:
                    step(name+':with_learning',lambda:generate(True))
        paid=Decimal(0);unpriced=[]
        for row in ledger['calls']:
            if not row.get('request_id'):unpriced.append(row['index']);continue
            response=metadata.get(BASE+'/usage/requests/'+row['request_id'])
            if not response.is_success:unpriced.append(row['index']);continue
            event=response.json().get('event') or {}
            if event.get('cost_usd') is None:unpriced.append(row['index']);continue
            row['billed_usd']=str(event['cost_usd']);paid+=Decimal(str(event['cost_usd']))
        delta=Decimal(ledger['starting_balance_usd'])-Decimal(metadata.get(BASE+'/balance').raise_for_status().json()['balance_usd'])
        cases=[]
        for case in CASES:
            name=case['name'];prefix='repair:' if repair or finish else ''
            core=(ledger['saved_brand_steps'].get(prefix+name+':pipeline') or {}).get('result') or {}
            if core.get('id'):core=storage.get(core['id'])
            learned=((ledger['saved_brand_steps'].get(('finish:' if finish else prefix)+name+':with_learning') or {}).get('result') or
                (ledger['saved_brand_steps'].get(prefix+name+':with_learning') or {}).get('result') or {})
            requirements=dict(concepts=case['concepts'],cta_terms=case['cta'],voice_terms=core.get('voice',{}).get('vocabulary',[]))
            saved_brand=storage.get(core.get('brand_id','')) or next((b for b in storage.listing('brand') if b['name']==name),{})
            item=dict(brand=name,platform=case['platform'],initial_status=core.get('status','not_completed'),
                approved=core.get('approved',False),verification_passed=core.get('verification',{}).get('passed',False),
                image_generated=bool(core.get('image')),profile_reused=bool(saved_brand) and core.get('voice')==saved_brand.get('profile'),sample_count=len(saved_brand.get('samples',[])),
                learned_post_approved=learned.get('approved',False),learned_post_status=learned.get('status','not_run'),
                applied_learning_ids=learned.get('used_learning_ids',[]))
            if core.get('drafts'):
                item.update(before=score(dict(text=core['drafts'][0],slides=core['slide_versions'][0]),case['platform'],requirements),
                    after=score(dict(text=core['text'],slides=core['slides']),case['platform'],requirements),
                    genuine_revision=core['drafts'][0]!=core['text'] or core['slide_versions'][0]!=core['slides'])
            if learned.get('text'):
                item.update(learned_output_changed=core['text']!=learned['text'] or core['slides']!=learned['slides'])
            cases.append(item)
        summary=dict(prior_cost_usd=ledger['prior_cost_usd'],additional_billed_cost_usd=str(paid-Decimal(ledger['prior_cost_usd'])),
            cumulative_billed_cost_usd=str(paid),cumulative_balance_delta_usd=str(delta),budget_usd='.75',internal_cap_usd='.70',
            within_budget=max(paid,delta)<Decimal('.75'),requests=len(ledger['calls']),
            additional_requests=len(ledger['calls'])-ledger['prior_request_count'],unpriced_receipt_indexes=unpriced,cases=cases,
            limits=['Saved brand-owner samples are assertions, not independent proof of product efficacy.',
                'Existing learned profiles reused; no paid voice relearning.',
                'Isolated database; no public social posting or live account metrics.',
                'Simulated feedback tests learning plumbing, not engagement uplift.',
                'Editorial proxy is not an independent human or semantic quality measure.'])
        ledger.update(saved_brands_finalized=True,saved_brands_summary=summary);save(LEDGER,ledger)
        def sanitize(v):
            if isinstance(v,dict):return {k:sanitize(x) for k,x in v.items() if k not in ('image','encrypted','file')}
            if isinstance(v,list):return [sanitize(x) for x in v]
            return v
        # This report contains only safe current-brand records and new requests;
        # the original full validation report remains intact, linked by hash.
        save(REPORT,sanitize(dict(summary=summary,parent_ledger_sha256=ledger['parent_ledger_sha256'],
            steps=ledger['saved_brand_steps'],calls=ledger['calls'][ledger['prior_request_count']:])))
        save(ROOT/'docs/validation-saved-brands-075-summary.json',summary)
        print('FINAL',json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--repair',action='store_true');parser.add_argument('--finish',action='store_true')
    args=parser.parse_args();main(args.execute,args.repair,args.finish)
