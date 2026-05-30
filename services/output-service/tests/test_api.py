"""测试辅助函数。"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from output_service.app import _output_store, app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def clear_store() -> None:
    """Clear the in-memory output store before each test."""
    _output_store.clear()


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "output-service" in data["service"]


class TestGenerateEndpoint:
    async def test_generate_markdown(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-001",
            "title": "Test Report",
            "sections": [{"title": "Intro", "level": 1, "content": "Hello [ref:doc:p1]."}],
            "citations": [{"ref_id": "doc:p1", "confidence": "direct"}],
            "formats": ["md"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert len(data["outputs"]) == 1
        assert data["outputs"][0]["format"] == "md"

    async def test_generate_docx(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-002",
            "title": "Policy Draft",
            "sections": [{"title": "S1", "level": 1, "content": "Content."}],
            "citations": [],
            "formats": ["docx"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["outputs"][0]["format"] == "docx"
        assert data["outputs"][0]["storage_path"].endswith(".docx")

    async def test_generate_xlsx(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-003",
            "title": "Comparison",
            "sections": [{"title": "S1", "level": 1, "content": "Data."}],
            "citations": [],
            "formats": ["xlsx"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 200
        assert response.json()["outputs"][0]["format"] == "xlsx"

    async def test_generate_pptx(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-004",
            "title": "Briefing",
            "sections": [{"title": "S1", "level": 1, "content": "Content."}],
            "citations": [],
            "formats": ["pptx"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 200
        assert response.json()["outputs"][0]["format"] == "pptx"

    async def test_generate_multiple_formats(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-005",
            "title": "Report",
            "sections": [{"title": "S1", "level": 1, "content": "Text."}],
            "citations": [],
            "formats": ["md", "docx"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert len(data["outputs"]) == 2

    async def test_generate_empty_sections_returns_400(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-err",
            "title": "Report",
            "sections": [],
            "citations": [],
            "formats": ["md"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 400

    async def test_generate_invalid_format_returns_400(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-err",
            "title": "Report",
            "sections": [{"title": "S1", "level": 1, "content": "Text."}],
            "citations": [],
            "formats": ["pdf"],
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 400

    async def test_generate_with_metadata(self, client: AsyncClient) -> None:
        request_body = {
            "task_id": "task-006",
            "title": "Test",
            "sections": [{"title": "S1", "level": 1, "content": "Text."}],
            "citations": [],
            "formats": ["md"],
            "metadata": {"author": "PolicyAI", "date": "2026-05-19", "keywords": ["trade"]},
        }
        response = await client.post("/internal/output/generate", json=request_body)
        assert response.status_code == 200


class TestPreviewEndpoint:
    async def test_preview_returns_markdown(self, client: AsyncClient) -> None:
        # First generate
        gen_body = {
            "task_id": "task-preview",
            "title": "Preview Test",
            "sections": [{"title": "S1", "level": 1, "content": "Preview content."}],
            "citations": [],
            "formats": ["md"],
        }
        await client.post("/internal/output/generate", json=gen_body)

        response = await client.get("/api/tasks/task-preview/output")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-preview"
        assert "Preview content" in data["content"]

    async def test_preview_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks/nonexistent/output")
        assert response.status_code == 404


class TestExportEndpoint:
    async def test_export_docx(self, client: AsyncClient) -> None:
        gen_body = {
            "task_id": "task-export",
            "title": "Export Test",
            "sections": [{"title": "S1", "level": 1, "content": "Content."}],
            "citations": [],
            "formats": ["docx"],
        }
        await client.post("/internal/output/generate", json=gen_body)

        response = await client.get("/api/tasks/task-export/export?format=docx")
        assert response.status_code == 200
        assert (
            response.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "attachment" in response.headers["content-disposition"]

    async def test_export_xlsx(self, client: AsyncClient) -> None:
        gen_body = {
            "task_id": "task-xlsx",
            "title": "XLSX Test",
            "sections": [{"title": "S1", "level": 1, "content": "Data."}],
            "citations": [],
            "formats": ["xlsx"],
        }
        await client.post("/internal/output/generate", json=gen_body)

        response = await client.get("/api/tasks/task-xlsx/export?format=xlsx")
        assert response.status_code == 200

    async def test_export_pptx(self, client: AsyncClient) -> None:
        gen_body = {
            "task_id": "task-pptx",
            "title": "PPTX Test",
            "sections": [{"title": "S1", "level": 1, "content": "Content."}],
            "citations": [],
            "formats": ["pptx"],
        }
        await client.post("/internal/output/generate", json=gen_body)

        response = await client.get("/api/tasks/task-pptx/export?format=pptx")
        assert response.status_code == 200

    async def test_export_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks/nonexistent/export?format=docx")
        assert response.status_code == 404

    async def test_export_markdown(self, client: AsyncClient) -> None:
        gen_body = {
            "task_id": "task-md",
            "title": "MD Export",
            "sections": [{"title": "S1", "level": 1, "content": "Markdown content."}],
            "citations": [],
            "formats": ["md"],
        }
        await client.post("/internal/output/generate", json=gen_body)

        response = await client.get("/api/tasks/task-md/export?format=md")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
