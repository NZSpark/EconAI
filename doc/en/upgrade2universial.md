# Upgrade Analysis: From Specialized Policy Analysis System to Universal Knowledge Base Analysis System

> **Analysis Date**: 2026-05-30
> **Scope**: Full end-to-end code call flow trace from task creation to completion, identifying all change points required to extend into a universal system

---

## 1. Background

PolicyAI is currently positioned as an institutional-grade economic policy analysis system, supporting 4 task types:

| Task Type | Identifier | Description |
|-----------|-----------|-------------|
| Literature Review | `literature_review` | Synthesize and review literature in the knowledge base |
| Policy Draft | `policy_draft` | Draft policy documents per Chinese government document standards |
| Policy Comparison | `policy_comparison` | Multi-dimensional comparative analysis of policies |
| Tech Interpretation | `tech_interpretation` | Interpret technical standards/regulations and compliance impacts |

**Core Insight**: The entire Agent engine (ReAct loop + 6 generic tools) is completely decoupled from the business domain and is inherently capable of being extended into a universal knowledge base analysis system. Adding new task types requires only **configuration-based registration** — no modifications to the core engine code.

---

## 2. System Architecture Layers and Extension Point Analysis

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (React + TypeScript)                │
│  TaskList.tsx           TaskOutput.tsx         labels.ts         │
│  (Task creation form)   (Result display)      (Label/color map)  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ POST /api/projects/{id}/tasks
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                Orchestration Service (FastAPI)                   │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ sensitivity │  │ task_        │  │ app.py                │   │
│  │ .py         │  │ workflows.py │  │ (create_task +        │   │
│  │ (Sensitivity)│  │ (Workflows/  │  │  _run_agent dispatch) │   │
│  │             │  │  Templates)  │  │                       │   │
│  └─────────────┘  └──────────────┘  └───────────┬───────────┘   │
│                                                  │               │
│  ┌───────────────────────────────────────────────┘               │
│  │  Agent Engine (Generic engine — no changes needed)             │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  │ agent_   │  │ tools.py │  │ state.py │  │ progress │    │
│  │  │ loop.py  │  │ (6 tools)│  │ (Agent   │  │ .py      │    │
│  │  │ (ReAct)  │  │          │  │  State)  │  │ (Progress)│    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  └───────────────────────────────────────────────────────────────┘
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP (internal APIs)
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
     ┌────────────┐   ┌──────────────┐   ┌──────────────┐
     │ KB Service │   │ LLM Router   │   │ Citation     │
     │ (Search/   │   │ (Model       │   │ Service      │
     │  Retrieval)│   │  Routing)    │   │ (Verification)│
     └────────────┘   └──────────────┘   └──────────────┘
```

### 2.2 Already Generic Components (No Changes Needed for New Task Types)

The following components are completely decoupled from the business domain and can be directly reused for any new task type:

| Component | File | Generic Mechanism |
|-----------|------|-------------------|
| **Agent Loop Engine** | `agent_loop.py` | Standard ReAct loop, driven by `_WORKFLOW_PLANS` dict, independent of task type |
| **6 Tools** | `tools.py` | `search_kb`, `generate_section`, `verify_citations`, `extract_key_claims`, `compare_policies`, `format_output` — all parameterized, dynamically registered via ToolRegistry |
| **Agent State** | `state.py` | `AgentState` is a generic data structure; fields are not bound to task type |
| **State Machine** | `status_machine.py` | `pending → running → completed/failed/cancelled`, universal for all task types |
| **LLM Routing Sensitivity** | `sensitivity.py` | Already has generic fallback logic (default `low`); only `policy_draft` has special rules |
| **Output Display** | `TaskOutput.tsx` | Unified Markdown + citation display, agnostic to task type |
| **Markdown Preview** | `MarkdownPreview.tsx` | Generic rendering component |
| **Progress Bar** | `TaskProgress.tsx` | Generic Step component |
| **API Gateway** | `api-gateway/` | Transparent proxy, unaware of `task_type` |
| **Output Service** | `output-service/` | Unified `format_output` API |
| **KB Service** | `kb-service/` | Unified `search` API |
| **Citation Service** | `citation-service/` | Unified `verify` API |

---

## 3. Full Call Flow (Using `literature_review` as Example)

```
Step 1: Frontend Creation
  TaskList.tsx → handleCreate() → POST /api/projects/{id}/tasks
  Parameters: { type, title, description, focus_areas, output_formats }

