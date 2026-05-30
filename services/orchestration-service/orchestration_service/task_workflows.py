"""Task-type-specific workflow orchestration (M4-27 through M4-35).

Each workflow defines:
    - initial_plan: the Agent's starting plan
    - initial_remaining_sections: sections to generate
    - system_prompt: the Jinja2-rendered system prompt
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import BaseLoader, Environment

from orchestration_service.config import settings

logger = logging.getLogger(__name__)

# ── Jinja2 templates ────────────────────────────────────────────────────────

_templates: dict[str, str] = {}

# 默认 templates (embedded, fallback when template dir is not available)


DEFAULT_TEMPLATES: dict[str, str] = {
    "system_prompt.j2": """You are PolicyAI, an institutional-grade AI economic policy analysis assistant.
Your task is to complete a {{ task_type }} analysis titled "{{ title }}".

## Task Description
{{ description or 'No additional description provided.' }}

## Available Tools
You have access to these tools:
- search_kb: Search the knowledge base for relevant chunks
- generate_section: Generate a section of the report with inline citations [ref:doc_id:page_range]
- verify_citations: Verify inline citations against source chunks
- extract_key_claims: Extract key claims and arguments from text
- compare_policies: Compare multiple policies across dimensions
- format_output: Generate final output in requested formats

## Citation Format
Always use [ref:doc_id:page_range] for inline citations. Example: [ref:doc_001:p3-5].

## Output Quality
- Write in academic style
- Support all claims with citations
- Use clear logic and evidence-based arguments
- Structure content with proper headings

## Process
{% if workflow_plan %}
Follow this plan:
{{ workflow_plan }}
{% endif %}
Plan step-by-step, use tools to retrieve and generate, verify all citations, and format the final output.

{% if type_specific_content %}
{{ type_specific_content }}
{% endif %}""",
    "literature_review.j2": """You are conducting a literature review analysis.

## Task
Title: {{ title }}
Description: {{ description or 'Comprehensive literature review' }}

## Focus Areas
{% for area in focus_areas %}
- {{ area }}
{% endfor %}

## Output Structure
1. 研究背景与范围 (Research Background and Scope)
2. 核心理论框架 (Core Theoretical Frameworks)
3. 方法论比较 (Methodology Comparison)
4. 主要研究发现 (Key Research Findings)
5. 政策建议汇总 (Policy Recommendations Summary)
6. 研究空白与展望 (Research Gaps and Future Directions)

## Instructions
- Start by searching the knowledge base for core arguments and theories
- Generate sections in order, one at a time
- Verify all citations after each section
- Extract key claims after generating findings
- Use [ref:doc_id:page_range] format for all citations""",
    "policy_draft.j2": """You are drafting a policy document following Chinese government document standards.

## Task
Title: {{ title }}
Description: {{ description or 'Policy draft' }}

## Output Structure
1. 背景与必要性 (Background and Necessity)
2. 政策依据 (Policy Basis / Legal Foundation)
3. 主要措施 (Main Measures)
4. 组织实施方案 (Implementation Plan)
5. 预期效果与评估 (Expected Outcomes and Evaluation)

## Instructions
- Search for relevant policy background and legal basis
- Generate each section with proper government document tone
- Use formal, precise language
- Cite all sources with [ref:doc_id:page_range]
- Verify citations after each section""",
    "policy_comparison.j2": """You are comparing multiple policies or policy options.

## Task
Title: {{ title }}
Description: {{ description or 'Policy comparison analysis' }}

## Comparison Dimensions
{% for dim in comparison_dimensions %}
- {{ dim }}
{% endfor %}

## Output Structure
1. 比较分析总览 (Comparison Overview)
2. 各政策要素对比 (Policy Element Comparison)
3. 优劣势分析 (Strengths and Weaknesses Analysis)
4. 实施效果比较 (Implementation Effectiveness Comparison)
5. 综合建议 (Comprehensive Recommendations)

## Instructions
- Use extract_key_claims to identify core elements of each policy
- Use compare_policies tool for structured comparison
- Search for implementation evidence
- Use [ref:doc_id:page_range] for all citations""",
    "tech_interpretation.j2": """You are interpreting a technical standard or regulation.

## Task
Title: {{ title }}
Description: {{ description or 'Technical standard interpretation' }}

## Output Structure
1. 技术标准概述 (Technical Standard Overview)
2. 关键条款解读 (Key Clause Interpretation)
3. 合规影响分析 (Compliance Impact Analysis)
4. 实施建议 (Implementation Recommendations)
5. 风险评估 (Risk Assessment)

## Instructions
- Search for the full text of relevant standards and regulations
- Interpret each key clause with practical implications
- Analyze compliance requirements and impacts
- Provide actionable implementation recommendations
- Use [ref:doc_id:page_range] for all citations""",
}

# Workflow plans per task type (M4-32 through M4-35)
_WORKFLOW_PLANS: dict[str, str] = {
    "literature_review": """1. search_kb: Retrieve global core arguments and theories
