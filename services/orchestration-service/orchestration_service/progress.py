"""Progress tracker (M4-38, M4-39, M4-40).

Updates analysis_tasks.progress JSONB after each Agent step.
Provides dynamic total_steps_estimate adjustment.
"""

from __future__ import annotations

from orchestration_service.schemas import ProgressDetails, TaskProgress

# 默认 steps estimate per task type
_PRESET_ESTIMATES: dict[str, int] = {
    "literature_review": 8,
    "policy_draft": 7,
    "tech_interpretation": 6,
    "policy_comparison": 7,
}


class ProgressTracker:
    """Tracks and updates Agent loop progress."""

    def __init__(self, task_type: str) -> None:
        self._task_type = task_type
        self._total = _PRESET_ESTIMATES.get(task_type, 6)
        self._step_index = 0

    def update(
        self,
        step: str,
        message: str,
        section_title: str = "",
        chunks_retrieved: int = 0,
        generation_tokens: int = 0,
    ) -> TaskProgress:
        """Advance progress and return the new progress object."""
        self._step_index += 1
        return TaskProgress(
            step=step,
            step_index=self._step_index,
            total_steps_estimate=self._total,
            message=message,
            details=ProgressDetails(
                section_title=section_title,
                chunks_retrieved=chunks_retrieved,
                generation_tokens=generation_tokens,
            ),
        )

    def adjust_total(self, new_total: int) -> None:
        """Dynamically adjust the total steps estimate (M4-39)."""
        new_total = max(new_total, self._step_index)
        self._total = new_total

    @property
    def total_estimate(self) -> int:
        return self._total
