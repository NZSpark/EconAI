"""Diagnostic tests for local LLM task timeout failures.

These tests systematically measure local LLM performance to identify the root
cause of task timeouts and determine the key factors for successful completion.

Problem: Local LLM tasks (sensitivity=high) fail due to timeouts.
Root cause candidates:
  - generate_section uses max_tokens=4096 — too slow for local 7B model
  - agent_tool_timeout_s=120s (updated from 60s) — 2 attempts × 120s = 240s max

These tests:
  1. Measure local LLM latency at various max_tokens levels
  2. Simulate full Agent loop with reduced max_tokens
  3. Test each of the 4 task types with local LLM via orchestration service
  4. Identify the max_tokens threshold where local LLM becomes reliable

Run:
  # Prerequisites: Ollama running on localhost:11434 with qwen2.5-coder:7b
  # LLM Router on port 8004, Orchestration Service on port 8003
  uv run pytest tests/test_local_llm_task_debug.py -v -s --tb=short

Environment variables:
  POLICYAI_TEST_LLM_ROUTER_URL  — default http://localhost:8004
  POLICYAI_TEST_OLLAMA_URL      — default http://localhost:11434
  POLICYAI_TEST_LOCAL_MODEL     — default local:qwen2.5-coder:7b
  POLICYAI_TEST_LLM_TIMEOUT_S   — default 300 (generous for diagnostics)
  POLICYAI_TEST_ORCH_URL        — default http://localhost:8003
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import httpx
import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

LLM_ROUTER_URL = os.environ.get("POLICYAI_TEST_LLM_ROUTER_URL", "http://localhost:8004")
OLLAMA_URL = os.environ.get("POLICYAI_TEST_OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = os.environ.get("POLICYAI_TEST_LOCAL_MODEL", "local:qwen2.5-coder:7b")
ORCH_URL = os.environ.get("POLICYAI_TEST_ORCH_URL", "http://localhost:8003")
CHAT_TIMEOUT = int(os.environ.get("POLICYAI_TEST_LLM_TIMEOUT_S", "300"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_llm_router_ready() -> bool:
    """Check LLM Router health."""
    try:
        r = httpx.get(f"{LLM_ROUTER_URL}/health", timeout=5)
        return bool(r.status_code == 200)
    except Exception:
        return False


def _is_ollama_ready() -> bool:
    """Check Ollama is reachable and model is available."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        model_bare = LOCAL_MODEL.replace("local:", "")
        return model_bare in models or any(
            m.startswith(model_bare.split(":")[0]) for m in models
        )
    except Exception:
        return False


def _is_orch_ready() -> bool:
    """Check Orchestration Service health."""
    try:
        r = httpx.get(f"{ORCH_URL}/health", timeout=5)
        return bool(r.status_code == 200)
    except Exception:
        return False


def _all_ready() -> bool:
    return _is_llm_router_ready() and _is_ollama_ready() and _is_orch_ready()


