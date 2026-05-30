"""PolicyAI Task Orchestration Service (M4) — FastAPI application.

Port 8003. Provides:
  - GET  /health                                      Health check
  - POST /api/projects/{project_id}/tasks             Create analysis task
  - GET  /api/projects/{project_id}/tasks             List project tasks
  - GET  /api/tasks/{task_id}                         Task detail
  - GET  /api/tasks/{task_id}/status                  Task status (polling)
  - POST /api/tasks/{task_id}/cancel                  Cancel task
  - POST /api/tasks/{task_id}/retry                   Retry failed task
  - GET  /api/tasks/{task_id}/output                  Output preview
  - GET  /api/tasks/{task_id}/output/citations        Citation list
  - GET  /api/tasks/{task_id}/output/citations/{cid}  Citation detail
  - GET  /api/tasks/{task_id}/export                  Export file download
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from orchestration_service.agent_loop import AgentLoopRunner
from orchestration_service.config import settings
from orchestration_service.progress import ProgressTracker
from orchestration_service.schemas import (
    CitationDetailResponse,
    CitationItem,
    CreateTaskRequest,
    CreateTaskResponse,
    OutputPreviewResponse,
    TaskDetailResponse,
    TaskListItem,
    TaskListResponse,
    TaskStatusResponse,
)
from orchestration_service.sensitivity import determine_sensitivity
from orchestration_service.state import AgentState
from orchestration_service.status_machine import (
    assert_valid_transition,
)
from orchestration_service.task_workflows import (
    get_initial_sections,
    get_workflow_plan,
    render_system_prompt,
)
from orchestration_service.tools import create_tool_registry, reset_http_client
from shared.metrics import setup_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── In-memory storage (MVP, no DB dependency for tests) ────────────────────

_tasks: dict[str, dict[str, Any]] = {}
_outputs: dict[str, Any] = {}
_tool_registry = create_tool_registry()


# ── Lifespan ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _tool_registry
    _tool_registry = create_tool_registry()
    logger.info(
        "Orchestration Service ready on port %d. %d tools registered.",
        settings.service_port,
        len(_tool_registry.list_names()),
    )
    yield
    reset_http_client()
    logger.info("Orchestration Service shutting down.")


app = FastAPI(
    title="PolicyAI Task Orchestration Service",
    version="0.1.0",
    lifespan=lifespan,
)

setup_metrics(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, object]:
    """健康检查 — reports agent configuration and defaults."""
    return {
        "status": "ok",
        "service": settings.service_name,
        "config": {
            "agent_max_iterations": settings.agent_max_iterations,
            "agent_tool_timeout_s": settings.agent_tool_timeout_s,
            "task_timeout_minutes": settings.task_timeout_minutes,
            "default_output_formats": settings.default_output_formats,
        },
        "dependencies": {
            "llm_router": settings.llm_router_url,
            "kb_service": settings.kb_service_url,
            "citation_service": settings.citation_service_url,
            "output_service": settings.output_service_url,
        },
    }


# ── Helper: build task detail ───────────────────────────────────────────────


def _build_detail(task_id: str) -> TaskDetailResponse:
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )
    return TaskDetailResponse(
        task_id=t["task_id"],
        project_id=t["project_id"],
        type=t["type"],
        title=t["title"],
        description=t.get("description", ""),
        status=t["status"],
        progress=t.get("progress"),
        params=t.get("params", {}),
        llm_route=t.get("llm_route", ""),
        sensitivity=t.get("sensitivity", "low"),
        iteration_count=t.get("iteration_count", 0),
        error_message=t.get("error_message"),
        created_by=t.get("created_by", ""),
        created_at=t.get("created_at"),
        started_at=t.get("started_at"),
        completed_at=t.get("completed_at"),
    )


# ── M4-05: Create task ──────────────────────────────────────────────────────


@app.post("/api/projects/{project_id}/tasks", status_code=201, response_model=CreateTaskResponse)
async def create_task(project_id: str, body: CreateTaskRequest) -> CreateTaskResponse:
    """创建新的分析任务并异步调度执行。
    
    创建流程：
    1. 生成唯一任务 ID
    2. 执行敏感度分析（M4-36）：决定使用本地还是云端 LLM
    3. 构建 system prompt（M4-31）：根据任务类型、标题、分析参数生成提示词
    4. 生成工作流计划（M4-27-30）：根据任务类型规划执行步骤
    5. 存储任务记录到内存（MVP）或数据库
    6. 通过 asyncio.create_task 在后台启动 Agent 循环
    """
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    # 敏感度分析：根据文档来源和任务类型决定 LLM 路由
    sensitivity_result = determine_sensitivity(body)

    # 构建系统提示词（模板渲染）
    system_prompt = render_system_prompt(
        task_type=body.type.value,
        title=body.title,
        description=body.description,
        focus_areas=body.analysis_params.focus_areas,
        comparison_dimensions=body.analysis_params.comparison_dimensions,
    )

    # 根据任务类型获取工作流计划和初始章节列表
    workflow_plan = get_workflow_plan(body.type.value)
    initial_sections = get_initial_sections(body.type.value)

    # 存储任务记录（MVP 阶段使用内存字典，生产环境应使用数据库）
    _tasks[task_id] = {
        "task_id": task_id,
        "project_id": project_id,
        "type": body.type.value,
        "title": body.title,
        "description": body.description,
        "status": "pending",
        "progress": None,
        "params": body.model_dump(),
        "llm_route": "cloud" if sensitivity_result.level == "low" else "local",
        "sensitivity": sensitivity_result.level,
        "sensitivity_reason": sensitivity_result.reason,
        "iteration_count": 0,
        "error_message": None,
        "created_by": "system",
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        # 内部字段（以下划线开头，不暴露给 API）
        "_system_prompt": system_prompt,
        "_workflow_plan": workflow_plan,
        "_initial_sections": initial_sections,
        "_output_formats": body.output_formats,
    }

    # 异步启动 Agent 循环（不阻塞 HTTP 响应）
    asyncio.create_task(_run_agent(task_id))

    return CreateTaskResponse(task_id=task_id, status="pending", created_at=now)


# ── M4-06: List tasks ───────────────────────────────────────────────────────


@app.get("/api/projects/{project_id}/tasks", response_model=TaskListResponse)
async def list_tasks(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    type: str | None = Query(None),
) -> TaskListResponse:
    """列出 tasks for a project with pagination and optional filters."""
    items = [
        t
        for t in _tasks.values()
        if t["project_id"] == project_id
        and (status is None or t["status"] == status)
        and (type is None or t["type"] == type)
    ]

    # Sort by created_at descending
    items.sort(key=lambda t: t.get("created_at") or datetime.min.replace(tzinfo=UTC), reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    task_items = [
        TaskListItem(
            task_id=t["task_id"],
            type=t["type"],
            title=t["title"],
            status=t["status"],
            progress=t.get("progress"),
            created_by=t.get("created_by", ""),
            created_at=t.get("created_at"),
        )
        for t in page_items
    ]

    pages = max(1, (total + page_size - 1) // page_size)
    return TaskListResponse(items=task_items, total=total, page=page, page_size=page_size, pages=pages)


# ── M4-07: Task detail ──────────────────────────────────────────────────────


@app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task_detail(task_id: str) -> TaskDetailResponse:
    """获取 full task details."""
    return _build_detail(task_id)


# ── M4-08: Task status (polling) ────────────────────────────────────────────


@app.get("/api/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Lightweight status endpoint for frontend polling."""
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )
    return TaskStatusResponse(status=t["status"], progress=t.get("progress"))


