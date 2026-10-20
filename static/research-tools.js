'use strict';
const followupDrafts=new Map(),followupPending=new Set();
const adaptationTargets=new Map(),adaptationPending=new Set();
function adaptationTools(box,p){
 if(['generating','failed'].includes(p.status))return;
 const section=el('section',undefined,'comparison');section.append(el('h3','Adapt this idea to another platform'),el('p','Keep this brief and brand. Create fresh native wording with its own editor, evidence checks and saved trace. One selected platform per run; no automatic publishing.'));
 const target=el('select');target.setAttribute('aria-label','Adaptation target platform');
 for(const platform of ['linkedin','instagram','youtube','telegram','threads','x']){if(platform===p.platform)continue;const option=el('option',platform==='x'?'X':platform);option.value=platform;target.append(option)}
 target.value=adaptationTargets.get(p.id)||target.options[0].value;target.onchange=()=>adaptationTargets.set(p.id,target.value);
 const preview=el('button','View format plan · free'),start=el('button','Create adapted post'),status=el('p');status.setAttribute('role','status');
 const locked=state.mode!=='offline'&&!state.paid_enabled;start.disabled=locked||adaptationPending.has(p.id);
 if(locked)section.append(el('small','Generation is locked. Viewing the format plan uses no Mesh credits.'));
 else section.append(el('small',state.mode==='offline'?'Offline fixture mode: scripted output only.':'Starting uses one normal Mesh generation budget, up to 10 calls including any image.'));
 const plan=el('div');preview.onclick=()=>busy(section,async()=>{const data=await request('/posts/'+encodeURIComponent(p.id)+'/adaptation-plan');plan.replaceChildren();details(plan,'Native format plan',data.platforms[target.value]);status.textContent='Format plan loaded. No AI calls.'});
 start.onclick=()=>{if(adaptationPending.has(p.id))return;if(state.post.some(v=>v.brand_id===p.brand_id&&v.status==='generating')){status.textContent='A run for this brand is already in progress.';return}adaptationPending.add(p.id);start.disabled=true;status.textContent='Starting one adapted post…';busy(section,async()=>{try{const saved=await request('/posts/'+encodeURIComponent(p.id)+'/adapt',{platform:target.value,use_learnings:p.learning_enabled!==false});active=saved.id;cursor=-1;notice('Adaptation started. Follow its saved agent trace.');await refresh(true)}catch(error){status.textContent=error.message;throw error}finally{adaptationPending.delete(p.id);start.disabled=locked}})};
 section.append(target,preview,start,status,plan);box.append(section)
}
function researchTools(box,p){
 if(state.preview){box.append(el('p','Report exports and follow-ups are available for saved workspace posts. This is a fictional preview.'));return}
 adaptationTools(box,p);
 const review=p.evidence_review||p.grounded_report?.evidence_review;
 if(review){const d=el('details');d.open=review.conflicts.length>0;d.append(el('summary','Source quality & disagreements · '+review.conflicts.length+' unresolved'));
  for(const source of review.sources)d.append(el('p','['+source.source_id+'] · '+source.tier+' · '+source.score),el('small',source.reason));
  for(const c of review.conflicts){const card=el('div',undefined,'comparison warning');card.append(el('h3',c.subject+' · unresolved'),el('p',c.reason));for(const e of c.evidence)card.append(el('blockquote',e.quote),el('small','['+e.source_id+']'));card.append(el('p','Review preference: '+c.preferred_source_id+'. This does not settle the disagreement.'));d.append(card)}
  d.append(el('p','Weights describe source provenance, not certainty. A real source quotation can still be irrelevant or inaccurate.'));box.append(d)
 }
 const exportBar=el('div',undefined,'replay');for(const [label,url] of [['Open report page','/posts/'+encodeURIComponent(p.id)+'/report'],['Download shareable HTML','/posts/'+encodeURIComponent(p.id)+'/report?download=true']]){const link=el('a',label);link.href=url;link.target='_blank';link.rel='noopener noreferrer';exportBar.append(link)}box.append(exportBar,el('small','The downloaded page includes saved copy, citations, quotes, provenance and unresolved disagreements. Browser Print → Save as PDF is available. No publishing or AI call.'));
 if(p.graph_definition)details(box,'Executable state-graph definition and trace',{definition:p.graph_definition,trace:p.graph_trace});
 if(p.status==='generating')return;
 const section=el('section',undefined,'comparison');section.append(el('h3','Continue with this research'),el('p','Browse the saved evidence for free, or ask Mesh a follow-up using the same evidence and the last two verified conversation turns. No fresh web/account lookup.'));
 const form=el('form'),mode=el('select');for(const [value,label] of [['evidence','Saved evidence · zero AI calls'],['conflicts','Recorded disagreements · zero AI calls'],['mesh','Ask Mesh · up to 2 paid calls']]){const option=el('option',label);option.value=value;if(value==='mesh')option.disabled=!state.paid_enabled;mode.append(option)}
 const question=el('textarea');question.maxLength=2000;question.rows=3;question.placeholder='What can we safely say about this product?';question.value=followupDrafts.get(p.id)||'';question.oninput=()=>followupDrafts.set(p.id,question.value);
 const status=el('p');status.setAttribute('role','status');const submit=el('button','Continue');submit.disabled=followupPending.has(p.id);
 form.append(mode,question,submit,status);section.append(form);if(!state.paid_enabled)section.append(el('small','Mesh follow-ups are locked while paid calls are disabled. Saved evidence and disagreement views remain available.'));
 const turns=el('div');section.append(turns);box.append(section);
 const show=items=>{turns.replaceChildren();for(const turn of items){const card=el('article',undefined,'planbox');card.append(el('strong',turn.question),el('p',turn.status+' · '+(turn.ai_calls||0)+' AI calls'),el('div',turn.text||'This follow-up is still running.','stagecopy'));if(turn.source_ids)card.append(el('small','Reused sources: '+turn.source_ids.join(', ')));if(turn.omitted_source_ids?.length)card.append(el('small','Sources omitted by the context cap: '+turn.omitted_source_ids.join(', ')));if(turn.grounded_report)details(card,'Cited answer and verifier findings',turn.grounded_report);turns.append(card)}};
 request('/posts/'+encodeURIComponent(p.id)+'/followups').then(items=>{if(turns.isConnected)show(items)}).catch(e=>{if(turns.isConnected)status.textContent=e.message});
 form.onsubmit=e=>{e.preventDefault();if(followupPending.has(p.id))return;const text=question.value.trim()||(mode.value==='conflicts'?'Show recorded source disagreements':'Show the saved evidence');if(mode.value==='mesh'&&question.value.trim().length<3){status.textContent='Enter a follow-up question first.';return}followupPending.add(p.id);submit.disabled=true;status.textContent=mode.value==='mesh'?'Answering through Mesh, then independently verifying. At most two calls.':'Reading saved evidence…';
  busy(form,async()=>{try{const turn=await request('/posts/'+encodeURIComponent(p.id)+'/followups',{question:text,mode:mode.value,request_id:crypto.randomUUID()});followupDrafts.delete(p.id);notice('Follow-up saved: '+turn.status+'. '+(turn.ai_calls||0)+' AI calls.')}catch(error){status.textContent=error.message;throw error}finally{followupPending.delete(p.id);submit.disabled=false;await refresh(true)}})
 }
}
