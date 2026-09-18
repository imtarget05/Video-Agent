# WP4 — Stateless Free-Infra Video-Agent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Feature:** WP4 Stateless Free-Infra Video-Agent

**Goal:** Stateless storage interface cho backend Video-Agent chạy được trên free-tier (local disk + S3Mock R2-compat + R2), OUT_DIR cấu hình được, ledger dùng DATABASE_URL.

**Architecture:** server.py (OUT_DIR) -> backend/app/storage factory -> base/local_disk/s3mock; ledger -> DATABASE_URL.

**Tech Stack:** Python, FastAPI, sqlite/DATABASE_URL, stdlib-only HTTP (urllib), pytest.

**Spec:** STORAGE_BACKEND=local|s3mock|r2; server.py OUT_DIR qua env; ledger DATABASE_URL; pytest tests/test_storage_stateless.py.

## Global Constraints

- CẤM sửa code ngoài phạm vi File Structure bên dưới.
- TDD: failing test trước, minimal code, rồi pass.
- Free-tier only: local + S3Mock + R2-compat + DATABASE_URL free-tier; chi phí $0.
- Stateless: không giữ state trên instance local ngoài OUT_DIR cấu hình được.
- Không commit/push trừ khi task ra lệnh.

---

## File Structure

- `backend/app/storage/base.py` (mới) — Storage ABC: `save(key, bytes)`, `load(key)->bytes`, `exists(key)->bool`, `delete(key)`.
- `backend/app/storage/local_disk.py` (mới) — LocalDisk backend, root = OUT_DIR cấu hình được, atomic write.
- `backend/app/storage/s3mock.py` (mới) — S3Mock + R2-compat backend, stdlib-only (urllib, không SDK ngoài), endpoint cấu hình được cho R2.
- `backend/app/storage/factory.py` (mới) — factory `get_storage()`: STORAGE_BACKEND=local|s3mock|r2.
- `backend/app/server.py` — OUT_DIR đọc từ env, mọi ghi file đi qua storage interface.
- `backend/app/ledger.py` — DATABASE_URL cấu hình được (sqlite local default, free-tier postgres khi set).
- `.env.example` — STORAGE_BACKEND + R2_ENDPOINT + DATABASE_URL + OUT_DIR.
- `docs/STATELESS_FREEINFRA.md` (mới) — hướng dẫn cấu hình free-tier.
- `tests/test_storage_stateless.py` (mới) — failing test + regression stateless.
- `tasks/notes/wp4-freeinfra.notes.md` — 5 dòng quyết định free-infra.

---

## Task 1 — Storage interface ABC

**Files:** `backend/app/storage/base.py` (mới)

**Interfaces:** `save(key, bytes)`, `load(key)`, `exists(key)`, `delete(key)`

**Steps:**

- [ ] Viết failing test interface trong `tests/test_storage_stateless.py`: import ABC, assert 4 method tồn tại.
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Tạo `backend/app/storage/base.py` với ABC + 4 method abstract tối thiểu.
- [ ] Chạy lại verify (kỳ vọng PASS task này).

---

## Task 2 — Local roundtrip (OUT_DIR)

**Files:** `backend/app/storage/local_disk.py` (mới)

**Interfaces:** `LocalDisk(root).save/load/exists/delete`

**Steps:**

- [ ] Bổ sung failing test: save bytes -> load ra bytes identical, exists true, delete xong exists false (tmp_path).
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Implement `local_disk.py` minimal (atomic write qua tmp+rename).
- [ ] Chạy lại verify (kỳ vọng PASS).

---

## Task 3 — S3Mock roundtrip (R2-compat stdlib-only)

**Files:** `backend/app/storage/s3mock.py` (mới)

**Interfaces:** `S3MockStorage(endpoint).save/load/exists/delete`

**Steps:**

- [ ] Bổ sung failing test roundtrip qua S3Mock (dùng server mock local, stdlib-only, endpoint cấu hình được).
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Implement `s3mock.py` minimal với urllib (PUT/GET/HEAD/DELETE), tương thích endpoint R2.
- [ ] Chạy lại verify (kỳ vọng PASS).

---

## Task 4 — Factory STORAGE_BACKEND

**Files:** `backend/app/storage/factory.py` (mới)

**Interfaces:** `get_storage(): STORAGE_BACKEND=local|s3mock|r2`

**Steps:**

- [ ] Bổ sung failing test: monkeypatch STORAGE_BACKEND từng giá trị, assert đúng class backend trả về.
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Implement `factory.py` minimal đọc env, default local.
- [ ] Chạy lại verify (kỳ vọng PASS).

---

## Task 5 — server.py OUT_DIR qua storage

**Files:** `backend/app/server.py`

**Interfaces:** `OUT_DIR` env + ghi/đọc file qua storage (giữ contract API cũ)

**Steps:**

- [ ] Bổ sung failing test: set OUT_DIR khác nhau, assert server ghi đúng root (mock storage, assert get_storage được gọi).
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Sửa server.py: OUT_DIR từ env, mọi ghi file qua `get_storage()`, giữ contract response cũ.
- [ ] Chạy lại verify (kỳ vọng PASS).

---

## Task 6 — Ledger DATABASE_URL

**Files:** `backend/app/ledger.py`

**Interfaces:** `DATABASE_URL` env (default sqlite local, free-tier postgres khi set)

**Steps:**

- [ ] Bổ sung failing test: set DATABASE_URL sqlite tmp, record/total hoạt động; contract record/total giữ nguyên.
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Sửa ledger đọc DATABASE_URL, giữ schema/behavior cũ.
- [ ] Chạy lại verify (kỳ vọng PASS).

---

## Task 7 — Env + docs free-tier

**Files:** `.env.example`, `docs/STATELESS_FREEINFRA.md` (mới)

**Interfaces:** `STORAGE_BACKEND`, `R2_ENDPOINT`, `DATABASE_URL`, `OUT_DIR`

**Steps:**

- [ ] Bổ sung failing test: đọc `.env.example` phải chứa đủ 4 biến STORAGE_BACKEND + R2_ENDPOINT + DATABASE_URL + OUT_DIR.
- [ ] Chạy verify (kỳ vọng FAIL):
```
pytest tests/test_storage_stateless.py -v
```
- [ ] Cập nhật `.env.example` + viết `docs/STATELESS_FREEINFRA.md` (local/s3mock/r2 + DATABASE_URL free-tier).
- [ ] Chạy full verify (kỳ vọng PASS):
```
pytest tests/test_storage_stateless.py -v
```
