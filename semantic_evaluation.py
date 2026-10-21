"""Fixed semantic verifier challenge scoring; no model or network calls.

The caller obtains real Mesh replies and passes them through the production
validator. Gold labels are used only here, never in ``model_input``. This small
synthetic, exact-candidate test does not estimate real social-platform success
or general-purpose factual accuracy.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


CASES = Path(__file__).parent / "evals" / "semantic" / "cases.json"
LABELS = {"supported", "unsupported", "nonfactual"}


def load_cases(path=CASES):
    dataset = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = dataset["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("Semantic challenge must contain cases")
    seen = set()
    for case in cases:
        if not isinstance(case.get("id"), str) or case["id"] in seen:
            raise ValueError("Semantic case IDs must be unique strings")
        seen.add(case["id"])
        parts = [case["draft"], *case.get("slides", [])]
        source_ids = {s["source_id"] for s in case["sources"]}
        if len(source_ids) != len(case["sources"]):
            raise ValueError("Source IDs must be unique within a case")
        claims = set()
        for gold in case["gold"]:
            claim = gold["claim"]
            if claim in claims or not claim or not any(claim in p for p in parts):
                raise ValueError("Gold claims must be unique exact draft passages")
            claims.add(claim)
            if gold["label"] not in LABELS:
                raise ValueError("Unknown semantic gold label")
            if not set(gold.get("source_ids", [])).issubset(source_ids):
                raise ValueError("Unknown gold source")
            if gold["label"] == "supported" and not gold.get("source_ids"):
                raise ValueError("Supported gold needs a source")
        factual = [g for g in case["gold"] if g["label"] != "nonfactual"]
        if not factual or case["expected_pass"] != all(g["label"] == "supported" for g in factual):
            raise ValueError("Case approval label must match the factual labels")
        for citation in case.get("citations", []):
            if citation["claim"] not in claims or not set(citation["source_ids"]).issubset(source_ids):
                raise ValueError("Writer citations must refer to annotated candidates and real sources")
        if any(any(decoy in p for p in parts) for decoy in case.get("absent_decoys", [])):
            raise ValueError("Absent-claim decoy must actually be absent")
    return cases


def model_input(case):
    """Export only ordinary production verifier inputs, with no gold or tags."""
    return copy.deepcopy(dict(draft=case["draft"], slides=case.get("slides", []),
        writer_citations=case.get("citations", []), sources=case["sources"]))


def validate_predictions(cases, raw_predictions):
    """Apply the actual production source-receipt validator to model replies.

    ``raw_predictions`` maps case ID to the resolved reply returned by
    ``Mesh.ask('Verifier: ...', model_input(case))``. Missing cases remain
    missing and count against factual coverage. Exceptions are recorded as
    invalid output rather than scored as correct abstention.
    """
    from workflow import _validate_verifier_result
    from source_policy import validate_semantic_conflicts, review_sources, blocking_conflicts
    expected = {c["id"] for c in cases}
    if set(raw_predictions) - expected:
        raise ValueError("Predictions contain an unknown semantic case ID")
    validated = {}
    for case in cases:
        if case["id"] not in raw_predictions:
            continue
        try:
            raw = raw_predictions[case["id"]]
            result = _validate_verifier_result(
                raw, case["draft"], case.get("slides", []),
                case.get("citations", []), case["sources"])
            # Mirror the pipeline's full verifier stage, including semantic and
            # deterministic contradictions. A real quote is never entailment.
            conflicts, error = validate_semantic_conflicts(
                raw.get("conflicts", []) if isinstance(raw, dict) else [], case["sources"])
            review = review_sources(case["sources"], conflicts)
            if error:
                result.update(status="invalid_conflict_output", passed=False, reason=error)
            for check in result["checks"]:
                affected = blocking_conflicts(check["claim"], check["source_ids"], review["conflicts"])
                if affected and check["verdict"] == "supported":
                    check.update(verdict="thin", reason="Unqualified claim relies on unresolved contradictory sources: " + ", ".join(affected))
                    result.update(passed=False, reason="Disputed source claims require more evidence or explicit attribution.")
            result["conflicts"] = review["conflicts"]
            validated[case["id"]] = result
        except (TypeError, ValueError, KeyError, AttributeError):
            validated[case["id"]] = dict(status="invalid_verifier_output", passed=False,
                checks=[], reason="Production verifier validation rejected the reply.")
    return validated


def ratio(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                value=round(numerator / denominator, 6) if denominator else None)


def score_case(case, prediction):
    """Score exact, manually annotated candidates without a second AI judge.

    A larger or overlapping check is not silently treated as correct for an
    unassessed smaller gold candidate. Such checks are reported as unscored;
    supported unscored checks lower conservative support precision. Thin and
    unsupported both count as withholding an unsupported claim. Missing checks
    do not count as correct withholding, even when the overall post is held.
    """
    valid = isinstance(prediction, dict) and isinstance(prediction.get("checks"), list)
    checks = prediction["checks"] if valid else []
    by_claim = {}
    for check in checks:
        if isinstance(check, dict) and isinstance(check.get("claim"), str):
            by_claim.setdefault(check["claim"], []).append(check)
    gold_by_claim = {g["claim"]: g for g in case["gold"]}
    counts = dict(factual_assertions=0, supported_gold=0, unsupported_gold=0,
        true_support=0, false_support=0, wrong_source_support=0,
        correct_withholding=0, missed_factual_assertions=0,
        supported_predictions=0, unscored_supported_checks=0,
        unscored_checks=0, absent_claim_checks=0, nonfactual_rejections=0)
    decisions = []
    for gold in case["gold"]:
        candidates = by_claim.get(gold["claim"], [])
        # Production normally merges exact duplicate checks. Keeping the worst
        # verdict here prevents a contradictory later row from hiding rejection.
        severity = {"supported": 0, "thin": 1, "unsupported": 2}
        check = max(candidates, key=lambda c: severity.get(c.get("verdict"), 3)) if candidates else None
        observed = check.get("verdict", "invalid") if check else "missing"
        # The production guard safely inserts rejection rows for omitted author
        # citations and numerical assertions. Those are useful safety holds but
        # must not receive credit as actual model claim detection or decisions.
        inserted_reason = check.get("reason", "") if check else ""
        if inserted_reason in (
                "Verifier did not assess this writer-cited claim.",
                "Numeric factual assertion was not covered by a supported exact verifier passage."):
            observed = "missing"
        ids = set(check.get("source_ids", [])) if check and isinstance(check.get("source_ids"), list) else set()
        label = gold["label"]
        if label == "nonfactual":
            rejected = observed not in ("missing", "supported")
            counts["nonfactual_rejections"] += int(rejected)
            correct = not rejected
        else:
            counts["factual_assertions"] += 1
            counts["supported_gold" if label == "supported" else "unsupported_gold"] += 1
            counts["missed_factual_assertions"] += int(observed == "missing")
            if observed == "supported":
                counts["supported_predictions"] += 1
            if label == "supported":
                correct = observed == "supported" and set(gold["source_ids"]).issubset(ids)
                counts["true_support"] += int(correct)
                counts["wrong_source_support"] += int(observed == "supported" and not correct)
            else:
                correct = observed in ("thin", "unsupported")
                counts["correct_withholding"] += int(correct)
                counts["false_support"] += int(observed == "supported")
        decisions.append(dict(claim=gold["claim"], gold=label, observed=observed,
                              correct=correct, observed_source_ids=sorted(ids)))
    parts = [case["draft"], *case.get("slides", [])]
    unscored = []
    for claim, matching in by_claim.items():
        if not any(claim and claim in p for p in parts):
            counts["absent_claim_checks"] += 1
        if claim not in gold_by_claim:
            counts["unscored_checks"] += 1
            supported = any(c.get("verdict") == "supported" for c in matching)
            counts["unscored_supported_checks"] += int(supported)
            unscored.append(dict(claim=claim, supported=supported))
    approved = valid and prediction.get("passed") is True
    return dict(id=case["id"], category=case["category"], counts=counts,
        expected_pass=case["expected_pass"], actual_pass=approved,
        case_false_approval=approved and not case["expected_pass"],
        case_false_rejection=not approved and case["expected_pass"],
        invalid_or_missing=not valid or str(prediction.get("status", "")).startswith("invalid_") or (
            prediction.get('coverage_required') is True and prediction.get('coverage_passed') is False),
        decisions=decisions, unscored=unscored)


def evaluate(cases, predictions):
    """Score a mapping of case IDs to actual production-validated outputs."""
    expected = {c["id"] for c in cases}
    if set(predictions) - expected:
        raise ValueError("Predictions contain an unknown semantic case ID")
    rows = [score_case(case, predictions.get(case["id"])) for case in cases]
    counts = {key: sum(row["counts"][key] for row in rows) for key in rows[0]["counts"]}
    true_support = counts["true_support"]
    correctly_decided = true_support + counts["correct_withholding"]
    return dict(case_count=len(rows), counts=counts,
        metrics=dict(
            supported_precision=ratio(true_support,
                counts["supported_predictions"] + counts["unscored_supported_checks"]),
            supported_recall=ratio(true_support, counts["supported_gold"]),
            unsupported_withholding_recall=ratio(counts["correct_withholding"], counts["unsupported_gold"]),
            factual_decision_accuracy=ratio(correctly_decided, counts["factual_assertions"]),
            factual_detection_coverage=ratio(counts["factual_assertions"] - counts["missed_factual_assertions"], counts["factual_assertions"]),
            false_approval_rate=ratio(counts["false_support"], counts["unsupported_gold"]),
            case_false_approval_rate=ratio(sum(r["case_false_approval"] for r in rows), sum(not r["expected_pass"] for r in rows))),
        case_false_approvals=sum(r["case_false_approval"] for r in rows),
        case_false_rejections=sum(r["case_false_rejection"] for r in rows),
        false_claim_approvals=counts["false_support"],
        missed_factual_assertions=counts["missed_factual_assertions"],
        invalid_or_missing_cases=sum(r["invalid_or_missing"] for r in rows), cases=rows)


def evaluate_named(named_predictions, cases=None):
    """Compare any named phases, for example ``before`` and ``after``."""
    cases = load_cases() if cases is None else cases
    if not isinstance(named_predictions, dict) or not named_predictions:
        raise ValueError("At least one named prediction phase is required")
    fingerprints = json.dumps(cases, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return dict(schema_version="semantic-verifier-evaluation-v1",
        dataset_id="creatoros-semantic-verifier-challenge-v1",
        dataset_sha256=hashlib.sha256(fingerprints.encode()).hexdigest(),
        scope="12 synthetic product-copy challenges; exact candidate annotations, not live platform or customer success.",
        limitations=["Small manually annotated test set, not a representative population estimate.",
            "Exact-candidate matching exposes omissions but can under-credit overlapping legitimate wording.",
            "Verbatim receipts alone do not establish semantic entailment; gold labels are separate from the validator.",
            "No model or network requests are made by this scorer; inference costs belong to the calling validation ledger.",
            "Any after phase informed by failures is a retrospective regression result, not held-out generalization."],
        phases={name: evaluate(cases, predictions) for name, predictions in named_predictions.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path,
                        help="JSON mapping phase names to case-ID production-validated results")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_named(json.loads(args.predictions.read_text(encoding="utf-8")))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
