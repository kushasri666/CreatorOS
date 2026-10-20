'use strict';
async function attachmentRequest(path,options){
 const response=await fetch(path,options),body=await response.json().catch(()=>({}));
 if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Attachment request failed ('+response.status+').');
 return body;
}

function renderResearchDocs(){
 const box=$('researchdocs');if(!box)return;
 const docs=(state.research_document||[]).filter(d=>d.brand_id===$('brand').value);
 const signature=JSON.stringify([$('brand').value,docs]);if(box.dataset.signature===signature)return;
 box.dataset.signature=signature;box.replaceChildren();
 if(!docs.length){box.append(el('small','No brand attachments saved yet.'));return}
 box.append(el('small','Up to three attachments per brand. Documents and supplied media transcripts/notes are included in content evidence.'));
 for(const d of docs){
  const card=el('div',undefined,'comparison');card.append(el('strong','✓ '+d.filename));
  if(!d.media_type){card.append(el('small','Text document · ready for content evidence'));box.append(card);continue}
  card.append(el('p',d.media_type+' · '+(d.size_bytes/1024/1024).toFixed(2)+' MiB · '+(d.evidence_status==='supplied_transcript'?'Supplied transcript/notes available':'Transcript/notes needed for content evidence')));
  const base='/brands/'+encodeURIComponent(d.brand_id)+'/research-media/'+encodeURIComponent(d.id);
  const player=el(d.media_type==='video'?'video':'audio');player.src=base+'/file';player.controls=true;player.preload='none';player.style.width='100%';if(d.media_type==='video')player.playsInline=true;card.append(player);
  const link=el('a','Download original file');link.href=base+'/file';link.download=d.filename;card.append(link);
  const editor=el('div');editor.hidden=true;
  card.append(button('Add / edit transcript or notes',()=>busy(card,async()=>{
   if(editor.dataset.loaded){editor.hidden=!editor.hidden;return}
   const saved=await attachmentRequest(base+'/transcript');const label=el('label','User-supplied transcript / notes (up to 12,000 characters)'),input=el('textarea');input.maxLength=12000;input.rows=6;input.value=saved.text;label.append(input);
   const status=el('p');status.setAttribute('role','status');editor.append(label,button('Save transcript / notes · no AI calls',()=>busy(editor,async()=>{
    status.textContent='Saving…';try{const result=await attachmentRequest(base+'/transcript',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:input.value})});await refresh(true);notice(result.note)}catch(e){status.textContent='Not saved: '+e.message;throw e}
   })),status);editor.dataset.loaded='1';editor.hidden=false;input.focus();
  })),editor);box.append(card)
 }
}

async function uploadBrandAttachment(){
 const file=$('researchfile').files[0],status=$('researchstatus'),selected=brand();
 try{
  if(state.preview)throw Error('Return to your workspace before attaching brand files.');
  if(!selected)throw Error('Select a brand first.');if(!file)throw Error('Choose a text, audio or video file first.');
  const textFile=/\.(txt|md)$/i.test(file.name);let result;
  status.textContent='Saving '+file.name+' to '+selected.name+'… No AI calls.';
  if(textFile){
   if(file.size>48000)throw Error('Text documents are limited to 12,000 characters.');
   const content=await file.text();if(content.length>12000)throw Error('Document exceeds the 12,000 character limit.');
   result=await request('/brands/'+encodeURIComponent(selected.id)+'/research-documents',{filename:file.name,text:content});
  }else{
   if(!/\.(mp4|mov|webm|mp3|m4a|wav|ogg|flac|aac)$/i.test(file.name))throw Error('Choose MP4, MOV, WEBM, MP3, M4A, WAV, OGG, FLAC or AAC media.');
   if(file.size>50*1024*1024)throw Error('Media files are limited to 50 MiB.');
   result=await attachmentRequest('/brands/'+encodeURIComponent(selected.id)+'/research-media?filename='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
   const notes=$('researchtranscript').value.trim();
   if(notes){
    try{const updated=await attachmentRequest('/brands/'+encodeURIComponent(selected.id)+'/research-media/'+encodeURIComponent(result.id)+'/transcript',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:notes})});result.note=updated.note}
    catch(e){await refresh(true);status.textContent='File saved to '+selected.name+', but transcript/notes were not saved: '+e.message+'. Use Add / edit below to retry.';notice(status.textContent);return}
   }
  }
  await refresh(true);status.textContent=(result.created?'Saved ':'Already saved ')+result.filename+' to '+selected.name+'. '+result.note;
  $('researchfile').value='';$('researchtranscript').value='';notice(status.textContent);
 }catch(e){status.textContent='Not saved: '+e.message;throw e}
}
