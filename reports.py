"""Standalone, print-friendly cited HTML export. Escapes all source/user text."""
from html import escape
from urllib.parse import urlsplit
from grounding import build_report
from source_policy import quality


def render_report(post):
    report=build_report(post);sources=post.get("sources",[])
    esc=lambda value:escape(str(value),quote=True)
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>CreatorOS · '+esc(post.get("brief","Content report"))+'</title><style>',
        'body{font:16px/1.6 system-ui,sans-serif;color:#20202a;background:#f7f6f3;max-width:850px;margin:40px auto;padding:0 24px}h1,h2,h3{line-height:1.25}section,article{background:white;padding:22px;border:1px solid #dedde1;border-radius:12px;margin:18px 0}blockquote{margin:14px 0;padding:10px 16px;border-left:3px solid #45816a;background:#f1f7f3;white-space:pre-wrap}.warning{border-color:#b86d45;background:#fff6ef}.copy{white-space:pre-wrap}small{display:block;color:#5a5a66}a{color:#215f8f;overflow-wrap:anywhere}code{overflow-wrap:anywhere}@media print{body{background:white;margin:0;max-width:none;padding:0}section,article{break-inside:avoid;border-radius:0}a{color:inherit}}',
        '</style></head><body><header><p>CREATOROS · SAVED CONTENT & EVIDENCE</p><h1>'+esc(post.get("brief","Content report"))+'</h1>',
        '<p>'+esc(post.get("platform",""))+' · '+esc(post.get("status","unknown"))+' · '+esc(post.get("mode","unknown"))+'</p>',
        '<p>Evidence report: <strong>'+esc(report["status"])+'</strong>. This standalone page can be shared as a file or printed to PDF using your browser.</p></header>']
    if not report["passed"]:parts.append('<section class="warning"><strong>Review required.</strong> Draft copy may contain unsupported assertions. Only claims in the cited section below have valid evidence receipts; source support is still an LLM judgment.</section>')
    parts.append('<section><h2>Saved copy</h2><div class="copy">'+esc(post.get("text","No saved copy"))+'</div>')
    for i,slide in enumerate(post.get("slides",[]),1):parts.append('<h3>Slide '+str(i)+'</h3><p>'+esc(slide)+'</p>')
    parts.append('</section><section><h2>Cited claims</h2>')
    if not report["claims"]:parts.append('<p>No verified factual claims are available.</p>')
    for claim in report["claims"]:
        parts.append('<article><strong>'+esc(claim["claim"])+'</strong> '+''.join('<a href="#source-'+esc(sid)+'">['+esc(sid)+']</a> ' for sid in claim["source_ids"]))
        for receipt in claim["evidence"]:parts.append('<blockquote>'+esc(receipt["quote"])+'</blockquote><small>Verbatim excerpt · '+esc(receipt["source_id"])+'</small>')
        parts.append('</article>')
    parts.append('</section>')
    parts.append('<section><h2>Recorded agent decisions</h2>')
    for key in ("angle","hook","audience","reason"):
        if (post.get("strategy") or {}).get(key):parts.append('<p><strong>'+esc(key)+':</strong> '+esc(post["strategy"][key])+'</p>')
    if post.get("schedule_recommendation"):
        schedule=post["schedule_recommendation"]
        parts.append('<p>Scheduling basis: '+esc(schedule.get("basis","unspecified"))+' · '+esc(schedule.get("reason",""))+'</p>')
    parts.append('<small>Planning and scheduling reasons are agent decisions, not independent product evidence.</small></section>')
    conflicts=report["evidence_review"]["conflicts"]
    parts.append('<section'+(' class="warning"' if conflicts else '')+'><h2>Source disagreements</h2>')
    if not conflicts:parts.append('<p>No disagreements were recorded by the available checks. This does not prove none exist.</p>')
    for conflict in conflicts:
        parts.append('<h3>'+esc(conflict["subject"])+' · unresolved</h3><p>'+esc(conflict["reason"])+'</p>')
        for row in conflict["evidence"]:parts.append('<blockquote>'+esc(row["quote"])+'</blockquote><a href="#source-'+esc(row["source_id"])+'">['+esc(row["source_id"])+']</a>')
        parts.append('<small>Review preference: '+esc(conflict["preferred_source_id"])+'. Preference does not resolve the disagreement.</small>')
    parts.append('</section><section><h2>Sources and provenance</h2>')
    for source in sources:
        weight=quality(source);sid=source["source_id"]
        parts.append('<article id="source-'+esc(sid)+'"><h3>['+esc(sid)+'] '+esc(source.get("title",sid))+'</h3><p>'+esc(weight["tier"])+' · weight '+str(weight["score"])+'</p><p>'+esc(weight["reason"])+'</p>')
        url=source.get("url") or "";parsed=urlsplit(url)
        if parsed.scheme in ("http","https") and parsed.hostname and not parsed.username and not parsed.password:
            parts.append('<p><a rel="noreferrer noopener" href="'+esc(url)+'">'+esc(url)+'</a></p>')
        parts.append('<blockquote>'+esc(source.get("excerpt",""))+'</blockquote><small>Captured '+esc(source.get("retrieved_at",source.get("collected_at","time unavailable")))+'</small>')
        for key in ("document_id","sha256","transcript_sha256","metric_id","window"):
            if source.get(key) is not None:parts.append('<small>'+esc(key)+': '+esc(source[key])+'</small>')
        parts.append('</article>')
    parts.append('</section>')
    if report["withheld_claims"]:
        parts.append('<section class="warning"><h2>Withheld claim findings</h2>')
        for claim in report["withheld_claims"]:parts.append('<p><strong>'+esc(claim["claim"])+'</strong><br>'+esc(claim["reason"])+'</p>')
        parts.append('</section>')
    parts.append('<section><h2>Limitations</h2>')
    for note in report["limitations"]:parts.append('<p>'+esc(note)+'</p>')
    parts.append('<small>Source weights describe provenance, not certainty. No external scripts, tracking, remote assets or API credentials are embedded.</small></section></body></html>')
    return ''.join(parts)
