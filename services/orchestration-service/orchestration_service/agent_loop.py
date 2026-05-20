"""Agent loop runner (M4-14 through M4-18).

The core ReAct-variant Agent loop:
    Plan → Execute → Observe → Update Progress → repeat

Max iterations: 5. Terminal conditions: finish action, max iterations reached, or fatal error.
"""

from __future__ import annotations

import contextlib
import json as json_module
import logging
import re
import uuid
from typing import Any

import httpx

from orchestration_service.config import settings
from orchestration_service.progress import ProgressTracker
from orchestration_service.state import AgentState
from orchestration_service.tools import ToolRegistry, get_http_client

logger = logging.getLogger(__name__)


class AgentLoopRunner:
    """Executes the Agent loop for a single task (M4-14)."""

    def __init__(
        self,
        state: AgentState,
        tool_registry: ToolRegistry,
        system_prompt: str,
        progress: ProgressTracker,
    ) -> None:
        self.state = state
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt
        self.progress = progress
        self._parse_failure_count = 0

    async def run(self) -> AgentState:
        """Execute the full Agent loop (M4-14)."""
        max_iter = settings.agent_max_iterations or 5

        # Initialize conversation with system prompt
        self.state.add_system(self.system_prompt)
        self.state.add_user(self._build_initial_user_message())

        while self.state.iteration < max_iter:
            self.state.increment_iteration()
            logger.info(
                "Task %s: Agent iteration %d/%d, remaining sections: %s",
                self.state.task_id,
                self.state.iteration,
                max_iter,
                self.state.remaining_sections,
            )

            # M4-15: Plan step — call LLM to decide next action
            action = await self._plan()

            # M4-17: Terminal check — finish signal or error
            if isinstance(action, str) or self.state.fatal_error:
                if self.state.fatal_error:
                    logger.warning("Task %s: Fatal error — %s", self.state.task_id, self.state.fatal_error)
                else:
                    logger.info(
                        "Task %s: LLM signalled finish at iteration %d", self.state.task_id, self.state.iteration
                    )
                break

            # M4-15: Parse tool call from plan result
            tool_name, tool_args = action

            if tool_name is None:
                logger.warning("Task %s: No valid action from plan, retrying", self.state.task_id)
                continue

            # Execute the tool
            from orchestration_service.tools import _run_with_timeout_and_retry

            tool_func = self.tool_registry.get(tool_name)
            if tool_func is None:
                logger.warning("Task %s: Unknown tool '%s', skipping", self.state.task_id, tool_name)
                self.state.add_tool_result(
                    f"call_{uuid.uuid4().hex[:8]}", tool_name, f"Error: unknown tool '{tool_name}'"
                )
                continue

            result = await _run_with_timeout_and_retry(
                tool_name=tool_name,
                tool_func=tool_func,
                args=tool_args,
                state=self.state,
                timeout_s=settings.agent_tool_timeout_s,
            )

            # M4-16: Observe — add tool result to messages
            result_str = json_module.dumps(result, ensure_ascii=False, default=str)
            self.state.add_tool_result(
                tool_call_id=f"call_{uuid.uuid4().hex[:8]}",
                tool_name=tool_name,
                content=result_str[:4000],
            )

            # M4-38: Update progress
            progress_obj = self.progress.update(
                step=tool_name,
                message=f"Executed {tool_name}",
                section_title="",
                chunks_retrieved=self.state.total_retrieved_chunks,
                generation_tokens=self.state.total_generation_tokens,
            )

            # Store progress on state for external access
            self.state._latest_progress = progress_obj  # type: ignore[attr-defined]

        # M4-18: Max iteration fallback — force format_output with available content
        if self.state.iteration >= max_iter and not self._has_finished():
            logger.warning(
                "Task %s: Reached max iterations (%d). Forcing format_output with %d sections.",
                self.state.task_id,
                max_iter,
                len(self.state.generated_sections),
            )
            await self._force_format_output()

        # Post-loop: always format output if not already done
        if not self._has_finished():
            await self._force_format_output()

        return self.state

    # ── M4-15: Plan step ─────────────────────────────────────────────────

    async def _plan(self) -> str | tuple[str | None, dict[str, Any]]:
        """Call LLM to decide next action. Returns 'finish' or (tool_name, tool_args)."""
        client = get_http_client()

        # Build planning prompt
        planning_msg = self._build_planning_message()
        self.state.add_user(planning_msg)

        tools = self.tool_registry.list_definitions()

        payload: dict[str, Any] = {
            "model": "auto",
            "messages": [msg.model_dump() for msg in self.state.messages],
            "temperature": 0.3,
            "max_tokens": 1024,
            "sensitivity": self.state.sensitivity,
            "task_id": self.state.task_id,
            "tools": tools,
        }

        try:
            resp = await client.post(f"{settings.llm_router_url}/internal/llm/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Task %s: LLM plan call failed: %s", self.state.task_id, exc)
            self._parse_failure_count += 1
            if self._parse_failure_count >= 2:
                self.state.fatal_error = "LLM plan call failed 2 consecutive times"
            return "finish" if self._parse_failure_count >= 2 else (None, {})

        choices = data.get("choices", [])
        if not choices:
            return (None, {})

        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        # M4-42: Try to parse finish signal or tool call
        if tool_calls:
            tc = tool_calls[0]
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = json_module.loads(func.get("arguments", "{}"))
            except (json_module.JSONDecodeError, TypeError):
                tool_args = {}

            self.state.add_assistant(tool_calls=tool_calls)
            return (tool_name, tool_args)

        # M4-42: Fallback — parse from content text
        if content:
            result = self._parse_action_from_text(content)
            if result is not None:
                self.state.add_assistant(content=content)
                return result

        # M4-42: Parsing failure
        self._parse_failure_count += 1
        logger.warning(
            "Task %s: Could not parse LLM output (failure %d/2)", self.state.task_id, self._parse_failure_count
        )
        self.state.add_assistant(content=content)

        if self._parse_failure_count >= 2:
            self.state.fatal_error = "LLM output unparseable 2 consecutive times"
            return "finish"

        return (None, {})

    def _parse_action_from_text(self, text: str) -> str | tuple[str, dict[str, Any]] | None:
        """M4-42: Regex-based fallback to extract tool_call or finish from LLM text."""
        # Check for explicit finish signals
        if re.search(r"(?i)\b(finish|done|complete|terminate|stop)\b", text):
            return "finish"

        # Try to find JSON tool call
        match = re.search(r'"name"\s*:\s*"(\w+)"', text)
        if not match:
            # Check if no more actions needed
            if re.search(r"(?i)(no more|nothing else|all done|all sections)", text):
                return "finish"
            return None

        tool_name = match.group(1)

        # Try to extract arguments JSON
        args_match = re.search(r'"arguments"\s*:\s*(\{.*?\})\s*\}', text, re.DOTALL)
        args: dict[str, Any] = {}
        if args_match:
            with contextlib.suppress(json_module.JSONDecodeError, TypeError):
                args = json_module.loads(args_match.group(1))

        # If arguments not found in tool_call format, try standalone JSON
        if not args:
            json_match = re.search(r"\{[^}]+\}", text)
            if json_match:
                with contextlib.suppress(json_module.JSONDecodeError, TypeError):
                    args = json_module.loads(json_match.group(0))

        return (tool_name, args)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_initial_user_message(self) -> str:
        """Build the initial user message describing the task."""
        parts = [
            f"Task: {self.state.title}",
            f"Type: {self.state.task_type}",
        ]
        if self.state.description:
            parts.append(f"Description: {self.state.description}")
        parts.append("Please plan and execute the analysis step by step using the available tools.")
        parts.append("Start by searching the knowledge base for relevant information.")
        return "\n".join(parts)

    def _build_planning_message(self) -> str:
        """Build the planning message for the current iteration."""
        completed = [s.title for s in self.state.generated_sections]
        remaining = self.state.remaining_sections

        parts = [
            f"Current iteration: {self.state.iteration}",
            f"Completed sections: {completed if completed else 'None yet'}",
            f"Remaining sections: {remaining if remaining else 'All assigned sections done'}",
            f"Chunks retrieved: {self.state.total_retrieved_chunks}",
        ]
        if self.state.plan:
            parts.insert(0, f"Current plan: {self.state.plan}")

        parts.append(
            "Decide the next action. If all sections are generated and verified, signal 'finish'. "
            "Otherwise, choose the next tool to call. Options: search_kb, generate_section, "
            "verify_citations, extract_key_claims, compare_policies, format_output, or finish."
        )
        return "\n".join(parts)

    def _has_finished(self) -> bool:
        """Check if format_output has already been called."""
        if not self.state.tool_call_history:
            return False
        return any(t.tool_name == "format_output" and t.success for t in self.state.tool_call_history)

    async def _force_format_output(self) -> None:
        """M4-18: Force format_output with whatever content is available."""
        from orchestration_service.tools import _format_output

        args = {
            "sections": [{"title": s.title, "level": 1, "content": s.content} for s in self.state.generated_sections],
            "citations": {
                ref_id: {"ref_id": c.ref_id, "confidence": c.confidence, "sentence": c.sentence}
                for ref_id, c in self.state.citations.items()
            },
        }
        try:
            await _format_output(args, self.state)
        except Exception as exc:
            logger.error("Task %s: Force format_output failed: %s", self.state.task_id, exc)
