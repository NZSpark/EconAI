"""敏感度分析器（M4-36, M4-37）。

根据文档敏感度确定 LLM 路由方向。

规则（按优先级）:
    1. 用户显式设置敏感度 → 直接使用
    2. 用户显式设置 llm_preference → 根据偏好覆盖
    3. 内部文档 → high
    4. policy_draft 任务类型 → high
    5. 默认 → low
"""

from __future__ import annotations

from orchestration_service.schemas import CreateTaskRequest, SensitivityResult


def determine_sensitivity(request: CreateTaskRequest, is_internal: bool = False) -> SensitivityResult:
    """分析任务参数，返回敏感度级别 + 原因。"""

    # 规则 1: 用户显式设置敏感度 — 直接覆盖
    if request.sensitivity and request.sensitivity in ("high", "low"):
        return SensitivityResult(
            level=request.sensitivity,
            reason=f"用户显式设置敏感度为 '{request.sensitivity}'",
        )

    # 规则 2: 用户 llm_preference 覆盖自动检测
    if request.llm_preference and request.llm_preference.value != "auto":
        return SensitivityResult(
            level="high" if request.llm_preference.value == "local" else "low",
            reason=f"用户显式设置 llm_preference 为 '{request.llm_preference.value}'",
        )

    # 规则 3: 内部文档
    if is_internal:
        return SensitivityResult(
            level="high",
            reason="任务使用内部/机密文档 — 路由到本地 LLM",
        )

    # 规则 4: policy_draft 始终视为敏感
    if request.type.value == "policy_draft":
        return SensitivityResult(
            level="high",
            reason="政策起草任务包含敏感的内部政策分析",
        )

    # 规则 5: 默认
    return SensitivityResult(
        level="low",
        reason="未检测到敏感文档；默认使用云端 LLM",
    )
