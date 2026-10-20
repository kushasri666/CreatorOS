"""Deterministic interface fixtures for development. No model or network calls.

This is deliberately not an AI substitute. Every generated record carries offline_fixture mode.
"""
import re


class OfflineGateway:
    mode = "offline_fixture"

    def ask(self, role, data):
        if role.startswith("Brand analyst"):
            samples = data["samples"]
            casual = any(re.search(r"[☕💛😊!]|\b(cozy|cosy|friend|brew|hey)\b", s, re.I) for s in samples)
            return dict(tone="Warm and playful" if casual else "Clear and precise",
                vocabulary=list(dict.fromkeys(re.findall(r"\b[a-zA-Z]{5,}\b", " ".join(samples))))[:10],
                structure="Short sentences with practical steps", cta_habits="Ask a friendly question" if casual else "Invite a concrete next step",
                avoid=["Unsupported claims", "Invented statistics"], evidence=samples[:3],
                method="Offline deterministic fixture: simple sample cues, not learned AI analysis")
        if role.startswith("Strategist"):
            memory = data["learnings"]
            return dict(angle="Practical mistakes to avoid" if memory else "Small, useful habits",
                hook=f"A better approach to {data['brief'].rstrip('.')} starts with one small change.",
                audience="People exploring " + data["brief"], format="carousel" if data["platform"] == "instagram" else "practical post",
                cta="Save the checklist and share your experience", reason="Testing this stored hypothesis: " + memory[0]["rule"] if memory else
                "Start with an actionable explanation; no performance evidence applied yet.",
                applied_learning_ids=[l["id"] for l in memory])
        if role.startswith("Writer"):
            revised = data["previous_draft"] is not None
            friendly = "playful" in str(data["voice"].get("tone", "")).lower()
            topic = data["brief"].rstrip('.')
            coffee = "coffee" in topic.lower()
            tips = ["Grind fresh beans just before brewing.", "Use filtered water just off the boil.",
                    "Froth warm milk for a silky finish.", "Try a little cinnamon before adding syrup.",
                    "Warm your mug so the last sip stays cosy."] if coffee else [
                    "Choose one useful outcome.", "Break it into small steps.", "Try a low-risk example.",
                    "Check what changed.", "Keep what works and adjust the rest."]
            hook = ("Your home coffee deserves a little café magic. ☕" if friendly and coffee else
                    f"Make {topic[:110]} practical in five steps.") if revised else topic
            if data["platform"] == "x":
                text = (f"{topic[:70]}: choose one goal, test a small change, then review the outcome. "
                        + ("Avoid repeating an unchecked assumption. " if data["learnings"] else "")
                        + ("What's your next small win?" if friendly else "What would you test first?")) if revised else f"{topic[:160]}. A useful idea to explore."
                return {"text": text, "slides": []}
            text = hook + "\n\n" + "\n".join(f"{i+1}. {s}" for i,s in enumerate(tips))
            if revised and data["learnings"]:
                text += "\n\nMistake to avoid: changing everything at once. Test one thing and keep a note."
            text += ("\n\nSave this for tomorrow. Which tip will you try first?" if friendly else
                     "\n\nUse this checklist, then document what changed. What will you test first?") if revised else "\n\nFollow for more."
            slides = [hook, *tips, "Save the checklist. What will you try first?"] if data["platform"] == "instagram" else []
            return dict(text=text, slides=slides)
        if role.startswith("Editor"):
            revised = data["draft"].endswith("?")
            return dict(scores={k: (8.6 if revised else 6.4) for k in ("hook", "clarity", "voice", "platform", "cta")},
                edits=["Replace the generic opening with a specific, audience-facing hook.",
                       "Keep one practical idea per carousel slide.", "End with one specific question or save CTA."],
                reason="Scripted offline scorecard used to exercise revision routing, not an AI judgment.")
        if role.startswith("Visual director"):
            return dict(prompt="Editorial visual illustrating " + data["brief"] + "; warm lighting, clear focal point, no text.",
                        reason="Matches the topic; offline mode displays a labeled vector placeholder.")
        if role.startswith("Learning analyst"):
            direction = data["direction"]
            rule = "Test an actionable checklist and one mistake to avoid."
            if direction == "avoid_or_test":
                rule = "Change the opening angle and test a more concrete checklist before repeating this format."
            return dict(rule=rule, reason=f"Offline hypothesis fixture. Direction: {direction}; "
                        f"weighted rate {data['rate']:.3f}, baseline {data['baseline']}. No causal claim.")
        raise ValueError("Unknown offline agent")

    def image(self, prompt):
        return "/static/fixture.svg"
