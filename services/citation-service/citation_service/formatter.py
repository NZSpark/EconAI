"""Citation formatters for output generation (M6-19 through M6-23).

Implements:
  - format_markdown: GFM footnote replacement + reference list (M6-19)
  - format_web_json: frontend tooltip-ready JSON (M6-20)
  - format_docx_footnotes: python-docx footnote text list (M6-21)
  - format_xlsx_sheet: "" sheet data rows (M6-22)
  - format_pptx: per-slide citation text + final slide list (M6-23)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Re-use the parser pattern for extracting ref markers in text
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"\[ref:([^\]]+)\]")


@dataclass
class FormattedRef:
    """A single resolved citation reference for formatting."""

    ref_id: str
    source: str  # e.g. "doc_123, p45-48"
    confidence: str
    page_info: str


@dataclass
class CitationFormatter:
    """引用格式化器 —— 将验证后的引用转换为各种输出格式。
    
    支持的格式：
    - Markdown (M6-19)：GFM 脚注风格，[ref:...] → [^1] + 末尾参考文献列表
    - Web JSON (M6-20)：前端 tooltip 友好的 JSON 格式
    - DOCX 脚注 (M6-21)：python-docx 可用的脚注文本列表
    - XLSX 表格 (M6-22)：Excel 引文数据行
    - PPTX (M6-23)：按幻灯片分组的引用 + 末尾全量引用列表
    """

    _ref_counter: int = field(default=0, init=False)

    # -------------------------------------------------------------------
    # M6-19: Markdown formatting
    # -------------------------------------------------------------------

    def format_markdown(
        self,
        text: str,
        citations: list[VerifiedCitationInput],
    ) -> str:
        """将 [ref:...] 标记替换为 GFM 脚注 [^n]，并追加参考文献列表。
        
        处理步骤：
        1. 提取所有 [ref:...] 标记
        2. 为每个唯一的引用分配序号
        3. 替换文本中的标记为脚注编号
        4. 在文末追加参考文献列表

        Args:
            text: 包含 [ref:...] 标记的原始文本。
            citations: 已验证的引用结果列表。

        Returns:
            带脚注的 Markdown 文本。
        """
        self._ref_counter = 0
        footnote_map: dict[str, tuple[int, str]] = {}  # raw_mark → (序号, 标签)
        raw_refs = _REF_PATTERN.findall(text)

        # 构建引用查找表
        citation_lookup: dict[str, VerifiedCitationInput] = {}
        for c in citations:
            citation_lookup[c.ref_id] = c

        for raw_mark in raw_refs:
            if raw_mark not in footnote_map:
                self._ref_counter += 1
                citation = citation_lookup.get(raw_mark)
                label = f"{citation.ref_id} ({citation.confidence})" if citation else raw_mark
                footnote_map[raw_mark] = (self._ref_counter, label)

        # 替换标记：[ref:xxx] → [^1]
        def _replace_ref(match: re.Match[str]) -> str:
            raw = match.group(1)
            entry = footnote_map.get(raw)
            if entry:
                return f"[^{entry[0]}]"
            return match.group(0)

        result_text = _REF_PATTERN.sub(_replace_ref, text)

        # 在文末追加参考文献列表
        if footnote_map:
            result_text += "\n"
            for _raw_mark, (num, label) in sorted(
                footnote_map.items(), key=lambda x: x[1][0]
            ):
                result_text += f"\n[^{num}]: {label}"

        return result_text

    # -------------------------------------------------------------------
    # M6-20: Web JSON formatting (frontend tooltip-ready)
    # -------------------------------------------------------------------

    def format_web_json(
        self,
        citations: list[VerifiedCitationInput],
    ) -> list[dict[str, Any]]:
        """生成 JSON-serializable citation data for frontend rendering.

        Args:
            citations: Verified citation results.

        Returns:
            List of dicts ready for JSON serialization.
        """
        result: list[dict[str, Any]] = []
        for c in citations:
            entry: dict[str, Any] = {
                "ref_id": c.ref_id,
                "sentence": c.sentence,
                "sentence_index": c.sentence_index,
                "confidence": c.confidence,
                "tooltip": c.sentence[:150],
                "sources": [
                    {
                        "document_id": chunk.document_id,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "excerpt": chunk.excerpt,
                        "similarity": chunk.similarity,
                    }
                    for chunk in c.matched_chunks
                ],
            }
            result.append(entry)
        return result

    # -------------------------------------------------------------------
    # M6-21: DOCX footnote formatting
    # -------------------------------------------------------------------

    def format_docx_footnotes(
        self,
        citations: list[VerifiedCitationInput],
    ) -> list[dict[str, Any]]:
        """生成 footnote text list for python-docx consumption.

        Args:
            citations: Verified citation results.

        Returns:
            List of {"footnote_id": n, "text": "..."} dicts.
        """
        result: list[dict[str, Any]] = []
        for i, c in enumerate(citations, start=1):
            source_texts: list[str] = []
            for chunk in c.matched_chunks:
                source_texts.append(
                    f"{chunk.document_id}, pp.{chunk.page_start}-{chunk.page_end}"
                )
            source_str = "; ".join(source_texts) if source_texts else c.ref_id
            result.append(
                {
                    "footnote_id": i,
                    "text": source_str,
                }
            )
        return result

    # -------------------------------------------------------------------
    # M6-22: XLSX "/" sheet formatting
    # -------------------------------------------------------------------

    def format_xlsx_sheet(
        self,
        citations: list[VerifiedCitationInput],
    ) -> list[dict[str, Any]]:
        """生成 data rows for "" sheet: ////

        Args:
            citations: Verified citation results.

        Returns:
            List of row dicts.
        """
        result: list[dict[str, Any]] = []
        for i, c in enumerate(citations, start=1):
            # Build source string from first matched chunk
            if c.matched_chunks:
                first = c.matched_chunks[0]
                source = first.document_id
                pages = f"{first.page_start}-{first.page_end}"
            else:
                source = c.ref_id
                pages = "-"

            result.append(
                {
                    "序号": i,
                    "来源": source,
                    "页码": pages,
                    "置信度": c.confidence,
                }
            )
        return result

    # -------------------------------------------------------------------
    # M6-23: PPTX formatting
    # -------------------------------------------------------------------

    def format_pptx(
        self,
        citations: list[VerifiedCitationInput],
    ) -> dict[str, Any]:
        """生成 per-slide citation text + final slide full citation list.

        Args:
            citations: Verified citation results.

        Returns:
            Dict with keys "slide_citations" and "final_slide_list".
        """
        # Group citations by sentence_index to distribute to slides
        slide_map: dict[int, list[dict[str, Any]]] = {}
        for c in citations:
            slide_map.setdefault(c.sentence_index, []).append(
                {
                    "ref_id": c.ref_id,
                    "text": c.sentence[:200],
                    "confidence": c.confidence,
                }
            )

        slide_citations: list[dict[str, Any]] = [
            {"slide_index": idx, "citations": refs}
            for idx, refs in sorted(slide_map.items())
        ]

        final_slide_list: list[dict[str, Any]] = []
        for i, c in enumerate(citations, start=1):
            if c.matched_chunks:
                first = c.matched_chunks[0]
                source = f"{first.document_id}, pp.{first.page_start}-{first.page_end}"
            else:
                source = c.ref_id
            final_slide_list.append(
                {
                    "index": i,
                    "ref_id": c.ref_id,
                    "sentence_excerpt": c.sentence[:200],
                    "source": source,
                    "confidence": c.confidence,
                }
            )

        return {
            "slide_citations": slide_citations,
            "final_slide_list": final_slide_list,
        }


# ---------------------------------------------------------------------------
# Input type for verified citations (reused from verifier types at runtime)
# ---------------------------------------------------------------------------


@dataclass
class MatchedChunkInput:
    """Input type for a matched chunk in formatting."""

    document_id: str
    page_start: int
    page_end: int
    excerpt: str
    similarity: float
    chunk_id: str = ""


@dataclass
class VerifiedCitationInput:
    """Input type for a verified citation in formatting."""

    ref_id: str
    sentence: str
    sentence_index: int
    confidence: str
    matched_chunks: list[MatchedChunkInput] = field(default_factory=list)
