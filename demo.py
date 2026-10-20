"""Optional fictional scenarios. Never loaded automatically; never use Mesh credits."""
from datetime import datetime, timedelta, timezone
from offline import OfflineGateway
from workflow import learn_voice
import storage

SCENARIOS = {
    "coffee": dict(name="Brew Lab Coffee", brief="5 ways to make café-style coffee at home", platform="instagram",
        samples=["Hey, home brewer! ☕ A fresh grind makes the kitchen smell like your favourite café. What are you brewing?",
                 "Cosy mornings start with a warm mug. Take a breath, take a sip, and tell us your little ritual. 💛",
                 "Too bitter? Try a gentler brew. Small changes can make a delicious difference. Save this for tomorrow!",
                 "Our milk-frothing experiment got a little messy. That's how we learn. What would you try next?",
                 "Coffee tastes better with friends. Share your weekend brew and tag your favourite coffee buddy. ☕"]),
    "research": dict(name="NeuralNest AI", brief="Practical AI safety for startup founders", platform="linkedin",
        samples=["Reliable AI requires documented failure cases, measurable criteria, and explicit ownership.",
                 "Before deployment, review the evidence. A strong benchmark does not guarantee safe operation.",
                 "We test assumptions through small experiments and report both findings and limitations.",
                 "A rollback plan is part of the release, not an afterthought. Assign responsibility before launch.",
                 "Good engineering records uncertainty and invites a precise question. What evidence would change your decision?"]),
    "education": dict(name="LearnWithAI", brief="Explain retrieval augmented generation in simple steps", platform="linkedin",
        samples=["Let's learn one idea at a time! Start with a question, try an example, then explain it to a friend.",
                 "Hey, curious minds! A tiny practice session beats a pile of unread notes. What did you try today?",
                 "Confusing words? Swap them for a concrete example. Save this little lesson for your next study break!",
                 "Your first explanation doesn't need to be perfect. Make it useful, then make it clearer.",
                 "Try teaching a concept to a friend. Their questions show you what to learn next!"])
}


def seed(scenario):
    spec = SCENARIOS[scenario]
    id = "demo:" + scenario
    existing = storage.get(id)
    if existing:
        return dict(brand=existing, brief=spec["brief"], platform=spec["platform"])
    client = OfflineGateway()
    brand = storage.save("brand", dict(kind="brand", name=spec["name"], samples=spec["samples"],
        profile=learn_voice(client, spec["samples"]), version=1, mode="offline_fixture", created_at=storage.now()), id)
    for i, (format, likes, comments, saves) in enumerate([
        ("Question", 640, 52, 88), ("Story", 1120, 96, 310), ("List", 780, 34, 142),
        ("Story", 1340, 118, 362), ("Guide", 690, 41, 120), ("Question", 560, 88, 46)
    ]):
        pid = f"{id}:history:{i}"
        due = (datetime.now(timezone.utc)-timedelta(days=14-i)).replace(hour=5 if i in (1,3) else 12, minute=30).isoformat()
        title = ["A small daily ritual", "An experiment that went wrong", "Six useful starting points",
                 "One mistake to avoid", "A practical guide", "What would you try next?"][i]
        post = storage.save("post", dict(kind="post", brand_id=id, brief=title,
            platform=spec["platform"], text=title + ". Fictional historical content for the offline scenario.",
            strategy=dict(format=format, angle=title, reason="Fictional example for dashboard testing"),
            voice=brand["profile"], voice_version=1, status="ready_to_publish", mode="offline_fixture",
            scheduled_for=due, created_at=due, learning_enabled=False), pid)
        observation = dict(event_id="demo24h", source="simulated", impressions=9000+i*1000,
                           likes=likes, comments=comments, saves=saves, window_hours=24)
        rate = (likes+2*comments+3*saves)/observation["impressions"]
        key = "metric:" + pid + ":demo24h"
        metric = dict(kind="metric", post_id=pid, brand_id=id, platform=spec["platform"],
                      input=observation, rate=rate, baseline=None, observed_at=storage.now())
        learning = dict(kind="learning", brand_id=id, platform=spec["platform"], post_id=pid,
            evidence_id=key, source="simulated", confidence="tentative", direction="explore",
            rule="Test a practical story with one mistake to avoid." if format == "Story" else "Test a concise checklist with a clear question.",
            reason="Fictional historical fixture. Compare normalized rates before adopting any hypothesis.", rate=rate, baseline=None)
        storage.feedback(key, metric, learning)
    return dict(brand=brand, brief=spec["brief"], platform=spec["platform"])
