# CLAUDE.md — orchestration-service (M4)

## Role

Agent engine driving analysis tasks. ReAct variant loop (Plan→Retrieve→Generate→Verify→Decide), 6 tools, task lifecycle management. Calls LLM Router for LLM, KB Service for search, Citation Service for validation, Output Service for export.

## Directory structure

```
services/orchestration-service/
├── Dockerfile
├── pyproject.toml
├── orchestration_service/
│   ├── app.py               # FastAPI: create/list/detail/poll/cancel/retry tasks, output preview, citation list, export
│   ├── config.py             # agent_max_iterations=5, tool_timeout=60s, task_timeout=30min
│   ├── agent_loop.py         # Core: ReAct loop (Plan→Execute→Observe→UpdateProgress), max 5 iterations
│   ├── tools.py              # 6 tools: search_kb, generate_section, verify_citations, extract_key_claims, compare_policies, format_output
│   ├── state.py              # AgentState: messages, chunks, sections, citations, plan, iteration counter
│   ├── sensitivity.py        # 4 rules: internal_docs→high, policy_draft→high, user-preference-override, default→low
│   ├── status_machine.py     # pending→running→completed/failed/cancelled
│   ├── progress.py           # Progress tracker with percentage
│   ├── schemas.py            # All Pydantic models (~9KB)
│   ├── task_workflows.py     # 4 task type workflows + initial section definitions
│   └── worker.py             # Celery worker integration (production)
```

## Agent loop

```
1. Plan    → Call LLM Router to decide next tool
2. Execute → Run selected tool (60s timeout, 1 retry)
3. Observe → Append tool result to conversation history
4. Update  → Set progress percentage
5. Repeat  → Until "finish" signal or max_iterations (5) → force format_output
```

## 6 tools

| Tool | Function |
|------|----------|
| `search_kb` | Queries KB Service hybrid search |
| `generate_section` | Calls LLM Router to write a report section |
| `verify_citations` | Validates [ref:doc:page] via Citation Service |
| `extract_key_claims` | Extracts key findings with LLM |
| `compare_policies` | Side-by-side policy comparison |
| `format_output` | Assembles final output, triggers Output Service |

## Task types

- `literature_review` — system prompt via `templates/prompts/literature_review.j2`
- `policy_draft` — `templates/prompts/policy_draft.j2`
- `policy_comparison` — `templates/prompts/policy_comparison.j2`
- `tech_interpretation` — `templates/prompts/tech_interpretation.j2`

## Key dependencies

- httpx (calls LLM Router, KB, Citation, Output services)
- Jinja2 (prompt templates)
- redis + celery (production task queue)
- `policyai-shared`

## Run / test

```bash
uv run uvicorn orchestration_service.app:app --host 0.0.0.0 --port 8003 --reload
# Celery worker:
uv run celery -A orchestration_service.celery_app worker --loglevel=INFO --concurrency=4 --queues=orchestration
pytest --tb=short && mypy . --strict && ruff check .
```
