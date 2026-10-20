"""Native editorial formats, not claims about provider publishing permissions."""
from content_quality import POLICIES

FORMATS = {
    "linkedin": dict(format="professional_post", structure="Specific professional insight, short paragraphs, practical takeaway, one relevant discussion CTA", avoid="Do not copy a carousel caption or use generic motivational filler"),
    "instagram": dict(format="carousel", structure="Separate caption plus 3–10 short slides: opening, one distinct idea per slide, closing action. Preserve every promised tip", avoid="Do not squeeze multiple promised tips onto one slide or put the entire caption on a slide"),
    "youtube": dict(format="short_script", structure="A spoken hook, concise narration, explicit [Visual: ...] or [Shot: ...] cues, payoff and a relevant closing action. Target 40–160 script/cue words", avoid="Do not return an essay or caption; do not claim a measured duration from word count"),
    "telegram": dict(format="channel_digest", structure="Useful self-contained update, scannable sections or bullets, actionable closing. Include a link only when supplied evidence contains it", avoid="Do not invent URLs or reproduce platform-specific hashtags mechanically"),
    "threads": dict(format="conversation_post", structure="One clear conversational observation, compact supporting detail, optional relevant question", avoid="Do not copy LinkedIn formatting or claim a multi-post thread was published"),
    "x": dict(format="short_post", structure="One specific insight and concise relevant action/question, preferably within 240 characters", avoid="Do not truncate essential claims or citations to force a longer caption into this format"),
}


def format_contract(platform):
    return dict(FORMATS[platform], platform=platform, editorial_character_budget=POLICIES[platform][0],
        preservation="Keep the same idea, product facts and brand voice; adapt the structure and wording, not just the platform label")
