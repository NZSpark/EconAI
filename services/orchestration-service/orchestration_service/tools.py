"""Agent tools — ToolRegistry + 6 tool implementations (M4-19 through M4-26).

Tools:
    search_kb          — Hybrid search via KB service (M4-20)
    generate_section   — LLM-powered section generation (M4-21)
    verify_citations   — Citation verification via citation service (M4-22)
    extract_key_claims — LLM-powered claim extraction (M4-23)
    compare_policies   — LLM-powered policy comparison (M4-24)
    format_output      — Multi-format output generation (M4-25)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

import httpx

from orchestration_service.config import settings
from orchestration_service.schemas import ToolCallRecord
from orchestration_service.state import AgentState

logger = logging.getLogger(__name__)

# ── LLM Router / dependent service HTTP client ──────────────────────────────

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(settings.agent_tool_timeout_s))
    return _http_client


def reset_http_client() -> None:
    global _http_client
    if _http_client is not None:
        _http_client = None


# ── Tool call protocol ──────────────────────────────────────────────────────


class ToolFunc(Protocol):
    """Signature for a tool implementation function."""

    async def __call__(self, args: dict[str, Any], state: AgentState) -> dict[str, Any]: ...


# ── M4-19: ToolRegistry ─────────────────────────────────────────────────────


class ToolRegistry:
    """Registry of available Agent tools with lookup and LLM-compatible definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolFunc] = {}
        self._descriptions: dict[str, str] = {}
        self._parameters: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: ToolFunc, description: str, parameters: dict[str, Any]) -> None:
        self._tools[name] = func
        self._descriptions[name] = description
        self._parameters[name] = parameters

    def get(self, name: str) -> ToolFunc | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions in OpenAI-compatible format for LLM tool_choice."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": self._descriptions.get(name, ""),
                    "parameters": self._parameters.get(name, {}),
                },
            }
            for name in self._tools
        ]


# ── Tool call framework (M4-26) ─────────────────────────────────────────────


async def _run_with_timeout_and_retry(
    tool_name: str,
    tool_func: ToolFunc,
    args: dict[str, Any],
    state: AgentState,
    timeout_s: float = 60.0,
    max_retries: int = 1,
) -> dict[str, Any]:
    """Execute a tool with timeout and retry logic (M4-26, M4-41)."""

    start = time.monotonic()
    last_error: str | None = None

    for attempt in range(max_retries + 1):
        try:
            result = await asyncio.wait_for(tool_func(args, state), timeout=timeout_s)
            elapsed_ms = (time.monotonic() - start) * 1000

            state.tool_call_history.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    tool_args=args,
                    result_summary=_summarize_result(tool_name, result),
                    elapsed_ms=round(elapsed_ms, 2),
                    success=True,
                )
            )
            return result

        except TimeoutError:
            last_error = "Tool call timed out"
            logger.warning("Tool '%s' timed out (attempt %d/%d)", tool_name, attempt + 1, max_retries + 1)
            if attempt >= max_retries:
                break

        except Exception as exc:
            last_error = str(exc)
            logger.warning("Tool '%s' failed (attempt %d/%d): %s", tool_name, attempt + 1, max_retries + 1, exc)
            if attempt >= max_retries:
                break

    elapsed_ms = (time.monotonic() - start) * 1000
    state.tool_call_history.append(
        ToolCallRecord(
            tool_name=tool_name,
            tool_args=args,
            result_summary=f"Failed after {max_retries + 1} attempts: {last_error}",
            elapsed_ms=round(elapsed_ms, 2),
            success=False,
            error_message=last_error,
        )
    )

    logger.warning("Tool '%s' skipped due to persistent failure: %s", tool_name, last_error)
    return {"error": last_error, "skipped": True}


def _summarize_result(tool_name: str, result: dict[str, Any]) -> str:
    """Create a short human-readable summary of a tool result."""
    if tool_name == "search_kb":
        n = len(result.get("chunks", result.get("results", [])))
        return f"Retrieved {n} chunks"
    if tool_name == "generate_section":
        wc = result.get("word_count", 0)
        return f"Generated {wc} words"
    if tool_name == "verify_citations":
        s = result.get("summary", {})
        return f"Verified: {s.get('total', 0)} total, {s.get('direct', 0)} direct"
    if tool_name == "extract_key_claims":
        n = len(result.get("claims", []))
        return f"Extracted {n} claims"
    if tool_name == "compare_policies":
        return "Policy comparison generated"
    if tool_name == "format_output":
        return f"Output generated: {result.get('output_id', '')}"
    return "ok"