# ── M4-09: Cancel task ──────────────────────────────────────────────────────


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, Any]:
    """Cancel a pending or running task."""
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )

    try:
        assert_valid_transition(t["status"], "cancelled")
    except ValueError as exc:
        raise HTTPException(
            status_code=409, detail={"error": {"code": "INVALID_TRANSITION", "message": str(exc)}}
        ) from exc

    t["status"] = "cancelled"
    t["completed_at"] = datetime.now(UTC)
    return {"task_id": task_id, "status": "cancelled"}


# ── M4-10: Retry task ───────────────────────────────────────────────────────


@app.post("/api/tasks/{task_id}/retry")
async def retry_task(task_id: str) -> dict[str, Any]:
    """Retry a failed task."""
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )

    if t["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "INVALID_STATE",
                    "message": (
                        f"Task {task_id} is not in 'failed' state "
                        f"(current: {t['status']}). Only failed tasks can be retried."
                    ),
                }
            },
        )

    t["status"] = "running"
    t["started_at"] = datetime.now(UTC)
    t["completed_at"] = None
    t["error_message"] = None
    t["iteration_count"] = 0
    t["progress"] = None

    asyncio.create_task(_run_agent(task_id))
    return {"task_id": task_id, "status": "running", "message": "Task retry dispatched."}


