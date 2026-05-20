"""Agent state management (M4-12, M4-13).

AgentState:
    messages          — LLM conversation history
    retrieved_chunks  — All retrieved KB chunks
    generated_sections — Completed sections
    citations         — ref_id → CitationInfo mapping
    plan              — Current execution plan text
    iteration         — Current iteration count
    remaining_sections — Sections yet to be generated
    tool_call_history — Record of all tool calls
"""

from __future__ import annotations

from orchestration_service.schemas import (
    ChunkInfo,
    CitationInfo,
    Message,
    SectionInfo,
    ToolCallRecord,
)


class AgentState:
    """Mutable state bag carried through the Agent loop."""

    def __init__(
        self,
        task_id: str,
        project_id: str,
        task_type: str,
        title: str,
        description: str = "",
        sensitivity: str = "low",
        output_formats: list[str] | None = None,
    ) -> None:
        self.task_id = task_id
        self.project_id = project_id
        self.task_type = task_type
        self.title = title
        self.description = description
        self.sensitivity = sensitivity
        self.output_formats: list[str] = output_formats or ["md", "docx"]

        # Conversation history
        self.messages: list[Message] = []

        # Knowledge base
        self.retrieved_chunks: list[ChunkInfo] = []

        # Output
        self.generated_sections: list[SectionInfo] = []
        self.citations: dict[str, CitationInfo] = {}

        # Planning
        self.plan: str = ""
        self.iteration: int = 0
        self.remaining_sections: list[str] = []

        # Audit
        self.tool_call_history: list[ToolCallRecord] = []

        # Error state
        self.fatal_error: str | None = None

    # ── Message helpers (M4-13) ──────────────────────────────────────────

    def add_message(self, role: str, content: str | None = None, **kwargs: object) -> None:
        """Append a message to the conversation history."""
        msg: dict[str, object] = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(kwargs)
        self.messages.append(Message(**msg))  # type: ignore[arg-type]

    def add_system(self, content: str) -> None:
        self.add_message("system", content)

    def add_user(self, content: str) -> None:
        self.add_message("user", content)

    def add_assistant(self, content: str | None = None, tool_calls: list[dict[str, object]] | None = None) -> None:
        kwargs: dict[str, object] = {}
        if tool_calls is not None:
            kwargs["tool_calls"] = tool_calls
        self.add_message("assistant", content, **kwargs)

    def add_tool_result(self, tool_call_id: str, tool_name: str, content: str) -> None:
        self.add_message("tool", content, tool_call_id=tool_call_id, name=tool_name)

    # ── Chunk management ─────────────────────────────────────────────────

    def add_chunks(self, chunks: list[dict[str, object]]) -> None:
        """Add retrieved chunks, deduplicating by chunk_id."""
        existing_ids = {c.chunk_id for c in self.retrieved_chunks}
        for ch in chunks:
            cid = str(ch.get("chunk_id", ""))
            if cid and cid not in existing_ids:
                existing_ids.add(cid)
                self.retrieved_chunks.append(
                    ChunkInfo(
                        chunk_id=cid,
                        document_id=str(ch.get("document_id", "")),
                        content=str(ch.get("content", "")),
                        score=float(str(ch.get("score", 0.0))),
                    )
                )

    # ── Section management ────────────────────────────────────────────────

    def add_section(self, title: str, content: str, word_count: int = 0) -> None:
        self.generated_sections.append(SectionInfo(title=title, content=content, word_count=word_count))
        # Remove from remaining if present
        if title in self.remaining_sections:
            self.remaining_sections.remove(title)

    # ── Citation management ───────────────────────────────────────────────

    def update_citations(self, verified: list[dict[str, object]]) -> None:
        """Merge verified citation results into state."""
        for cit in verified:
            ref_id = str(cit.get("ref_id", ""))
            if ref_id:
                self.citations[ref_id] = CitationInfo(
                    ref_id=ref_id,
                    confidence=str(cit.get("confidence", "uncertain")),
                    sentence=str(cit.get("sentence", "")),
                )

    # ── Progress helpers ──────────────────────────────────────────────────

    @property
    def total_retrieved_chunks(self) -> int:
        return len(self.retrieved_chunks)

    @property
    def total_generation_tokens(self) -> int:
        return sum(s.word_count for s in self.generated_sections)

    # ── Reset ─────────────────────────────────────────────────────────────

    def increment_iteration(self) -> int:
        self.iteration += 1
        return self.iteration
