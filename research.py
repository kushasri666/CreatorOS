"""Product-focused, source-preserving research from supplied product pages and files."""
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from html.parser import HTMLParser
import re
import socket
from uuid import uuid4
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import storage

MAX_PRODUCT_PAGES = 3
MAX_DOCUMENTS = 3
MAX_EXCERPT = 1100
MAX_PAGE_BYTES = 1_500_000
USER_AGENT = "CreatorOS/1.0 (https://github.com/kushasri666/CreatorOS) httpx"
PRODUCT_LINK_TERMS = ("product", "feature", "pricing", "price", "plan", "faq", "how-it-works", "use-case", "solution")


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title_depth = 0
        self.title = []
        self.text = []
        self.links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in ("script","style","noscript","svg","iframe","nav","footer"):
            self.skip += 1
        if tag=="title":self.title_depth+=1
        if tag=="a" and attrs.get("href"):
            self.anchor=[attrs["href"],[]]

    def handle_endtag(self, tag):
        if tag in ("script","style","noscript","svg","iframe","nav","footer"):
            self.skip=max(0,self.skip-1)
        if tag=="title":self.title_depth=max(0,self.title_depth-1)
        if tag=="a" and self.anchor:
            self.links.append((self.anchor[0]," ".join(self.anchor[1])))
            self.anchor=None

    def handle_data(self, data):
        if self.title_depth:self.title.append(data)
        if not self.skip and data.strip():self.text.append(data.strip())
        if self.anchor:self.anchor[1].append(data.strip())


def save_document(brand_id, filename, text):
    brand=storage.get(brand_id)
    if not brand or brand.get("kind")!="brand":raise ValueError("Brand not found")
    name=filename.strip()
    if not name.lower().endswith((".txt",".md")):
        raise ValueError("Upload a plain text .txt or Markdown .md document")
    text=text.replace("\x00","").strip()
    if not text or len(text)>12000:raise ValueError("Document must contain 1–12,000 characters")
    digest=hashlib.sha256(text.encode("utf-8")).hexdigest()
    prior=next((d for d in storage.listing("research_document") if d.get("brand_id")==brand_id and d.get("sha256")==digest),None)
    if prior:return prior,False
    existing=[d for d in storage.listing("research_document") if d.get("brand_id")==brand_id]
    if len(existing)>=MAX_DOCUMENTS:
        raise ValueError("This brand already has three attachments (documents, audio or video).")
    return storage.save("research_document",dict(brand_id=brand_id,filename=name[:120],text=text,
        sha256=digest,created_at=storage.now(),source_type="user_document")),True


def _document_source(doc, excerpt, start):
    media=bool(doc.get("media_type"))
    source=dict(source_type="user_media_transcript" if media else "user_document",
        provider="User-supplied media transcript/notes" if media else "User upload",
        title=doc["filename"]+(" · supplied transcript/notes" if media else ""),url=None,
        excerpt=excerpt,excerpt_start=start,document_id=doc["id"],sha256=doc["sha256"],document_created_at=doc["created_at"])
    if media:
        source.update(media_type=doc["media_type"],transcript_origin="user_supplied",
            transcript_sha256=doc.get("transcript_sha256"),
            attachment_url=f"/brands/{doc['brand_id']}/research-media/{doc['id']}/file")
    return source


def _validate_url(url):
    message="Use a public HTTPS product page URL without credentials, query parameters, or a custom port"
    try:
        parsed=urlsplit(url.strip())
        if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):
            raise ValueError(message)
        host=parsed.hostname.encode("idna").decode("ascii").lower()
        if host=="localhost" or host.endswith((".localhost",".local",".internal")):
            raise ValueError(message)
        try:
            literal=ipaddress.ip_address(host)
        except ValueError:
            literal=None
        if literal is not None:
            if not literal.is_global:raise ValueError(message)
        else:
            addresses=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                raise ValueError("Product page must resolve only to public addresses")
    except (UnicodeError, ValueError, socket.gaierror) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Product page"):
            raise
        raise ValueError(message) from exc
    return urlunsplit(("https",host,parsed.path or "/","",""))


