'use strict';
function instagramPublishCard(box,p){
 if(state.preview||p.platform!=='instagram'||!['approved','scheduled','ready_to_publish','published'].includes(p.status))return;
 const panel=el('details');panel.append(el('summary','Publish a single image to Instagram'),el('p','This publishes one image and its caption, not the carousel slides. Nothing is posted until you review and confirm. No Mesh calls.'));
 const download=el('a','Download Instagram-ready JPEG');download.href='/posts/'+p.id+'/instagram/jpeg';panel.append(download,el('p','Meta needs a public HTTPS URL for this JPEG. Localhost and data images do not work. CreatorOS does not upload assets or expose your local server automatically.'));
 const form=el('form'),label=el('label','Instagram account connection'),select=el('select');label.append(select);form.append(label);
 const urlLabel=el('label','Public HTTPS URL of the reviewed JPEG'),url=el('input');url.type='url';url.required=true;url.placeholder='https://your-media-host.example/post.jpg';urlLabel.append(url);form.append(urlLabel,el('button','Prepare delivery · no external calls'));
 const status=el('p'),review=el('div'),visual=el('div');panel.append(visual,form,status,review);let loaded=false,connectionsAvailable=false;
 const prepareButton=form.querySelector('button');prepareButton.disabled=true;
 async function visualStatus(){
  const info=await request('/posts/'+p.id+'/visual-review');visual.replaceChildren(el('h3','Review the saved visual'),el('p',info.message));
  prepareButton.disabled=!connectionsAvailable||!['approved','not_required'].includes(info.status);
  if(!['approved','not_required'].includes(info.status)){
   const f=el('form'),label=el('label',' I inspected the saved image and caption for legibility, misleading charts and product claims.'),check=el('input');check.type='checkbox';check.required=true;check.style.width='auto';label.prepend(check);
   f.append(label,el('button','Approve this saved visual · no AI calls'));
   f.onsubmit=e=>{e.preventDefault();busy(f,async()=>{await request('/posts/'+p.id+'/visual-review',{fingerprint:info.fingerprint,approved:true,confirm_review:check.checked});await visualStatus();notice('Visual review saved for this exact image and caption.')})};visual.append(f);
  }
 }
 panel.ontoggle=async()=>{if(!panel.open||loaded)return;loaded=true;try{const data=await request('/connections');const connections=data.connections.filter(c=>c.provider==='instagram'&&c.brand_id===p.brand_id&&c.status!=='disconnected');connectionsAvailable=connections.length>0;for(const c of connections){const o=el('option',(c.account_id||'Instagram account')+' · '+c.status);o.value=c.id;select.append(o)}await visualStatus();if(!connections.length){status.textContent='No Instagram connection for this brand. Open Accounts & analytics to create one, configure your Meta app, and authorize the account.';prepareButton.disabled=true}}catch(e){status.textContent=e.message}};
 const path=(id,action)=>'/instagram/deliveries/'+encodeURIComponent(id)+(action?'/'+action:'');
 function show(job){review.replaceChildren(el('h3','Review delivery'),el('p','State: '+job.status),el('p','Account: '+(job.username?'@'+job.username:'not verified yet')),el('div',job.caption,'stagecopy'));const link=el('a','Open exact image URL for review');link.href=job.image_url;link.target='_blank';link.rel='noopener';review.append(link);details(review,'Saved delivery receipt',job);
  const operate=async(action)=>{try{const updated=await request(path(job.id,action),{});show(updated)}catch(e){status.textContent=e.message;show(await request(path(job.id)))}};
  if(job.status==='prepared')review.append(button('Verify account & create media container',()=>operate('stage')));
  if(['container_created','ready'].includes(job.status))review.append(button('Check Instagram readiness · at most once per minute',()=>operate('check')));
  if(job.status==='ready'){const f=el('form'),l=el('label','Type the verified Instagram username to confirm'),name=el('input'),c=el('input'),cl=el('label',' I reviewed this exact caption, image and account and want to publish now.');name.required=true;l.append(name);c.type='checkbox';c.required=true;c.style.width='auto';cl.prepend(c);f.append(l,cl,el('button','Publish this image to Instagram now'));f.onsubmit=e=>{e.preventDefault();busy(f,async()=>{const result=await request(path(job.id,'publish'),{username:name.value,confirm_publish:c.checked});show(result);if(result.status==='published')notice('Published to Instagram. Media ID: '+result.external_id);await refresh(true)})};review.append(f)}
  if(job.status.includes('unknown')||['creating_container','publishing'].includes(job.status))review.append(el('p','Outcome uncertain. Check Instagram before taking any further action. Automatic retry is blocked to prevent duplicates.'));
 }
 form.onsubmit=e=>{e.preventDefault();busy(form,async()=>{const job=await request('/posts/'+p.id+'/instagram/delivery',{connection_id:select.value,image_url:url.value});show(job);status.textContent='Prepared locally. Account verification and media staging have not run.'})};box.append(panel);
}