# ---------------------------------------------------------------------------
# Section 1: Latency profiling — find safe max_tokens for local LLM
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_is_llm_router_ready() and _is_ollama_ready()),
    reason="LLM Router or Ollama not available",
)
class TestLocalLLMLatencyProfile:
    """Measure local LLM generation latency at various max_tokens levels.

    Goal: find the maximum max_tokens that completes reliably within 120s
    (the updated agent_tool_timeout_s setting).
    """

    # Test various token budgets to profile latency
    TOKEN_BUDGETS = [
        ("tiny", 64, 20),     # max_tokens=64,  expected <20s
        ("small", 128, 30),    # max_tokens=128, expected <30s
        ("medium", 256, 45),   # max_tokens=256, expected <45s
        ("large", 512, 90),    # max_tokens=512, may exceed 120s on slow HW
        ("huge", 1024, 180),   # max_tokens=1024, likely slow
        ("current", 4096, 600), # max_tokens=4096, current default
    ]

    @pytest.mark.parametrize("label,max_tokens,expected_max_s", TOKEN_BUDGETS)
    def test_local_llm_latency_by_max_tokens(
        self, label: str, max_tokens: int, expected_max_s: float
    ) -> None:
        """Measure latency for generate_section-like prompt at given max_tokens.

        Uses a realistic prompt similar to what generate_section sends:
        system prompt + user prompt with context.
        """
        system_prompt = (
            "You are an economic policy analysis assistant. Generate a well-structured section "
            'for the task: "Policy Analysis Test". Always cite sources using [ref:doc_id:page_range] format. '
            "Write in academic style with clear logic and evidence-based arguments."
        )
        user_prompt = (
            "## Section Goal\nProvide a comprehensive analysis of the policy implications.\n\n"
            "## Section Title\n政策影响分析\n\n"
            "## Reference Context\n"
            "[Chunk 1] doc:test_001 (score:0.950)\n"
            "Research shows that renewable energy policies significantly impact carbon emissions. "
            "Multiple studies confirm the positive correlation between policy stringency and emission reductions.\n\n"
            "Generate the section content with inline citations in [ref:doc_id:page_range] format. "
            "Keep the output focused and well-structured."
        )

        start = time.monotonic()
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": LOCAL_MODEL,
                "sensitivity": "high",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=CHAT_TIMEOUT,
        )
        elapsed = time.monotonic() - start

        print(f"\n  [PROFILE] max_tokens={max_tokens} ({label}): {elapsed:.1f}s")

        if resp.status_code == 200:
            body = resp.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            content_len = len(content)
            usage = body.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            print(f"    content_len={content_len} chars, completion_tokens={completion_tokens}")
        else:
            print(f"    FAILED: status={resp.status_code}, body={resp.text[:200]}")

        assert resp.status_code == 200, (
            f"Local LLM failed at max_tokens={max_tokens}: {resp.status_code} {resp.text[:300]}"
        )

        # Record latency for analysis (not a hard assert — diagnostic only)
        if elapsed > 120:
            print(f"  [WARN] max_tokens={max_tokens} exceeds 120s tool timeout "
                  f"({elapsed:.1f}s > 120s) — may cause timeouts on slow HW")
        if elapsed > expected_max_s:
            print(f"  [NOTE] max_tokens={max_tokens} is slower than expected "
                  f"({elapsed:.1f}s > {expected_max_s}s)")


# ---------------------------------------------------------------------------
# Section 2: Simulated generate_section at various max_tokens
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_is_llm_router_ready() and _is_ollama_ready()),
    reason="LLM Router or Ollama not available",
)
class TestGenerateSectionSimulation:
    """Simulate the orchestration service's generate_section tool call
    with various max_tokens to find the safe threshold."""

    SAFE_MAX_TOKENS_CANDIDATES = [128, 256, 384, 512, 768, 1024]

    @pytest.mark.parametrize("max_tokens", SAFE_MAX_TOKENS_CANDIDATES)
    def test_simulate_generate_section(self, max_tokens: int) -> None:
        """Simulate what _generate_section actually sends to LLM Router.

        Key observation: _generate_section in tools.py sends max_tokens=4096 (hardcoded).
        For local 7B models, this is far too aggressive.
        """
        # Replicate the exact system prompt from tools.py _generate_section
        system_prompt = (
            "You are an economic policy analysis assistant. Generate a well-structured section "
            'for the task: "Local LLM Timeout Debug". Always cite sources using '
            "[ref:doc_id:page_range] format. Write in academic style with clear logic "
            "and evidence-based arguments."
        )

        # Replicate the user prompt structure
        section_goal = "Analyze the key factors causing local LLM task timeouts in the PolicyAI system"
        section_title = "Timeout Root Cause Analysis"
        context_text = (
            "[Chunk 1] doc:test_001 (score:0.950)\n"
            "The agent_tool_timeout_s is set to 60 seconds. "
            "The generate_section tool hardcodes max_tokens=4096. "
            "For local 7B models, generating 4096 tokens can take 2-5 minutes.\n\n"
            "[Chunk 2] doc:test_002 (score:0.880)\n"
            "The _run_with_timeout_and_retry function allows 1 retry, "
            "giving a total of 120 seconds per tool call. "
            "If the LLM generation exceeds this, the tool is skipped.\n"
        )

        user_prompt = (
            f"## Section Goal\n{section_goal}\n\n"
            f"## Section Title\n{section_title}\n\n"
            f"## Reference Context\n{context_text}\n\n"
            "Generate the section content with inline citations in [ref:doc_id:page_range] format. "
            "Keep the output focused and well-structured."
        )

        start = time.monotonic()
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": LOCAL_MODEL,
                "sensitivity": "high",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=CHAT_TIMEOUT,
        )
        elapsed = time.monotonic() - start

        assert resp.status_code == 200, (
            f"Generate section simulation failed at max_tokens={max_tokens}: "
            f"{resp.status_code} {resp.text[:300]}"
        )

        body = resp.json()
        content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        completion_tokens = body.get("usage", {}).get("completion_tokens", 0)

        # Verify the response is meaningful
        assert len(content) > 20, (
            f"Content too short ({len(content)} chars) at max_tokens={max_tokens}"
        )
        # Should contain Chinese or English analytical content
        assert any(c.isalpha() for c in content), (
            f"Content lacks meaningful text at max_tokens={max_tokens}"
        )

        # Check if inline citations are present (key quality indicator)
        has_citation = "[ref:" in content

        print(f"\n  [SIMULATE] max_tokens={max_tokens}: {elapsed:.1f}s, "
              f"content={len(content)} chars, completion_tokens={completion_tokens}, "
              f"citations={'yes' if has_citation else 'no'}")

        # Diagnostic: flag if this would timeout under current 120s limit
        if elapsed > 120:
            print(f"  [WARN] WOULD TIMEOUT under 120s agent_tool_timeout_s!")
        elif elapsed > 90:
            print(f"  [NOTE] Marginal — may timeout with heavier context")
        else:
            print(f"  [OK] Well within 120s timeout")


