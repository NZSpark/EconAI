# 从专用政策分析系统到通用知识库分析系统的升级分析

> **分析日期**: 2026-05-30
> **分析范围**: 完整追踪任务创建到完成的全链路代码调用流程，梳理扩展为通用系统所需的所有改动点

---

## 1. 背景

EconAI 当前定位于机构级经济政策分析系统，支持 4 种任务类型：

| 任务类型 | 英文标识 | 说明 |
|----------|----------|------|
| 文献综述 | `literature_review` | 对知识库中的文献进行综述分析 |
| 政策草案 | `policy_draft` | 按中国政府公文标准起草政策文件 |
| 政策比较 | `policy_comparison` | 对多个政策进行多维度比较分析 |
| 技术解读 | `tech_interpretation` | 解读技术标准/法规条款及合规影响 |

**核心洞察**：整个 Agent 引擎（ReAct 循环 + 6 个通用工具）完全与业务领域解耦，天然具备扩展为通用知识库分析系统的条件。增加新任务类型仅需**配置化注册**，无需修改核心引擎代码。

---

## 2. 系统架构分层与扩展点分析

### 2.1 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React + TypeScript)             │
│  TaskList.tsx          TaskOutput.tsx          labels.ts         │
│  (任务创建表单)          (结果展示)              (标签/颜色映射)      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ POST /api/projects/{id}/tasks
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Orchestration Service (FastAPI)                  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ sensitivity │  │ task_        │  │ app.py                │   │
│  │ .py         │  │ workflows.py │  │ (create_task +        │   │
│  │ (敏感度)     │  │ (工作流/模板)  │  │  _run_agent dispatch) │   │
│  └─────────────┘  └──────────────┘  └───────────┬───────────┘   │
│                                                  │               │
│  ┌───────────────────────────────────────────────┘               │
│  │  Agent Engine (通用引擎，无需改动)                               │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  │ agent_   │  │ tools.py │  │ state.py │  │ progress │    │
│  │  │ loop.py  │  │ (6 工具)  │  │ (Agent   │  │ .py      │    │
│  │  │ (ReAct)  │  │          │  │  状态)    │  │ (进度)    │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  └───────────────────────────────────────────────────────────────┘
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP (internal APIs)
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
     ┌────────────┐   ┌──────────────┐   ┌──────────────┐
     │ KB Service │   │ LLM Router   │   │ Citation     │
     │ (搜索/检索) │   │ (模型路由)    │   │ Service      │
     └────────────┘   └──────────────┘   │ (引用校验)    │
                                         └──────────────┘
```

### 2.2 已通用化的组件（新增任务类型无需修改）

以下组件与业务领域完全解耦，新增任何任务类型均可直接复用：

| 组件 | 文件 | 通用化方式 |
|------|------|-----------|
| **Agent 循环引擎** | `agent_loop.py` | 标准 ReAct 循环，通过 `_WORKFLOW_PLANS` 字典驱动，不依赖具体任务类型 |
| **6 个工具** | `tools.py` | `search_kb`、`generate_section`、`verify_citations`、`extract_key_claims`、`compare_policies`、`format_output` — 全部参数化，通过 ToolRegistry 动态注册 |
| **Agent 状态** | `state.py` | `AgentState` 是通用数据结构，字段不绑定任务类型 |
| **状态机** | `status_machine.py` | `pending → running → completed/failed/cancelled`，所有任务类型通用 |
| **LLM 路由敏感度** | `sensitivity.py` | 已有通用 fallback 逻辑（默认 `low`），仅 `policy_draft` 有特殊规则 |
| **输出展示** | `TaskOutput.tsx` | 统一 Markdown + 引用展示，不区分任务类型 |
| **Markdown 预览** | `MarkdownPreview.tsx` | 通用渲染组件 |
| **进度条** | `TaskProgress.tsx` | 通用 Step 组件 |
| **API Gateway** | `api-gateway/` | 透明代理，不感知 `task_type` |
| **输出服务** | `output-service/` | 统一 `format_output` 接口 |
| **知识库服务** | `kb-service/` | 统一 `search` 接口 |
| **引用校验服务** | `citation-service/` | 统一 `verify` 接口 |

---

## 3. 完整调用链路（以 `literature_review` 为例）

```
Step 1: 前端创建
  TaskList.tsx → handleCreate() → POST /api/projects/{id}/tasks
  参数: { type, title, description, focus_areas, output_formats }