2. generate_section: "研究背景与范围"
3. verify_citations: Verify all citations in background section
4. search_kb: Retrieve methodology-related literature
5. generate_section: "核心理论框架"
6. generate_section: "方法论比较"
7. verify_citations: Verify methodology section citations
8. search_kb: Retrieve findings and recommendations
9. generate_section: "主要研究发现"
10. generate_section: "政策建议汇总"
11. extract_key_claims: Extract key claims from findings
12. search_kb: Retrieve research gaps and future directions
13. generate_section: "研究空白与展望"
14. verify_citations: Final verification of all sections
15. format_output: Generate final output""",
    "policy_draft": """1. search_kb: Retrieve policy background and context
2. generate_section: "背景与必要性"
3. search_kb: Retrieve legal basis and related regulations
4. generate_section: "政策依据"
5. generate_section: "主要措施"
6. search_kb: Retrieve implementation references
7. generate_section: "组织实施方案"
8. generate_section: "预期效果与评估"
9. verify_citations: Verify all citations
10. format_output: Generate final output""",
    "policy_comparison": """1. search_kb: Retrieve policy documents to compare
2. extract_key_claims: Extract core elements from each policy
3. compare_policies: Structured comparison across dimensions
4. generate_section: "比较分析总览"
5. generate_section: "各政策要素对比"
6. generate_section: "优劣势分析"
7. search_kb: Retrieve implementation evidence
8. generate_section: "实施效果比较"
9. generate_section: "综合建议"
10. verify_citations: Verify all citations
11. format_output: Generate final output""",
    "tech_interpretation": """1. search_kb: Retrieve full text of technical standard
2. generate_section: "技术标准概述"
3. generate_section: "关键条款解读"
4. search_kb: Retrieve compliance analysis references
5. generate_section: "合规影响分析"
6. generate_section: "实施建议"
7. generate_section: "风险评估"
8. verify_citations: Verify all citations
9. format_output: Generate final output""",
}

# 默认 sections per task type
_DEFAULT_SECTIONS: dict[str, list[str]] = {
    "literature_review": [
        "研究背景与范围",
        "核心理论框架",
        "方法论比较",
        "主要研究发现",
        "政策建议汇总",
        "研究空白与展望",
    ],
    "policy_draft": [
        "背景与必要性",
        "政策依据",
        "主要措施",
        "组织实施方案",
        "预期效果与评估",
    ],
    "policy_comparison": [
        "比较分析总览",
        "各政策要素对比",
        "优劣势分析",
        "实施效果比较",
        "综合建议",
    ],
    "tech_interpretation": [
        "技术标准概述",
        "关键条款解读",
        "合规影响分析",
        "实施建议",
        "风险评估",
    ],
}


# ── Template loading ────────────────────────────────────────────────────────


def _load_templates() -> dict[str, str]:
    """Load Jinja2 templates from disk, falling back to embedded defaults."""
    loaded: dict[str, str] = dict(DEFAULT_TEMPLATES)
    templates_dir = Path(settings.prompt_templates_dir)
    if templates_dir.is_dir():
        for path in templates_dir.glob("*.j2"):
            content = path.read_text(encoding="utf-8")
            loaded[path.name] = content
            logger.info("Loaded template: %s", path.name)
    return loaded


def render_system_prompt(
    task_type: str,
    title: str,
    description: str = "",
    focus_areas: list[str] | None = None,
    comparison_dimensions: list[str] | None = None,
) -> str:
    """M4-31: Build the system prompt for a task by rendering Jinja2 templates."""
    global _templates
    if not _templates:
        _templates = _load_templates()

    env = Environment(loader=BaseLoader())

    # Render the type-specific template
    type_template_name = f"{task_type}.j2"
    type_template_str = _templates.get(type_template_name, "")
    if not type_template_str:
        type_template_str = DEFAULT_TEMPLATES.get(type_template_name, "")

    # Render the system prompt wrapper
    sys_template_str = _templates.get("system_prompt.j2", DEFAULT_TEMPLATES["system_prompt.j2"])

    workflow_plan = _WORKFLOW_PLANS.get(task_type, "")

    # Build context
    ctx: dict[str, object] = {
        "task_type": task_type,
        "title": title,
        "description": description,
        "focus_areas": focus_areas or [],
        "comparison_dimensions": comparison_dimensions or [],
        "workflow_plan": workflow_plan,
    }

    # Render type-specific content and inject into system prompt
    if type_template_str:
        type_content = env.from_string(type_template_str).render(**ctx)
        ctx["type_specific_content"] = type_content
    else:
        ctx["type_specific_content"] = ""

    # Render system prompt
    system_prompt = env.from_string(sys_template_str).render(**ctx)
    return system_prompt


def get_initial_sections(task_type: str) -> list[str]:
    """获取 the default section list for a task type."""
    return list(_DEFAULT_SECTIONS.get(task_type, []))


def get_workflow_plan(task_type: str) -> str:
    """获取 the workflow plan text for a task type."""
    return _WORKFLOW_PLANS.get(task_type, "")
