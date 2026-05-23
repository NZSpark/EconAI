# CLAUDE.md — citation-service (M6)

## Role

Parses `[ref:doc_id:page_range]` inline citations from LLM output, verifies them against source chunks (page matching + cosine similarity), assigns confidence levels (direct/fuzzy/uncertain), and formats citations for Markdown/DOCX/XLSX/PPTX output.

## Directory structure

```
services/citation-service/
├── Dockerfile
├── pyproject.toml
├── citation_service/
│   ├── app.py               # FastAPI: verify citations, list citations, citation detail
│   ├── config.py             # Similarity threshold=0.85, batch size=50
│   ├── parser.py             # Parses [ref:doc_id:page_range] format, Chinese+English sentence splitting
│   ├── verifier.py           # Page match + cosine similarity → confidence classification
│   ├── formatter.py          # MD (GFM footnotes), DOCX (footnotes/endnotes), XLSX (citation sheet), PPTX
│   └── models.py             # Pydantic data models
```

## Confidence levels

| Level | Color | Condition |
|-------|-------|-----------|
| **direct** | Green | Exact page match + similarity ≥ 0.85 |
| **fuzzy** | Yellow | Partial page match OR similarity 0.65–0.85 |
| **uncertain** | Red | No match, similarity < 0.65 |

## Citation format

```
[ref:doc_uuid:page_range]
Example: [ref:a1b2c3d4:p3-5]
```

LLM MUST use this exact format for all factual claims. Citation service parses, verifies each claim against the KB chunks it was generated from.

## Key dependencies

- SQLAlchemy[asyncio] + asyncpg (reference storage)
- redis + numpy
- `econai-shared`

## Run / test

```bash
uv run uvicorn citation_service.app:app --host 0.0.0.0 --port 8005 --reload
pytest --tb=short && mypy . --strict && ruff check .
```
