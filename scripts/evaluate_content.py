"""Rescore immutable historical Mesh outputs and separate authored regression cases. No AI."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from content_quality import VERSION, POLICIES, score

OUTPUT = ROOT / "docs/evaluation-content-v2.json"


def load_cases():
    historical = json.loads((ROOT / "docs/evaluation-live.json").read_text(encoding="utf-8"))
    cases = []
    for i, row in enumerate(historical["rows"]):
        cases.append(dict(id=f"historical-{i}", origin="recorded_mesh", platform=row["platform"],
            brand=row["brand"], learned=row["learned"], pair=f"{row['brand']}/{row['platform']}",
            requirements=dict(concepts=[["AI"], ["safety"], ["startup", "founders"]],
                              cta_terms=["?", "share", "try", "save"], voice_terms=row["voice"].get("vocabulary", [])),
            before={"text": row["initial"]}, after={"text": row["final"]}))
    calls = json.loads((ROOT / "docs/model-comparison-075.json").read_text(encoding="utf-8"))["calls"]
    for model in sorted({c["model"] for c in calls if c["task"] == "main_writer"}):
        selected = {c["task"]: c for c in calls if c["model"] == model and c["task"] in ("main_writer", "main_revision")}
        cases.append(dict(id=f"carousel-{model}", origin="recorded_mesh", platform="instagram", model=model,
            requirements=dict(concepts=[["coffee"], ["beans", "grind", "grinding"], ["mug"], ["water"]],
                cta_terms=["save", "share", "?"], voice_terms=["silky", "ritual", "fresh"], slide_count=7),
            before=selected["main_writer"]["result"], after=selected["main_revision"]["result"]))
    cases += json.loads((ROOT / "evals/content/cases.json").read_text(encoding="utf-8"))["cases"]
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    return cases


def aggregate(rows):
    n = len(rows)
    return dict(n=n, mean_before=round(sum(r["before"]["score_100"] for r in rows)/n, 3),
        mean_after=round(sum(r["after"]["score_100"] for r in rows)/n, 3),
        improved=sum(r["delta"] > 0 for r in rows), unchanged=sum(r["delta"] == 0 for r in rows),
        regressed=sum(r["delta"] < 0 for r in rows), changed=sum(r["changed"] for r in rows))


def evaluate():
    cases = load_cases()
    rows = []
    for c in cases:
        before = score(c["before"], c["platform"], c["requirements"])
        after = score(c["after"], c["platform"], c["requirements"])
        rows.append(dict(id=c["id"], origin=c["origin"], platform=c["platform"], before=before, after=after,
            delta=round(after["score_100"]-before["score_100"], 3), changed=c["before"] != c["after"]))
    groups = {}
    for origin in sorted({r["origin"] for r in rows}):
        selected = [r for r in rows if r["origin"] == origin]
        groups[origin] = dict(overall=aggregate(selected), by_platform={p: aggregate([r for r in selected if r["platform"] == p])
            for p in POLICIES if any(r["platform"] == p for r in selected)})
    paired = []
    for key in sorted({c["pair"] for c in cases if "pair" in c}):
        pair = {c["learned"]: rows[i] for i, c in enumerate(cases) if c.get("pair") == key}
        paired.append(dict(pair=key, delta=round(pair[True]["after"]["score_100"]-pair[False]["after"]["score_100"], 3)))
    paths = ["content_quality.py", "scripts/evaluate_content.py", "evals/content/cases.json", "docs/evaluation-live.json", "docs/model-comparison-075.json"]
    return dict(rubric=VERSION, ai_calls=0, validation_cost_usd=0, policies={p: list(v) for p, v in POLICIES.items()},
        fingerprints={p: hashlib.sha256((ROOT/p).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths},
        cohorts=groups, memory_pairs=paired, rows=rows,
        limitations="Historical Mesh outputs only, not validation of newer pipeline changes. Authored fixtures are scorer regressions, not model quality. Equal-weight editorial proxies; lexical coverage and voice cues do not establish meaning, truth or brand fidelity. No engagement uplift, representative population, independent human rating or statistical significance claimed. Source verification is measured separately.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-recorded", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.check_recorded:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != result:
            raise SystemExit("Recorded content evaluation differs; review and regenerate")
        print("Content evaluation reproduces exactly; zero AI calls.")
    else:
        OUTPUT.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(result["cohorts"], indent=2))
