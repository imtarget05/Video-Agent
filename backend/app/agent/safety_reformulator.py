"""
SafetyReformulator: single-pass sanitizer for moderation-blocked prompts.
Runs at most once per project (guarded by reformulated flag / reformulation_count).
"""
from typing import Dict, Any
from backend.app.agent.guardrails import PROHIBITED_KEYWORDS

_REPLACEMENTS = {
    "bomb": "fireworks celebration",
    "kill": "transform",
    "weapon": "tool",
    "blood": "red paint",
    "suicide": "self-improvement journey",
    "terror": "thriller story",
    "porn": "romantic story",
    "nude": "portrait",
    "nsfw": "family-friendly",
    "violence": "action",
    "hate": "friendship",
    "drugs": "medicine",
    "illegal": "creative",
    "exploit": "use",
}


def reformulate_prompt(prompt: str) -> str:
    out = prompt or ""
    lowered = out.lower()
    for kw in PROHIBITED_KEYWORDS:
        if kw in lowered:
            out = _replace_ci(out, kw, _REPLACEMENTS.get(kw, "safe creative topic"))
            lowered = out.lower()
    return out


def _replace_ci(text: str, old: str, new: str) -> str:
    import re
    return re.sub(re.escape(old), new, text, flags=re.IGNORECASE)


def safety_reformulator_node(state) -> Dict[str, Any]:
    """Sanitize topic + scene prompts once; mark reformulated."""
    scenes = []
    for s in state.scenes:
        sc = s.model_copy()
        sc.visual_prompt = reformulate_prompt(s.visual_prompt)
        sc.voiceover_text = reformulate_prompt(s.voiceover_text or "")
        scenes.append(sc)
    original_error = getattr(state, "error_message", None)
    return {
        "topic": reformulate_prompt(state.topic),
        "scenes": scenes,
        "reformulated": True,
        "reformulation_count": int(getattr(state, "reformulation_count", 0) or 0) + 1,
        "error_message": f"Reformulated after block: {original_error}" if original_error else "Reformulated",
    }
