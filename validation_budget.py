"""Shared persistent validation reservations at the real SDK HTTP boundary."""
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

CAP = Decimal("0.745")  # Latest explicit authorization permits the full $.75; retain a $.005 margin.
BASE = "https://api.meshapi.ai/v1"


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temp.replace(path)


def bound(body, path, prices):
    model=body.get('model');price=prices.get(model)
    if not price:raise ValueError('Validation model has no approved pricing')
    size=len(json.dumps(body,ensure_ascii=False).encode('utf-8'))+1024
    if path=='/v1/chat/completions':
        allowed={'model','messages','max_tokens','response_format','n','temperature','top_p','stop','seed'}
        if set(body)-allowed or type(body.get('n',1)) is not int or body.get('n',1)!=1:
            raise ValueError('Only one explicitly priced text completion is permitted')
        messages=body.get('messages')
        if not isinstance(messages,list) or not messages or any(not isinstance(m,dict) or
            set(m)-{'role','content','name'} or m.get('role') not in ('system','developer','user','assistant') or
            not isinstance(m.get('content'),str) for m in messages):
            raise ValueError('Only text messages are covered by this validation pricing')
        if body.get('response_format',{'type':'text'}) not in ({'type':'text'},{'type':'json_object'}):
            raise ValueError('Unapproved response format is outside this validation pricing')
        if price.get('pricing_unit')!='per_1m_tokens' or body.get('stream') or body.get('tools'):
            raise ValueError('Unpriced streaming or tool calls are not permitted')
        maximum=body.get('max_tokens')
        if type(maximum) is not int or not 1<=maximum<=1600:raise ValueError('Missing bounded output cap')
        rates=[Decimal(price[k]) for k in ('prompt_usd_per_1m','completion_usd_per_1m')]
        if any(not r.is_finite() or r<0 for r in rates):raise ValueError('Invalid validation model pricing')
        cost=(rates[0]*size+rates[1]*maximum)/Decimal(1000000)
    elif path=='/v1/images/generations':
        if set(body)-{'model','prompt','size','n'}:raise ValueError('Unpriced image options are not permitted')
        if price.get('pricing_unit')!='per_image' or body.get('n',1)!=1 or body.get('size')!='1024x1024':
            raise ValueError('Only one fixed-price 1024px image is permitted')
        cost=Decimal(price['image_output_usd_per_image'])
        if not cost.is_finite() or cost<0:raise ValueError('Invalid validation image pricing')
    else:raise ValueError('Generation endpoint is outside this validation authorization')
    # Retained even on failure: account for up to six gateway attempts plus margin.
    return max(Decimal('.005'),cost*6+Decimal('.002'))


def liability(calls):
    """Only finalized successful billing may replace an upper-bound reservation."""
    return sum((Decimal(r['settled_usd']) if r.get('billing_status')=='success' and r['status']=='response_received'
                else Decimal(r['usage_bound_usd']) if r.get('billing_status')=='usage_bound' and r['status']=='response_received'
                else Decimal(r['reserved_usd']) for r in calls),Decimal(0))


def family_key(authorization,balance,cap):
    values=[Decimal(str(balance)),Decimal(str(cap))]
    if any(not v.is_finite() or v<0 for v in values):raise ValueError('Invalid validation authorization balance or cap')
    identity=[authorization,*[str(v.normalize()) for v in values]]
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