Step 2: Orchestration Service Receives
  app.py: create_task()
  ├── determine_sensitivity(body)              → sensitivity.py
  ├── render_system_prompt(task_type, ...)      → task_workflows.py
  │   ├── Look up "{task_type}.j2" template
  │   ├── Jinja2 render: inject title, description, focus_areas
  │   └── Embed workflow_plan + system_prompt.j2 wrapper
  ├── get_workflow_plan(task_type)              → read _WORKFLOW_PLANS[task_type]
  ├── get_initial_sections(task_type)           → read _DEFAULT_SECTIONS[task_type]
  └── asyncio.create_task(_run_agent(task_id))

Step 3: Agent Loop Execution
  agent_loop.py: AgentLoopRunner.run()
  while iteration < 5:
    ├── _plan() → POST llm-router/internal/llm/chat
    │   LLM returns: tool_name + tool_args or "finish"
    ├── Execute tool (tool_registry.get(tool_name))
    │   ├── search_kb       → POST kb-service/internal/search
    │   ├── generate_section → POST llm-router/internal/llm/chat
    │   ├── verify_citations → POST citation-service/internal/citations/verify
    │   ├── extract_key_claims → POST llm-router
    │   ├── compare_policies   → POST llm-router
    │   └── format_output     → POST output-service/internal/output/generate
    ├── observe → state.add_tool_result()
    └── progress.update(step, message)

Step 4: Completion
  _force_format_output() → generate final output
  Status: running → completed

Step 5: Frontend Polls Result
  GET /api/projects/{id}/tasks/{task_id}/output
  TaskOutput.tsx renders Markdown + citation list
```

---

## 4. Change Checklist for Adding a New Task Type

Assuming a new type `"new_type"`, **7 files need modification + 1 new file**, with a total of approximately **50 lines** of changes.

### 4.1 Required File Changes

#### A. `shared/models.py` — TaskType Enum (1 line)

```python
class TaskType(StrEnum):
    literature_review = "literature_review"
    policy_draft = "policy_draft"
    policy_comparison = "policy_comparison"
    tech_interpretation = "tech_interpretation"
    new_type = "new_type"   # ← New
```

#### B. `templates/prompts/new_type.j2` — New Prompt Template (~30 lines)

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
1. Section One
2. Section Two
3. Section Three
4. Section Four
5. Section Five

## Instructions
- Search the knowledge base for relevant information
- Generate each section with proper structure
- Verify all citations after each section
- Use [ref:doc_id:page_range] format for all citations
```

**Key Design Points**:
- The template is parameterized via Jinja2 variables `{{ title }}`, `{{ description }}`, `{{ focus_areas }}`
- The output structure defines the sections the Agent must generate, and must be consistent with `_DEFAULT_SECTIONS`
- `## Instructions` controls the Agent's behavioral strategy

#### C. `task_workflows.py` — Three Dictionary Additions (~30 lines)

**c1) DEFAULT_TEMPLATES (after ~line 148):** Embedded default template (fallback when the template directory is unavailable)

```python
"new_type.j2": """You are performing a {{ task_type }} analysis.

## Task
Title: {{ title }}
Description: {{ description or 'Default description' }}

## Output Structure
1. Section One
2. Section Two
3. Section Three
4. Section Four
5. Section Five

## Instructions
- Search the knowledge base for relevant information
- Generate each section with proper structure
- Verify all citations after each section
- Use [ref:doc_id:page_range] format for all citations""",
```

**c2) _WORKFLOW_PLANS (after ~line 197):** Define the Agent's step plan

```python
"new_type": """1. search_kb: Retrieve background information
2. generate_section: "Section One"
3. generate_section: "Section Two"
4. search_kb: Retrieve supplementary data
5. generate_section: "Section Three"
6. generate_section: "Section Four"
7. generate_section: "Section Five"
8. verify_citations: Verify all citations
9. format_output: Generate final output""",
```

**Step Plan Design Principles**:
- `search_kb` is interspersed between section generations to ensure the Agent has sufficient context before generating
- `verify_citations` + `format_output` are placed at the end for a unified final pass
- Available tools: `search_kb`, `generate_section`, `verify_citations`, `extract_key_claims`, `compare_policies`, `format_output`
- The number of steps determines the Agent's iteration count and should fall within `agent_max_iterations` (default: 5)

**c3) _DEFAULT_SECTIONS (after ~line 230):** Define the initial list of remaining sections

```python
"new_type": [
    "Section One",
    "Section Two",
    "Section Three",
    "Section Four",
    "Section Five",
],
```

#### D. `progress.py` — Progress Estimate (1 line)