# ── M4-20: search_kb ────────────────────────────────────────────────────────


_SEARCH_KB_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query string"},
        "filters": {"type": "object", "description": "Optional filters (document_ids, chunk_types)"},
        "top_k": {"type": "integer", "description": "Number of results to return", "default": 10},
    },
    "required": ["query"],
}


async def _search_kb(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """Call kb-service /internal/search (M4-20)."""
    client = get_http_client()

    body: dict[str, Any] = {
        "query": args["query"],
        "top_k": args.get("top_k", 10),
        "project_id": state.project_id,
        "filters": args.get("filters", {}),
    }

    try:
        resp = await client.post(f"{settings.kb_service_url}/internal/search", json=body)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("KB search HTTP error: %s", exc)
        return {"chunks": [], "total_hits": 0, "search_time_ms": 0, "error": str(exc)}

    results = data.get("results", [])

    # Add chunks to state with dedup (M4-20)
    state.add_chunks(results)

    return {
        "chunks": results,
        "total_hits": data.get("total_hits", len(results)),
        "search_time_ms": data.get("search_time_ms", 0),
    }


# ── M4-21: generate_section ─────────────────────────────────────────────────


_GENERATE_SECTION_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "section_goal": {"type": "string", "description": "What this section should accomplish"},
        "section_title": {"type": "string", "description": "Title of the section to generate"},
        "context_chunk_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of chunks to use as context",
        },
    },
    "required": ["section_goal", "section_title"],
}


async def _generate_section(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """Call LLM Router to generate a section (M4-21)."""
    client = get_http_client()
    section_title = str(args.get("section_title", ""))
    section_goal = str(args.get("section_goal", ""))

    # Build context from selected chunks
    chunk_ids = args.get("context_chunk_ids", [])
    context_text = _build_context_text(state, chunk_ids)

    # Build prompt
    system_prompt = (
        f"You are an economic policy analysis assistant. Generate a well-structured section "
        f'for the task: "{state.title}". Always cite sources using [ref:doc_id:page_range] format. '
        f"Write in academic style with clear logic and evidence-based arguments."
    )

    user_prompt = f"## Section Goal\n{section_goal}\n\n## Section Title\n{section_title}\n\n"
    if context_text:
        user_prompt += f"## Reference Context\n{context_text}\n\n"
    user_prompt += (
        "Generate the section content with inline citations in [ref:doc_id:page_range] format. "
        "Keep the output focused and well-structured."
    )

    payload: dict[str, Any] = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "sensitivity": state.sensitivity,
        "task_id": state.task_id,
    }

    try:
        resp = await client.post(f"{settings.llm_router_url}/internal/llm/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("LLM Router HTTP error during generate_section: %s", exc)
        return {"content": f"[Generation failed: {exc}]", "word_count": 0}

    content = ""
    choices = data.get("choices", [])
    if choices:
        msg = choices[0].get("message", {})
        content = msg.get("content", "")

    word_count = len(content.split()) if content else 0

    # Store in state
    state.add_section(section_title, content, word_count)

    return {"content": content, "word_count": word_count}


def _build_context_text(state: AgentState, chunk_ids: list[str] | None) -> str:
    """Build combined context text from retrieved chunks."""
    if not chunk_ids:
        # Use all retrieved chunks if no specific IDs
        chunks = state.retrieved_chunks
    else:
        id_set = set(chunk_ids)
        chunks = [c for c in state.retrieved_chunks if c.chunk_id in id_set]

    lines: list[str] = []
    for i, ch in enumerate(chunks):
        lines.append(f"[Chunk {i + 1}] doc:{ch.document_id} (score:{ch.score:.3f})\n{ch.content}\n")
    return "\n".join(lines)


# ── M4-22: verify_citations ─────────────────────────────────────────────────


_VERIFY_CITATIONS_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Text containing [ref:...] markers to verify"},
        "chunk_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of context chunks for verification",
        },
    },
    "required": ["text"],
}


