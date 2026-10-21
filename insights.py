"""Evidence-based scheduling and transparent performance aggregates; no AI calls."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo
import storage


def _aware(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _api_timing(post, zone, current, posts):
    """Compare like-for-like account observations, never aggregate mixed windows."""
    connections = [c for c in storage.listing("social_connection")
        if c.get("brand_id") == post["brand_id"] and c.get("provider") == post["platform"]
        and c.get("status") != "disconnected"]
    selected = post.get("connection_id")
    matches = [c for c in connections if c["id"] == selected] if selected else connections
    policy = dict(minimum_posts_per_slot=2, minimum_comparable_slots=2,
        maximum_observation_age_days=14, maximum_publication_age_days=90)
    detail = dict(status="insufficient_evidence", policy=policy)
    if len(matches) != 1 or not matches[0].get("account_id"):
        detail["reason"] = "Select one matching account with a resolved provider account ID before using API timing evidence."
        return None, detail
    connection = matches[0]
    detail.update(connection_id=connection["id"], account_id=connection["account_id"])
    latest = {}
    for row in storage.listing("social_metric"):
        if (row.get("brand_id") != post["brand_id"] or row.get("platform") != post["platform"]
                or row.get("connection_id") != connection["id"] or row.get("source") != "api"):
            continue
        collected = _aware(row.get("collected_at"))
        if collected and (row.get("post_id") not in latest
                or collected > latest[row["post_id"]][0]):
            latest[row["post_id"]] = (collected, row)
    groups = defaultdict(lambda: defaultdict(list))
    expected_format = post.get("strategy", {}).get("format")
    for collected, row in latest.values():
        published = _aware(row.get("published_at"))
        rate = row.get("rate")
        original = posts.get(row.get("post_id"), {})
        if (original.get("brand_id") != post["brand_id"] or original.get("platform") != post["platform"]
                or row.get("account_id") != connection["account_id"]
                or row.get("published_at_source") not in ("api_metadata", "api_publication_receipt")
                or not published or collected < published or collected > current
                or current-collected > timedelta(days=14) or current-published > timedelta(days=90)
                or type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0
                or not all(isinstance(row.get(k), str) and row[k] for k in ("window", "age_bucket", "formula", "format"))
                or row["format"] in ("unknown", "FEED")
                or (expected_format and row["format"] != expected_format)):
            continue
        local = published.astimezone(zone)
        cohort = (row["window"], row["age_bucket"], row["formula"], row["format"])
        groups[cohort][(local.weekday(), local.hour)].append((rate, row["id"]))
    eligible = []
    for cohort, slots in groups.items():
        supported = {slot: values for slot, values in slots.items() if len(values) >= 2}
        if len(supported) >= 2:
            eligible.append((sum(map(len, supported.values())), cohort, supported))
    if not eligible:
        detail["reason"] = ("API timing needs recent account-pinned observations with provider publication timestamps, "
            "one format/window/age/formula cohort, and at least two distinct posts in each of two weekday/hour slots. "
            "Legacy snapshots or manually entered publication times are not sufficient.")
        return None, detail
    # Choose the largest comparable cohort, not the cohort with the highest rate.
    _, cohort, slots = max(eligible, key=lambda candidate: (candidate[0], candidate[1]))
    slot, values = max(slots.items(), key=lambda item: (sum(v[0] for v in item[1])/len(item[1]), item[0]))
    detail.update(status="used", cohort=dict(zip(("window", "age_bucket", "formula", "format"), cohort)),
        comparable_slots=len(slots), comparable_posts=sum(map(len, slots.values())),
        comparison_evidence_ids=[v[1] for entries in slots.values() for v in entries],
        reason="Highest observed mean interaction rate within one comparable account cohort; exploratory association, not causal best-time evidence.")
    return (slot, values), detail


def recommend(post, timezone_name="Asia/Kolkata"):
    zone = ZoneInfo(timezone_name)
    posts = {p["id"]: p for p in storage.listing("post")}
    current = datetime.now(zone)
    api_slot, api_detail = _api_timing(post, zone, current, posts)
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
    if api_slot:
        (day, hour), values = api_slot
        reason = api_detail["reason"] + f" {len(values)} distinct posts support the selected slot; publication times use {timezone_name}."
        evidence = [v[1] for v in values]
        basis = "api_observational_metrics"
    elif slots:
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
    if not api_slot:
        reason += " API timing evidence not used: " + api_detail["reason"]
    candidate = (current + timedelta(days=(day-current.weekday()) % 7)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=7)
    return dict(scheduled_for=candidate.astimezone(timezone.utc).isoformat(),
                local_time=candidate.isoformat(), timezone=timezone_name, basis=basis,
                reason=reason, evidence_ids=evidence, api_evidence=api_detail)


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