def _parse_page(response, topic):
    if len(response.content)>MAX_PAGE_BYTES:raise ValueError("Product page exceeds the retrieval size limit")
    content_type=response.headers.get("content-type","").lower()
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise ValueError("Product URL did not return a readable text or HTML page")
    parser=_PageParser()
    if "text/html" in content_type:parser.feed(response.text[:MAX_PAGE_BYTES])
    else:parser.text=[response.text[:MAX_PAGE_BYTES]]
    title=re.sub(r"\s+"," "," ".join(parser.title)).strip()[:240]
    text=re.sub(r"\s+"," "," ".join(parser.text)).strip()
    excerpt,_=_relevant_excerpt(text,topic)
    return title or response.url.path.rstrip("/").split("/")[-1] or response.url.host,excerpt,parser.links


def _relevant_excerpt(text, topic):
    terms={t.casefold() for t in re.findall(r"[A-Za-z0-9]{4,}",topic)}
    parts=[];offset=0
    for paragraph in re.split(r"(\n\s*\n)",text):
        if re.fullmatch(r"\n\s*\n",paragraph):offset+=len(paragraph);continue
        leading=len(paragraph)-len(paragraph.lstrip());clean=paragraph.strip()
        if clean:
            for start in range(0,max(1,len(clean)),MAX_EXCERPT-120):
                segment=clean[start:start+MAX_EXCERPT]
                parts.append((offset+leading+start,re.sub(r"\s+"," ",segment)))
        offset+=len(paragraph)
    if not parts:return text[:MAX_EXCERPT],0
    ranked=max(parts,key=lambda row:(sum(t in row[1].casefold() for t in terms),-row[0]))
    # A product page can include generic navigation and corporate boilerplate. If none
    # of the supplied product/topic terms occur, don't present that text as evidence.
    return (ranked[1],ranked[0]) if not terms or any(t in ranked[1].casefold() for t in terms) else ("",ranked[0])


def _alternate_excerpt(text, query, previous):
    terms={t.casefold() for t in re.findall(r"[A-Za-z0-9]{4,}",query)}
    prior={re.sub(r"\s+"," ",value).strip().casefold() for value in previous}
    parts=[];offset=0
    for paragraph in re.split(r"(\n\s*\n)",text):
        if re.fullmatch(r"\n\s*\n",paragraph):offset+=len(paragraph);continue
        clean=paragraph.strip();leading=len(paragraph)-len(paragraph.lstrip())
        for start in range(0,max(1,len(clean)),MAX_EXCERPT-120):
            excerpt=re.sub(r"\s+"," ",clean[start:start+MAX_EXCERPT]).strip()
            if excerpt and excerpt.casefold() not in prior:
                parts.append((sum(term in excerpt.casefold() for term in terms),offset+leading+start,excerpt))
        offset+=len(paragraph)
    if not parts:return "",0
    score,start,excerpt=max(parts,key=lambda item:(item[0],-item[1]))
    return (excerpt,start) if score or not terms else ("",0)