async def _verify_citations(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """Call citation-service /internal/citations/verify (M4-22)."""
    client = get_http_client()

    chunk_ids = args.get("chunk_ids", [])
    context_chunks = _build_context_chunks_for_verify(state, chunk_ids)

    body: dict[str, Any] = {
        "text": args["text"],
        "context_chunks": context_chunks,
    }

    try:
        resp = await client.post(f"{settings.citation_service_url}/internal/citations/verify", json=body)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Citation service HTTP error: %s", exc)
        return {"citations": [], "summary": {"total": 0, "direct": 0, "fuzzy": 0, "uncertain": 0}, "error": str(exc)}

    citations = data.get("citations", [])
    state.update_citations(citations)

    # M4-43: warn on many uncertain citations
    uncertain_count = data.get("summary", {}).get("uncertain", 0)
    if uncertain_count > 3:
        logger.warning("Task %s: %d uncertain citations detected", state.task_id, uncertain_count)

    return {"citations": citations, "summary": data.get("summary", {})}


def _build_context_chunks_for_verify(state: AgentState, chunk_ids: list[str]) -> list[dict[str, Any]]:
    """Build context chunk list for citation verification."""
    if chunk_ids:
        id_set = set(chunk_ids)
        chunks = [c for c in state.retrieved_chunks if c.chunk_id in id_set]
    else:
        chunks = state.retrieved_chunks

    return [
        {
            "chunk_id": ch.chunk_id,
            "document_id": ch.document_id,
            "content": ch.content,
            "page_start": 0,
            "page_end": 0,
        }
        for ch in chunks
    ]


# ── M4-23: extract_key_claims ───────────────────────────────────────────────


_EXTRACT_CLAIMS_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Text to extract claims from"},
    },
    "required": ["text"],
}


async def _extract_key_claims(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """Call LLM Router to extract key claims (M4-23)."""
    client = get_http_client()

    text = str(args.get("text", ""))
    system_prompt = (
        "Extract key claims from the provided text. For each claim, identify: "
        "the claim statement itself, any source references, and the methodology used. "
        "Output as a JSON array of objects with fields: claim, source_ref, methodology."
    )

    payload: dict[str, Any] = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract key claims from:\n\n{text}"},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
        "sensitivity": state.sensitivity,
        "task_id": state.task_id,
    }

    try:
        resp = await client.post(f"{settings.llm_router_url}/internal/llm/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("LLM Router HTTP error during extract_key_claims: %s", exc)
        return {"claims": []}

    content = ""
    choices = data.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")

    # Parse claims from LLM response (try JSON, fallback to text)
    claims = _parse_claims(content)
    return {"claims": claims}


def _parse_claims(raw: str) -> list[dict[str, Any]]:
    """Parse claim extraction results from LLM response."""
    import json as json_module

    # Try JSON parse
    try:
        parsed = json_module.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "claims" in parsed:
            return parsed["claims"]
    except (json_module.JSONDecodeError, TypeError):
        pass

    # Fallback: extract JSON array from text
    import re

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            return json_module.loads(match.group(0))
        except (json_module.JSONDecodeError, TypeError):
            pass

    return []


# ── M4-24: compare_policies ─────────────────────────────────────────────────


_COMPARE_POLICIES_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "policies": {
            "type": "array",
            "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}},
            "description": "List of policies to compare",
        },
        "dimensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Comparison dimensions",
        },
    },
    "required": ["policies", "dimensions"],
}


