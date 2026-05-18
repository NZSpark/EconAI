"""EconAI LLM Router Service (M5) — FastAPI application.

Port 8004. Provides:
  - GET  /health                       Health check
  - GET  /internal/llm/models          List available models
  - POST /internal/llm/chat            Unified chat completion with routing
  - GET  /internal/llm/usage/stats     Token usage statistics (optional filter by user_id/task_id/model)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from llm_router.adapters import (
    AdapterAuthError,
    AdapterConnectionError,
    AdapterError,
    AdapterModelUnavailableError,
    AdapterRateLimitError,
    AdapterServerError,
    AdapterTimeoutError,
    ClaudeAdapter,
    LocalAdapter,
)
from llm_router.config import settings
from llm_router.models.registry import ModelRegistry
from llm_router.models.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    ModelsResponse,
    RoutingInfo,
    UsageAggregation,
)
from llm_router.routing import CircuitBreaker, RoutingDecision, RoutingEngine
from llm_router.tracker import TokenUsageTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Global state (initialised during lifespan) ──────────────────────────

_registry: ModelRegistry
_router: RoutingEngine
_claude_adapter: ClaudeAdapter
_local_adapter: LocalAdapter
_tracker: TokenUsageTracker
_cb_claude: CircuitBreaker
_cb_local: CircuitBreaker


# ── Lifespan ────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _registry, _router, _claude_adapter, _local_adapter, _tracker, _cb_claude, _cb_local

    logger.info("LLM Router starting up...")

    _registry = ModelRegistry(settings.model_registry_path)
    _router = RoutingEngine(_registry)

    _claude_adapter = ClaudeAdapter(
        api_key=settings.anthropic_api_key or None,
        timeout_s=settings.llm_request_timeout_s,
    )
    _local_adapter = LocalAdapter(
        endpoint=settings.local_llm_endpoint or None,
        api_key=settings.local_llm_api_key or None,
        timeout_s=settings.llm_request_timeout_s,
    )
    _tracker = TokenUsageTracker()

    _cb_claude = CircuitBreaker(
        name="claude",
        failure_threshold=settings.circuit_breaker_failure_threshold,
        recovery_timeout_s=settings.circuit_breaker_recovery_timeout_s,
    )
    _cb_local = CircuitBreaker(
        name="local",
        failure_threshold=settings.circuit_breaker_failure_threshold,
        recovery_timeout_s=settings.circuit_breaker_recovery_timeout_s,
    )

    logger.info(
        "LLM Router ready. %d models loaded, default_local=%s, default_cloud=%s",
        len(_registry.list_models()),
        _registry.default_local,
        _registry.default_cloud,
    )

    yield

    logger.info("LLM Router shutting down.")


# ── Application ──────────────────────────────────────────────────────────

app = FastAPI(
    title="EconAI LLM Router Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ───────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Model list ───────────────────────────────────────────────────────────


@app.get("/internal/llm/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """Return all available models with default_local and default_cloud."""
    models = _registry.list_models()
    return ModelsResponse(
        models=models,
        default_local=_registry.default_local,
        default_cloud=_registry.default_cloud,
    )


# ── Chat completion ──────────────────────────────────────────────────────


@app.post("/internal/llm/chat", response_model=ChatResponse)
async def chat_completion(request: ChatRequest) -> ChatResponse:
    """Unified chat completion endpoint.

    Process:
      1. Validate request parameters.
      2. Truncate messages if needed (keep system + last N).
      3. Decide routing target and adapter.
      4. Execute with retry + circuit-breaker logic.
      5. Record token usage.
    """
    _validate_request(request)

    # Truncate messages if token count is likely over the limit
    request = _truncate_messages(request)

    # Routing decision
    decision = _router.decide(request.model, request.sensitivity)

    # Execute with retry / circuit-breaker / fallback
    response, latency_ms = await _execute_with_retry(request, decision)

    # Record token usage
    if settings.token_tracking_enabled:
        await _tracker.record(
            request_id=response.id,
            model=response.model,
            routing=response.routing.target,
            usage=response.usage,
            latency_ms=latency_ms,
            user_id=request.user_id,
            task_id=request.task_id,
        )

    return response


# ── Usage statistics ─────────────────────────────────────────────────────


@app.get("/internal/llm/usage/stats", response_model=UsageAggregation)
async def usage_stats(
    user_id: str | None = Query(None),
    task_id: str | None = Query(None),
    model: str | None = Query(None),
) -> UsageAggregation:
    """Return aggregated token usage statistics."""
    return _tracker.aggregate(user_id=user_id, task_id=task_id, model=model)


# ── Internal helpers ─────────────────────────────────────────────────────


def _validate_request(request: ChatRequest) -> None:
    """Validate the chat request parameters."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    if request.temperature < 0.0 or request.temperature > 2.0:
        raise HTTPException(
            status_code=400,
            detail="temperature must be in [0.0, 2.0]",
        )

    if request.max_tokens < 1 or request.max_tokens > 128000:
        raise HTTPException(
            status_code=400,
            detail="max_tokens must be in [1, 128000]",
        )

    if request.sensitivity not in ("high", "low"):
        raise HTTPException(
            status_code=400,
            detail="sensitivity must be 'high' or 'low'",
        )

    for i, msg in enumerate(request.messages):
        if msg.role not in ("system", "user", "assistant", "tool"):
            raise HTTPException(
                status_code=400,
                detail=f"messages[{i}].role must be one of: system, user, assistant, tool",
            )