def _official_pages(product_url, product, topic, client, *, max_pages=MAX_PRODUCT_PAGES,
                    exclude_urls=(), target_terms=(), observe=None):
    observe = observe or (lambda detail: None)
    start=_validate_url(product_url)
    host=urlsplit(start).hostname
    queue=[start];seen=set();rows=[]
    excluded=set(exclude_urls);pages_fetched=0
    while queue and pages_fetched<max_pages:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        # Revalidate same-origin links and block private-address DNS answers.
        validated=_validate_url(url)
        parsed_url=urlsplit(validated)
        if (parsed_url.scheme,parsed_url.hostname,parsed_url.port)!=(urlsplit(start).scheme,urlsplit(start).hostname,urlsplit(start).port):continue
        query=product+" "+topic+" "+" ".join(target_terms)
        attempt=dict(attempt_id=str(uuid4()),action="official_page_fetch",url=validated,query=query,
            reason="Inspect this official product page for relevant evidence; no general web search.")
        observe(dict(attempt,status="started"))
        try:
            response=client.get(validated,headers={"User-Agent":USER_AGENT},follow_redirects=False)
            response.raise_for_status()
            pages_fetched+=1
            title,excerpt,links=_parse_page(response,query)
        except (httpx.HTTPError,ValueError,TypeError,OSError) as exc:
            observe(dict(attempt,status="failed",error_type=type(exc).__name__,
                http_status=getattr(getattr(exc,"response",None),"status_code",None),
                reason="Product-page request or parsing failed; no evidence was accepted from this attempt."))
            raise
        observe(dict(attempt,status="retrieved" if excerpt and str(response.url) not in excluded else "no_new_evidence",
            http_status=response.status_code,title=title,excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
            reason="Relevant excerpt retrieved." if excerpt and str(response.url) not in excluded else "Page was already used or had no relevant excerpt."))
        if excerpt and str(response.url) not in excluded:
            rows.append(dict(source_type="official_product_page",provider="Official product website",
                title=title,url=str(response.url),excerpt=excerpt,
                source_updated_at=response.headers.get("last-modified")))
        candidates=[]
        for href,label in links:
            absolute=urljoin(str(response.url),href)
            parsed=urlsplit(absolute)
            if parsed.scheme!="https" or not parsed.hostname or parsed.hostname.lower()!=host:continue
            searchable=(label+" "+parsed.path).casefold()
            if any(term in searchable for term in PRODUCT_LINK_TERMS):
                candidate=urlunsplit(("https",host,parsed.path,"",""))
                relevance=sum(term.casefold() in searchable for term in target_terms)
                candidates.append((relevance,candidate))
        candidates.sort(key=lambda row:(-row[0],row[1]))
        for _,candidate in candidates:
            if candidate not in seen and candidate not in queue:queue.append(candidate)
    return rows