Step 2: Orchestration Service 接收
  app.py: create_task()
  ├── determine_sensitivity(body)              → sensitivity.py
  ├── render_system_prompt(task_type, ...)      → task_workflows.py
  │   ├── 查找 "{task_type}.j2" 模板
  │   ├── Jinja2 渲染: 注入 title, description, focus_areas
  │   └── 嵌入 workflow_plan + system_prompt.j2 wrapper
  ├── get_workflow_plan(task_type)              → 读取 _WORKFLOW_PLANS[task_type]
  ├── get_initial_sections(task_type)           → 读取 _DEFAULT_SECTIONS[task_type]
  └── asyncio.create_task(_run_agent(task_id))

Step 3: Agent 循环执行
  agent_loop.py: AgentLoopRunner.run()
  while iteration < 5:
    ├── _plan() → POST llm-router/internal/llm/chat
    │   LLM 返回: tool_name + tool_args 或 "finish"
    ├── 执行工具 (tool_registry.get(tool_name))
    │   ├── search_kb       → POST kb-service/internal/search
    │   ├── generate_section → POST llm-router/internal/llm/chat
    │   ├── verify_citations → POST citation-service/internal/citations/verify
    │   ├── extract_key_claims → POST llm-router
    │   ├── compare_policies   → POST llm-router
    │   └── format_output     → POST output-service/internal/output/generate
    ├── observe → state.add_tool_result()
    └── progress.update(step, message)

Step 4: 完成
  _force_format_output() → 生成最终输出
  状态: running → completed

Step 5: 前端轮询结果
  GET /api/projects/{id}/tasks/{task_id}/output
  TaskOutput.tsx 渲染 Markdown + 引用列表
```

---

## 4. 新增任务类型所需改动清单

假设新增类型 `"new_type"`，需要改动 **7 个文件 + 1 个新建文件**，总改动量约 **50 行**。

### 4.1 必须改动的文件

#### A. `shared/models.py` — TaskType 枚举（1 行）

```python
class TaskType(StrEnum):
    literature_review = "literature_review"
    policy_draft = "policy_draft"
    policy_comparison = "policy_comparison"
    tech_interpretation = "tech_interpretation"
    new_type = "new_type"   # ← 新增
```

#### B. `templates/prompts/new_type.j2` — 新建提示词模板（~30 行）

```jinja2
You are performing a {{ task_type }} analysis.

## Task
Title: {{ title }}
Description: {{ description or 'Default description for this task type' }}

## Focus Areas
{% for area in focus_areas %}
- {{ area }}
{% endfor %}
{% if not focus_areas %}
- Area 1
- Area 2
- Area 3
{% endif %}

## Output Structure
1. 章节一 (Section One)
2. 章节二 (Section Two)
3. 章节三 (Section Three)
4. 章节四 (Section Four)
5. 章节五 (Section Five)

## Instructions
- Search the knowledge base for relevant information
- Generate each section with proper structure
- Verify all citations after each section
- Use [ref:doc_id:page_range] format for all citations
```

**关键设计点**：
- 模板通过 Jinja2 变量 `{{ title }}`、`{{ description }}`、`{{ focus_areas }}` 参数化
- 输出结构定义了 Agent 需要生成的章节列表，必须与 `_DEFAULT_SECTIONS` 保持一致
- `## Instructions` 控制 Agent 的行为策略

#### C. `task_workflows.py` — 三处字典新增（~30 行）

**c1) DEFAULT_TEMPLATES（约 line 148 之后）：** 嵌入默认模板（当模板目录不存在时的 fallback）

```python
"new_type.j2": """You are performing a {{ task_type }} analysis.

## Task
Title: {{ title }}
Description: {{ description or 'Default description' }}

## Output Structure
1. 章节一 (Section One)
2. 章节二 (Section Two)
3. 章节三 (Section Three)
4. 章节四 (Section Four)
5. 章节五 (Section Five)

## Instructions
- Search the knowledge base for relevant information
- Generate each section with proper structure
- Verify all citations after each section
- Use [ref:doc_id:page_range] format for all citations""",
```

**c2) _WORKFLOW_PLANS（约 line 197 之后）：** 定义 Agent 的步骤计划

```python
"new_type": """1. search_kb: Retrieve background information
2. generate_section: "章节一"
3. generate_section: "章节二"
4. search_kb: Retrieve supplementary data
5. generate_section: "章节三"
6. generate_section: "章节四"
7. generate_section: "章节五"
8. verify_citations: Verify all citations
9. format_output: Generate final output""",
```

**步骤计划设计原则**：
- `search_kb` 穿插在章节生成之间，确保 Agent 在生成前有充分的上下文
- 最后统一 `verify_citations` + `format_output`
- 可用工具：`search_kb`、`generate_section`、`verify_citations`、`extract_key_claims`、`compare_policies`、`format_output`
- 步骤数量决定 Agent 迭代次数，应在 `agent_max_iterations`（默认 5）范围内

**c3) _DEFAULT_SECTIONS（约 line 230 之后）：** 定义初始剩余章节列表

