"""Reduce duplicate context, not brand rules or publishable content."""
import copy
import json

VERSION = "lean-v1"


def compact_data(role, data):
    result = copy.deepcopy(data)
    if role.startswith("Brand analyst"):
        return result  # Every historical sample is needed for voice inference.
    if isinstance(result.get("voice"), dict):
        result["voice"] = {k: v for k, v in result["voice"].items()
                           if k in ("tone", "vocabulary", "structure", "cta_habits", "avoid")}
    if "learnings" in result:
        result["learnings"] = [{k: item[k] for k in ("id", "rule", "reason", "source", "confidence") if k in item}
                               for item in result["learnings"]]
    if "limits" in result:
        result["limits"] = {result["platform"]: result["limits"][result["platform"]]}
    if role.startswith(("Editor", "Visual director")):
        result.pop("learnings", None)  # Strategist already selected the hypothesis.
    if role.startswith("Visual director"):
        result.pop("limits", None)
    return result


def encode(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