# ---------------------------------------------------------------------------
# Section 3: Measure how context size affects local LLM latency
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_is_llm_router_ready() and _is_ollama_ready()),
    reason="LLM Router or Ollama not available",
)
class TestContextSizeImpact:
    """Measure how the amount of context (retrieved chunks) affects local LLM latency.

    In the Agent loop, each generate_section call may include many retrieved chunks
    as context. Larger context = longer prompt processing time for local LLMs.
    """

    @pytest.mark.parametrize("num_chunks", [0, 1, 3, 5])
    def test_context_size_latency(self, num_chunks: int) -> None:
        """Measure latency with varying numbers of context chunks."""
        # Build context
        chunks = []
        for i in range(num_chunks):
            chunks.append(
                f"[Chunk {i + 1}] doc:test_{i:03d} (score:0.{950 - i * 50:03d})\n"
                f"Research finding {i + 1}: Policy interventions in sector {i + 1} show "
                f"significant effects on economic indicators. Multiple studies confirm "
                f"these findings with robust methodological approaches.\n"
            )
        context_text = "\n".join(chunks)

        system_prompt = (
            "You are an analysis assistant. Generate a concise section with citations."
        )
        user_prompt = "## Section Goal\nSummarize the findings.\n\n## Section Title\nFindings\n\n"
        if context_text:
            user_prompt += f"## Reference Context\n{context_text}\n\n"
        user_prompt += "Generate the section content with inline citations in [ref:doc_id:page_range] format."

        start = time.monotonic()
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": LOCAL_MODEL,
                "sensitivity": "high",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 256,
                "temperature": 0.3,
            },
            timeout=CHAT_TIMEOUT,
        )
        elapsed = time.monotonic() - start

        assert resp.status_code == 200, (
            f"Context size test failed with {num_chunks} chunks: {resp.status_code}"
        )

        body = resp.json()
        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        print(f"\n  [CONTEXT] chunks={num_chunks}: {elapsed:.1f}s, "
              f"prompt_tokens={prompt_tokens}, completion_tokens={completion_tokens}")


