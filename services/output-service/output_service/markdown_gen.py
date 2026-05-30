"""Markdown output generator (M7-06, M7-07, M7-08).

Generates Markdown with YAML front-matter, [ref:]→[^n] footnote replacement,
and a references section at the end.
"""

from __future__ import annotations

import re
from typing import Any

from jinja2 import BaseLoader, Environment

REF_PATTERN = re.compile(r"\[ref:([^\]]+)\]")

MARKDOWN_TEMPLATE = """---
title: "{{ title }}"
date: "{{ date }}"
{% if keywords %}keywords: [{{ keywords|join(', ') }}]{% endif %}
generated_by: PolicyAI
---

{% for section in sections %}
{% if section.title %}{{ "#" * (section.level + 1) }} {{ section.title }}

{% endif %}
{{ section.content }}

{% endfor %}
## 参考文献

{% for citation in citations %}
[^{{ loop.index }}]: {{ citation.ref_id }}{% if citation.confidence %} ({{ citation.confidence }}){% endif %}

{% endfor %}
"""


def _replace_refs_with_footnotes(text: str, ref_map: dict[str, int]) -> str:
    """Replace [ref:xxx] markers with [^n] footnote references.

    Each unique ref_id maps to a single footnote number.
    """

    def _replacer(match: re.Match[str]) -> str:
        ref_id = match.group(1)
        num = ref_map.setdefault(ref_id, len(ref_map) + 1)
        return f"[^{num}]"

    return REF_PATTERN.sub(_replacer, text)


class MarkdownGenerator:
    """Generates Markdown output with footnotes and YAML front-matter."""

    def __init__(self) -> None:
        self._env = Environment(loader=BaseLoader())

    def generate(
        self,
        title: str,
        sections: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """生成 Markdown output.

        Args:
            title: Document title.
            sections: List of {"title": str, "level": int, "content": str} dicts.
            citations: List of citation dicts with ref_id, confidence, etc.
            metadata: Optional metadata dict with date, keywords, etc.

        Returns:
            Complete Markdown string.
        """
        meta = metadata or {}
        date = meta.get("date", "")

        # Build ref_id -> footnote_number mapping and replace in all sections
        ref_map: dict[str, int] = {}
        processed_sections: list[dict[str, Any]] = []
        for section in sections:
            content = _replace_refs_with_footnotes(section.get("content", ""), ref_map)
            processed_sections.append(
                {
                    "title": section.get("title", ""),
                    "level": section.get("level", 1),
                    "content": content,
                }
            )

        # Build citation list in footnote order
        ordered_citations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for section in sections:
            for m in REF_PATTERN.finditer(section.get("content", "")):
                ref_id = m.group(1)
                if ref_id not in seen:
                    seen.add(ref_id)
                    # Find matching citation data
                    cit = next((c for c in citations if c.get("ref_id") == ref_id), None)
                    ordered_citations.append(cit or {"ref_id": ref_id})

        template = self._env.from_string(MARKDOWN_TEMPLATE)
        return template.render(
            title=title,
            date=date,
            keywords=meta.get("keywords", []),
            sections=processed_sections,
            citations=ordered_citations,
        )
