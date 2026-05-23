# CLAUDE.md — templates

## Role

Jinja2 prompt templates for the 4 task types (used by orchestration-service) and YAML style configurations for the 3 output formats (used by output-service).

## Directory structure

```
templates/
├── prompts/                        # LLM system prompts (Jinja2)
│   ├── system_prompt.j2            # Generic: tools description, citation format, quality requirements
│   ├── literature_review.j2        # Literature review specific instructions
│   ├── policy_draft.j2             # Policy drafting specific instructions
│   ├── policy_comparison.j2        # Policy comparison specific instructions
│   └── tech_interpretation.j2      # Technical interpretation specific instructions
└── output/                         # Output style configs (YAML)
    ├── docx_gbt9704.yaml           # DOCX GB/T 9704-2012: fonts, margins, heading mapping
    ├── pptx_briefing.yaml          # PPTX briefing: slide layouts, color scheme
    └── xlsx_matrix.yaml            # XLSX comparison: column widths, cell styles
```

## Prompt templates

Loaded by `orchestration-service` via Jinja2. Variables injected:
- `user_query` — user's original task description
- `docs` — list of retrieved document titles/summaries
- `format` — desired output format

Key instruction common to all prompts:
> ALL factual claims MUST use inline citations in format `[ref:doc_id:page_range]`

## Output style configs

Loaded by `output-service` via `template_loader.py`.

**docx_gbt9704.yaml** defines:
```yaml
fonts:
  title: 小标宋
  heading1: 黑体
  heading2: 楷体
  body: 仿宋_GB2312
margins:
  top: 37mm
  bottom: 35mm
```

**pptx_briefing.yaml** and **xlsx_matrix.yaml** define slide/column layouts respectively.

## Used by

- `services/orchestration-service` — loads prompt templates
- `services/output-service` — loads output style configs
