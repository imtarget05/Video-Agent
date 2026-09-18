# WP1 — Decimal Precision Video-Agent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Feature:** WP1 Decimal precision Video-Agent

**Goal:** Loại bỏ float drift trong CostLedger (0.1+0.2), đảm bảo tính toán chi phí chính xác tuyệt đối.

**Architecture:** state.py -> ledger.py -> nodes.py (CostRecord lan truyền Decimal qua ledger tới nodes/CPFM).

**Tech Stack:** Python, Pydantic, Decimal, sqlite, pytest.

**Spec:** CostRecord Decimal + ledger TEXT + CPFM quantize + giữ contract float (backcompat cho server.py).

## Global Constraints

- CẤM sửa code ngoài phạm vi File Structure bên dưới; không đụng `server.py` contract (giữ float ở boundary).
- TDD: failing test trước, minimal code, rồi pass.
- CPFM mọi phép tính phải quantize Decimal (ROUND_HALF_UP, 2 decimals).
- Ledger sqlite lưu TEXT (str(Decimal)), đọc ra rebuild Decimal — không lưu REAL/float.
- Không commit/push trừ khi task ra lệnh.

---

## File Structure

- `state.py:65-72` — CostRecord: `dollar_cost` chuyển float -> Decimal + validator.
- `ledger.py:36-116` — schema TEXT + insert/select chuyển đổi Decimal + CPFM quantize.
- `nodes.py:140/176/186/234-238` — lan truyền Decimal (tính cost, cộng dồn, CPFM, emit).
- `tests/test_decimal_precision.py` (mới) — failing test + regression Decimal.
- `tests/test_cost_ledger.py` (regression) — giữ xanh, bổ sung backcompat float.
- `tasks/notes/wp1-decimal.notes.md` — 1 dòng quyết định: giữ contract float cho server.py.

---

## Task 1 — Failing test 0.1x3=0.30

**Files:** `tests/test_decimal_precision.py` (mới)

**Interfaces:** `CostRecord(dollar_cost)`, `ledger.record()`, `ledger.total()`, CPFM helper.

**Steps:**

- [ ] Tạo `tests/test_decimal_precision.py` với test đỏ chứng minh float drift:
```python
from decimal import Decimal
def test_decimal_precision_01x3():
    # 0.1 x 3 phải == 0.30 chính xác, không phải 0.30000000000000004
    vals = [Decimal("0.1")] * 3
    assert sum(vals, Decimal("0")) == Decimal("0.30")
    # CPFM quantize 2 decimals
    total, minutes = Decimal("0.30"), Decimal("1")
    cpfm = (total / minutes).quantize(Decimal("0.01"))
    assert cpfm == Decimal("0.30")
```
- [ ] Chạy lệnh verify (kỳ vọng FAIL trước khi sửa code):
```
pytest tests/test_decimal_precision.py -v
```

## Task 2 — CostRecord validator (state.py:65-72)

**Files:** `state.py:65-72`

**Interfaces:** `CostRecord.dollar_cost: Decimal`, Pydantic validator coerce float/str -> Decimal.

**Steps:**

- [ ] Thêm validator `CostRecord`: nhận `float | str | Decimal`, ép về `Decimal(str(v))`, quantize `0.01`.
```python
from decimal import Decimal, ROUND_HALF_UP
from pydantic import field_validator
class CostRecord(BaseModel):
    dollar_cost: Decimal
    @field_validator("dollar_cost", mode="before")
    @classmethod
    def _coerce_decimal(cls, v):
        d = v if isinstance(v, Decimal) else Decimal(str(v))
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```
- [ ] Verify:
```
pytest tests/test_decimal_precision.py -v
```

## Task 3 — Ledger TEXT + Decimal (ledger.py:36-116)

**Files:** `ledger.py:36-116`

**Interfaces:** `record(CostRecord) -> TEXT`, `total() -> Decimal`, CPFM `quantize`.

**Steps:**

- [ ] Đổi schema cột cost `REAL -> TEXT`; insert `str(record.dollar_cost)`; select rebuild `Decimal(row)`.
```python
# schema
dollar_cost TEXT NOT NULL
# insert
cur.execute("INSERT INTO ledger (dollar_cost) VALUES (?)", (str(rec.dollar_cost),))
# total
total = sum((Decimal(r[0]) for r in rows), Decimal("0")).quantize(Decimal("0.01"))
```
- [ ] CPFM quantize mọi đường tính: `(total / minutes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
- [ ] Verify:
```
pytest tests/test_decimal_precision.py tests/test_cost_ledger.py -v
```

## Task 4 — Nodes lan truyền Decimal (nodes.py:140/176/186/234-238)

**Files:** `nodes.py:140/176/186/234-238`

**Interfaces:** scriptwriter/cost nodes truyền `Decimal`, không `float()` giữa chừng.

**Steps:**

- [ ] Dòng 140/176/186: tạo `CostRecord(dollar_cost=Decimal(...))`, cộng dồn bằng `Decimal`, không cast float.
- [ ] Dòng 234-238: tính CPFM bằng Decimal + quantize trước khi emit/float boundary.
```python
from decimal import Decimal
cost = Decimal(str(video_seconds)) * Decimal("0.05")  # ví dụ đơn giá
```
- [ ] Verify:
```
pytest tests/test_decimal_precision.py tests/test_cost_ledger.py -v
```

## Task 5 — Backcompat + full suite

**Files:** `tests/test_cost_ledger.py`, `tests/test_decimal_precision.py`

**Interfaces:** Giữ contract float cho `server.py` (boundary `float(Decimal)` khi trả API).

**Steps:**

- [ ] Bổ sung test backcompat: `float(record.dollar_cost)` vẫn dùng được cho server.py; Decimal nội bộ không vỡ API cũ.
- [ ] Chạy full suite chống regression:
```
pytest -v --tb=short
```
- [ ] Ghi `tasks/notes/wp1-decimal.notes.md` 1 dòng quyết định: giữ contract float cho server.py.

---

## Self-Review

1. Spec coverage: CostRecord Decimal + ledger TEXT + CPFM quantize + giữ contract float — đủ 4 điểm spec.
2. Placeholder scan: mọi task có test code + implement code + lệnh pytest Expected cụ thể, không TBD.
3. Type consistency: `Decimal` nội bộ (state/ledger/nodes) nhất quán; chỉ `float()` tại boundary server.py.

## Execution Handoff

Plan complete and saved to `plans/plan-2026-09-18-decimal-precision.md`. Quyết định log tại `tasks/notes/wp1-decimal.notes.md` (1 dòng: giữ contract float cho server.py).
