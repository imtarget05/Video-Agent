# WP1 Decimal Notes — Video-Agent (2026-09-18)

- Quyết định 1 dòng: giữ contract float cho server.py — Decimal nội bộ (CostRecord/ledger/nodes), chỉ `float()` tại boundary state/server emit; ledger sqlite lưu TEXT `str(Decimal)`, đọc rebuild `Decimal(str(v))` (hỗ trợ legacy REAL), SUM diễn ra trong Python để không drift, CPFM quantize HALF_UP 2 decimals.
