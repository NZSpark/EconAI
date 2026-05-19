"""M7-39: Tests for template loading and fallback."""

from output_service.template_loader import (
    DEFAULT_DOCX_TEMPLATE,
    DocxTemplateConfig,
    TemplateLoader,
)


class TestDocxTemplateConfig:
    def test_page_margins(self) -> None:
        cfg = DocxTemplateConfig(DEFAULT_DOCX_TEMPLATE)
        margins = cfg.page_margins
        assert margins["top_mm"] == 37
        assert margins["left_mm"] == 28

    def test_fonts(self) -> None:
        cfg = DocxTemplateConfig(DEFAULT_DOCX_TEMPLATE)
        fonts = cfg.fonts
        assert "title_h1" in fonts
        assert "body" in fonts
        assert fonts["title_h1"]["size_pt"] == 22

    def test_header_config(self) -> None:
        cfg = DocxTemplateConfig(DEFAULT_DOCX_TEMPLATE)
        header = cfg.header
        assert header["enabled"] is True

    def test_footer_config(self) -> None:
        cfg = DocxTemplateConfig(DEFAULT_DOCX_TEMPLATE)
        footer = cfg.footer
        assert footer["enabled"] is True

    def test_reference_list(self) -> None:
        cfg = DocxTemplateConfig(DEFAULT_DOCX_TEMPLATE)
        refs = cfg.reference_list
        assert refs["title"] == "参考文献"

    def test_citation_display(self) -> None:
        cfg = DocxTemplateConfig(DEFAULT_DOCX_TEMPLATE)
        display = cfg.citation_display
        assert display["style"] in ("footnote", "endnote")


class TestTemplateLoader:
    def test_load_docx_default(self) -> None:
        loader = TemplateLoader(templates_dir="/nonexistent/path")
        template = loader.load_docx_template()
        assert isinstance(template, DocxTemplateConfig)
        assert template.page_margins["top_mm"] == 37

    def test_load_pptx_default(self) -> None:
        loader = TemplateLoader(templates_dir="/nonexistent/path")
        template = loader.load_pptx_template()
        assert "slide" in template
        assert "fonts" in template

    def test_load_xlsx_default(self) -> None:
        loader = TemplateLoader(templates_dir="/nonexistent/path")
        template = loader.load_xlsx_template()
        assert "sheet_comparison" in template
        assert "sheet_citations" in template

    def test_caching(self) -> None:
        loader = TemplateLoader(templates_dir="/nonexistent/path")
        t1 = loader.load_docx_template()
        t2 = loader.load_docx_template()
        assert t1 is t2  # Same cached object

    def test_clear_cache(self) -> None:
        loader = TemplateLoader(templates_dir="/nonexistent/path")
        loader.load_docx_template()
        loader.clear_cache()
        # Should reload without error
        t = loader.load_docx_template()
        assert isinstance(t, DocxTemplateConfig)

    def test_loads_from_real_templates_dir(self) -> None:
        """Verify the actual templates in the repo load correctly."""
        loader = TemplateLoader(templates_dir="templates/output")
        template = loader.load_docx_template()
        assert isinstance(template, DocxTemplateConfig)
        # The real template should have GB/T 9704 metadata
        loader.clear_cache()
