# STATELESS FREE-INFRA — Hướng dẫn cấu hình free-tier ($0)

Video-Agent chạy stateless trên free-tier: không state dính instance, mọi
artifact đi qua storage interface, ledger qua DATABASE_URL.

## 1. Storage backends (`STORAGE_BACKEND`)

| Giá trị   | Dùng khi                          | Cấu hình |
|-----------|-----------------------------------|----------|
| `local`   | dev / CI / single-instance        | `OUT_DIR` = thư mục gốc artifact (default `./out`) |
| `s3mock`  | test integration, S3-compat mock  | `S3_ENDPOINT` = URL mock server (vd `http://localhost:9000`) |
| `r2`      | Cloudflare R2 (S3-compat, free)   | `R2_ENDPOINT` = `https://<account>.r2.cloudflarestorage.com/<bucket>` |

Backend nằm ở `backend/app/storage/` — stdlib-only (urllib), không SDK ngoài:

- `base.py` — ABC: `save(key, bytes)`, `load(key)`, `exists(key)`, `delete(key)`
- `local_disk.py` — LocalDisk, atomic write (tmp + rename)
- `s3mock.py` — S3Mock/R2-compat (PUT/GET/HEAD/DELETE)
- `factory.py` — `get_storage()` đọc `STORAGE_BACKEND`

## 2. OUT_DIR qua env

`server.py` đọc `OUT_DIR` từ env (`_out_dir()`). Mọi artifact (manifest,
render mp4) được persist qua `get_storage().save(...)`, đồng thời giữ bản
local cho Remotion subprocess.

## 3. Ledger DATABASE_URL

`CostLedger` đọc `DATABASE_URL` (ưu tiên) rồi `LEDGER_DB_PATH`:

- Default: `sqlite:///./data/video_agent.db` (local, $0)
- Free-tier postgres: Neon / Supabase — set
  `DATABASE_URL=postgresql://user:pass@host/db`

## 4. Chạy test

```bash
pytest backend/tests/test_storage_stateless.py -v
```

## 5. Deploy free-tier gợi ý

- App: Render/Railway free (hoặc Fly.io) — không volume; artifact → R2.
- DB: Neon/Supabase free qua `DATABASE_URL`.
- Render GPU vẫn cloud-first (serverless GPU); instance API thuần stateless.