# ── M4-45: Output preview ───────────────────────────────────────────────────


@app.get("/api/tasks/{task_id}/output", response_model=OutputPreviewResponse)
async def preview_output(task_id: str) -> OutputPreviewResponse:
    """获取 Markdown preview of task output."""
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )

    if t["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "NOT_COMPLETED",
                    "message": f"Task {task_id} is not completed (status: {t['status']}).",
                }
            },
        )

    output_data = _outputs.get(task_id, {})
    return OutputPreviewResponse(
        task_id=task_id,
        title=t.get("title", ""),
        content=output_data.get("content", ""),
        format=output_data.get("format", "markdown"),
    )


# ── M4-46: Citation list ────────────────────────────────────────────────────


@app.get("/api/tasks/{task_id}/output/citations", response_model=list[CitationItem])
async def list_citations(task_id: str) -> list[CitationItem]:
    """列出 all citations for a completed task."""
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )

    citations_data = _outputs.get(f"{task_id}:citations", [])
    return [
        CitationItem(
            ref_id=c.get("ref_id", ""),
            sentence=c.get("sentence", ""),
            confidence=c.get("confidence", "uncertain"),
            document_title=c.get("document_title", ""),
            source_page=c.get("source_page", ""),
        )
        for c in citations_data
    ]


# ── M4-47: Citation detail ──────────────────────────────────────────────────


@app.get("/api/tasks/{task_id}/output/citations/{citation_id}", response_model=CitationDetailResponse)
async def get_citation_detail(task_id: str, citation_id: str) -> CitationDetailResponse:
    """获取 a single citation detail."""
    citations_data = _outputs.get(f"{task_id}:citations", [])
    for c in citations_data:
        if c.get("ref_id") == citation_id:
            return CitationDetailResponse(
                ref_id=c["ref_id"],
                sentence=c.get("sentence", ""),
                confidence=c.get("confidence", "uncertain"),
                source=c.get("source"),
                verified_at=c.get("verified_at"),
            )

    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "NOT_FOUND",
                "message": f"Citation {citation_id} not found for task {task_id}.",
            }
        },
    )


# ── M4-48: Export file ──────────────────────────────────────────────────────


@app.get("/api/tasks/{task_id}/export")
async def export_output(
    task_id: str,
    format: str = Query("docx", description="Output format: md, docx, xlsx, pptx"),
) -> dict[str, Any]:
    """Export endpoint — returns file metadata (actual download handled by output-service)."""
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Task {task_id} not found."}}
        )

    if t["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "NOT_COMPLETED", "message": f"Task {task_id} is not completed."}},
        )

    output_data = _outputs.get(f"{task_id}:{format}")
    if not output_data:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"No {format} output found for task {task_id}."}},
        )

    return {
        "task_id": task_id,
        "format": format,
        "filename": f"{t.get('title', 'output')}.{_ext_for_format(format)}",
        "storage_path": output_data.get("storage_path", ""),
        "size_bytes": output_data.get("size_bytes", 0),
    }


