# M4: 任务编排服务 任务清单

> 目录：`services/orchestration-service/` | 服务端口：8003

## 任务列表

### 项目初始化
- [x] M4-01 初始化 FastAPI 项目结构，创建 `services/orchestration-service/` 目录，配置依赖
- [x] M4-02 创建配置管理模块（Agent 最大迭代、tool 超时、任务总超时、队列名）
- [x] M4-03 配置 Celery worker 启动入口，注册 `orchestration` 队列
- [x] M4-04 创建 Jinja2 提示词模板目录 `templates/prompts/`，准备 4 种任务类型的模板占位

### 任务管理 API
- [x] M4-05 实现任务创建端点 `POST /api/projects/{project_id}/tasks`：参数校验 + 敏感度判定 + 写入 DB + dispatch Celery
- [x] M4-06 实现任务列表端点 `GET /api/projects/{project_id}/tasks`（分页 + 状态/类型过滤）
- [x] M4-07 实现任务详情端点 `GET /api/tasks/{task_id}`
- [x] M4-08 实现任务状态轮询端点 `GET /api/tasks/{task_id}/status`（精简版，仅 status + progress）
- [x] M4-09 实现任务取消端点 `POST /api/tasks/{task_id}/cancel`：调用 Celery revoke + 更新 status=cancelled
- [x] M4-10 实现任务重试端点 `POST /api/tasks/{task_id}/retry`：仅 failed 状态允许，创建新 Celery 任务
- [x] M4-11 实现任务状态机校验函数：只允许合法的状态转换（pending→running/cancelled, running→completed/failed/cancelled 等）

### Agent 引擎 — 核心循环
- [x] M4-12 实现 AgentState 数据结构：messages, retrieved_chunks, generated_sections, citations, plan, iteration, remaining_sections, tool_call_history
- [x] M4-13 实现 AgentStateManager：state 初始化、追加 messages、追加 chunks、追加 sections、更新 plan、保存 tool_call_history
- [x] M4-14 实现 AgentLoopRunner：while 循环（max_iterations=5），执行 plan → execute → observe → update_progress
- [x] M4-15 实现 Plan 步骤：构建 planning messages → 调用 LLM Router → 解析返回的 tool_call 或 finish 信号
- [x] M4-16 实现 Observe 步骤：将 tool 执行结果格式化追加到 state.messages
- [x] M4-17 实现 terminal 判定：action=="finish" 或 iteration>=MAX_ITERATIONS 或 state 含 fatal_error
- [x] M4-18 实现到达最大迭代时的兜底：使用已有 generated_sections 强制进入 format_output

### Agent 工具实现
- [x] M4-19 实现 ToolRegistry：注册/查找/列出所有可用 tool 的定义（name, description, parameters JSON schema）
- [x] M4-20 实现 tool `search_kb`：调用 kb-service `/internal/search`，结果追加到 state.retrieved_chunks，去重
- [x] M4-21 实现 tool `generate_section`：构建生成 prompt（系统提示 + 目标章节 + context chunks + 已生成内容），调用 LLM Router，解析带 [ref:] 的输出
- [x] M4-22 实现 tool `verify_citations`：调用 citation-service `/internal/citations/verify`，更新 state.citations 置信度
- [x] M4-23 实现 tool `extract_key_claims`：调用 LLM Router 提取结构化论点列表（claim + source_ref + methodology）
- [x] M4-24 实现 tool `compare_policies`：调用 LLM Router 生成政策对比文本 + 对比矩阵
- [x] M4-25 实现 tool `format_output`：收集所有 sections + citations → 调用 output-service `/internal/output/generate`
- [x] M4-26 实现 tool 调用通用框架：调用前记录 tool_call_history → 设置超时（60s）→ 重试1次 → 异常隔离

### Agent 提示词模板
- [x] M4-27 实现 literature_review 提示词模板（Jinja2）：角色定义 + 知识源摘要 + 输出结构要求 + inline 引用规范
- [x] M4-28 实现 policy_draft 提示词模板（Jinja2）：政策草案特有的结构要求（背景/依据/措施/实施/评估）
- [x] M4-29 实现 policy_comparison 提示词模板（Jinja2）：比较维度 + 矩阵格式要求
- [x] M4-30 实现 tech_interpretation 提示词模板（Jinja2）：技术标准解读 + 合规影响分析结构
- [x] M4-31 实现 System Prompt 构建器：组装角色 + 知识源摘要 + 输出格式规范 + 可用工具 + 约束条件

### 任务类型工作流
- [x] M4-32 实现 literature_review 工作流编排：全局论点检索 → 按章节逐步生成 → 每章 verify → 最后 format
- [x] M4-33 实现 policy_draft 工作流编排：政策背景检索 → 依据/措施/实施/评估 逐步生成 → verify → format
- [x] M4-34 实现 policy_comparison 工作流编排：各政策要素提取 → 多维度对比 → 优劣势分析 → 效果比较 → format
- [x] M4-35 实现 tech_interpretation 工作流编排：标准原文检索 → 条款解读 → 合规影响 → 实施建议 → format

### 敏感度判定
- [x] M4-36 实现敏感度分析器：规则1（内部文档→high）、规则2（policy_draft→high）、规则3（用户指定优先）、规则4（默认 low）
- [x] M4-37 敏感度结果写入 task 记录（sensitivity 字段），传递给 LLM Router 用于路由决策

### 进度追踪
- [x] M4-38 实现进度更新函数：每个 tool 执行后更新 analysis_tasks.progress JSONB（step/step_index/total_steps_estimate/message）
- [x] M4-39 实现 total_steps_estimate 动态调整：根据工作流类型预设初始值，Agent 运行中可动态修正
- [x] M4-40 实现进度详情扩展（details 字段）：当前章节名、已检索 chunk 数、已生成 token 数

### 容错与超时
- [x] M4-41 实现 tool 调用超时处理（60s）：超时 → 重试 1 次 → 仍超时则跳过该 tool，记录 warning
- [x] M4-42 实现 LLM 返回格式不可解析的 fallback：正则兜底提取 tool_call → 连续 2 次失败 → 终止任务
- [x] M4-43 实现 citation 大量 uncertain 时的处理：记录 warning 日志，继续输出但标记置信度
- [x] M4-44 实现 Celery 任务级超时（30 min）：SoftTimeLimitExceeded → 调用 format_output 兜底 → 标记 failed

### 输出与导出 API
- [x] M4-45 实现输出预览端点 `GET /api/tasks/{task_id}/output`：返回 Markdown 格式内容
- [x] M4-46 实现引用列表端点 `GET /api/tasks/{task_id}/output/citations`
- [x] M4-47 实现单个引用详情端点 `GET /api/tasks/{task_id}/output/citations/{citation_id}`
- [x] M4-48 实现文件导出端点 `GET /api/tasks/{task_id}/export?format=docx|md|xlsx|pptx`：返回文件流

### 测试
- [x] M4-49 编写任务状态机转换测试
- [x] M4-50 编写 Agent 循环 mock 测试（mock LLM 返回 tool_call/finish，验证循环次数）
- [x] M4-51 编写 tool 调用超时和重试逻辑测试
- [x] M4-52 编写敏感度判定规则测试
- [x] M4-53 编写 literature_review 端到端集成测试（mock 依赖服务）
- [x] M4-54 编写到达最大迭代后的兜底输出测试