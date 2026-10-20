"""Explicit single-photo Instagram delivery. No AI calls, public hosting or automatic retries."""
import base64
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, ImageOps
import httpx
import social
import social_auth
import storage

router = APIRouter()
OUTPUT = Path("data/instagram-media")


def require(id, kind):
    row = next((r for r in storage.listing(kind) if r["id"] == id), None)
    if not row:
        raise ValueError(kind+" not found")
    return row


def signature(post):
    return hashlib.sha256(json.dumps([post.get("text"),post.get("image")],ensure_ascii=False).encode()).hexdigest()


def jpeg(post):
    raw = post.get("image", "")
    if not re.match(r"^data:image/(png|jpeg|webp);base64,",raw) or len(raw)>28000000:
        raise ValueError("Export requires a saved PNG, JPEG or WebP data image; remote images are not fetched")
    payload = base64.b64decode(raw.split(",",1)[1],validate=True)
    with Image.open(io.BytesIO(payload)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.pad(image,(1080,1080),color="white")
        OUTPUT.mkdir(parents=True,exist_ok=True)
        path = OUTPUT/(signature(post)+".jpg")
        image.save(path,"JPEG",quality=95)
    return path


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Use a public HTTPS JPEG URL; localhost and data images cannot be fetched by Instagram")
    host=parsed.hostname.lower()
    if host=='localhost' or '.' not in host or host.endswith(('.local','.localhost','.internal')):
        raise ValueError("Image URL must be publicly accessible")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private image URLs are not supported")
    except ValueError as exc:
        if 'Private' in str(exc): raise
    return url  # This server never fetches this URL. Meta fetches it on explicit staging.


def prepare(post_id, connection_id, image_url):
    post,connection=require(post_id,'post'),require(connection_id,'social_connection')
    if post.get('platform')!='instagram' or post.get('status') not in ('approved','scheduled','ready_to_publish'):
        raise ValueError('Select an approved Instagram post')
    if connection['provider']!='instagram' or connection['brand_id']!=post['brand_id']:
        raise ValueError('Instagram connection must match the post brand')
    if not post.get('text') or len(post['text'])>2200:
        raise ValueError('A caption of 1–2200 characters is required')
    public_url(image_url)
    id='instagram_delivery:'+hashlib.sha256((post_id+connection_id).encode()).hexdigest()
    body=dict(post_id=post_id,connection_id=connection_id,caption=post['text'],image_url=image_url,
              fingerprint=signature(post),status='prepared',created_at=storage.now())
    with storage.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute("SELECT body FROM records WHERE id=? AND kind='instagram_delivery'",(id,)).fetchone()
        if old:
            old=json.loads(old[0])
            if old['fingerprint']!=body['fingerprint'] or old['image_url']!=image_url:
                raise ValueError('An existing delivery already reserves this post/account; inspect it before changing assets')
            return old
        body['id']=id
        db.execute("INSERT INTO records VALUES (?,'instagram_delivery',?)",(id,json.dumps(body)))
    return body


def claim(id, allowed, status):
    with storage.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT body FROM records WHERE id=? AND kind='instagram_delivery'",(id,)).fetchone()
        job=json.loads(row[0]) if row else None
        if not job or job['status'] not in allowed:
            raise ValueError('Delivery is not in the required state; ambiguous submissions are never retried automatically')
        job['status']=status
        db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(job),id))
    return job


def context(job,client):
    if os.getenv('INSTAGRAM_ENABLE_PUBLISHING','0')!='1':
        raise ValueError('Instagram publishing is disabled. Configure the app, publishing permission and INSTAGRAM_ENABLE_PUBLISHING=1 locally')
    connection=require(job['connection_id'],'social_connection')
    post=require(job['post_id'],'post')
    if post.get('status') not in ('approved','scheduled','ready_to_publish') or connection['provider']!='instagram' or connection['brand_id']!=post['brand_id']:
        raise ValueError('Post approval or connection no longer matches this delivery')
    if job.get('account_id') and str(connection.get('account_id',''))!=str(job['account_id']):
        raise ValueError('Connected Instagram account changed after staging; publishing withheld')
    if connection.get('status') in ('disconnected','not_authorized'):
        raise ValueError('Authorize the Instagram account first')
    if signature(post)!=job['fingerprint']:
        raise ValueError('Post changed after delivery preparation; publishing withheld')
    token=social_auth.access_token(connection)
    version=os.getenv('INSTAGRAM_API_VERSION','v24.0')
    if not re.fullmatch(r'v[0-9]+\.0',version):raise ValueError('Invalid Instagram API version')
    base='https://graph.instagram.com/'+version
    headers={'Authorization':'Bearer '+token}
    return connection,post,base,headers


