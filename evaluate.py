"""Reproducible offline scoring; --live uses paid Mesh generations, no test doubles."""
import argparse
import json
import os
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from workflow import Mesh, learn_voice, run_pipeline
from model_policy import routes


def score(text):
    """Transparent 0–5 heuristic: specific hook, steps, readability, question CTA, brevity."""
    lines = text.splitlines()
    return {
        "specific_hook": int(len(lines[0].split()) >= 6 and "?" not in lines[0]),
        "actionable_steps": int(all(f"{n}." in text for n in (1, 2, 3))),
        "readable_paragraphs": int("\n\n" in text),
        "question_cta": int(text.rstrip().endswith("?")),
        "platform_length": int(len(text) <= 280),
    }


def paired_comparison(rows):
    pairs = [(rows[i], rows[i+1]) for i in range(0, len(rows)-1, 2)]
    return dict(pairs=len(pairs),
        changed_strategies=sum(a["strategy"] != b["strategy"] for a, b in pairs),
        changed_outputs=sum(a["final"] != b["final"] for a, b in pairs),
        learning_quality_delta=sum(sum(b["after"].values())-sum(a["after"].values())
                                   for a, b in pairs)/len(pairs) if pairs else None,
        interpretation="Changed output shows sensitivity to supplied memory, not engagement uplift.")


def evaluate_recorded(output_path=None):
    """Reproduce measured scores from saved actual Mesh outputs; never calls a model."""
    source = Path(__file__).parent / "docs/evaluation-live.json"
    raw = source.read_bytes()
    dataset = json.loads(raw)
    if dataset.get("mode") != "live_mesh" or not dataset.get("rows"):
        raise ValueError("A nonempty recorded live Mesh dataset is required")
    rows = []
    for row in dataset["rows"]:
        if not row.get("initial") or not row.get("final"):
            raise ValueError("Recorded case is missing actual before/after text")
        rows.append(dict(row, before=score(row["initial"]), after=score(row["final"])))
    before = [sum(r["before"].values()) for r in rows]
    after = [sum(r["after"].values()) for r in rows]
    result = dict(mode="recorded_live_rescore", source="docs/evaluation-live.json",
        source_sha256=hashlib.sha256(raw).hexdigest(), generated_at=dataset["measured_at"],
        rescored_at=datetime.now(timezone.utc).isoformat(), n=len(rows),
        mean_before=sum(before)/len(rows), mean_after=sum(after)/len(rows),
        improved=sum(b>a for a,b in zip(before,after)),
        unchanged=sum(b==a for a,b in zip(before,after)),
        regressed=sum(b<a for a,b in zip(before,after)),
        revision_rate=sum(r["initial"] != r["final"] for r in rows)/len(rows),
        memory_comparison=paired_comparison(rows),
        limitations="Historical real outputs, not a new live run or validation of later code changes. "
        "The v1 heuristic favors numbered lists and uses a strict 280-character ceiling across platforms; "
        "it cannot measure factuality, nuanced brand voice or engagement uplift. No credits spent rescoring.", rows=rows)
    Path(output_path or source.parent / "evaluation-recorded.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "rows"}, indent=2))
    return result


def evaluate(live=False, approve_paid=False, cases=2, images=False):
    if live and (not approve_paid or os.getenv("MESH_ENABLE_PAID", "0") != "1"):
        raise SystemExit("Live evaluation is locked. Explicit approval requires --approve-paid AND MESH_ENABLE_PAID=1.")
    if not 1 <= cases <= 8:
        raise SystemExit("--cases must be between 1 and 8")
    if live:
        mesh = Mesh()
    else:
        from tests.test_studio import ScriptedMesh
        mesh = ScriptedMesh()
    rows = []
    for brand, samples in {
        "Brew": ["coffee is a daily ritual. Keep it warm, playful and practical.",
                 "Brew a better day with small steps and a curious question.",
                 "Your next coffee break is a chance to learn something new."],
        "Lab": ["Research requires evidence. Describe uncertainty before making claims.",
                "Review the findings, then record the limitations with precision.",
                "Practical safety checks require clear accountability and documentation."]
    }.items():
        if live and len(rows) >= cases:
            break
        if live:
            mesh = Mesh()
        voice = learn_voice(mesh, samples)
        for platform in ("x", "linkedin"):
            for learned in (False, True):
                if live and len(rows) >= cases:
                    continue
                memory = [{"id": "simulated-evidence-1", "rule": "Test checklists and a question CTA",
                           "source": "simulated", "confidence": "tentative"}] if learned else []
                trace = []
                def record(agent, detail):
                    trace.append(dict(agent=agent, detail=detail))
                    if live:
                        Path("docs/evaluation-live-trace.json").write_text(json.dumps(dict(
                            brand=brand, platform=platform, learned=learned, trace=trace,
                            completed_rows=rows), indent=2), encoding="utf-8")
                        print(f"{brand}/{platform}/learned={learned}: {agent}", flush=True)
                if live:
                    mesh = Mesh()  # Independent per-run budget; no accumulated client retries.
                result = run_pipeline(mesh, "Practical AI safety for startup founders", platform,
                                      voice, memory, record, generate_image=images if live else True)
                before, after = score(result["drafts"][0]), score(result["drafts"][-1])
                rows.append(dict(brand=brand, platform=platform, learned=learned,
                    before=before, after=after, initial=result["drafts"][0], final=result["text"],
                    strategy=result["strategy"], reviews=result["reviews"], voice=voice,
                    visual_prompt=(result["visual"] or {}).get("prompt"), image_generated=bool(result["image"])))
                print(f"Completed {len(rows)}/8: {brand}, {platform}, learned={learned}", flush=True)
                if live:
                    Path("docs/evaluation-live-progress.json").write_text(
                        json.dumps(dict(mode="live_mesh_partial", rows=rows), indent=2), encoding="utf-8")
    n = len(rows)
    result = dict(mode="live_mesh" if live else "deterministic_test_double", n=n,
        text_model=routes() if live else "scripted_fixture",
        image_model=(os.getenv("MESH_IMAGE_MODEL", "openai/gpt-image-1") if images else "skipped") if live else "scripted_fixture",
        measured_at=datetime.now(timezone.utc).isoformat(),
        rubric="Five binary checks; platform_length uses strict 280-char limit for comparability",
        limitations="Offline outputs are scripted contract fixtures, not evidence of model quality or engagement uplift. "
                     "Heuristic scores do not establish truthfulness or voice quality. Live scores are also small-sample self-evaluations.",
        mean_before=sum(sum(r["before"].values()) for r in rows)/n,
        mean_after=sum(sum(r["after"].values()) for r in rows)/n,
        memory_comparison=paired_comparison(rows),
        revision_rate=sum(r["initial"] != r["final"] for r in rows)/n, rows=rows)
    target = Path("docs/evaluation-live-new.json" if live else "docs/evaluation-offline.json")
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Makes paid Mesh text and image calls")
    parser.add_argument("--approve-paid", action="store_true", help="Explicitly authorize the requested live run")
    parser.add_argument("--cases", type=int, default=2, help="Live cases, 1-8; defaults to one pair")
    parser.add_argument("--images", action="store_true", help="Also spend credits generating matching images")
    parser.add_argument("--fixtures", action="store_true", help="Run scripted contract fixtures instead of scoring recorded real outputs")
    args = parser.parse_args()
    if args.live and args.fixtures:
        parser.error("Choose either --live or --fixtures")
    if args.live or args.fixtures:
        evaluate(args.live, args.approve_paid, args.cases, args.images)
    else:
        evaluate_recorded()