```python
_PRESET_ESTIMATES: dict[str, int] = {
    "literature_review": 8,
    "policy_draft": 7,
    "tech_interpretation": 6,
    "policy_comparison": 7,
    "new_type": 9,   # ← New; should match the step count in _WORKFLOW_PLANS
}
```

#### E. `frontend/src/api/types.ts` — TypeScript Union Type (1 line)

```typescript
export type TaskType =
  | 'literature_review'
  | 'policy_draft'
  | 'policy_comparison'
  | 'tech_interpretation'
  | 'new_type';  // ← New
```

#### F. `frontend/src/constants/labels.ts` — Labels and Colors (2 lines)

```typescript
// taskTypeColorMap
new_type: 'green',   // ← New color

// taskTypeLabelMap
new_type: 'New Task Type',   // ← New label
```

#### G. `frontend/src/pages/TaskList.tsx` — Dropdown Selector (1 line)

```tsx
// Add to Select options:
{ label: 'New Task Type', value: 'new_type' },
```

### 4.2 Optional Changes

#### H. `sensitivity.py` — Sensitivity Rules (if special routing is needed)

```python
# Modify only if this task type needs special LLM routing
if request.type.value == "new_type":
    return SensitivityResult(
        level="high",
        reason="New type tasks contain sensitive analysis",
    )
```

Current rules:
- `policy_draft` → forced `high` (local LLM)
- User explicitly set → use directly
- Default → `low` (cloud LLM)

#### I. `db/init/01-schema.sql` — Database CHECK Constraint

```sql
task_type VARCHAR(32) NOT NULL CHECK (
    task_type IN (
        'literature_review','policy_draft','policy_comparison','tech_interpretation','new_type'
    )
),
```

**Note**: If using PostgreSQL, modifying the CHECK constraint requires `ALTER TABLE` or constraint recreation. If `task_type` is validated at the application layer (Pydantic enum), the database constraint update can be deferred until the next schema migration.

---

## 5. Change Volume Summary

| Category | File | Change Type | Lines |
|----------|------|-------------|-------|
| Shared Type | `shared/models.py` | Enum addition | 1 |
| Prompt Template | `templates/prompts/new_type.j2` | **New file** | ~30 |
| Workflow Definition | `task_workflows.py` | 3 dictionary additions | ~30 |
| Progress Estimate | `progress.py` | Dictionary addition | 1 |
| Frontend Type | `frontend/src/api/types.ts` | Union type addition | 1 |
| Frontend Labels | `frontend/src/constants/labels.ts` | 2 map additions | 2 |
| Frontend Form | `frontend/src/pages/TaskList.tsx` | Select options addition | 1 |
| **Required Subtotal** | **7 files + 1 new** | | **~66 lines** |
| Sensitivity Rules | `sensitivity.py` | As needed | 0–5 |
| Database Constraint | `db/init/01-schema.sql` | CHECK constraint update | 1 |
| **Optional Subtotal** | **2 files** | | **0–6 lines** |
| **Total** | **9 files + 1 new** | | **~70 lines** |

### 5.1 Components Requiring No Changes (10+)

| Component | Reason |
|-----------|--------|
| `agent_loop.py` | Generic ReAct loop, driven by `_WORKFLOW_PLANS` |
| `tools.py` | All 6 tools fully parameterized, dynamically registered via ToolRegistry |
| `state.py` | AgentState is a generic data structure |
| `status_machine.py` | Generic state transitions |
| `app.py` | `create_task()` dynamically looks up templates and plans by task_type |
| `schemas.py` | CreateTaskRequest.type already uses string validation |
| `TaskOutput.tsx` | Unified Markdown + citation display |
| `MarkdownPreview.tsx` | Generic rendering |
| `TaskProgress.tsx` | Generic Step component |
| API Gateway | Transparent proxy, unaware of task_type |
| KB / Citation / Output Service | Unified internal APIs |

---

## 6. Task Type Definition Template

The following is a copy-and-paste standard template — simply replace placeholders like `{new_type}`, `{label}`, `{section list}`, etc.:

### 6.1 Step Checklist

1. Determine the business name and English identifier for the task type
2. Design the output structure (section list, ideally 3–6 sections)
3. Design the Agent step plan (tool invocation sequence)
4. Write the Jinja2 prompt template (define Agent behavioral strategy)
5. Modify the 7 files + create 1 new template file per Section 4.1
6. Determine if special sensitivity routing rules are needed
7. (Optional) Update the database CHECK constraint

### 6.2 Design Principles

