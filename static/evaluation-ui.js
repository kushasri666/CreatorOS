'use strict';
async function renderEvaluation(box){
 const token=Symbol();box.evaluationRequest=token;box.append(el('p','Loading recorded self-evaluation…'));
 try{
  const result=await request('/evaluation/grounding');if(tabName!=='evaluation'||box.evaluationRequest!==token)return;
  box.replaceChildren();box.append(el('h2','Grounding & completeness evaluation'),el('span','Authored stress fixtures · '+result.case_count+' cases · '+result.question_count+' questions','tagpill'));
  box.append(el('p','These recorded numbers measure the production evidence-receipt filter on authored synthetic reports. They are not live Mesh accuracy or engagement results.'));
  if(!result.artifact_matches_current_code)box.append(el('p','Recorded results do not match current code/data fingerprints. Regenerate locally with python scripts/evaluate_grounding.py.'));
  const labels={grounded_claim_fraction:'Grounded claims · gold support + valid citations',citation_integrity:'Citation integrity',annotation_coverage:'Gold annotation coverage',required_fact_completeness:'Required fact completeness',question_completeness:'Question completeness',abstention_accuracy:'Correct abstention on evidence gaps'};
  const wrap=el('div',undefined,'tablewrap'),table=el('table'),head=el('tr');for(const label of ['Measure','Submitted fixtures','After receipt filtering'])head.append(el('th',label));table.append(head);
  const metric=m=>m.value===null?'N/A · no denominator':m.numerator+'/'+m.denominator+' · '+(m.value*100).toFixed(1)+'%';
  for(const [key,label] of Object.entries(labels)){const row=el('tr');row.append(el('td',label));for(const stage of ['before','after'])row.append(el('td',metric(result[stage].metrics[key])));table.append(row)}wrap.append(table);box.append(wrap);
  const warning=el('div',undefined,'comparison warning');warning.append(el('h3',result.after.unsupported_claims+' unsupported fixture claims remain after receipt filtering'),el('p','These adversarial fixtures deliberately include incorrect verifier judgments. A real quotation can still be irrelevant or contradicted. Semantic support requires the verifier, and live verifier accuracy has not been evaluated here.'));box.append(warning);
  box.append(el('p','No empty-output reward: claim rates are N/A without claims; answerable questions still score zero completeness. Missing cases fail validation. Unseen paraphrases require annotation.'));
  for(const [label,path] of [['Recorded results (JSON)','/evaluation/grounding'],['Gold-labeled questions and sources (JSON)','/evaluation/grounding/questions'],['Authored response fixtures (JSON)','/evaluation/grounding/fixtures']]){const p=el('p'),link=el('a',label);link.href=path;link.target='_blank';link.rel='noopener noreferrer';p.append(link);box.append(p)}
  box.append(el('h3','Per-case results'));for(const c of result.cases){const d=el('details');d.append(el('summary',c.id+' · '+c.platform),el('p',c.brief),el('p','Grounded claims: '+metric(c.before.metrics.grounded_claim_fraction)+' → '+metric(c.after.metrics.grounded_claim_fraction)),el('p','Required facts: '+metric(c.after.metrics.required_fact_completeness)));details(d,'Claim assessments and missing facts',{claims:c.after.claims,questions:c.after.questions,withheld:c.withheld_claims});box.append(d)}
  details(box,'Reproducibility fingerprints',result.fingerprints);box.append(el('p','Evaluation AI calls: '+result.ai_calls+' · spend: $'+result.validation_spend_usd));
  for(const note of result.limitations)box.append(el('p',note));
 }catch(error){if(tabName==='evaluation')box.replaceChildren(el('p',error.message))}
}