def stage(id,client):
    job=require(id,'instagram_delivery')
    connection,post,base,headers=context(job,client)
    me=client.get(base+'/me',params={'fields':'user_id,username'},headers=headers).raise_for_status().json()
    account=str(me.get('user_id') or me.get('id',''))
    if not account.isdigit() or not me.get('username') or (connection.get('account_id') and connection['account_id']!=account):
        raise ValueError('Instagram identity did not match the selected connection')
    job=claim(id,('prepared',),'creating_container')
    job.update(account_id=account,username=me['username'])
    try:
        result=client.post(base+'/'+account+'/media',data={'image_url':job['image_url'],'caption':job['caption']},headers=headers).raise_for_status().json()
        if not str(result.get('id','')).isdigit():raise ValueError('Provider returned no container ID')
        job.update(container_id=str(result['id']),status='container_created')
    except Exception:
        job['status']='container_creation_unknown'
        storage.save('instagram_delivery',job,id)
        raise
    return storage.save('instagram_delivery',job,id)


def check(id,client):
    job=require(id,'instagram_delivery')
    if job['status'] not in ('container_created','ready'):
        raise ValueError('No unpublished container is available to check')
    connection,post,base,headers=context(job,client)
    from datetime import datetime,timezone,timedelta
    if job.get('checked_at') and datetime.fromisoformat(job['checked_at'])>datetime.now(timezone.utc)-timedelta(seconds=60):
        return job
    if job.get('checks',0)>=5:raise ValueError('Container check limit reached; inspect the provider before proceeding')
    result=client.get(base+'/'+job['container_id'],params={'fields':'status_code'},headers=headers).raise_for_status().json()
    code=result.get('status_code')
    job.update(checked_at=storage.now(),checks=job.get('checks',0)+1,provider_status=code,
               status='ready' if code=='FINISHED' else 'container_created' if code=='IN_PROGRESS' else 'provider_'+str(code).lower())
    return storage.save('instagram_delivery',job,id)


def publish(id,username,confirmed,client):
    job=require(id,'instagram_delivery')
    if job['status']=='published':return job
    if not confirmed or username.lstrip('@')!=job.get('username'):
        raise ValueError('Review the exact caption, public JPEG and account, then confirm its username')
    connection,post,base,headers=context(job,client)
    job=claim(id,('ready',),'publishing')
    try:
        result=client.post(base+'/'+job['account_id']+'/media_publish',data={'creation_id':job['container_id']},headers=headers).raise_for_status().json()
        if not str(result.get('id','')).isdigit():raise ValueError('Provider returned no published media ID')
    except Exception:
        job['status']='publication_unknown'
        storage.save('instagram_delivery',job,id)
        raise
    job.update(status='published',external_id=str(result['id']),published_at=storage.now())
    # Save publication state atomically before analytics bookkeeping can fail.
    with storage.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        post.update(status='published',instagram_media_id=job['external_id'],published_at=job['published_at'])
        db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(job),id))
        db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(post),post['id']))
        db.execute("UPDATE jobs SET status='published' WHERE post_id=?",(post['id'],))
    social.track(connection,post,job['external_id'],job['published_at'],'single_image')
    storage.audit(post['id'],'publisher',{'reason':'Explicitly confirmed Instagram single-photo publication','external_id':job['external_id'],'delivery_id':id})
    return job


class PrepareRequest(BaseModel):
    connection_id:str
    image_url:str=Field(max_length=4096)


class ConfirmRequest(BaseModel):
    username:str=Field(max_length=100)
    confirm_publish:bool=False


@router.get('/posts/{id}/instagram/jpeg')
def export(id:str):
    try:return FileResponse(jpeg(require(id,'post')),media_type='image/jpeg',filename='instagram-post.jpg')
    except (ValueError,OSError) as exc:raise HTTPException(422,str(exc)) from None


@router.post('/posts/{id}/instagram/delivery')
def prepare_route(id:str,req:PrepareRequest):
    try:return prepare(id,req.connection_id,req.image_url)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None


@router.get('/instagram/deliveries/{id}')
def delivery(id:str):
    try:return require(id,'instagram_delivery')
    except ValueError as exc:raise HTTPException(404,str(exc)) from None


def perform(fn,*args):
    try:
        with httpx.Client(timeout=30,follow_redirects=False) as client:return fn(*args,client)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except httpx.HTTPStatusError as exc:raise HTTPException(422,'Instagram rejected the request (HTTP '+str(exc.response.status_code)+'). Check permissions and the saved delivery state.') from None
    except httpx.HTTPError:raise HTTPException(502,'Instagram request outcome may be unknown. Inspect the delivery; do not resubmit blindly.') from None


@router.post('/instagram/deliveries/{id}/stage')
def stage_route(id:str):return perform(stage,id)


@router.post('/instagram/deliveries/{id}/check')
def check_route(id:str):return perform(check,id)


@router.post('/instagram/deliveries/{id}/publish')
def publish_route(id:str,req:ConfirmRequest):return perform(publish,id,req.username,req.confirm_publish)