def _ext_for_format(fmt: str) -> str:
    return {"md": "md", "markdown": "md", "docx": "docx", "xlsx": "xlsx", "pptx": "pptx"}.get(fmt, fmt)


# ── M4-03: Agent runner (async background task) ─────────────────────────────


async def _run_agent(task_id: str) -> None:
    """在后台执行任务的 Agent 循环（M4-03）。
    
    Agent 循环流程：
    1. 验证状态转换：pending/running → running（M4-11）
    2. 构建 AgentState：包含任务上下文、工作流计划、剩余章节
    3. 初始化 ProgressTracker：追踪每个步骤的完成进度
    4. 创建 AgentLoopRunner：Agent 核心循环（搜索→分析→生成→迭代）
    5. 设置 30 分钟整体超时（M4-44）
    6. 存储结果：Markdown 内容 + 引用列表
    7. 更新任务状态：completed / failed
    """
    t = _tasks.get(task_id)
    if not t:
        return

    # 验证状态转换（M4-11）：允许从 pending 或 retry 转到 running
    current_status = t["status"]
    if current_status != "running":
        try:
            assert_valid_transition(current_status, "running")
        except ValueError:
            logger.warning("Task %s: Cannot transition %s → running", task_id, current_status)
            return
        t["status"] = "running"
        t["started_at"] = datetime.now(UTC)

    try:
        # 构建 Agent 状态对象
        state = AgentState(
            task_id=task_id,
            project_id=t["project_id"],
            task_type=t["type"],
            title=t["title"],
            description=t.get("description", ""),
            sensitivity=t.get("sensitivity", "low"),
            output_formats=t.get("_output_formats", ["md", "docx"]),
        )
        state.plan = t.get("_workflow_plan", "")
        state.remaining_sections = list(t.get("_initial_sections", []))

        # 初始化进度追踪器
        progress = ProgressTracker(t["type"])

        # 创建 Agent 循环运行器
        runner = AgentLoopRunner(
            state=state,
            tool_registry=_tool_registry,
            system_prompt=t.get("_system_prompt", ""),
            progress=progress,
        )

        # M4-44：30 分钟整体超时保护
        try:
            final_state = await asyncio.wait_for(runner.run(), timeout=settings.task_timeout_minutes * 60)
        except TimeoutError:
            logger.warning("Task %s: Timeout after %d minutes", task_id, settings.task_timeout_minutes)
            # 超时后强制格式化当前已有的输出内容
            await runner._force_format_output()
            final_state = runner.state

        # 存储输出结果（Markdown 预览）
        _outputs[task_id] = {
            "content": _build_markdown_content(final_state),
            "format": "markdown",
        }

        # 存储引用列表（供 citation-service 查询）
        _outputs[f"{task_id}:citations"] = [
            {
                "ref_id": c.ref_id,
                "sentence": c.sentence,
                "confidence": c.confidence,
                "document_title": "",
                "source_page": "",
            }
            for c in final_state.citations.values()
        ]

        # 检查是否有致命错误
        if final_state.fatal_error:
            t["status"] = "failed"
            t["error_message"] = final_state.fatal_error
        else:
            t["status"] = "completed"

        t["iteration_count"] = final_state.iteration

    except Exception as exc:
        logger.exception("Task %s: Unhandled error", task_id)
        t["status"] = "failed"
        t["error_message"] = str(exc)

    finally:
        t["completed_at"] = datetime.now(UTC)


def _build_markdown_content(state: AgentState) -> str:
    """构建 a simple Markdown preview from generated sections."""
    lines = [f"# {state.title}\n"]
    for section in state.generated_sections:
        lines.append(f"## {section.title}\n")
        lines.append(section.content)
        lines.append("")
    if not state.generated_sections:
        lines.append("*No sections were generated.*")
    return "\n".join(lines)


# ── Exception handlers ──────────────────────────────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "ORCH_ERROR", "message": str(detail)}},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception in Orchestration Service")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "ORCH_INTERNAL_ERROR", "message": str(exc)}},
    )
