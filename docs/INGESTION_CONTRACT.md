# Ingestion Contract (P1 activates)

JSONL, one document per line. Row schema:

```json
{
  "doc_id": "kw-law-6-2010",
  "doc_type": "law",
  "title_ar": "قانون رقم 6 لسنة 2010",
  "number": "6",
  "year": 2010,
  "issue_date": "2010-02-21",
  "effective_date": "2010-02-21",
  "status": "in_force",
  "legal_domain": ["labor"],
  "language": "ar",
  "jurisdiction": "KW",
  "source_uri": "s3://.../original.pdf",
  "units": [
    {
      "unit_id": "kw-law-6-2010/a41",
      "unit_type": "article",
      "path": ["الباب الخامس"],
      "article_number": 41,
      "article_label": "المادة 41",
      "text": "…",
      "valid_from": "2010-02-21",
      "valid_to": null,
      "amended_by": null
    }
  ]
}
```

Amended articles = multiple units, same `article_number`, non-overlapping validity ranges.

Rejects: bad rows are logged with a per-row error; the job continues.
