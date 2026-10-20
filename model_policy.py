"""Explicit economical Mesh routes; no automatic model escalation or extra calls."""
import os

AGENTS = {
    "Brand analyst": ("MESH_BRAND_MODEL", "openai/gpt-4.1-mini", 1400),
    "Strategist": ("MESH_STRATEGIST_MODEL", "google/gemini-2.5-flash-lite", 700),
    "Writer": ("MESH_WRITER_MODEL", "openai/gpt-4.1-mini", 1600),
    "Editor": ("MESH_EDITOR_MODEL", "openai/gpt-4.1-mini", 900),
    "Verifier": ("MESH_VERIFIER_MODEL", "openai/gpt-4.1-mini", 1000),
    "Follow-up": ("MESH_FOLLOWUP_MODEL", "openai/gpt-4.1-mini", 1000),
    "Visual director": ("MESH_VISUAL_MODEL", "google/gemini-2.5-flash-lite", 400),
    "Learning analyst": ("MESH_LEARNER_MODEL", "google/gemini-2.5-flash-lite", 500),
}


def route(role):
    agent = role.split(":")[0]
    if agent not in AGENTS:
        raise ValueError("Unknown agent role")
    env, default, limit = AGENTS[agent]
    model = os.getenv(env) or os.getenv("MESH_TEXT_MODEL") or default
    if model == "auto":
        raise ValueError("Unrestricted auto-routing is disabled; select an explicit evaluated model for this agent")
    if model.startswith("typesafe/"):
        raise ValueError("Jev requires the Mesh evaluation API; it cannot replace a prose agent")
    cap = int(os.getenv("MESH_MAX_OUTPUT_TOKENS", "1600"))
    if cap < 1:
        raise ValueError("Output token cap must be positive")
    return dict(agent=agent, model=model, max_tokens=min(limit, cap))


def routes():
    return {agent: route(agent) for agent in AGENTS}


def image_model():
    return os.getenv("MESH_IMAGE_MODEL") or "openai/gpt-image-1-mini"
