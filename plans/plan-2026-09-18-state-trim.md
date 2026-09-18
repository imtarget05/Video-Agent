# Plan: State Trimming — Video-Agent (WP2)

> Header (writing-plans chuẩn):
> - **Repo:** Video-Agent (`/Users/mainguyenbinhtan/Downloads/Video-Agent`)
> - **File:** `plans/plan-2026-09-18-state-trim.md`
> - **Date:** 2026-09-18
> - **Status:** Approved (draft đã duyệt, chờ implement)
> - **Scope:** CHỈ repo Video-Agent — chống State Bloat / Context overflow phía Video pipeline. KHÔNG đụng Smart-Document-Chatbot (xem file plan twin bên repo đó).
> - **Out of scope:** Thay LLM, đổi schema state vĩnh viễn, refactor nodes.py lớn, S3/CDN.

## 1. Goal
Chống State Bloat / Context overflow khi số scenes tăng và cost_records phình to:
- Giới hạn scenes/cost_records mang theo trong LangGraph state.
- Giữ token budget ≤ 2000 tokens cho phần trimmed context.
- Không mất dữ liệu gốc (chỉ trim khi truyền vào LLM / node nặng).

## 2. Context / Vấn đề
- `nodes.py` hiện truyền toàn bộ `scenes` + `cost_records` vào prompt → prompt dài, dễ overflow, tốn token.
- Không có helper trim tập trung → mỗi node tự cắt kiểu khác nhau (rủi ro).
- Cần 1 module `context_trim.py` duy nhất + wire vào nodes.

## 3. Design — module mới `context_trim.py`
Tạo file mới (ví dụ `src/video_agent/context_trim.py` hoặc vị trí tương đương theo repo, squad implement xác nhận path khi làm):

```python
MAX_SCENES_KEPT = 5
MAX_COST_RECORDS_KEPT = 20
TOKEN_BUDGET = 2000  # rough estimate

def estimate_tokens(text: str) -> int:
    # rough: ~4 chars = 1 token
    return max(1, len(text or "") // 4)

def truncate(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...[truncated]"

def trim_scenes(scenes: list, keep: int = MAX_SCENES_KEPT) -> list:
    """Giữ `keep` scenes gần nhất; mỗi scene truncate fields dài (script/narration)."""
    if not scenes:
        return []
    tail = scenes[-keep:]
    out = []
    for s in tail:
        s2 = dict(s)
        for k in ("script", "narration", "prompt", "description"):
            if k in s2 and isinstance(s2[k], str):
                s2[k] = truncate(s2[k], 500)
        out.append(s2)
    return out

def trim_cost_records(records: list, keep: int = MAX_COST_RECORDS_KEQT if False else 20) -> list:
    """Giữ 20 records gần nhất; drop fields verbose."""
    if not records:
        return []
    tail = records[-keep:]
    out = []
    for r in tail:
        r2 = dict(r)
        # drop raw payload nếu có
        r2.pop("raw_response", None)
        for k in ("detail", "notes"):
            if k in r2 and isinstance(r2[k], str):
                r2[k] = truncate(r2[k], 300)
        out.append(r2)
    return out
```

> Ghi chú: fix tên hằng khi implement (`MAX_COST_RECORDS_KEPT = 20`).

Budget enforce (pseudo):

```python
def build_trimmed_context(scenes, cost_records, budget: int = TOKEN_BUDGET) -> dict:
    scenes_t = trim_scenes(scenes)
    records_t = trim_cost_records(cost_records)
    # nếu vượt budget → giảm dần: truncate mạnh hơn / bớt scenes
    while estimate_tokens(str(scenes_t) + str(records_t)) > budget and len(scenes_t) > 1:
        scenes_t = scenes_t[1:]
    return {"scenes": scenes_t, "cost_records": records_t}
```

## 4. Wire vào `nodes.py`
- Import `build_trimmed_context / trim_scenes / trim_cost_records` trong nodes build prompt cho LLM.
- Chỉ dùng bản trimmed khi compose prompt; state gốc giữ nguyên (không ghi đè mất dữ liệu).
- Thêm 1 helper `_llm_context(state)` trong nodes.py gọi `build_trimmed_context`.

## 5. Tasks TDD (Video — 3/7 tasks tổng WP2)
- [ ] **V-T1 (RED):** pytest failing: `trim_scenes` với 10 scenes → chỉ giữ 5 cuối + truncate field dài ≤500 chars.
- [ ] **V-T2 (GREEN):** implement `context_trim.py` (`trim_scenes/trim_cost_records/truncate/estimate_tokens/build_trimmed_context`, keep 5/20, budget 2000).
- [ ] **V-T3 (WIRE):** wire vào `nodes.py` (`_llm_context`), pytest: prompt dùng bản trimmed, state gốc intact.

Pytest đã có trong draft (squad dùng lại):
- `test_trim_scenes_keeps_last_5`
- `test_trim_cost_records_keeps_20_drops_raw`
- `test_build_trimmed_context_respects_budget`
- `test_nodes_uses_trimmed_context`

## 6. Verify
```bash
pytest tests/test_context_trim.py -v
pytest tests/test_nodes.py -v -k trim
```

## 7. Self-Review
- [ ] Có truncate mọi string dài trước khi vào prompt? (không còn path nào truyền raw scenes)
- [ ] keep constants đúng 5 scenes / 20 records / 2000 tokens?
- [ ] state gốc không bị ghi đè bởi bản trimmed?
- [ ] budget enforce có vòng lặp giảm scenes khi vượt?
- [ ] Không sửa code ngoài `context_trim.py` + wire `nodes.py`?

## 8. Notes
- Estimate token rough (len//4) là đủ cho WP2; không cần tiktoken.
- Nếu sau này scenes có image b64 → phải strip trước khi trim (để WP sau).
- File twin phía Smart: `Smart-Document-Chatbot/plans/plan-2026-09-18-state-trim.md`.