async def _compare_policies(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """Call LLM Router to compare policies (M4-24)."""
    client = get_http_client()

    policies = args.get("policies", [])
    dimensions = args.get("dimensions", [])

    policies_text = "\n".join(
        f"- **{p.get('name', f'Policy {i + 1}')}**: {p.get('description', '')}" for i, p in enumerate(policies)
    )
    dimensions_text = ", ".join(dimensions) if dimensions else "key aspects"

    system_prompt = (
        "You are an economic policy analyst. Compare the provided policies along the specified dimensions. "
        "For each dimension, identify similarities and differences. Include a comparison matrix."
    )

    user_prompt = (
        f"## Policies to Compare\n{policies_text}\n\n"
        f"## Comparison Dimensions\n{dimensions_text}\n\n"
        "Provide a detailed comparison analysis and a comparison matrix."
    )

    payload: dict[str, Any] = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "sensitivity": state.sensitivity,
        "task_id": state.task_id,
    }

    try:
        resp = await client.post(f"{settings.llm_router_url}/internal/llm/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("LLM Router HTTP error during compare_policies: %s", exc)
        return {"comparison": f"[Comparison failed: {exc}]", "matrix": []}

    content = ""
    choices = data.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")

    # Build matrix from policy names × dimensions
    policy_names = [str(p.get("name", f"Policy {i + 1}")) for i, p in enumerate(policies)]
    matrix: list[list[str]] = [["Dimension"] + policy_names]
    for dim in dimensions:
        matrix.append([str(dim)] + ["" for _ in policies])

    return {"comparison": content, "matrix": matrix}


# ── M4-25: format_output ────────────────────────────────────────────────────


_FORMAT_OUTPUT_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Generated sections to format",
        },
        "citations": {"type": "object", "description": "Verified citations mapping"},
        "format": {"type": "string", "description": "Output format (md, docx, xlsx, pptx)"},
    },
    "required": ["sections"],
}


async def _format_output(args: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """Call output-service /internal/output/generate (M4-25)."""
    client = get_http_client()

    sections_data = args.get("sections", [])
    if not sections_data and state.generated_sections:
        sections_data = [{"title": s.title, "level": 1, "content": s.content} for s in state.generated_sections]

    citations_data = args.get("citations", {})
    if not citations_data and state.citations:
        citations_data = {
            ref_id: {"ref_id": c.ref_id, "confidence": c.confidence, "sentence": c.sentence}
            for ref_id, c in state.citations.items()
        }

    formats = state.output_formats if state.output_formats else ["md", "docx"]

    body: dict[str, Any] = {
        "task_id": state.task_id,
        "title": state.title,
        "sections": sections_data if isinstance(sections_data, list) else [],
        "citations": (
            list(citations_data.values())
            if isinstance(citations_data, dict)
            else citations_data
            if isinstance(citations_data, list)
            else []
        ),
        "formats": formats,
        "metadata": {
            "author": "EconAI",
            "date": "",
            "keywords": [],
        },
    }

    try:
        resp = await client.post(f"{settings.output_service_url}/internal/output/generate", json=body)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Output service HTTP error: %s", exc)
        return {"output_id": "", "storage_path": "", "error": str(exc)}

    outputs = data.get("outputs", [])
    first = outputs[0] if outputs else {}
    return {"output_id": first.get("output_id", ""), "storage_path": first.get("storage_path", ""), "outputs": outputs}


# ── Registry initialisation ─────────────────────────────────────────────────


def create_tool_registry() -> ToolRegistry:
    """Create and populate the standard tool registry (M4-19)."""
    reg = ToolRegistry()

    reg.register(
        "search_kb",
        _search_kb,
        "Search the knowledge base using hybrid retrieval (vector + BM25 + reranker)",
        _SEARCH_KB_PARAMS,
    )
    reg.register(
        "generate_section",
        _generate_section,
        "Generate a section of the analysis report with inline citations",
        _GENERATE_SECTION_PARAMS,
    )
    reg.register(
        "verify_citations",
        _verify_citations,
        "Verify inline citations in generated text against source chunks",
        _VERIFY_CITATIONS_PARAMS,
    )
    reg.register(
        "extract_key_claims",
        _extract_key_claims,
        "Extract key claims and arguments from text with source references",
        _EXTRACT_CLAIMS_PARAMS,
    )
    reg.register(
        "compare_policies",
        _compare_policies,
        "Compare multiple policies across specified dimensions",
        _COMPARE_POLICIES_PARAMS,
    )
    reg.register(
        "format_output",
        _format_output,
        "Generate final formatted output in requested formats (md, docx, xlsx, pptx)",
        _FORMAT_OUTPUT_PARAMS,
    )

    return reg