def gather(post_id, brand_id, topic, product, document_ids=(), platform=None, client=None, connection_id=None):
    """Collect brand documents, product-page evidence and connected-account observations."""
    name=(product or {}).get("name","").strip()
    query=name+" "+topic
    storage.audit(post_id,"research_plan",dict(phase="initial",reason="Resolve product-specific evidence questions before drafting; deterministic plan uses no AI call.",
        questions=[dict(id="Q-product",question=f"Which claims about {name or 'the product'} are supported by supplied facts and its official pages?"),
            dict(id="Q-documents",question=f"What do the uploaded brand documents substantiate for this brief: {topic}?"),
            dict(id="Q-performance",question=f"What engagement observations are available from this brand's selected {platform or 'social'} account?")]))
    all_docs={d["id"]:d for d in storage.listing("research_document") if d.get("brand_id")==brand_id}
    # Every saved brand document participates by default.
    selected=list(all_docs)[:MAX_DOCUMENTS]
    if len(selected)>MAX_DOCUMENTS:raise ValueError("Attach up to three documents")
    docs=all_docs
    if any(id not in docs for id in selected):raise ValueError("A selected document does not belong to this brand")
    sources=[];warnings=[]
    details=(product or {}).get("details","").strip()
    if details:
        sources.append(dict(source_type="user_product_facts",provider="Brand product profile",
            title=name or "User-provided product facts",url=None,excerpt=details[:MAX_EXCERPT]))
        storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-product"],action="supplied_product_fact_lookup",
            query=query,status="retrieved",reason="Included the brand owner's supplied product facts; no external request."))
    for id in selected:
        doc=docs[id]
        if not doc.get("text","").strip():
            warnings.append(doc["filename"]+" is saved as media but has no supplied transcript/notes; raw media was not analyzed and is excluded from factual evidence.")
            storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-documents"],action="media_evidence_lookup",
                document_id=id,status="skipped",reason="No transcript/notes supplied; automatic media analysis did not run."))
            continue
        excerpt,start=_relevant_excerpt(doc["text"],name+" "+topic)
        if not excerpt:
            excerpt,start=doc["text"][:MAX_EXCERPT],0
        sources.append(_document_source(doc,excerpt,start))
        if doc.get("media_type"):
            warnings.append(doc["filename"]+" contributes user-supplied transcript/notes only; these are not automatic audio/video observations.")
        storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-documents"],action="document_excerpt_lookup",
            document_id=id,document_sha256=doc["sha256"],query=query,status="retrieved",excerpt_start=start,
            reason="Selected a brand document excerpt; the verifier must still assess whether it supports draft claims."))
    if not selected:
        storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-documents"],action="document_excerpt_lookup",
            query=query,status="skipped",reason="This brand has no uploaded documents."))
    # Only provider-collected observations for this brand and platform are evidence
    # about audience behavior. Simulated and hand-entered values remain separate.
    if platform:
        eligible_connections=[c for c in storage.listing("social_connection")
            if c.get("brand_id")==brand_id and c.get("provider")==platform and c.get("enabled")]
        if connection_id:
            eligible_connections=[c for c in eligible_connections if c.get("id")==connection_id]
        elif len(eligible_connections)!=1:
            eligible_connections=[]
        active_ids={c["id"] for c in eligible_connections}
        metrics=[m for m in storage.listing("social_metric") if m.get("brand_id")==brand_id
                 and m.get("platform")==platform and m.get("source")=="api"
                 and m.get("connection_id") in active_ids]
        metrics.sort(key=lambda m:m.get("collected_at", ""),reverse=True)
        storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-performance"],action="stored_provider_observation_lookup",
            filters=dict(brand_id=brand_id,platform=platform,connection_ids=sorted(active_ids),source="api",limit=5),
            metric_ids=[m["id"] for m in metrics[:5]],status="retrieved" if metrics else "no_evidence",
            reason="Queried already-collected provider observations for the selected enabled account; this lookup makes no provider API request."))
        for metric in metrics[:5]:
            published=storage.get(metric.get("post_id")) or {}
            connection=storage.get(metric.get("connection_id")) or {}
            counts=metric.get("counts",{})
            metric_excerpt=(f"Connected {platform} account performance observation for {metric.get('format','content')}. "
                f"Content: {(published.get('text') or published.get('brief') or '')[:260]} "
                f"Observed metrics: {json.dumps(counts,ensure_ascii=False,sort_keys=True)}. "
                f"Connected account: {connection.get('account_id','linked account')}. "
                f"Reporting window: {metric.get('window','provider-reported')}; collected: {metric.get('collected_at','unknown')}. "
                f"Engagement rate: {metric.get('rate') if metric.get('rate') is not None else 'unavailable'}.")
            sources.append(dict(source_type="social_account_metrics",provider=platform,
                title=f"Observed {platform} post performance · {metric.get('format','content')}",
                url=None,excerpt=metric_excerpt[:MAX_EXCERPT],metric_id=metric["id"],
                external_id=metric.get("external_id"),linked_post_id=metric.get("post_id"),
                connection_id=metric.get("connection_id"),account_id=connection.get("account_id"),
                format=metric.get("format"),counts=counts,window=metric.get("window"),
                collected_at=metric.get("collected_at"),source="api"))
        if not metrics:
            warnings.append(f"No provider-collected {platform} engagement observations are available for the selected enabled account. Connect and enable one account, then wait for sync or import/link published posts.")
    product_url=(product or {}).get("url","").strip()
    if product_url:
        owns=False
        try:
            if client is None:
                client=httpx.Client(timeout=8,follow_redirects=False)
                owns=True
            sources.extend(_official_pages(product_url,name,topic,client,
                observe=lambda d:storage.audit(post_id,"research_attempt",dict(d,phase="initial",question_ids=["Q-product"]))))
            if not any(s["source_type"]=="official_product_page" for s in sources):
                warnings.append("The official product website returned no readable product information.")
        except (httpx.HTTPError,ValueError,TypeError,OSError) as exc:
            warnings.append("Official product page retrieval failed: "+str(exc)[:240])
            storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-product"],action="official_product_retrieval",
                status="failed",error_type=type(exc).__name__,reason="Official page retrieval was blocked or failed. See per-page attempts when a request was made."))
        finally:
            if owns:client.close()
    else:
        warnings.append("No official product URL was supplied; product-page retrieval was skipped.")
        storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-product"],action="official_product_retrieval",
            status="skipped",reason="No official product URL was supplied."))
    if not platform:
        storage.audit(post_id,"research_attempt",dict(phase="initial",question_ids=["Q-performance"],action="stored_provider_observation_lookup",
            status="skipped",reason="Connected-account evidence lookup was not requested."))
    stored=_store_sources(post_id,brand_id,sources,1)
    storage.audit(post_id,"research_retrieval",dict(source_ids=[r["source_id"] for r in stored],
        source_types=[r["source_type"] for r in stored],warnings=warnings,
        reason="Retrieved uploaded brand documents, product facts/pages, and provider-collected performance when available."))
    return stored,warnings


