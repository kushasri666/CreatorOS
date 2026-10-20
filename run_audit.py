"""Project recorded run decisions into a readable/exportable trail. No AI calls."""
from grounding import build_report


def build_trail(post, events, sources):
    timeline = []
    questions, searches, decisions = [], [], []
    for sequence, event in enumerate(events, 1):
        entry = dict(event, sequence=sequence)
        timeline.append(entry)
        detail = event.get("detail", {})
        reference = dict(event_id=event["id"], sequence=sequence, at=event.get("at"))
        if event["agent"] == "research_plan":
            for question in detail.get("questions", []):
                questions.append(dict(question, **reference, phase=detail.get("phase")))
        if event["agent"] == "research_attempt":
            searches.append(dict(detail, **reference))
        if event["agent"] == "verification":
            for check in detail.get("checks", []):
                decisions.append(dict(check, **reference, verification_pass=detail.get("version"),
                    draft_version=detail.get("draft_version")))
    report = build_report(dict(post, sources=post.get("sources") or sources))
    return dict(schema_version="run-audit-v1", post_id=post["id"], brand_id=post.get("brand_id"),
        brief=post.get("brief"), platform=post.get("platform"), status=post.get("status"),
        mode=post.get("mode"), created_at=post.get("created_at"),
        questions=questions, searches=searches, claim_decisions=decisions,
        passed_claims=[d for d in decisions if d.get("verdict") == "supported"],
        rejected_claims=[d for d in decisions if d.get("verdict") in ("thin", "unsupported")],
        sources=sources, grounded_report=report, timeline=timeline,
        source_review=report["evidence_review"],graph_definition=post.get("graph_definition"),graph_trace=post.get("graph_trace",[]),
        limitations=["This is the recorded decision trail, not private model reasoning.",
            "Historical runs may lack question or search-attempt records; missing events are not reconstructed.",
            "Document/observation lookups are labeled local. Only official_page_fetch events represent web requests.",
            "A supported verdict records source comparison, not guaranteed truth. Earlier rejected claims remain visible even after correction.",
            "Records are stored in local SQLite; this is not a tamper-proof or externally signed log."])