```python
"new_type": [
    "章节一",
    "章节二",
    "章节三",
    "章节四",
    "章节五",
],
```

#### D. `progress.py` — 进度预估（1 行）

```python
_PRESET_ESTIMATES: dict[str, int] = {
    "literature_review": 8,
    "policy_draft": 7,
    "tech_interpretation": 6,
    "policy_comparison": 7,
    "new_type": 9,   # ← 新增，应与 _WORKFLOW_PLANS 步骤数一致
}
```

#### E. `frontend/src/api/types.ts` — TypeScript 类型联合（1 行）

```typescript
export type TaskType =
  | 'literature_review'
  | 'policy_draft'
  | 'policy_comparison'
  | 'tech_interpretation'
  | 'new_type';  // ← 新增
```

#### F. `frontend/src/constants/labels.ts` — 标签和颜色（2 行）

```typescript
// taskTypeColorMap
new_type: 'green',   // ← 新增颜色

// taskTypeLabelMap
new_type: '新任务类型',   // ← 新增中文标签
```

#### G. `frontend/src/pages/TaskList.tsx` — 下拉选择器（1 行）

```tsx
// 在 Select options 中新增：
{ label: '新任务类型', value: 'new_type' },
```

### 4.2 可选改动

#### H. `sensitivity.py` — 敏感度规则（如需要特殊路由）

```python
# 仅当该任务类型需要特殊 LLM 路由时修改
if request.type.value == "new_type":
    return SensitivityResult(
        level="high",
        reason="New type tasks contain sensitive analysis",
    )
```

当前已有规则：
- `policy_draft` → 强制 `high`（本地 LLM）
- 用户显式设置 → 直接使用
- 默认 → `low`（云端 LLM）

#### I. `db/init/01-schema.sql` — 数据库 CHECK 约束

```sql
task_type VARCHAR(32) NOT NULL CHECK (
    task_type IN (
        'literature_review','policy_draft','policy_comparison','tech_interpretation','new_type'
    )
),
```

**注意**：如果使用 PostgreSQL，修改 CHECK 约束需要 `ALTER TABLE` 或重建约束。如果 `task_type` 在应用层（Pydantic 枚举）校验，数据库约束的更新可以延迟到下次 schema 迁移时统一处理。

---

## 5. 改动量总结

| 类别 | 文件 | 改动类型 | 行数 |
|------|------|----------|------|
| 共享类型 | `shared/models.py` | 枚举新增 | 1 |
| 提示词模板 | `templates/prompts/new_type.j2` | **新建文件** | ~30 |
| 工作流定义 | `task_workflows.py` | 3 处字典新增 | ~30 |
| 进度预估 | `progress.py` | 字典新增 | 1 |
| 前端类型 | `frontend/src/api/types.ts` | 联合类型新增 | 1 |
| 前端标签 | `frontend/src/constants/labels.ts` | 2 处映射新增 | 2 |
| 前端表单 | `frontend/src/pages/TaskList.tsx` | Select options 新增 | 1 |
| **必须改动小计** | **7 文件 + 1 新建** | | **~66 行** |
| 敏感度规则 | `sensitivity.py` | 按需新增 | 0~5 |
| 数据库约束 | `db/init/01-schema.sql` | CHECK 约束更新 | 1 |
| **可选改动小计** | **2 文件** | | **0~6 行** |
| **总计** | **9 文件 + 1 新建** | | **~70 行** |

### 5.1 无需改动的组件（10+ 个）

| 组件 | 原因 |
|------|------|
| `agent_loop.py` | 通用 ReAct 循环，通过 `_WORKFLOW_PLANS` 驱动 |
| `tools.py` | 6 个工具全部参数化，通过 ToolRegistry 动态注册 |
| `state.py` | AgentState 是通用数据结构 |
| `status_machine.py` | 通用状态转换 |
| `app.py` | `create_task()` 通过 task_type 动态查找模板和计划 |
| `schemas.py` | CreateTaskRequest.type 已是 string 验证 |
| `TaskOutput.tsx` | 统一 Markdown + 引用展示 |
| `MarkdownPreview.tsx` | 通用渲染 |
| `TaskProgress.tsx` | 通用 Step 组件 |
| API Gateway | 透明代理，不感知 task_type |
| KB / Citation / Output Service | 统一内部 API |

---

## 6. 任务类型定义模版

以下是一个可直接复制使用的标准模版，替换 `{new_type}`、`{标签}`、`{章节列表}` 等占位符即可：

### 6.1 步骤清单

1. 确定任务类型的业务名称和英文标识
2. 设计输出结构（章节列表，3~6 个为宜）
3. 设计 Agent 步骤计划（工具调用顺序）
4. 编写 Jinja2 提示词模板（定义 Agent 行为策略）
5. 按 4.1 节清单依次修改 7 个文件 + 新建 1 个模板文件
6. 确定是否需要特殊敏感度路由规则
7. （可选）更新数据库 CHECK 约束