class Budget:
    def __init__(self,path,ledger,metadata,call_limit=80,image_limit=1,state_dir=None,search_root=None):
        if type(call_limit) is not int or not 1<=call_limit<=240:raise ValueError('Invalid bounded validation request limit')
        if type(image_limit) is not int or not 1<=image_limit<=5:raise ValueError('Invalid bounded validation image limit')
        self.path,self.ledger,self.metadata=Path(path),ledger,metadata
        self.call_limit,self.image_limit=call_limit,image_limit
        self.lock=threading.Lock();self.pending=None
        # Inherited ledgers share the ORIGINAL authorization, not the new phase's
        # continuation wording. Hashing avoids balances/authorization in filenames.
        authorization=ledger.get('authorization')
        root=Path(__file__).resolve().parent/'data' if authorization else self.path.resolve().parent
        family=family_key(authorization or 'isolated:'+str(self.path.resolve().parent),ledger['starting_balance_usd'],ledger.get('user_cap_usd','.75'))
        self.state_dir=Path(state_dir) if state_dir is not None else root/'validation-budget-guards'
        self.search_root=Path(search_root) if search_root is not None else root
        self.family_id=family;self.lease=self.state_dir/(family+'.lease')
        self.state_file=self.state_dir/(family+'.json');self.lease_owned=False;self.owner=uuid.uuid4().hex

    @staticmethod
    def _history(ledger):
        return [r.get('request_sha256') or hashlib.sha256(json.dumps({k:r.get(k) for k in
            ('index','model','endpoint','reserved_usd')},sort_keys=True).encode()).hexdigest() for r in ledger['calls']]

    def _same_family(self,ledger):
        if 'starting_balance_usd' not in ledger:return False
        return family_key(ledger.get('authorization') or 'isolated:'+str(self.path.resolve().parent),
            ledger['starting_balance_usd'],ledger.get('user_cap_usd','.75'))==self.family_id

    def _acquire(self):
        self.state_dir.mkdir(parents=True,exist_ok=True)
        try:self.lease.mkdir()
        except FileExistsError:raise ValueError('Another or unresolved request owns this validation budget family') from None
        self.lease_owned=True
        try:
            save(self.lease/'owner.json',dict(owner=self.owner,pid=os.getpid()))
            current=self._history(self.ledger)
            if self.state_file.exists():state=json.loads(self.state_file.read_text(encoding='utf-8'))
            else:
                # Migrate existing runs before spending: the old 78-request
                # ancestor cannot become authoritative over its 129-request child.
                state=dict(history=current,authority=str(self.path.resolve()))
                for path in self.search_root.rglob('ledger.json'):
                    other=json.loads(path.read_text(encoding='utf-8'))
                    if not self._same_family(other):continue
                    history=self._history(other)
                    if history[:min(len(current),len(history))]!=current[:min(len(current),len(history))]:
                        raise ValueError('Divergent validation histories require billing review before spending')
                    if len(history)>len(state['history']):state=dict(history=history,authority=str(path.resolve()))
                save(self.state_file,state)
            history=state['history']
            if len(current)<len(history) or current[:len(history)]!=history:
                raise ValueError('Stale validation ledger cannot spend after a newer continuation')
            if len(current)==len(history) and state['authority']!=str(self.path.resolve()):
                parent=Path(state['authority'])
                if not parent.is_file() or self.ledger.get('parent_ledger_sha256')!=hashlib.sha256(parent.read_bytes()).hexdigest():
                    raise ValueError('Only the current validation ledger may spend this authorization')
            self._sync_family()
        except Exception:
            self._release()
            raise

    def _sync_family(self):
        save(self.state_file,dict(history=self._history(self.ledger),authority=str(self.path.resolve())))

    def _release(self):
        if not self.lease_owned:return
        owner=self.lease/'owner.json'
        # Never remove a lease taken over or damaged outside this process.
        if json.loads(owner.read_text(encoding='utf-8')).get('owner')!=self.owner:
            raise ValueError('Validation lease ownership changed; manual review required')
        owner.unlink();self.lease.rmdir();self.lease_owned=False

    def before(self,request):
        try:self._before(request)
        except ValueError as exc:
            self.ledger.setdefault('blocked_requests',[]).append(dict(reason=str(exc),endpoint=request.url.path))
            # A stale/overlapping client must never overwrite the active ledger.
            if self.lease_owned and self.pending is None:
                save(self.path,self.ledger);self._release()
            print('Validation request blocked:',str(exc),flush=True)
            raise
        except Exception:
            if self.lease_owned and self.pending is None:self._release()
            raise

    def _before(self,request):
        if request.url.host!='api.meshapi.ai' or request.url.scheme!='https' or request.url.port not in (None,443) or request.url.username or request.url.password:
            raise ValueError('Non-Mesh inference blocked')
        if request.method!='POST':raise ValueError('Only explicitly budgeted generation requests are permitted on this client')
        body=json.loads(request.content)
        with self.lock:
            if self.pending is not None or any(r['status']=='reserved_or_unknown' for r in self.ledger['calls']):
                raise ValueError('An unresolved request blocks further validation spend')
            self._acquire()
            if len(self.ledger['calls'])>=self.call_limit:raise ValueError('Validation call-count ceiling reached')
            reservation=bound(body,request.url.path,self.ledger['prices'])
            for prior in self.ledger['calls']:
                if prior['status']!='response_received' or prior.get('billing_status')=='success' or not prior.get('request_id'):continue
                receipt=self.metadata.get(BASE+'/usage/requests/'+prior['request_id'])
                if not receipt.is_success:continue
                payload=receipt.json();event=payload.get('event') or {}
                costs=[Decimal(str(a['cost_usd'])) for a in payload.get('attempts',[]) if a.get('cost_usd') is not None]
                if event.get('status')=='success' and event.get('cost_usd') is not None:
                    paid=Decimal(str(event['cost_usd']))
                    if paid.is_finite() and paid>=0:
                        prior.update(billing_status='success',settled_usd=str(max(paid,sum(costs,Decimal(0)))))
                elif event.get('status')=='success' and not payload.get('ambiguous') and payload.get('attempt_count')==1 and payload.get('retry_count',0)==0:
                    # Gateway cache hits have null charges. Without a recorded
                    # HIT header, do not assume zero: retain a conservative
                    # catalog-price bound on the authoritative completed usage.
                    pricing=self.ledger['prices'][prior['model']]
                    pin,pout=event.get('prompt_tokens'),event.get('completion_tokens')
                    if pricing.get('pricing_unit')=='per_1m_tokens' and type(pin) is int and type(pout) is int and min(pin,pout)>=0:
                        upper=(Decimal(pricing['prompt_usd_per_1m'])*pin+Decimal(pricing['completion_usd_per_1m'])*pout)/Decimal(1000000)
                        prior.update(billing_status='usage_bound',usage_bound_usd=str(min(Decimal(prior['reserved_usd']),upper*6+Decimal('.002'))))
            total=liability(self.ledger['calls'])
            if total+reservation>CAP:raise ValueError('Shared validation reservation ceiling reached')
            balance=Decimal(self.metadata.get(BASE+'/balance').raise_for_status().json()['balance_usd'])
            spent=max(Decimal(0),Decimal(self.ledger['starting_balance_usd'])-balance)
            if spent+reservation>CAP:raise ValueError('Account-balance guard stopped validation')
            if request.url.path.endswith('/images/generations') and sum(r['endpoint'].endswith('/images/generations') for r in self.ledger['calls'])>=self.image_limit:
                raise ValueError('Paid validation image-count ceiling reached')
            row=dict(index=len(self.ledger['calls'])+1,model=body['model'],endpoint=request.url.path,
                reserved_usd=str(reservation),status='reserved_or_unknown',request_sha256=hashlib.sha256(request.content).hexdigest())
            self.ledger['calls'].append(row);self.pending=row
            self.ledger['max_liability_usd']=str(max(Decimal(self.ledger.get('max_liability_usd','0')),total+reservation))
            save(self.path,self.ledger)
            self._sync_family()
            print('Mesh validation request',row['index'],body['model'],'reserved',str(reservation),flush=True)

    def after(self,response):
        response.read()
        with self.lock:
            row=self.pending
            if row is None:raise ValueError('Received an unreserved inference response')
            row.update(http_status=response.status_code,request_id=response.headers.get('x-request-id') or response.headers.get('x-mesh-request-id'),
                status='response_received' if response.is_success else 'failed_response')
            row['gateway_cache']=response.headers.get('x-cache')
            if response.is_success and row['gateway_cache']=='HIT':row.update(billing_status='success',settled_usd='0',billing_basis='documented_gateway_cache_hit')
            try:
                payload=response.json();row['usage']=payload.get('usage');row['returned_model']=payload.get('model')
                if payload.get('choices'):
                    row['finish_reason']=payload['choices'][0].get('finish_reason')
                    row['raw_output']=payload['choices'][0]['message'].get('content')
            except (ValueError,KeyError,TypeError):pass
            save(self.path,self.ledger);self._sync_family()
            self.pending=None;self._release()
