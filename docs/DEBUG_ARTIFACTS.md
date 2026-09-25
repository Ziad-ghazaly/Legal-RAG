# Ingestion Debug Artifacts

MinIO bucket `v3-ingestion-debug/` (P1 populates; P0 stubs the endpoints).

```
{ingestion_job_id}/
  {doc_id}/
    01_original.pdf          exact bytes uploaded
    02_extraction.json       parser output, per-page
    03_ocr.json              OCR output (if fired)
    04_cleaned.txt           after boilerplate removal
    05_units.json            discovered units
    06_chunks.json           final chunks
    07_dropped.jsonl         dropped chunks + reasons
    report.md                one-page summary
```

Access:
- `GET /api/v1/admin/ingestion/jobs/{job_id}/debug/{doc_id}` — signed URLs.
- `GET /api/v1/admin/ingestion/jobs/{job_id}/debug/{doc_id}/report` — inline Markdown.

Retention: 90 days (`.env`).