### 6.2 设计原则

- **章节数量**：建议 3~6 个，每个章节对应一次 `generate_section` 调用
- **步骤数量**：应 ≤ `agent_max_iterations`（默认 5），但 `_WORKFLOW_PLANS` 的步骤不受此限制（单次迭代可执行多步）
- **提示词策略**：在 `## Instructions` 中明确定义 Agent 的行为策略（先检索再生成、逐节生成等）
- **工具选择**：6 个工具均可选用，按需组合。不需要的工具（如 `compare_policies`）可以不出现在计划中
- **输出格式**：默认 `["md", "docx"]`，可在 `_DEFAULT_SECTIONS` 定义章节时适配

### 6.3 与现有任务类型的差异

| 维度 | `literature_review` | `policy_draft` | `policy_comparison` | `tech_interpretation` |
|------|---------------------|----------------|---------------------|----------------------|
| 章节数 | 6 | 5 | 5 | 5 |
| 步骤数 | 15 | 10 | 11 | 9 |
| 特殊工具 | `extract_key_claims` | — | `compare_policies` + `extract_key_claims` | — |
| 敏感度 | 默认 low | 强制 high | 默认 low | 默认 low |
| 提示词风格 | 学术综述 | 政府公文 | 比较分析 | 技术解读 |

---

## 7. 扩展后的系统能力

当系统从 4 种专用任务类型扩展为支持任意自定义类型后，EconAI 将蜕变为一个**通用知识库文件分析系统**：

| 能力维度 | 当前（专用） | 扩展后（通用） |
|----------|-------------|---------------|
| 任务类型 | 4 种（经济政策领域） | 任意（用户定义） |
| 适用领域 | 经济政策分析 | 任何知识库驱动的分析场景 |
| 输出结构 | 固定章节 | 完全自定义章节 |
| Agent 行为 | 预设步骤 | 完全自定义步骤计划 |
| 提示词策略 | 预设风格 | 完全自定义 |
| 工具组合 | 预设 | 从 6 个工具中自由组合 |
| LLM 路由 | 预设规则 | 可扩展规则 |
| 前端 UI | 固定下拉选项 | 动态选项 |
| 数据库 | CHECK 约束 | 可移除或动态管理 |

### 7.1 潜在通用场景示例

- **法律文件分析**：合同审查、法规解读、判例研究
- **科技情报**：技术专利分析、论文综述、竞品技术对比
- **商业分析**：市场研究报告、竞品对比、行业趋势分析
- **教育研究**：课程文献综述、教学方法比较、教育政策解读
- **医疗健康**：医学文献综述、治疗方案比较、临床指南解读

---

## 8. 风险与注意事项

1. **数据库 CHECK 约束**：如果使用 PostgreSQL 且启用了 CHECK 约束，新增类型后需要迁移。建议在应用层（Pydantic 枚举）做校验，数据库层改为宽松约束或移除 CHECK。
2. **`_WORKFLOW_PLANS` 步骤过多**：如果自定义步骤超过 `agent_max_iterations`（默认 5），Agent 会提前触发 `_force_format_output`，只输出已完成的部分。需要在设计步骤时合理分配。
3. **提示词质量**：Jinja2 模板是 Agent 行为的核心驱动力。模板质量直接影响输出质量，需要在 `## Instructions` 中精心设计行为策略。
4. **前端兼容性**：`TaskOutput.tsx` 和 `MarkdownPreview.tsx` 是通用组件，但如果新类型需要特殊展示（如图表、矩阵），可能需要扩展前端组件。
5. **工具扩展**：当前 6 个工具覆盖了检索-生成-校验-输出全链路。如果未来需要新增工具（如 `run_data_analysis`、`generate_chart`），可以通过 `ToolRegistry.register()` 动态注册，无需改动 Agent 循环。

---

## 9. 结论

EconAI 的 Agent 引擎（ReAct 循环 + ToolRegistry）与业务领域天然解耦，从专用政策分析系统升级为通用知识库分析系统的**核心改动量仅为约 70 行代码**，分布在 7 个已有文件 + 1 个新建模板文件中。新增任务类型的实质是**配置化注册**——定义输出结构（章节列表）、Agent 步骤计划（工具调用序列）和提示词策略（Jinja2 模板），即可让整个系统适配任何知识库驱动的分析场景。

这种架构设计的核心优势在于：**Agent 引擎是平台，任务类型是配置**。通过简单的字典注册和模板编写，无需修改核心循环、工具实现、状态管理或前端渲染逻辑，即可实现业务领域的横向扩展。
