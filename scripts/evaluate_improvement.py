"""Reproduce outer-loop routing measurements using labeled scripted fixtures only."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_improvement import TrajectoryGateway
from workflow import run_pipeline


def evaluate():
    rows = []
    for name, scores in [("normal_revision", [8, 9]), ("recoverable_regression", [6, 5, 9]),
                         ("unrecoverable", [5, 5, 4]), ("improving_but_insufficient", [5, 6, 7])]:
        gateway = TrajectoryGateway(scores)
        result = run_pipeline(gateway, "Useful habits", "linkedin", {"tone": "precise"},
                              [{"id": "evidence-1", "rule": "Test a checklist"}], lambda *_: None)
        rows.append(dict(case=name, scripted_scores=scores, approved=result["approved"],
            actions=[a["action"] for a in result["assessments"]], calls=len(gateway.calls),
            strategy_restarts=gateway.strategies-1, selected_version=result["selected_draft_index"]+1,
            image_generated=bool(result["image"])))
    report = dict(mode="scripted_contract_fixtures", paid_calls=0, cases=rows,
        limitations="Measures routing and call bounds only. No live model quality, calibrated confidence, factual verification or engagement uplift measured.")
    Path("docs/evaluation-improvement.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    evaluate()
