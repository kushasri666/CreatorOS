"""Cheap observable feedback for writers; never substitutes for source verification."""
import re
from content_quality import POLICIES, words

VERSION = "editorial-guidance-v1"
TARGET_AVERAGE = 9.1
MINIMUM_CRITERION = 8


def contract(platform):
    limit, paragraph, sentence = POLICIES[platform]
    return dict(policy=VERSION, target_editor_average=TARGET_AVERAGE,
        minimum_editor_criterion=MINIMUM_CRITERION, max_characters=limit,
        preferred_characters=240 if platform=="x" else 450 if platform=="threads" else limit,
        max_paragraph_words=paragraph, max_sentence_words=sentence, hook_words=[4, 30],
        requirements=[
            "Preserve the brief's actual topic, named product and requested audience; brand metaphors must not replace them.",
            "Use a concrete 4–30 word opening and short paragraphs; do not pad short posts into numbered lists.",
            "End with one relevant low-friction action or question, following the brand CTA habits.",
            "Use brand voice naturally; do not stuff vocabulary or invent facts to satisfy a score.",
            "Resolve concrete editor and local-check feedback while preserving successful parts of the draft.",
            "For carousels preserve each promised tip, one idea per short distinct slide. For video include visual direction.",
            "Aspirational editor scores are not independent quality measurements; never inflate scores to reach a target."])


def inspect(text, slides, platform):
    limit, paragraph, sentence = POLICIES[platform]
    opening = slides[0] if slides else text.splitlines()[0] if text else ""
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    normalized = [" ".join(words(s)) for s in slides]
    checks = {
        "length": (bool(text.strip()) and len(text) <= limit, f"{len(text)}/{limit} characters; shorten without dropping essential meaning"),
        "hook": (4 <= len(words(opening)) <= 30, "Use a concise opening with a concrete audience problem or benefit (4–30 words)"),
        "readability": (bool(sentences) and all(len(words(s)) <= sentence for s in sentences)
            and all(len(words(p)) <= paragraph for p in paragraphs), f"Split sentences above {sentence} words and paragraphs above {paragraph} words"),
    }
    if platform == "instagram":
        checks["carousel"] = (3 <= len(slides) <= 10 and all(0 < len(words(s)) <= 35 for s in slides)
            and len(set(normalized)) == len(slides), "Use 3–10 distinct slides, one idea per slide, each at most 35 words")
    return dict(policy=VERSION, checks={k: bool(v[0]) for k,v in checks.items()},
        issues=[dict(check=k, instruction=v[1]) for k,v in checks.items() if not v[0]],
        limitations="Local style checks only; no claim of factuality, voice fidelity, semantic completeness or engagement.")


def regressions(previous, current):
    return [key for key, passed in previous["checks"].items() if passed and not current["checks"].get(key, False)]