def _estimate_tokens(messages: list) -> int:
    """Rough token count estimate: chars / 4 for multilingual text."""
    total = 0
    for msg in messages:
        content = getattr(msg, "content", None) or ""
        total += len(content) // 4
    return total


def _truncate_messages(request: ChatRequest) -> ChatRequest:
    """Truncate messages if estimated token count exceeds the limit.

    Strategy:
      1. Always keep the first system message.
      2. Keep the last N non-system messages.
      3. N defaults to token_truncation_keep_last_n (config).
    """
    estimated = _estimate_tokens(request.messages)
    max_context = settings.llm_max_context_tokens

    if estimated <= max_context:
        return request

    logger.warning(
        "Estimated token count %d exceeds limit %d, truncating messages",
        estimated,
        max_context,
    )

    keep_n = settings.token_truncation_keep_last_n
    from llm_router.models.schemas import Message

    truncated: list[Message] = []
    system_msgs = [m for m in request.messages if m.role == "system"]
    other_msgs = [m for m in request.messages if m.role != "system"]

    # Keep all system messages (they define the task)
    truncated.extend(system_msgs)

    # Keep the last keep_n non-system messages
    truncated.extend(other_msgs[-keep_n:])

    return ChatRequest(
        model=request.model,
        messages=truncated,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=request.stream,
        tools=request.tools,
        sensitivity=request.sensitivity,
        user_id=request.user_id,
        task_id=request.task_id,
    )


