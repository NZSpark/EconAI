# CLAUDE.md — document-service (M2)

## Role

Upload, parse (8 formats + OCR), multi-granularity chunking, MinIO storage. Publishes `kb:index:request` events for KB Service to pick up.

## Directory structure

```
services/document-service/
├── Dockerfile
├── pyproject.toml
├── document_service/
│   ├── app.py               # FastAPI: upload, list, detail, delete, reindex
│   ├── config.py             # MinIO bucket, chunk params, OCR languages, max file size
│   ├── models.py             # Pydantic models + IndexEvent
│   ├── format_identifier.py  # magic bytes + extension based format detection
│   ├── validation.py         # Size limits, format whitelist
│   ├── state_machine.py      # Document state: pending→parsing→ready/error
│   ├── tasks.py              # Celery async parse tasks (production)
│   ├── celery_app.py         # Celery app config
│   ├── minio_client.py       # MinIO upload/download/delete
│   ├── parsers/
│   │   ├── router.py         # Dispatch to format-specific parser
│   │   ├── pdf_parser.py     # PyMuPDF
│   │   ├── word_parser.py    # python-docx
│   │   ├── markdown_parser.py
│   │   ├── excel_parser.py   # openpyxl + pandas
│   │   ├── ppt_parser.py     # python-pptx
│   │   ├── email_parser.py   # .eml via BeautifulSoup4
│   │   ├── html_parser.py    # HTML/MHTML via BeautifulSoup4
│   │   ├── image_parser.py   # OCR via Tesseract
│   │   └── ocr_processor.py  # Tesseract (chi_sim + eng)
│   └── chunker/
│       ├── paragraph_splitter.py  # ~300 tokens, 50 token overlap
│       ├── section_splitter.py    # ~2000 tokens, 100 token overlap
│       └── chunk_metadata.py      # Generate both granularities with metadata
```

## Formats supported

| Format | Library |
|--------|---------|
| PDF | PyMuPDF |
| DOCX | python-docx |
| MD | built-in |
| XLSX/CSV | openpyxl + pandas |
| PPTX | python-pptx |
| EML | BeautifulSoup4 + lxml |
| HTML/MHTML | BeautifulSoup4 |
| Image (PNG/JPG/TIFF) | Tesseract OCR |

## Chunking

- **Paragraph-level**: ~300 tokens, 50-token overlap → precise retrieval
- **Section-level**: ~2000 tokens, 100-token overlap → context window

## Key dependencies

- PyMuPDF, python-docx, openpyxl, pandas, python-pptx (parsing)
- Pillow + Tesseract (OCR)
- MinIO (object storage)
- Celery[redis] (async tasks)
- `econai-shared`

## Run / test

```bash
uv run uvicorn document_service.app:app --host 0.0.0.0 --port 8001 --reload
# Celery worker (separate terminal):
uv run celery -A document_service.celery_app worker --loglevel=INFO --concurrency=2 --queues=document
pytest --tb=short && mypy . --strict && ruff check .
```
