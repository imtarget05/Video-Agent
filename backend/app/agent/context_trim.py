"""WP2 — State trimming for Video-Agent.

Chống State Bloat / Context overflow: chỉ trim bản copy truyền vào LLM/prompt,
KHÔNG ghi đè state gốc (scenes/cost_records đầy đủ vẫn nằm trong LangGraph state).
Token estimate rough: ~4 chars = 1 token (đủ cho WP2, không cần tiktoken).
"""
from typing import Any, Dict, List

MAX_SCENES_KEPT = 5
MAX_COST_RECORDS_KEPT = 20
TOKEN_BUDGET = 2000

SCENE_TRUNCATE_KEYS = ("script", "narration", "prompt", "description", "visual_prompt", "voiceover_text")
SCENE_FIELD_CHARS = 500
RECORD_FIELD_CHARS = 300
TRUNCATE_SUFFIX = "...[truncated]"


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars = 1 token."""
    return max(1, len(text or "") // 4)


def truncate(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + TRUNCATE_SUFFIX


def _as_dict(item: Any) -> Dict[str, Any]:
    """Pydantic models -> dict (không mutate object gốc)."""
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return dict(item)


def trim_scenes(scenes: List[Any], keep: int = MAX_SCENES_KEPT) -> List[Dict[str, Any]]:
    """Giữ `keep` scenes gần nhất; truncate các field dài trên bản copy."""
    if not scenes:
        return []
    tail = scenes[-keep:]
    out = []
    for s in tail:
        s2 = _as_dict(s)
        for k in SCENE_TRUNCATE_KEYS:
            if k in s2 and isinstance(s2[k], str):
                s2[k] = truncate(s2[k], SCENE_FIELD_CHARS)
        out.append(s2)
    return out


def trim_cost_records(records: List[Any], keep: int = MAX_COST_RECORDS_KEPT) -> List[Dict[str, Any]]:
    """Giữ `keep` records gần nhất; drop raw payload + truncate field verbose."""
    if not records:
        return []
    tail = records[-keep:]
    out = []
    for r in tail:
        r2 = _as_dict(r)
        # drop raw payload nếu có
        r2.pop("raw_response", None)
        for k in ("detail", "notes"):
            if k in r2 and isinstance(r2[k], str):
                r2[k] = truncate(r2[k], RECORD_FIELD_CHARS)
        out.append(r2)
    return out


def build_trimmed_context(
    scenes: List[Any],
    cost_records: List[Any],
    budget: int = TOKEN_BUDGET,
) -> Dict[str, Any]:
    """Bản trimmed context cho prompt LLM, enforce token budget rough.

    Vượt budget → giảm dần: bớt scenes cũ nhất trước, rồi truncate mạnh hơn.
    """
    scenes_t = trim_scenes(scenes)
    records_t = trim_cost_records(cost_records)

    def _over(ctx: Dict[str, Any]) -> bool:
        return estimate_tokens(str(ctx)) > budget

    if _over({"scenes": scenes_t, "cost_records": records_t}):
        # Vòng 1: giảm dần số scenes (giữ tối thiểu 1)
        while len(scenes_t) > 1 and _over({"scenes": scenes_t, "cost_records": records_t}):
            scenes_t = scenes_t[1:]
        # Vòng 2: truncate mạnh hơn field scene (500 -> 150 chars)
        if _over({"scenes": scenes_t, "cost_records": records_t}):
            for s in scenes_t:
                for k in SCENE_TRUNCATE_KEYS:
                    if k in s and isinstance(s[k], str):
                        s[k] = truncate(s[k], 150)
        # Vòng 3: giảm dần cost records
        while len(records_t) > 1 and _over({"scenes": scenes_t, "cost_records": records_t}):
            records_t = records_t[1:]
        # Vòng 4: truncate field records mạnh hơn
        if _over({"scenes": scenes_t, "cost_records": records_t}):
            for r in records_t:
                for k in ("detail", "notes"):
                    if k in r and isinstance(r[k], str):
                        r[k] = truncate(r[k], 100)

    return {"scenes": scenes_t, "cost_records": records_t}
