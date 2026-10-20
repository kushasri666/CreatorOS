"""Evidence-based scheduling and transparent performance aggregates; no AI calls."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import storage


def recommend(post, timezone_name="Asia/Kolkata"):
    zone = ZoneInfo(timezone_name)
    posts = {p["id"]: p for p in storage.listing("post")}
    slots = defaultdict(list)
    sources = set()
    # Pick one latest 24-hour observation per post; never mix simulated with observed.
    seen = set()
    metrics = [m for m in storage.listing("metric") if m["brand_id"] == post["brand_id"]
               and m["platform"] == post["platform"] and m["input"]["window_hours"] == 24]
    source = "user_entered" if any(m["input"]["source"] == "user_entered" for m in metrics) else "simulated"
    for m in metrics:
        p = posts.get(m["post_id"], {})
        if m["post_id"] in seen or m["input"]["source"] != source or not p.get("scheduled_for"):
            continue
        seen.add(m["post_id"])
        local = datetime.fromisoformat(p["scheduled_for"]).astimezone(zone)
        slots[(local.weekday(), local.hour)].append((m["rate"], m["id"]))
        sources.add(m["input"]["source"])
    current = datetime.now(zone)
    if slots:
        (day, hour), values = max(slots.items(), key=lambda item: sum(v[0] for v in item[1])/len(item[1]))
        reason = f"Highest mean weighted engagement per impression among {len(slots)} observed slots; " \
                 f"{len(values)} post(s) support this slot. Observational, not a causal best-time claim."
        evidence = [v[1] for v in values]
        basis = "observed_metrics" if source == "user_entered" else "simulated_metrics"
    else:
        day, hour = (5, 11) if post["platform"] == "instagram" else (1, 9)
        reason = "No comparable 24-hour metrics yet. Testing a weekend morning for Instagram " \
                 "or a weekday morning for professional feeds; this is an unvalidated heuristic."
        evidence, basis = [], "heuristic"
    candidate = (current + timedelta(days=(day-current.weekday()) % 7)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=7)
    return dict(scheduled_for=candidate.astimezone(timezone.utc).isoformat(),
                local_time=candidate.isoformat(), timezone=timezone_name, basis=basis,
                reason=reason, evidence_ids=evidence)


def analytics(brand_id, platform):
    posts = {p["id"]: p for p in storage.listing("post") if p["brand_id"] == brand_id and p["platform"] == platform}
    rows, seen = [], set()
    for m in storage.listing("metric"):
        if m["post_id"] not in posts:
            continue
        key = (m["post_id"], m["input"]["source"], m["input"]["window_hours"])
        if key in seen:
            continue
        seen.add(key)
        p = posts[m["post_id"]]
        rows.append(dict(m, brief=p["brief"], hook=p["strategy"].get("format", "unspecified")))
    groups = defaultdict(list)
    for m in rows:
        groups[(m["hook"], m["input"]["source"], m["input"]["window_hours"])].append(m)
    aggregates = [dict(format=k[0], source=k[1], window_hours=k[2], count=len(v),
                       mean_rate=sum(m["rate"] for m in v)/len(v)) for k, v in groups.items()]
    return dict(rows=rows, groups=aggregates)
