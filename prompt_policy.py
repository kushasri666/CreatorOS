"""Reduce duplicate context, not brand rules or publishable content."""
import copy
import json

VERSION = "lean-v4-native-formats"


def compact_data(role, data):
    result = copy.deepcopy(data)
    if role.startswith("Verifier") and isinstance(result.get("sources"),list):
        # One canonical source packet, with exact excerpts intact. Voice, prior
        # chat and copied research findings are not additional factual evidence.
        result.pop("voice",None);result.pop("learnings",None);result.pop("history",None);result.pop("limits",None)
        result.pop("editorial_contract",None);result.pop("local_checks",None)
        result.pop("format_contract",None)
        if isinstance(result.get("research"),dict):result["research"].pop("findings",None)
        result["sources"]=[{k:s[k] for k in ("source_id","source_ids","excerpt","claim","title","source_type","quality","url","account_id","window","collected_at") if k in s} for s in result["sources"]]
    if role.startswith("Brand analyst"):
        return result  # Every historical sample is needed for voice inference.
    if isinstance(result.get("voice"), dict):
        result["voice"] = {k: v for k, v in result["voice"].items()
                           if k in ("tone", "vocabulary", "structure", "cta_habits", "avoid")}
    if "learnings" in result:
        result["learnings"] = [{k: item[k] for k in ("id", "rule", "reason", "source", "confidence", "memory", "experiment") if k in item}
                               for item in result["learnings"]]
        for item in result["learnings"]:
            if "memory" in item:
                item["memory"]={k:item["memory"][k] for k in ("status","version","policy") if k in item["memory"]}
    if "limits" in result:
        result["limits"] = {result["platform"]: result["limits"][result["platform"]]}
    if role.startswith(("Editor", "Visual director")):
        result.pop("learnings", None)  # Strategist already selected the hypothesis.
    if role.startswith("Visual director"):
        result.pop("limits", None)
        result.pop("editorial_contract", None)
        result.pop("format_contract", None)
    return result


def encode(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
