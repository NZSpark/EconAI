# CLAUDE.md — output-service (M7)

## Role

Generates structured output from orchestrated task results: Markdown (with YAML front-matter and GitHub-style footnotes), DOCX (GB/T 9704-2012 compliant), XLSX (comparison matrices + citation sheets), PPTX (briefing decks). Outputs stored in MinIO.

## Directory structure

```
services/output-service/
├── Dockerfile
├── pyproject.toml
├── output_service/
│   ├── app.py               # FastAPI: generate, preview (Markdown), export download
│   ├── config.py             # MinIO bucket, default docx font (仿宋_GB2312), storage paths
│   ├── format_router.py      # Parallel multi-format generation
│   ├── markdown_gen.py       # Jinja2, YAML front-matter, [ref:]→[^n] footnotes
│   ├── docx_gen.py           # GB/T 9704-2012: header/body/footer, heading mapping, citation list
│   ├── xlsx_gen.py           # Comparison matrix + citation sheet + data summary
│   ├── pptx_gen.py           # Cover, TOC, findings, recommendations, references
│   ├── template_loader.py    # Loads style config from templates/output/*.yaml
│   ├── models.py             # Pydantic models
│   └── minio_client.py       # MinIO store + presigned URL generation
```

## GB/T 9704 (DOCX standard)

Chinese government document standard applied to DOCX output:
- **Header**: 小标宋 font, document number
- **Body**: 3号 仿宋_GB2312, specific margins
- **Headings**: 黑体 (level 1), 楷体 (level 2), 仿宋 bold (level 3)
- **Footer**: Separator line, contact info

## Templates

Style configs in `templates/output/`:
- `docx_gbt9704.yaml` — font names, sizes, margins, heading convention
- `pptx_briefing.yaml` — slide layouts
- `xlsx_matrix.yaml` — column widths, cell styles

## Key dependencies

- python-docx, openpyxl, python-pptx (document generation)
- Jinja2 + pyyaml (templates)
- MinIO (output file storage)
- `policyai-shared`

## Run / test

```bash
uv run uvicorn output_service.app:app --host 0.0.0.0 --port 8006 --reload
pytest --tb=short && mypy . --strict && ruff check .
```