- **Section Count**: Recommended 3–6; each section corresponds to one `generate_section` call
- **Step Count**: Should be ≤ `agent_max_iterations` (default: 5), but `_WORKFLOW_PLANS` steps are not strictly limited by this (multiple steps can execute in a single iteration)
- **Prompt Strategy**: Clearly define the Agent's behavioral strategy in `## Instructions` (search-first-then-generate, generate section by section, etc.)
- **Tool Selection**: All 6 tools are available; combine as needed. Unused tools (e.g., `compare_policies`) can simply be omitted from the plan
- **Output Format**: Default `["md", "docx"]`; adapt when defining sections in `_DEFAULT_SECTIONS`

### 6.3 Differences from Existing Task Types

| Dimension | `literature_review` | `policy_draft` | `policy_comparison` | `tech_interpretation` |
|-----------|---------------------|----------------|---------------------|----------------------|
| Sections | 6 | 5 | 5 | 5 |
| Steps | 15 | 10 | 11 | 9 |
| Special Tools | `extract_key_claims` | — | `compare_policies` + `extract_key_claims` | — |
| Sensitivity | Default low | Forced high | Default low | Default low |
| Prompt Style | Academic review | Government document | Comparative analysis | Technical interpretation |

---

## 7. System Capabilities After Extension

When the system is extended from 4 specialized task types to support arbitrary custom types, PolicyAI will transform into a **universal knowledge base file analysis system**:

| Capability Dimension | Current (Specialized) | Extended (Universal) |
|----------------------|----------------------|----------------------|
| Task Types | 4 (economic policy domain) | Arbitrary (user-defined) |
| Applicable Domain | Economic policy analysis | Any knowledge-base-driven analysis scenario |
| Output Structure | Fixed sections | Fully customizable sections |
| Agent Behavior | Predefined steps | Fully customizable step plans |
| Prompt Strategy | Predefined style | Fully customizable |
| Tool Combination | Predefined | Free combination from 6 tools |
| LLM Routing | Predefined rules | Extensible rules |
| Frontend UI | Fixed dropdown options | Dynamic options |
| Database | CHECK constraint | Can be removed or managed dynamically |

### 7.1 Potential Universal Use Case Examples

- **Legal Document Analysis**: Contract review, regulation interpretation, case law research
- **Technology Intelligence**: Patent analysis, paper reviews, competitive technology comparison
- **Business Analysis**: Market research reports, competitive comparison, industry trend analysis
- **Educational Research**: Course literature reviews, teaching methodology comparison, education policy interpretation
- **Healthcare**: Medical literature reviews, treatment plan comparison, clinical guideline interpretation

---

## 8. Risks and Considerations

1. **Database CHECK Constraint**: If using PostgreSQL with CHECK constraints enabled, a migration is required after adding a new type. It is recommended to validate at the application layer (Pydantic enum) and relax or remove the database-level constraint.
2. **Excessive `_WORKFLOW_PLANS` Steps**: If custom steps exceed `agent_max_iterations` (default: 5), the Agent will trigger `_force_format_output` early, outputting only the completed portions. Steps should be allocated reasonably during design.
3. **Prompt Quality**: The Jinja2 template is the core driver of Agent behavior. Template quality directly impacts output quality; behavioral strategy must be carefully designed in `## Instructions`.
4. **Frontend Compatibility**: `TaskOutput.tsx` and `MarkdownPreview.tsx` are generic components, but if a new type requires special displays (e.g., charts, matrices), the frontend components may need extension.
5. **Tool Extension**: The current 6 tools cover the full retrieval-generation-verification-output pipeline. If new tools are needed in the future (e.g., `run_data_analysis`, `generate_chart`), they can be dynamically registered via `ToolRegistry.register()` without modifying the Agent loop.

---

## 9. Conclusion

PolicyAI's Agent engine (ReAct loop + ToolRegistry) is naturally decoupled from the business domain. Upgrading from a specialized policy analysis system to a universal knowledge base analysis system requires only **approximately 70 lines of code changes**, spread across 7 existing files + 1 new template file. The essence of adding a new task type is **configuration-based registration** — define the output structure (section list), the Agent step plan (tool invocation sequence), and the prompt strategy (Jinja2 template) to adapt the entire system to any knowledge-base-driven analysis scenario.

The core advantage of this architectural design is: **the Agent engine is a platform, and task types are configuration**. Through simple dictionary registration and template authoring, horizontal business domain expansion is achieved without modifying the core loop, tool implementations, state management, or frontend rendering logic.