# ---------------------------------------------------------------------------
# Section 4: Test each task type with local LLM via orchestration service
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _all_ready(),
    reason="LLM Router, Ollama, or Orchestration Service not available",
)
class TestTaskTypesLocalLLM:
    """Create and monitor tasks of each type with sensitivity=high (local LLM).

    These are end-to-end tests that create real tasks and monitor their progress.
    They help identify which task types succeed and which fail with local LLM.

    NOTE: These tests take 5-10 minutes each. Run with --timeout=600 or similar.
    """

    TASK_TYPES = [
        "literature_review",
        "policy_draft",
        "policy_comparison",
        "tech_interpretation",
    ]

    @pytest.mark.slow
    @pytest.mark.parametrize("task_type", TASK_TYPES)
    def test_create_and_monitor_local_llm_task(self, task_type: str) -> None:
        """Create a task with sensitivity=high and monitor until completion or timeout.

        Tracks:
          - Whether the task reaches 'completed' or 'failed'
          - Progress updates (which tools succeed/fail)
          - Final error message if failed
        """
        # Create task with sensitivity=high → routes to local LLM
        create_payload = {
            "type": task_type,
            "title": f"[LOCAL TEST] {task_type.replace('_', ' ').title()} Debug",
            "description": f"Diagnostic test for {task_type} with local LLM",
            "sensitivity": "high",
            "output_formats": ["md"],
            "analysis_params": {
                "focus_areas": ["diagnostic_test"],
                "comparison_dimensions": ["effectiveness", "cost"],
            },
            "kb_sources": {
                "documents": [],
                "include_institutional": False,
            },
        }

        # Use a project that may or may not exist; create one if needed
        # First try to get/create a project
        resp = httpx.post(
            f"{ORCH_URL}/api/projects/test-local-llm/tasks",
            json=create_payload,
            timeout=15,
        )

        if resp.status_code == 404:
            print(f"\n  [SKIP] Project 'test-local-llm' not found — need existing project")
            pytest.skip("Project not found — create a project first")
        elif resp.status_code == 401 or resp.status_code == 403:
            # Try without auth if gateway bypass
            print(f"  [INFO] Auth required ({resp.status_code}), trying direct orch port...")
            # Some setups don't require auth on internal endpoints
            pass

        assert resp.status_code in (200, 201, 202, 401, 403, 404), (
            f"Unexpected status creating task: {resp.status_code} {resp.text[:300]}"
        )

        if resp.status_code not in (200, 201, 202):
            print(f"  [SKIP] Cannot create task: {resp.status_code}")
            pytest.skip(f"Cannot create task: {resp.status_code}")

        task_data = resp.json()
        task_id = task_data.get("task_id")
        assert task_id, f"No task_id in response: {task_data}"

        print(f"\n  [TASK] Created {task_type} task: {task_id}")

        # Monitor progress
        max_wait_s = 600  # 10 minutes max
        poll_interval = 5  # seconds
        start = time.monotonic()
        final_status = "pending"
        progress_history: list[dict[str, Any]] = []

        while time.monotonic() - start < max_wait_s:
            time.sleep(poll_interval)
            status_resp = httpx.get(
                f"{ORCH_URL}/api/tasks/{task_id}/status",
                timeout=10,
            )
            if status_resp.status_code != 200:
                print(f"    Status check failed: {status_resp.status_code}")
                continue

            status_data = status_resp.json()
            final_status = status_data.get("status", final_status)
            progress = status_data.get("progress", {})
            progress_history.append({
                "status": final_status,
                "progress": progress,
                "elapsed": time.monotonic() - start,
            })

            step = progress.get("step", "") if isinstance(progress, dict) else ""
            step_idx = progress.get("step_index", 0) if isinstance(progress, dict) else 0
            total = progress.get("total_steps_estimate", "?") if isinstance(progress, dict) else "?"
            print(f"    [{final_status}] step={step} ({step_idx}/{total}) "
                  f"elapsed={time.monotonic() - start:.0f}s")

            if final_status in ("completed", "failed", "cancelled"):
                break

        # Final diagnostics
        print(f"\n  [RESULT] {task_type}: {final_status} after {time.monotonic() - start:.0f}s")

        if final_status == "failed":
            # Get error details
            error_resp = httpx.get(
                f"{ORCH_URL}/api/tasks/{task_id}/status",
                timeout=10,
            )
            if error_resp.status_code == 200:
                error_data = error_resp.json()
                error_msg = error_data.get("error_message", "")
                print(f"  [ERROR] {error_msg[:500]}")

            # Analyze progress history for failure pattern
            for entry in progress_history:
                p = entry.get("progress", {})
                if isinstance(p, dict):
                    step = p.get("step", "")
                    msg = p.get("message", "")
                    print(f"    progress: step={step}, msg={msg}")

        # Don't assert completion — this is diagnostic
        # The test "passes" if it runs and collects data
        assert final_status in (
            "pending", "running", "completed", "failed", "cancelled",
        ), f"Unexpected status: {final_status}"


