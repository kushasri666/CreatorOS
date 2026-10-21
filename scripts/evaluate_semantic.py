"""Replay public recorded synthetic Mesh replies with zero model/API calls.

This re-applies the current production verifier and source-conflict policy to
the unchanged before/after/reference replies. The original 16/18 after report
is retained as a separately fingerprinted historical snapshot. Its later 18/18
replay comes from a generic attribution-policy repair, not fresh inference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import semantic_evaluation

PREDICTIONS = ROOT / "evals/semantic/predictions.json"
HOLDOUT_PREDICTIONS = ROOT / "evals/semantic/holdout-predictions.json"
HOLDOUT_CASES = ROOT / "evals/semantic/holdout.json"
HOLDOUT_OUTPUT = ROOT / "docs/evaluation-semantic-holdout.json"
OUTPUT = ROOT / "docs/evaluation-semantic-reproduced.json"
PHASES = ("before", "after", "reference")


def sha256(path):
    """Normalize Git checkout line endings, preserving reproducibility on Windows."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_artifact(artifact, cases):
    if artifact.get("schema_version") != "creatoros-recorded-semantic-predictions-v1":
        raise ValueError("Unknown recorded semantic prediction schema")
    if artifact.get("gold_file_sha256") != sha256(semantic_evaluation.CASES):
        raise ValueError("Frozen semantic gold changed; recorded predictions must not be relabeled")
    if artifact.get("dataset_id") != "creatoros-semantic-verifier-challenge-v1":
        raise ValueError("Recorded replies belong to a different challenge set")
    phases = artifact.get("phases")
    if not isinstance(phases, dict) or set(phases) != set(PHASES):
        raise ValueError("Exactly the recorded before, after and reference phases are required")
    expected = {case["id"] for case in cases}
    for name in PHASES:
        phase = phases[name]
        predictions = phase.get("predictions") if isinstance(phase, dict) else None
        if not isinstance(predictions, dict) or set(predictions) != expected:
            raise ValueError("Every phase must retain every case, including null model failures")
        if not isinstance(phase.get("model"), str) or not isinstance(phase.get("max_output_tokens"), int):
            raise ValueError("Recorded model and token limit are required for each phase")
        if any(result is not None and not isinstance(result, dict) for result in predictions.values()):
            raise ValueError("Recorded model replies must be resolved objects or explicit null failures")


def evaluate_holdout():
    """Replay the separate one-pass holdout without prompts or policy tuning."""
    artifact = json.loads(HOLDOUT_PREDICTIONS.read_text(encoding="utf-8"))
    if artifact.get("schema_version") != "creatoros-recorded-semantic-holdout-predictions-v1":
        raise ValueError("Unknown recorded semantic holdout schema")
    if artifact.get("dataset_id") != "creatoros-semantic-verifier-holdout-v1" or artifact.get("gold_sha256") != sha256(HOLDOUT_CASES):
        raise ValueError("Frozen holdout gold changed; do not relabel or retune after inference")
    cases = semantic_evaluation.load_cases(HOLDOUT_CASES)
    predictions = artifact.get("predictions")
    if not isinstance(predictions, dict) or set(predictions) != {case["id"] for case in cases}:
        raise ValueError("Every holdout case must remain in the denominator")
    results = semantic_evaluation.evaluate(cases, semantic_evaluation.validate_predictions(cases, predictions))
    return dict(dataset_id=artifact["dataset_id"], gold_sha256=artifact["gold_sha256"],
        model=artifact["model"], max_output_tokens=artifact["max_output_tokens"],
        scope="Untouched eight-case synthetic holdout, run once after diagnostic repairs; gold not sent to model.",
        results=results)


def evaluate():
    cases = semantic_evaluation.load_cases()
    artifact = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
    validate_artifact(artifact, cases)
    snapshot = artifact.get("initial_result_snapshot", {})
    # Only this fixed public synthetic report may be read as the historical
    # snapshot. Prediction metadata cannot redirect the evaluator to a secret.
    historical_path = ROOT / "docs/evaluation-semantic-live-initial.json"
    if snapshot.get("path") != "docs/evaluation-semantic-live-initial.json" or snapshot.get("sha256") != sha256(historical_path):
        raise ValueError("The original pre-repair semantic report changed")
    historical = json.loads(historical_path.read_text(encoding="utf-8"))
    current = semantic_evaluation.evaluate_named({name:
        semantic_evaluation.validate_predictions(cases, artifact["phases"][name]["predictions"])
        for name in PHASES}, cases)
    initial = {name: dict(metrics=value["metrics"],
        false_claim_approvals=value["false_claim_approvals"],
        missed_factual_assertions=value["missed_factual_assertions"],
        case_false_rejections=value["case_false_rejections"])
        for name, value in historical["phases"].items()}
    holdout = evaluate_holdout()
    fingerprints = ["evals/semantic/cases.json", "evals/semantic/predictions.json",
        "evals/semantic/holdout.json", "evals/semantic/holdout-predictions.json",
        "semantic_evaluation.py", "workflow.py", "verification_contract.py", "source_policy.py",
        "grounding.py", "scripts/evaluate_semantic.py", "docs/evaluation-semantic-live-initial.json"]
    return dict(schema_version="creatoros-semantic-replay-v1", ai_calls=0, validation_cost_usd=0,
        dataset_id=artifact["dataset_id"], provenance=artifact["provenance"],
        phase_notes=artifact["phase_notes"],
        models={name: dict(model=artifact["phases"][name]["model"],
            max_output_tokens=artifact["phases"][name]["max_output_tokens"]) for name in PHASES},
        historical_initial=dict(source=snapshot["path"], sha256=snapshot["sha256"],
            treatment=snapshot["treatment"], phases=initial),
        current_policy_replay=current,
        untuned_holdout_replay=holdout,
        fingerprints={path: sha256(ROOT / path) for path in fingerprints},
        interpretation="The original economical after result was 16/18. Its 18/18 current-policy replay reuses identical stored model replies after the generic source-attribution repair. This replay adds zero inference calls and must not be reported as a new live model run or held-out improvement.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-recorded", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.check_recorded:
        if not OUTPUT.exists() or json.loads(OUTPUT.read_text(encoding="utf-8")) != result:
            raise SystemExit("Recorded semantic replay differs; review changes before regenerating")
        if not HOLDOUT_OUTPUT.exists() or json.loads(HOLDOUT_OUTPUT.read_text(encoding="utf-8")) != result["untuned_holdout_replay"]:
            raise SystemExit("Recorded holdout differs; preserve the one-pass results including invalid coverage holds")
        print("Semantic before/after/reference and separate eight-case holdout reproduce exactly; zero Mesh calls.")
    else:
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({name: phase["metrics"]["factual_decision_accuracy"]
            for name, phase in result["current_policy_replay"]["phases"].items()}, indent=2))


if __name__ == "__main__":
    main()
