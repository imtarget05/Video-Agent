# WP4 Free-Infra Notes — Video-Agent (2026-09-18)

1. Không dùng orchestrator container hay cụm máy chủ tự quản — chỉ deploy free-tier đơn giản (local/s3mock/R2).
2. Free-tier only ($0): local disk + S3Mock + R2-compat + DATABASE_URL free-tier, không dịch vụ trả phí.
3. Storage stdlib-only (urllib, không SDK S3 ngoài) để giữ CI nhẹ và tương thích endpoint R2.
4. Stateless: server.py OUT_DIR qua env, mọi ghi file qua storage interface STORAGE_BACKEND=local|s3mock|r2.
5. Ledger DATABASE_URL cấu hình được, default sqlite local, prod trỏ free-tier postgres; docs trong STATELESS_FREEINFRA.md.