async def _execute_with_retry(
    request: ChatRequest,
    decision: RoutingDecision,
) -> tuple[ChatResponse, float]:
    """Execute the adapter call with retry and circuit breaker logic.

    Retry strategy:
      - 429: Exponential backoff, base=2s, max 3 retries
      - 5xx: Linear backoff, 1s per attempt, max 2 retries
      - Timeout: Retry once, then 504
      - Circuit breaker open: 503 immediately

    Returns:
        Tuple of (ChatResponse, latency_ms).
    """
    adapter = _claude_adapter if decision.adapter_type == "claude" else _local_adapter
    cb = _cb_claude if decision.adapter_type == "claude" else _cb_local

    if cb.is_open:
        # If Claude circuit breaker is open and fallback allowed, try local
        if decision.adapter_type == "claude" and _router.can_fallback_to_local(request.sensitivity):
            logger.warning("Claude circuit breaker open, falling back to local")
            fallback_decision = _router.decide(
                request.model, request.sensitivity, fallback_to_local=True
            )
            local_adapter = _local_adapter
            start_time = time.monotonic()
            try:
                response = await local_adapter.chat(request, fallback_decision.model_id)
                _cb_local.record_success()
                latency_ms = (time.monotonic() - start_time) * 1000
                response.routing = RoutingInfo(
                    target="local",
                    reason="circuit_breaker_open_fallback",
                    model_used=fallback_decision.model_id,
                )
                return response, latency_ms
            except Exception as exc:
                _cb_local.record_failure()
                raise HTTPException(
                    status_code=503,
                    detail="All LLM backends are currently unavailable",
                ) from exc

        raise HTTPException(
            status_code=503,
            detail=f"Circuit breaker open for {decision.adapter_type}",
        )

    # Retry loop
    max_429_retries = settings.llm_retry_max_429
    max_5xx_retries = settings.llm_retry_max_5xx
    base_backoff = settings.llm_retry_backoff_base_s
    linear_backoff = settings.llm_retry_backoff_5xx_s

    total_attempts = 0
    timeout_retries = 0

    while True:
        total_attempts += 1
        start_time = time.monotonic()

        try:
            response = await asyncio.wait_for(
                adapter.chat(request, decision.model_id),
                timeout=settings.llm_request_timeout_s,
            )
            cb.record_success()
            latency_ms = (time.monotonic() - start_time) * 1000
            return response, latency_ms

        except TimeoutError as exc:
            logger.warning("LLM request timed out (attempt %d)", total_attempts)
            timeout_retries += 1
            if timeout_retries > 1:
                cb.record_failure()
                raise HTTPException(status_code=504, detail="LLM request timed out after retry") from exc
            await asyncio.sleep(linear_backoff)
            continue

        except AdapterRateLimitError as exc:
            logger.warning("Rate limited (attempt %d)", total_attempts)
            if total_attempts > max_429_retries:
                cb.record_failure()
                # If Claude rate limited and fallback allowed
                if decision.adapter_type == "claude" and _router.can_fallback_to_local(request.sensitivity):
                    return await _fallback_to_local(request)
                raise HTTPException(status_code=429, detail="Rate limit exceeded after retries") from exc
            wait_s = base_backoff * (2 ** (total_attempts - 1))
            await asyncio.sleep(wait_s)
            continue

        except (AdapterServerError, AdapterConnectionError) as exc:
            logger.warning("Server/connection error (attempt %d): %s", total_attempts, exc)
            if total_attempts > max_5xx_retries:
                cb.record_failure()
                # On 5xx with Claude, try fallback to local
                if decision.adapter_type == "claude" and _router.can_fallback_to_local(request.sensitivity):
                    return await _fallback_to_local(request)
                raise HTTPException(status_code=502, detail=f"LLM backend error: {exc}") from exc
            await asyncio.sleep(linear_backoff * total_attempts)
            continue

        except (AdapterTimeoutError, AdapterError) as exc:
            logger.warning("Adapter error (attempt %d): %s", total_attempts, exc)
            if total_attempts > max_5xx_retries:
                cb.record_failure()
                if decision.adapter_type == "claude" and _router.can_fallback_to_local(request.sensitivity):
                    return await _fallback_to_local(request)
                raise HTTPException(status_code=502, detail=f"LLM adapter error: {exc}") from exc
            await asyncio.sleep(linear_backoff)
            continue

        except AdapterModelUnavailableError as exc:
            logger.warning("Model unavailable: %s", exc)
            cb.record_failure()
            raise HTTPException(status_code=503, detail=f"Model unavailable: {exc}") from exc

        except AdapterAuthError as exc:
            logger.error("Authentication error: %s", exc)
            raise HTTPException(status_code=500, detail=f"LLM auth error: {exc}") from exc


async def _fallback_to_local(request: ChatRequest) -> tuple[ChatResponse, float]:
    """Fallback to local model when Claude is unavailable."""
    logger.info("Falling back to local LLM")
    start_time = time.monotonic()

    local_model = _registry.default_local
    try:
        response = await _local_adapter.chat(request, local_model)
        _cb_local.record_success()
        latency_ms = (time.monotonic() - start_time) * 1000
        response.routing = RoutingInfo(
            target="local",
            reason="claude_unavailable_fallback",
            model_used=local_model,
        )
        return response, latency_ms
    except Exception as exc:
        _cb_local.record_failure()
        raise HTTPException(
            status_code=503,
            detail="All LLM backends are currently unavailable",
        ) from exc


# ── Exception handlers ───────────────────────────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error={
                "code": f"LLM_{'CLIENT' if exc.status_code < 500 else 'SERVER'}_ERROR",
                "message": exc.detail,
                "status_code": exc.status_code,
            }
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception in LLM Router")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error={
                "code": "LLM_INTERNAL_ERROR",
                "message": str(exc),
                "status_code": 500,
            }
        ).model_dump(),
    )
