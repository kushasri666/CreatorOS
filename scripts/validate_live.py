"""One authorized resumable live validation. All inference uses the production Mesh SDK."""
import argparse
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validation_budget import BASE,CAP,Budget,save

DIRECTORY=ROOT/'data/live-validation-075'
LEDGER=DIRECTORY/'ledger.json'
REPORT=ROOT/'docs/validation-live-075.json'
TOPIC='Teach three habits for consistent home coffee with Brew Mini: choose a grind setting, grind before brewing, and clean with its brush. Address home brewers; invite saving the guide. No taste or performance guarantees.'
FACTS='Brew Mini is a manual coffee grinder. Brew Mini has 12 grind settings. Brew Mini includes a cleaning brush. Its care guide says: select a grind setting, grind beans before brewing, and use the supplied brush for cleaning.'


def run(execute=False,repair=False,quality=False,final=False,receipts=False,resume=False,finish=False):
    if not execute:raise SystemExit('Requires --execute and a human-authorized shared budget. No default paid calls.')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    import httpx
    from openai import OpenAI as RealOpenAI
    os.environ.update(CREATOROS_MODE='live',CREATOROS_DB=str(DIRECTORY/'studio.db'),MESH_ENABLE_PAID='1',
        MESH_CACHE_ENABLED='1',MESH_FORMAT_RETRIES='0',MESH_MAX_CALLS='10',MESH_MAX_OUTPUT_TOKENS='1600',
        MESH_IMAGE_MODEL='alibaba/z-image-turbo',MESH_ENABLE_MEDIA_PAID='0',LINKEDIN_AUTO_SYNC='0',SOCIAL_ENABLE_PAID_X='0')
    if quality or final or receipts or resume or finish:
        # Explicit diagnostic profile only; never silently changes .env/defaults.
        os.environ.update(MESH_WRITER_MODEL='openai/gpt-4.1',MESH_EDITOR_MODEL='openai/gpt-4.1',MESH_VERIFIER_MODEL='openai/gpt-4.1')
    if finish:os.environ['MESH_LEARNER_MODEL']='openai/gpt-4.1-mini'
    # Process-only configuration: never modifies the user's .env or saved accounts.
    key=os.environ['MESH_API_KEY'];DIRECTORY.mkdir(parents=True,exist_ok=True)
    with httpx.Client(headers={'Authorization':'Bearer '+key},timeout=45,follow_redirects=False) as metadata:
        if LEDGER.exists():
            ledger=json.loads(LEDGER.read_text(encoding='utf-8'))
            if ledger.get('complete') and not (repair or quality or final or receipts or resume or finish):
                print('Validation already completed; no new generation. See',REPORT);return
            if repair or quality or final or receipts or resume or finish:ledger['complete']=False
        else:
            data=metadata.get(BASE+'/models').raise_for_status().json();rows=data if isinstance(data,list) else data['data']
            allowed={'openai/gpt-4.1-mini','google/gemini-2.5-flash-lite','alibaba/z-image-turbo'}
            prices={r['id']:r['pricing'] for r in rows if r['id'] in allowed}
            if set(prices)!=allowed:raise ValueError('Validation models unavailable')
            ledger=dict(authorization='creatoros-e2e-075-2026-10-20',internal_cap_usd=str(CAP),
                user_cap_usd='0.75',starting_balance_usd=metadata.get(BASE+'/balance').raise_for_status().json()['balance_usd'],
                prices=prices,calls=[],steps={},started_at=datetime.now(timezone.utc).isoformat(),complete=False)
            save(LEDGER,ledger)
        if (quality or final or receipts or resume or finish) and 'openai/gpt-4.1' not in ledger['prices']:
            catalog=metadata.get(BASE+'/models').raise_for_status().json()
            rows=catalog if isinstance(catalog,list) else catalog['data']
            ledger['prices']['openai/gpt-4.1']=next(r['pricing'] for r in rows if r['id']=='openai/gpt-4.1')
            save(LEDGER,ledger)
        guard=Budget(LEDGER,ledger,metadata)
        with httpx.Client(event_hooks={'request':[guard.before],'response':[guard.after]},timeout=120,follow_redirects=False) as inference:
            def sdk(**kwargs):return RealOpenAI(**kwargs,http_client=inference)
            import workflow
            with patch.object(workflow,'OpenAI',side_effect=sdk):
                import main,storage,followups,video
                phase='finish_' if finish else 'settled_' if resume else 'receipts_' if receipts else 'final_quality_' if final else 'quality_' if quality else 'repair_' if repair else ''
                from content_quality import score
                def step(name,fn):
                    if name in ledger['steps']:
                        print('Preserving prior step',name,ledger['steps'][name]['status'],flush=True)
                        return ledger['steps'][name].get('result')
                    ledger['steps'][name]=dict(status='in_progress');save(LEDGER,ledger)
                    print('STEP',name,flush=True)
                    try:
                        result=fn();ledger['steps'][name]=dict(status='passed',result=result)
                    except Exception as e:
                        ledger['steps'][name]=dict(status='failed',error_type=type(e).__name__,
                            reason=str(e) if isinstance(e,ValueError) else 'Inspect the isolated run audit')
                    save(LEDGER,ledger)
                    print('STEP RESULT',name,ledger['steps'][name]['status'],flush=True)
                    return ledger['steps'][name].get('result')
                brand=step('learn_brand_voice',lambda:main.brand(main.BrandRequest(name='Brew Mini validation — fictional',
                    samples=['Good coffee starts with one small habit. Keep it fresh and simple. Save a favourite step.',
                             'A fresh coffee ritual needs a little care. Try one change, then enjoy your next brew.',
                             'Less fuss, more curiosity. Share your coffee ritual with a friend and keep learning.'],
                    product_name='Brew Mini',product_details=FACTS)))
                if not brand:raise ValueError('Brand-voice stage failed; no downstream generation attempted')
                doc=step('brand_document',lambda:main.research_document(brand['id'],main.ResearchDocumentRequest(filename='fictional-care-guide.txt',text=FACTS)))
                def generate(platform,learned=False):
                    request=main.BriefRequest(brand_id=brand['id'],topic=TOPIC,platform=platform,use_learnings=learned,
                        use_research=False,document_ids=[doc['id']] if doc else [])
                    post=main.create_post(request)
                    real_pipeline=main.run_pipeline
                    def pipeline(*args,**kwargs):
                        # A single visual validates the image path; repeated
                        # comparisons explicitly skip additional image spend.
                        kwargs['generate_image']=not any(r['endpoint'].endswith('/images/generations') for r in ledger['calls'])
                        return real_pipeline(*args,**kwargs)
                    try:
                        with patch.object(main,'run_pipeline',side_effect=pipeline):main.execute(request,post['id'])
                    finally:
                        current=storage.get(post['id']);save(DIRECTORY/(platform+('-learned' if learned else '')+'.json'),current)
                    return storage.get(post['id'])
                core=step(phase+'instagram_full_pipeline',lambda:ledger['steps']['settled_instagram_full_pipeline']['result'] if finish else generate('instagram'))
                if core:
                    step(phase+'cited_report_and_audit',lambda:dict(html_bytes=len(main.content_report(core['id']).body),
                        audit_events=len(main.audit_trail(core['id']).get('events',[])),
                        verification_status=core.get('verification',{}).get('status'),approved=core.get('approved')))
                    def local_media():
                        if not core.get('approved'):return dict(status='blocked',reason='Editorial/source approval was not reached; no scheduling or media bypass')
                        current=storage.get(core['id'])
                        if isinstance(current.get('image'),str) and current['image'].startswith('https://'):
                            from mesh_assets import materialize
                            current=storage.save('post',dict(current,image=materialize(current['image'])),core['id'])
                        due=None
                        if current['status'] in ('approved','scheduled'):
                            due=datetime.now(timezone.utc)+timedelta(seconds=2)
                            main.schedule(core['id'],main.ScheduleRequest(scheduled_for=due))
                        item,started=video.start(storage.get(core['id']),core.get('slides'),2,True)
                        if started:video.render(item,storage.get(core['id']))
                        while due and datetime.now(timezone.utc)<=due:time.sleep(.2)
                        storage.tick();saved=storage.get(item['id'])
                        return dict(status=saved['status'],renderer=saved.get('renderer'),audio=saved.get('audio'),
                            video_id=item['id'],file=str(video.output_path(item['id'])),
                            scheduling_status=storage.get(core['id'])['status'],bytes=video.output_path(item['id']).stat().st_size if video.output_path(item['id']).exists() else 0)
                    step(phase+'local_video_music_and_queue',local_media)
                    def feedback():
                        if storage.get(core['id'])['status'] not in ('ready_to_publish','feedback_recorded'):return dict(status='blocked',reason='No approved handoff; feedback was not fabricated')
                        return main.metrics(core['id'],main.MetricsRequest(event_id='validation-simulated-1',source='simulated',impressions=1000,likes=50,comments=8,saves=20))
                    feedback_result=step(phase+'simulated_feedback_live_learner',feedback)
                    if feedback_result and feedback_result.get('status')!='blocked':step(phase+'instagram_with_saved_learning',lambda:generate('instagram',True))
                    step(phase+'grounded_followup',lambda:followups.answer(storage.get(core['id']),'How many grind settings does Brew Mini have?','mesh','validation-followup-'+(phase or '001')))
                # These are actual native writer/editor pairs, separately labeled
                # from the two complete graph runs above; no fake orchestration.
                def adaptation(platform):
                    from platform_formats import format_contract
                    from editorial_guidance import contract
                    mesh=workflow.Mesh(max_calls=2)
                    context=dict(brief=TOPIC,platform=platform,voice=brand['profile'],learnings=[],format_contract=format_contract(platform),
                        editorial_contract=contract(platform),product=dict(name='Brew Mini',user_provided_facts=FACTS),
                        sources=[dict(source_id='V1',excerpt=FACTS)],previous_draft=None)
                    draft=mesh.ask(f"Writer: adapt this idea natively for {platform}. {format_contract(platform)['structure']}. Maximum {format_contract(platform)['editorial_character_budget']} characters. Use only supplied facts; return exact claim-to-source citations. Keep the requested three habits and a relevant save CTA.",context)
                    review=mesh.ask('Editor: independently critique this native adaptation. Score hook, clarity, voice, platform, cta 0–10; give concrete edits. Never inflate a score to meet a target.',dict(context,draft=draft['text'],slides=draft.get('slides',[])))
                    return dict(kind='live_agent_contract_pair_not_full_graph',platform=platform,draft=draft,review=review,
                        independent_score=score(draft,platform,dict(concepts=[['coffee'],['grind','grinding'],['brush']],cta_terms=['save','?'],voice_terms=brand['profile'].get('vocabulary',[]),**({'format':'short_script'} if platform=='youtube' else {}))))
                for platform in ('x','linkedin','youtube','telegram','threads'):
                    step(('finish_' if finish else '')+'native_'+platform,lambda p=platform:adaptation(p))
        # Metadata only: billing is recorded even for failed generation requests.
        total=Decimal(0);missing=[]
        for row in ledger['calls']:
            if not row.get('request_id'):missing.append(row['index']);continue
            response=metadata.get(BASE+'/usage/requests/'+row['request_id'])
            if not response.is_success:missing.append(row['index']);continue
            billing=response.json();event=billing.get('event') or {}
            if event.get('cost_usd') is None:missing.append(row['index']);continue
            row['billed_usd']=str(event['cost_usd']);total+=Decimal(str(event['cost_usd']))
        end=Decimal(metadata.get(BASE+'/balance').raise_for_status().json()['balance_usd'])
        ledger.update(complete=True,ending_balance_usd=str(end),balance_delta_usd=str(Decimal(ledger['starting_balance_usd'])-end),
            reconciled_request_cost_usd=str(total),unreconciled_calls=missing,reserved_total_usd=str(sum(Decimal(r['reserved_usd']) for r in ledger['calls'])),
            limitations='Real Mesh responses for a fictional brand. Feedback is explicitly simulated. Social publishing/authorization and paid generative video/audio were not attempted. Local video/music is not AI-generated. Agent contract pairs are not complete platform pipelines. Editor opinions are not independent quality or engagement proof.')
        def outcome(item):
            if item['status']!='passed':return item['status']
            result=item.get('result') or {}
            if result.get('status') in ('blocked','failed','needs_review'):return result['status']
            if result.get('approved') is False:return 'needs_review'
            return 'passed'
        ledger['validation_outcomes']={name:outcome(item) for name,item in ledger['steps'].items()}
        save(LEDGER,ledger)
        public={k:v for k,v in ledger.items() if k not in ('starting_balance_usd','ending_balance_usd','prices')}
        # Keep raw assets and private DB in gitignored data; public report includes
        # real text, decisions and receipts, never credentials or image base64.
        def sanitize(value):
            if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items() if k not in ('image','encrypted','file')}
            if isinstance(value,list):return [sanitize(v) for v in value]
            return value
        save(REPORT,sanitize(public))
        print('VALIDATION COMPLETE',json.dumps({k:ledger[k] for k in ('balance_delta_usd','reconciled_request_cost_usd','reserved_total_usd','unreconciled_calls')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    parser.add_argument('--repair-pass',action='store_true',help='One named repair pass sharing the original ledger; never resets spending')
    parser.add_argument('--quality-pass',action='store_true',help='One explicit stronger-model diagnostic, same shared ledger and ceiling')
    parser.add_argument('--final-pass',action='store_true',help='One named regression-fix pass, same original ledger; no resets')
    parser.add_argument('--receipts-pass',action='store_true',help='One exact-reference contract validation, same original ledger')
    parser.add_argument('--resume-receipts',action='store_true',help='Resume after authoritative cache billing reconciliation, same ledger')
    parser.add_argument('--finish-pass',action='store_true',help='Finish feedback/media/follow-up fixes using the existing approved post; same ledger')
    args=parser.parse_args();run(args.execute,args.repair_pass,args.quality_pass,args.final_pass,args.receipts_pass,args.resume_receipts,args.finish_pass)
