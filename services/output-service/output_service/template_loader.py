"""YAML template loader with fallback defaults (M7-25 through M7-28).

Loads output format templates from YAML files, falling back to built-in defaults.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path("templates/output")


# ---------------------------------------------------------------------------
# 默认 template configurations (fallback when YAML files are missing)
# ---------------------------------------------------------------------------

DEFAULT_DOCX_TEMPLATE: dict[str, Any] = {
    "page_margins": {"top_mm": 37, "bottom_mm": 35, "left_mm": 28, "right_mm": 26, "header_mm": 15, "footer_mm": 15},
    "page_setup": {"paper_size": "A4", "orientation": "portrait"},
    "fonts": {
        "title_h1": {"name": "小标宋_GB2312", "size_pt": 22, "bold": False},
        "title_h2": {"name": "黑体", "size_pt": 16},
        "title_h3": {"name": "楷体_GB2312", "size_pt": 16},
        "body": {"name": "仿宋_GB2312", "size_pt": 16},
        "citation_superscript": {"name": "仿宋_GB2312", "size_pt": 10, "superscript": True},
    },
    "header": {
        "enabled": True,
        "content": {
            "institution_name": "{{ institution_name }}",
            "institution_name_font": {"name": "小标宋_GB2312", "size_pt": 18, "bold": False, "color": "#CC0000"},
            "separator_line": {"enabled": True, "width_pt": 1, "color": "#CC0000"},
        },
    },
    "body_structure": {
        "heading_mapping": {"level_1": "一、", "level_2": "(一)", "level_3": "1.", "level_4": "(1)"},
    },
    "citation_display": {
            "style": "footnote", "superscript": True, "bracket_style": "square", "numbering": "continuous"
        },
    "footer": {
        "enabled": True,
        "content": {
            "separator_line": {"enabled": True, "width_pt": 0.5, "color": "#000000"},
        },
    },
    "reference_list": {
        "title": "参考文献",
        "title_font": {"name": "黑体", "size_pt": 16},
        "entry_format": "[{index}] {authors}. {title}. {source}. {year}. {page_range}.",
        "entry_font": {"name": "仿宋_GB2312", "size_pt": 14},
        "entry_spacing_pt": 22,
    },
}

DEFAULT_PPTX_TEMPLATE: dict[str, Any] = {
    "slide": {"width_cm": 33.867, "height_cm": 19.05},
    "fonts": {
        "title": {"name": "微软雅黑", "size_pt": 28, "bold": True},
        "body": {"name": "微软雅黑", "size_pt": 16},
        "citation_text": {"name": "微软雅黑", "size_pt": 9},
    },
}

DEFAULT_XLSX_TEMPLATE: dict[str, Any] = {
    "sheet_comparison": {"name": "对比分析"},
    "sheet_citations": {"name": "引用清单"},
    "sheet_data_summary": {"name": "数据摘要", "enabled": True},
}


class DocxTemplateConfig:
    """Typed wrapper around the docx template dict for convenient access."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def page_margins(self) -> dict[str, Any]:
        return self._data.get("page_margins", {})  # type: ignore[no-any-return]

    @property
    def fonts(self) -> dict[str, Any]:
        return self._data.get("fonts", {})  # type: ignore[no-any-return]

    @property
    def header(self) -> dict[str, Any]:
        return self._data.get("header", {})  # type: ignore[no-any-return]

    @property
    def footer(self) -> dict[str, Any]:
        return self._data.get("footer", {})  # type: ignore[no-any-return]

    @property
    def body_structure(self) -> dict[str, Any]:
        return self._data.get("body_structure", {})  # type: ignore[no-any-return]

    @property
    def reference_list(self) -> dict[str, Any]:
        return self._data.get("reference_list", {})  # type: ignore[no-any-return]

    @property
    def citation_display(self) -> dict[str, Any]:
        return self._data.get("citation_display", {})  # type: ignore[no-any-return]


class TemplateLoader:
    """Loads YAML output templates with built-in fallback defaults."""

    def __init__(self, templates_dir: str | None = None) -> None:
        self._dir = Path(templates_dir) if templates_dir else _TEMPLATES_DIR
        self._cache: dict[str, dict[str, Any]] = {}

    _docx_template_cache: DocxTemplateConfig | None = None

    def load_docx_template(self) -> DocxTemplateConfig:
        """Load the GB/T 9704 DOCX template."""
        if self._docx_template_cache is not None:
            return self._docx_template_cache
        data = self._load_yaml("docx_gbt9704.yaml", DEFAULT_DOCX_TEMPLATE)
        self._docx_template_cache = DocxTemplateConfig(data)
        return self._docx_template_cache

    def load_pptx_template(self) -> dict[str, Any]:
        """Load the PPTX briefing template."""
        return self._load_yaml("pptx_briefing.yaml", DEFAULT_PPTX_TEMPLATE)

    def load_xlsx_template(self) -> dict[str, Any]:
        """Load the XLSX matrix template."""
        return self._load_yaml("xlsx_matrix.yaml", DEFAULT_XLSX_TEMPLATE)

    def _load_yaml(self, filename: str, default: dict[str, Any]) -> dict[str, Any]:
        """Load a YAML file or return the default if unavailable."""
        if filename in self._cache:
            return self._cache[filename]

        filepath = self._dir / filename
        try:
            if filepath.exists():
                with open(filepath, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        self._cache[filename] = data
                        logger.info("Loaded template: %s", filepath)
                        return self._cache[filename]
        except Exception as e:
            logger.warning("Failed to load template %s: %s. Using defaults.", filepath, e)

        self._cache[filename] = default
        return default

    def clear_cache(self) -> None:
        """Clear the template cache (useful for testing)."""
        self._cache.clear()
        self._docx_template_cache = None


_loader: TemplateLoader | None = None


def get_template_loader(templates_dir: str | None = None) -> TemplateLoader:
    """获取 or create the singleton TemplateLoader."""
    global _loader
    if _loader is None:
        _loader = TemplateLoader(templates_dir=templates_dir)
    return _loader


def reset_template_loader() -> None:
    """Reset the template loader singleton."""
    global _loader
    _loader = None
