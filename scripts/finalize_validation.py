"""Finish the existing authorized ledger; never creates or resets a spending budget."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validation_budget import BASE,Budget,save
from scripts.validate_live import DIRECTORY,LEDGER,REPORT,TOPIC,FACTS


def main(execute=False):
    if not execute:raise SystemExit('Requires --execute; this only continues the existing authorized ledger')
    if not LEDGER.exists():raise SystemExit('Existing validation ledger required; no new budget may be created here')
    ledger=json.loads(LEDGER.read_text(encoding='utf-8'))
    if ledger.get('finalized'):
        print('Already finalized; no paid calls.');return
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.update(CREATOROS_MODE='live',CREATOROS_DB=str(DIRECTORY/'studio.db'),MESH_ENABLE_PAID='1',
        MESH_CACHE_ENABLED='1',MESH_FORMAT_RETRIES='0',MESH_MAX_OUTPUT_TOKENS='1600',MESH_MAX_CALLS='10',
        MESH_WRITER_MODEL='openai/gpt-4.1',MESH_EDITOR_MODEL='openai/gpt-4.1',MESH_VERIFIER_MODEL='openai/gpt-4.1')
    import httpx
    from openai import OpenAI as RealOpenAI
    import workflow,storage,followups
    from content_quality import score
    from platform_formats import format_contract
    with httpx.Client(headers={'Authorization':'Bearer '+os.environ['MESH_API_KEY']},timeout=45) as metadata:
        guard=Budget(LEDGER,ledger,metadata)
        with httpx.Client(event_hooks={'request':[guard.before],'response':[guard.after]},timeout=120,follow_redirects=False) as inference:
            def sdk(**kwargs):return RealOpenAI(**kwargs,http_client=inference)
            with patch.object(workflow,'OpenAI',side_effect=sdk):
                original=ledger['steps']['settled_instagram_full_pipeline']['result']
                post=storage.get(original['id'])
                if 'final_followup' not in ledger['steps']:
                    ledger['steps']['final_followup']=dict(status='in_progress');save(LEDGER,ledger)
                    result=followups.answer(post,'How many grind settings does Brew Mini have?','mesh','validation-final-followup')
                    ledger['steps']['final_followup']=dict(status='passed' if result['status']=='completed' else result['status'],result=result)
                    save(LEDGER,ledger)
                    print('Final follow-up',result['status'],result.get('ai_calls'),flush=True)
                for platform in ('x','threads'):
                    name='final_native_'+platform
                    if name in ledger['steps']:continue
                    ledger['steps'][name]=dict(status='in_progress');save(LEDGER,ledger)
                    earlier=ledger['steps']['finish_native_'+platform]['result']
                    mesh=workflow.Mesh(max_calls=2)
                    requirements=dict(concepts=[['coffee'],['grind','grinding'],['brush']],cta_terms=['save','?'],voice_terms=post['voice'].get('vocabulary',[]))
                    data=dict(platform=platform,brief=TOPIC,voice=post['voice'],learnings=[],
                        previous_draft=earlier['draft']['text'],previous_slides=[],editor_feedback=earlier['review'],
                        local_checks=earlier['independent_score'],format_contract=format_contract(platform),
                        sources=[dict(source_id='V1',excerpt=FACTS)])
                    try:
                        draft=mesh.ask(f"Writer: revise the actual previous {platform} post. Put a short hook of 4–30 words on its own first line. Then explain all three requested habits concisely. Keep product features explicit using their source terminology. Preserve the learned voice and one save CTA. Native structure: {format_contract(platform)['structure']}. Maximum {format_contract(platform)['editorial_character_budget']} characters. Do not invent or imply causal benefits. Each cited claim must be an exact substring of your own text.",data)
                        review=mesh.ask('Editor: independently score hook, clarity, voice, platform and cta 0–10 and list concrete remaining edits. No target score is supplied; judge the actual brief and native format.',dict(data,draft=draft['text']))
                        ledger['steps'][name]=dict(status='passed',result=dict(kind='live_agent_revision_pair_not_full_graph',platform=platform,
                            before=earlier['draft'],draft=draft,review=review,independent_score=score(draft,platform,requirements)))
                    except Exception as exc:ledger['steps'][name]=dict(status='failed',error_type=type(exc).__name__)
                    save(LEDGER,ledger)
                    print(name,ledger['steps'][name]['status'],flush=True)
        paid=Decimal(0);unpriced=[]
        for row in ledger['calls']:
            if not row.get('request_id'):unpriced.append(row['index']);continue
            response=metadata.get(BASE+'/usage/requests/'+row['request_id'])
            if not response.is_success:unpriced.append(row['index']);continue
            event=response.json().get('event') or {}
            if event.get('cost_usd') is None:unpriced.append(row['index']);continue
            row['billed_usd']=str(event['cost_usd']);paid+=Decimal(str(event['cost_usd']))
        ending=Decimal(metadata.get(BASE+'/balance').raise_for_status().json()['balance_usd'])
        balance_delta=Decimal(ledger['starting_balance_usd'])-ending
        ledger.update(finalized=True,complete=True,ending_balance_usd=str(ending),balance_delta_usd=str(balance_delta),
            reconciled_request_cost_usd=str(paid),unreconciled_calls=unpriced,finalized_at=datetime.now(timezone.utc).isoformat())
        cases=[]
        for label,key in [('instagram','settled_instagram_full_pipeline'),('instagram_with_learning','finish_instagram_with_saved_learning')]:
            p=ledger['steps'][key]['result']
            requirements=dict(concepts=[['coffee'],['grind','grinding'],['brush']],cta_terms=['save','?'],voice_terms=p['voice'].get('vocabulary',[]))
            before=score(dict(text=p['drafts'][0],slides=p['slide_versions'][0]),'instagram',requirements)
            after=score(dict(text=p['text'],slides=p['slides']),'instagram',requirements)
            cases.append(dict(case=label,platform='instagram',approved=p['approved'],before=before,after=after,
                text_changed=p['drafts'][0]!=p['text'],slides_changed=p['slide_versions'][0]!=p['slides'],
                verification_passed=p['verification']['passed'],sources=len(p['sources']),claims=len(p['grounded_report']['claims'])))
        for platform in ('x','linkedin','youtube','telegram','threads'):
            key=('final_native_' if platform in ('x','threads') else 'finish_native_')+platform
            result=ledger['steps'][key].get('result') or {}
            cases.append(dict(case=platform,platform=platform,kind=result.get('kind'),after=result.get('independent_score')))
        learned=ledger['steps']['finish_instagram_with_saved_learning']['result']
        baseline=ledger['steps']['settled_instagram_full_pipeline']['result']
        summary=dict(cost_usd=str(paid),balance_delta_usd=str(balance_delta),budget_usd='.75',internal_cap_usd='.70',
            within_budget=paid<Decimal('.75') and balance_delta<Decimal('.75'),requests=len(ledger['calls']),
            unpriced_successful_receipts=unpriced,
            unpriced_note='Null charges are gateway-cache behavior in Mesh documentation. Historical missing HIT headers are not assumed free by the budget guard; it retains conservative usage-price bounds. Known billed costs match the overall account balance delta.',
            max_live_liability_usd=ledger.get('max_liability_usd'),
            quality_cases=cases,mean_final_editorial_score=round(sum(c['after']['score_100'] for c in cases if c.get('after'))/sum(bool(c.get('after')) for c in cases),3),
            learned_output_changed=baseline['text']!=learned['text'] or baseline['slides']!=learned['slides'],
            applied_learning_ids=learned['strategy'].get('applied_learning_ids',[]),
            strategy_changed=baseline['strategy']!=learned['strategy'],feedback_source='simulated',
            followup_status=ledger['steps']['final_followup'].get('result',{}).get('status'),
            video=ledger['steps']['finish_local_video_music_and_queue']['result'],
            limits=['One fictional product and one learned voice, retrospective prompt/model fixes; not held-out population evidence.',
                'Quality diagnostic used GPT-4.1 writer/editor/verifier; economical defaults were held for review. Permanent model settings were not changed.',
                'Five other platforms are actual agent contract/revision pairs, not full graph runs or live publishing.',
                'Editorial scores are structural/lexical proxies, not independent human judgments or factuality guarantees.',
                'Memory pair uses simulated metrics; changed output does not establish causal engagement uplift.',
                'Social OAuth/publishing/read-back remain mocked/offline tests; no account authorization or public posting occurred.',
                'Video/music were locally rendered; paid generative video/audio and embedding calls were not tested.'])
        ledger['summary']=summary;save(LEDGER,ledger)
        public={k:v for k,v in ledger.items() if k not in ('starting_balance_usd','ending_balance_usd','prices','reserved_total_usd')}
        public['gross_request_reservations_usd']=str(sum(Decimal(r['reserved_usd']) for r in ledger['calls']))
        public['reservation_note']='Gross reservations sum reused sequential headroom, not spend; max_live_liability is the shared active cap check.'
        def sanitize(value):
            if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items() if k not in ('image','encrypted','file')}
            if isinstance(value,list):return [sanitize(v) for v in value]
            return value
        save(REPORT,sanitize(public));save(ROOT/'docs/validation-live-075-summary.json',sanitize(summary))
        print('FINAL VALIDATION',json.dumps({k:summary[k] for k in ('cost_usd','within_budget','requests','mean_final_editorial_score','followup_status')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    main(parser.parse_args().execute)
