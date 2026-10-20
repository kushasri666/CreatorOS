"""Versioned editorial proxies, not factuality or engagement predictions. Stdlib only."""
import re

VERSION = "platform-editorial-v2"
# Evaluation policies, deliberately conservative; not provider entitlement limits.
POLICIES = {
    "x": (280, 45, 35), "threads": (500, 70, 40),
    "linkedin": (3000, 90, 40), "instagram": (2200, 90, 40),
    "telegram": (4096, 90, 40), "youtube": (5000, 90, 40),
}


def words(value):
    return re.findall(r"\b[\w'-]+\b", value.lower())


def score(draft, platform, requirements):
    if platform not in POLICIES:
        raise ValueError("Unknown platform")
    text = draft.get("text", "")
    slides = draft.get("slides", [])
    if not isinstance(text, str) or not isinstance(slides, list) or any(not isinstance(s, str) for s in slides):
        raise ValueError("Text and slide strings required")
    limit, paragraph_limit, sentence_limit = POLICIES[platform]
    content = "\n".join([text] + slides)
    tokens = set(words(content))
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences = [s for s in re.split(r"[.!?]+", content) if s.strip()]
    hook = (slides[0] if slides else text.splitlines()[0] if text else "").strip()
    checks = {}
    def check(name, passed, reason):
        checks[name] = {"passed": bool(passed) and bool(text.strip()), "reason": reason}
    check("length", len(text) <= limit, f"{len(text)} characters; editorial budget {limit}")
    check("readability", bool(sentences) and all(len(words(p)) <= paragraph_limit for p in paragraphs)
          and all(len(words(s)) <= sentence_limit for s in sentences),
          f"Paragraph budget {paragraph_limit} words; sentence budget {sentence_limit} words")
    check("hook", 4 <= len(words(hook)) <= 30, f"Opening has {len(words(hook))} words; target 4–30")
    groups = requirements.get("concepts", [])
    covered = [any(set(words(term)) <= tokens for term in group) for group in groups]
    check("brief_coverage", bool(groups) and all(covered), f"{sum(covered)}/{len(groups)} required concept groups found (lexical only)")
    cta = requirements.get("cta_terms", [])
    ending = " ".join((text[-300:], slides[-1] if slides else "")).lower()
    check("cta", bool(cta) and any(term.lower() in ending for term in cta), "Configured CTA cue in closing text/slide; intent not semantically verified")
    vocabulary = requirements.get("voice_terms", [])
    if vocabulary:
        check("voice_cues", any(set(words(term)) <= tokens for term in vocabulary), "At least one configured brand vocabulary cue; not a full voice judgment")
    if platform == "instagram" and requirements.get("slide_count"):
        count = requirements["slide_count"]
        normalized = [" ".join(words(s)) for s in slides]
        check("carousel_structure", len(slides) == count and all(1 <= len(words(s)) <= 35 for s in slides)
              and len(set(normalized)) == len(slides), f"Exactly {count} distinct nonempty slides, each <=35 words; semantic duplication not detected")
    if platform == "youtube" and requirements.get("format") == "short_script":
        check("script_format", 40 <= len(words(text)) <= 160 and bool(re.search(r"\[(?:visual|scene|shot)[^\]]*\]", text, re.I)),
              "Short-script editorial target 40–160 spoken/cue words and explicit visual direction; not measured duration")
    passed = sum(v["passed"] for v in checks.values())
    return {"passed": passed, "total": len(checks), "score_100": round(100 * passed / len(checks), 3), "checks": checks}