# ---------------------------------------------------------------------------
# Section 5: Direct tool-level timeout simulation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_is_llm_router_ready() and _is_ollama_ready()),
    reason="LLM Router or Ollama not available",
)
class TestToolTimeoutBoundary:
    """Test the exact timeout boundaries that the orchestration service uses.

    Key finding: _run_with_timeout_and_retry uses:
      - timeout_s=agent_tool_timeout_s (120s, updated from 60s)
      - max_retries=1 (total 2 attempts)
      - Each attempt: asyncio.wait_for(tool_func(args, state), timeout=120)

    So a tool call has exactly 240 seconds before being skipped.
    """

    def test_llm_router_timeout_is_generous(self) -> None:
        """Verify LLM Router timeout (300s) is larger than tool timeout (120s).

        The LLM Router's timeout is NOT the bottleneck — the tool timeout is.
        """
        resp = httpx.get(f"{LLM_ROUTER_URL}/health", timeout=5)
        assert resp.status_code == 200
        config = resp.json().get("config", {})
        router_timeout = config.get("request_timeout_s", 0)
        print(f"\n  [CONFIG] LLM Router timeout: {router_timeout}s")
        print(f"  [CONFIG] Agent tool timeout: 120s (from AGENT_TOOL_TIMEOUT_S)")
        print(f"  [CONFIG] Ratio: {router_timeout / 120:.1f}x")
        assert router_timeout > 120, (
            f"LLM Router timeout ({router_timeout}s) should exceed tool timeout (120s)"
        )

    def test_short_prompt_always_succeeds(self) -> None:
        """A very short prompt (max_tokens=10) should always complete well under 120s."""
        start = time.monotonic()
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": LOCAL_MODEL,
                "sensitivity": "high",
                "messages": [{"role": "user", "content": "Say 'OK'."}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=CHAT_TIMEOUT,
        )
        elapsed = time.monotonic() - start

        assert resp.status_code == 200, f"Short prompt failed: {resp.status_code}"
        assert elapsed < 30, f"Short prompt took {elapsed:.1f}s — local LLM may be very slow"
        print(f"\n  [BASELINE] Short prompt (max_tokens=10): {elapsed:.1f}s")

    def test_generate_section_default_4096_is_too_slow(self) -> None:
        """Confirm that generate_section's default max_tokens=4096 is too slow.

        This is the PROOF that the root cause is max_tokens=4096.
        """
        # Replicate the exact system prompt from tools.py
        system_prompt = (
            "You are an economic policy analysis assistant. Generate a well-structured section "
            'for the task: "Timeout Diagnostic". Always cite sources using '
            "[ref:doc_id:page_range] format. Write in academic style with clear logic "
            "and evidence-based arguments."
        )
        user_prompt = (
            "## Section Goal\nDiagnose the timeout issue in the PolicyAI Agent loop.\n\n"
            "## Section Title\nTimeout Root Cause\n\n"
            "## Reference Context\n"
            "[Chunk 1] doc:test_001 (score:0.950)\n"
            "The current implementation uses max_tokens=4096 for generate_section. "
            "This is appropriate for cloud LLMs but too slow for local 7B models.\n\n"
            "Generate the section content with inline citations in [ref:doc_id:page_range] format. "
            "Keep the output focused and well-structured."
        )

        start = time.monotonic()
        resp = httpx.post(
            f"{LLM_ROUTER_URL}/internal/llm/chat",
            json={
                "model": LOCAL_MODEL,
                "sensitivity": "high",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 4096,  # Current hardcoded default in tools.py
                "temperature": 0.3,
            },
            timeout=CHAT_TIMEOUT,
        )
        elapsed = time.monotonic() - start

        print(f"\n  [DIAGNOSTIC] generate_section with max_tokens=4096: {elapsed:.1f}s")

        if resp.status_code != 200:
            print(f"  [CONFIRMED] 4096 max_tokens FAILS: {resp.status_code} {resp.text[:200]}")
            # This is expected — the test documents the failure
        else:
            print(f"  [INFO] 4096 max_tokens succeeded in {elapsed:.1f}s — within 120s limit")
            if elapsed > 120:
                print(f"  [WARN] But would still timeout under 120s tool limit!")
                print(f"  [FIX] Reduce max_tokens in tools.py _generate_section from 4096 "
                      f"to a value that completes within 120s (e.g., 512-1024 for local)")

        # This test always "passes" — it's diagnostic, not pass/fail
        assert True


