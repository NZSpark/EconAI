# CLAUDE.md — llm-router (M5)

## Role

Routes LLM requests to cloud (Claude API) or local models (Ollama/vLLM) based on sensitivity analysis. Adapts between Anthropic and OpenAI-compatible APIs. Circuit breaker for cloud failures. Token usage tracking.

## Directory structure

```
services/llm-router/
├── Dockerfile
├── pyproject.toml
├── models.yaml              # Model registry: claude-sonnet-4-6, claude-opus-4-7, local:qwen2.5-coder:7b
├── llm_router/
│   ├── app.py               # FastAPI: list models, unified /chat, usage stats
│   ├── config.py             # Timeout, retry params, circuit breaker thresholds
│   ├── tracker.py            # Token usage tracking (prompt/completion/total per user/task/model)
│   ├── models/
│   │   ├── registry.py      # YAML model registry loader (hot-reload)
│   │   └── schemas.py       # ChatRequest, ChatResponse, Message Pydantic models
│   ├── routing/
│   │   ├── engine.py        # sensitivity=high→local, low→cloud, explicit model override, Claude→local fallback
│   │   └── circuit_breaker.py  # CLOSED→OPEN(5 failures)→HALF_OPEN→CLOSED, 60s recovery timeout
│   └── adapters/
│       ├── claude_adapter.py    # Anthropic SDK wrapper, tool_use bidirectional conversion
│       ├── local_adapter.py     # OpenAI-compatible /v1/chat/completions
│       └── exceptions.py        # Unified: RateLimit, Timeout, ServerError, AuthError
```

## Sensitivity rules

| Rule | Sensitivity | Route |
|------|-------------|-------|
| Document tagged "internal" | high | local LLM |
| Task type = policy_draft | high | local LLM |
| User preference override | as specified | per preference |
| Default (no match) | low | Claude API |

## Retry strategy

| Error | Backoff | Max retries |
|-------|---------|-------------|
| 429 Rate Limit | Exponential (base=2s) | 3 |
| 5xx Server Error | Linear | 2 |
| Timeout | — | 1 |
| Claude unavailable | — | Fallback to local |

## Key dependencies

- anthropic (Claude SDK)
- httpx + redis
- pyyaml (model registry)
- `econai-shared`

## Model registry (models.yaml)

```yaml
models:
  - id: claude-sonnet-4-6
    provider: cloud
    adapter: anthropic
  - id: claude-opus-4-7
    provider: cloud
    adapter: anthropic
  - id: local:qwen2.5-coder:7b
    provider: local
    adapter: ollama
```

Default local: `qwen2.5-coder:7b`, default cloud: `claude-sonnet-4-6`.

## Run / test

```bash
uv run uvicorn llm_router.app:app --host 0.0.0.0 --port 8004 --reload
pytest --tb=short && mypy . --strict && ruff check .
```