def _store_sources(post_id,brand_id,sources,start_index):
    stored=[]
    for i,source in enumerate(sources,start_index):
        identity=source.get("url") or source.get("sha256") or hashlib.sha256(source["excerpt"].encode()).hexdigest()
        key=hashlib.sha256((post_id+"\0"+str(i)+"\0"+identity).encode()).hexdigest()[:24]
        row=storage.save("research_source",dict(source,id="source:"+key,post_id=post_id,
            brand_id=brand_id,source_id="S"+str(i),retrieved_at=datetime.now(timezone.utc).isoformat()),"source:"+key)
        stored.append(row)
    return stored


def gather_more(post_id, brand_id, topic, product, claims, existing_sources,
                platform=None, connection_id=None, client=None):
    """One bounded retrieval retry targeted at failed-verification draft claims."""
    query=" ".join(str(c)[:300] for c in claims[:5])
    if not query:return [],["No specific failed-verification claim was supplied to target."]
    question_ids=[f"Q-retry-{i+1}" for i,_ in enumerate(claims[:5])]
    storage.audit(post_id,"research_plan",dict(phase="verification_retry",target_claims=claims[:5],
        questions=[dict(id=qid,question=f"What additional product evidence directly supports this flagged claim: {claim}") for qid,claim in zip(question_ids,claims[:5])],
        reason="Verifier requested more support; one bounded retrieval retry will investigate these claims."))
    additional=[];warnings=[]
    docs={d["id"]:d for d in storage.listing("research_document") if d.get("brand_id")==brand_id}
    for doc_id,doc in docs.items():
        previous=[s.get("excerpt","") for s in existing_sources if s.get("document_id")==doc_id]
        excerpt,start=_alternate_excerpt(doc["text"],query,previous)
        storage.audit(post_id,"research_attempt",dict(phase="verification_retry",question_ids=question_ids,action="document_excerpt_lookup",
            document_id=doc_id,document_sha256=doc["sha256"],query=query,excerpt_start=start,
            status="retrieved" if excerpt else "no_new_evidence",reason="Looked for a distinct document passage relevant to the flagged claims."))
        if excerpt:
            additional.append(dict(_document_source(doc,excerpt,start),targeted_to_claims=True))

    if platform:
        eligible=[c for c in storage.listing("social_connection") if c.get("brand_id")==brand_id
            and c.get("provider")==platform and c.get("enabled")]
        if connection_id:eligible=[c for c in eligible if c.get("id")==connection_id]
        elif len(eligible)!=1:eligible=[]
        account_ids={c["id"] for c in eligible}
        used={s.get("metric_id") for s in existing_sources}
        metrics=[m for m in storage.listing("social_metric") if m.get("brand_id")==brand_id
            and m.get("platform")==platform and m.get("source")=="api"
            and m.get("connection_id") in account_ids and m["id"] not in used]
        metrics.sort(key=lambda m:m.get("collected_at",""),reverse=True)
        storage.audit(post_id,"research_attempt",dict(phase="verification_retry",question_ids=question_ids,action="stored_provider_observation_lookup",
            filters=dict(brand_id=brand_id,platform=platform,connection_ids=sorted(account_ids),source="api",limit=3,exclude_metric_ids=sorted(x for x in used if x)),
            metric_ids=[m["id"] for m in metrics[:3]],status="retrieved" if metrics else "no_new_evidence",
            reason="Looked for additional stored provider observations within the same account scope; no provider API request."))
        for metric in metrics[:3]:
            published=storage.get(metric.get("post_id")) or {};connection=storage.get(metric.get("connection_id")) or {}
            counts=metric.get("counts",{})
            excerpt=(f"Connected {platform} account observation for {metric.get('format','content')}. "
                f"Content: {(published.get('text') or published.get('brief') or '')[:260]} "
                f"Metrics: {json.dumps(counts,ensure_ascii=False,sort_keys=True)}. "
                f"Account: {connection.get('account_id','linked account')}. Window: {metric.get('window','unknown')}; "
                f"collected: {metric.get('collected_at','unknown')}; engagement rate: {metric.get('rate','unavailable')}.")
            additional.append(dict(source_type="social_account_metrics",provider=platform,
                title=f"Additional observed {platform} post performance · {metric.get('format','content')}",
                url=None,excerpt=excerpt[:MAX_EXCERPT],metric_id=metric["id"],external_id=metric.get("external_id"),
                linked_post_id=metric.get("post_id"),connection_id=metric.get("connection_id"),
                account_id=connection.get("account_id"),format=metric.get("format"),counts=counts,
                window=metric.get("window"),collected_at=metric.get("collected_at"),source="api",targeted_to_claims=True))

    product_url=(product or {}).get("url","").strip()
    if product_url:
        owns=False
        try:
            if client is None:
                client=httpx.Client(timeout=8,follow_redirects=False);owns=True
            prior_urls={s.get("url") for s in existing_sources if s.get("url")}
            pages=_official_pages(product_url,(product or {}).get("name",""),topic,client,
                max_pages=2,exclude_urls=prior_urls,target_terms=re.findall(r"[A-Za-z0-9]{4,}",query)[:12],
                observe=lambda d:storage.audit(post_id,"research_attempt",dict(d,phase="verification_retry",question_ids=question_ids)))
            additional.extend(dict(page,targeted_to_claims=True) for page in pages)
        except (httpx.HTTPError,ValueError,TypeError,OSError) as exc:
            warnings.append("Targeted product-page retrieval failed: "+str(exc)[:200])
            storage.audit(post_id,"research_attempt",dict(phase="verification_retry",question_ids=question_ids,action="official_product_retrieval",
                status="failed",error_type=type(exc).__name__,reason="Targeted official-page retrieval was blocked or failed."))
        finally:
            if owns:client.close()

    used={s.get("document_id")+":"+s.get("excerpt","") for s in existing_sources if s.get("document_id")}
    additional=[s for s in additional if not s.get("document_id") or s.get("document_id")+":"+s.get("excerpt","") not in used]
    first=max([int(s["source_id"][1:]) for s in existing_sources if re.fullmatch(r"S[0-9]+",s.get("source_id",""))] or [0])+1
    stored=_store_sources(post_id,brand_id,additional,first)
    if not stored:warnings.append("The bounded retry found no additional product-specific source text. Unsupported claims will remain flagged for review.")
    storage.audit(post_id,"research_retrieval",dict(source_ids=[s["source_id"] for s in stored],
        target_claims=claims[:5],warnings=warnings,
        reason="One bounded retrieval retry targeted only claims flagged by the verifier."))
    return stored,warnings