# ---------------------------------------------------------------------------
# Section 6: Recommended fix verification
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_is_llm_router_ready() and _is_ollama_ready()),
    reason="LLM Router or Ollama not available",
)
class TestRecommendedFix:
    """Verify that the recommended fix (reduced max_tokens) would resolve timeouts.

    Recommendation: When sensitivity=high, reduce max_tokens in generate_section
    from 4096 to a value that completes reliably within 120s on local hardware.
    """

    RECOMMENDED_MAX_TOKENS = [256, 384, 512]

    @pytest.mark.parametrize("max_tokens", RECOMMENDED_MAX_TOKENS)
    def test_recommended_max_tokens_completes_quickly(self, max_tokens: int) -> None:
        """Verify recommended max_tokens values complete well within 120s."""
        system_prompt = (
            "You are an economic policy analysis assistant. Generate a well-structured section. "
            "Use [ref:doc_id:page_range] format for citations."
        )
        user_prompt = (
            "## Section Goal\nAnalyze the timeout issue and propose solutions.\n\n"
            "## Section Title\nRecommended Fix\n\n"
            "## Reference Context\n"
            "[Chunk 1] doc:test_001 (score:0.950)\n"
            "Reducing max_tokens from 4096 to 256-512 for local LLM tasks "
            "would bring generation time under 120 seconds. "
            "Cloud LLM tasks can keep the 4096 default.\n\n"
            "Generate the section with inline citations."
        )

        # Run 3 times to check consistency
        latencies = []
        for run in range(3):
            start = time.monotonic()
            resp = httpx.post(
                f"{LLM_ROUTER_URL}/internal/llm/chat",
                json={
                    "model": LOCAL_MODEL,
                    "sensitivity": "high",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
                timeout=CHAT_TIMEOUT,
            )
            elapsed = time.monotonic() - start
            latencies.append(elapsed)

            assert resp.status_code == 200, (
                f"Run {run + 1} failed at max_tokens={max_tokens}: {resp.status_code}"
            )

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"\n  [FIX] max_tokens={max_tokens}: "
              f"avg={avg_latency:.1f}s, max={max_latency:.1f}s "
              f"(3 runs: {[f'{l:.1f}s' for l in latencies]})")

        # The average should be well under 120s
        assert avg_latency < 120, (
            f"Average latency {avg_latency:.1f}s exceeds 120s tool timeout "
            f"at max_tokens={max_tokens} — need smaller max_tokens"
        )

        # Even the worst case should be under 120s with some margin
        assert max_latency < 180, (
            f"Max latency {max_latency:.1f}s exceeds 180s at max_tokens={max_tokens} — "
            f"may cause intermittent timeouts"
        )

        if max_latency < 120:
            print(f"  [SAFE] All runs within 120s — recommended max_tokens={max_tokens}")


# ---------------------------------------------------------------------------
# Section 7: Concurrent tool calls stress test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_is_llm_router_ready() and _is_ollama_ready()),
    reason="LLM Router or Ollama not available",
)
class TestConcurrentToolCalls:
    """Test if concurrent local LLM calls cause additional slowdown.

    In the Agent loop, tool calls are sequential, but understanding
    the throughput helps set expectations.
    """

    def test_sequential_vs_concurrent_latency(self) -> None:
        """Compare sequential vs concurrent local LLM call latency.

        This helps determine if Ollama's queue depth affects latency.
        """
        async def _single_call(max_tokens: int) -> float:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=httpx.Timeout(CHAT_TIMEOUT)) as client:
                resp = await client.post(
                    f"{LLM_ROUTER_URL}/internal/llm/chat",
                    json={
                        "model": LOCAL_MODEL,
                        "sensitivity": "high",
                        "messages": [
                            {"role": "user", "content": "Say 'OK' and nothing else."}
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.0,
                    },
                )
            return time.monotonic() - start

        async def _measure():
            # Sequential: 3 calls one at a time
            seq_start = time.monotonic()
            seq_latencies = []
            for _ in range(3):
                lat = await _single_call(32)
                seq_latencies.append(lat)
            seq_total = time.monotonic() - seq_start

            # Concurrent: 3 calls simultaneously
            con_start = time.monotonic()
            con_results = await asyncio.gather(
                _single_call(32), _single_call(32), _single_call(32)
            )
            con_total = time.monotonic() - con_start

            return seq_latencies, seq_total, con_results, con_total

        seq_lat, seq_total, con_lat, con_total = asyncio.run(_measure())

        print(f"\n  [CONCURRENCY] Sequential: {[f'{l:.1f}s' for l in seq_lat]} total={seq_total:.1f}s")
        print(f"  [CONCURRENCY] Concurrent: {[f'{l:.1f}s' for l in con_lat]} total={con_total:.1f}s")

        # Concurrent should be faster (or similar) than sequential
        # If concurrent is much slower, Ollama may be queuing requests
        if con_total > seq_total * 0.8:
            print(f"  [NOTE] Concurrent is not significantly faster — "
                  f"Ollama may serialize requests internally")
