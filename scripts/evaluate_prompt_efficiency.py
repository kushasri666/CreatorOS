"""Offline token accounting on clearly labeled synthetic contexts; no AI calls."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prompt_policy import compact_data, encode
from demo import SCENARIOS


def evaluate():
    import tiktoken
    encoder = tiktoken.get_encoding("cl100k_base")
    rows = []
    for name, sample in SCENARIOS.items():
        context = dict(brief=sample["brief"], platform=sample["platform"],
            voice=dict(tone="Warm and clear", vocabulary=["practical", "useful"], structure="Short steps",
                cta_habits="Ask a specific question", avoid=["Unsupported claims"], evidence=sample["samples"]),
            learnings=[dict(id=f"example-{i}", rule="Test a practical story opening", reason="Tentative observation; not causal",
                source="simulated", confidence="tentative", post_id=f"post-{i}", evidence_id=f"metric-{i}",
                rate=.05, baseline=.03, observed_at="2026-10-20T00:00:00Z") for i in range(4)],
            limits={"instagram": 2200, "linkedin": 3000, "x": 280},
            previous_draft="Complete existing draft: " + sample["brief"], editor_feedback={"edits": ["Make the CTA specific"]})
        for role in ("Strategist", "Writer", "Editor", "Visual director"):
            before = len(encoder.encode(json.dumps(context)))
            after_data = compact_data(role, context)
            after = len(encoder.encode(encode(after_data)))
            assert after_data["previous_draft"] == context["previous_draft"]
            assert after_data["voice"]["avoid"] == context["voice"]["avoid"]
            rows.append(dict(scenario=name, role=role, before_input_tokens=before,
                after_input_tokens=after, reduction_percent=round(100*(before-after)/before, 2)))
    result = dict(method="Synthetic payload serialization/context benchmark, cl100k_base; excludes system prompts and output tokens",
        paid_calls=0, cases=rows, before=sum(r["before_input_tokens"] for r in rows),
        after=sum(r["after_input_tokens"] for r in rows),
        limitations="Not a live quality evaluation, actual provider billing measurement, or proof that content quality is unchanged.")
    Path("docs/prompt-efficiency.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("paid_calls", "before", "after", "limitations")}))


if __name__ == "__main__":
    evaluate()
