"""引文服务 FastAPI 端点测试 (M6-29).

所有测试使用 httpx AsyncClient 对 TestClient 应用进行测试。
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from citation_service.app import _citation_store, _store_verification_result
from citation_service.app import app as fastapi_app
from citation_service.verifier import CitationVerifier, MatchedChunk, VerificationResult, VerifiedCitation


@pytest.fixture
def app() -> FastAPI:
    """返回 FastAPI 应用。"""
    return fastapi_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """返回异步 HTTP 测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def clear_store() -> Generator[None, None, None]:
    """每个测试前清理内存引文存储。"""
    _citation_store.clear()
    yield
    _citation_store.clear()


class TestHealthEndpoint:
    """M6 -- 健康检查。"""

    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "citation-service" in data["service"]


class TestVerifyEndpoint:
    """M6-14/M6-15: POST /internal/citations/verify。"""

    async def test_verify_single_citation_direct(self, client: AsyncClient) -> None:
        request_body = {
            "text": "GDP grew 5% in 2023 [ref:report:p1-5].",
            "context_chunks": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "report",
                    "content": "GDP grew 5% in 2023 driven by strong industrial output.",
                    "page_start": 1,
                    "page_end": 5,
                }
            ],
        }

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 200
        data = response.json()

        assert "citations" in data
        assert "summary" in data
        assert len(data["citations"]) == 1
        assert data["citations"][0]["ref_id"] == "report:p1-5"

    async def test_verify_returns_correct_confidence(self, client: AsyncClient) -> None:
        request_body = {
            "text": "Some claim [ref:doc:p10].",
            "context_chunks": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "doc",
                    "content": "A completely unrelated text about healthcare reform and policy.",
                    "page_start": 10,
                    "page_end": 10,
                }
            ],
        }

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 默认阈值 0.85 且内容不相关时，应为 uncertain
        assert data["citations"][0]["confidence"] == "uncertain"

    async def test_verify_direct_confidence(self, client: AsyncClient) -> None:
        # 将引用标记放在句号前，使句子包含声明文本
        request_body = {
            "text": "GDP grew 5% in 2023 driven by strong industrial output [ref:report:p1-5].",
            "context_chunks": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "report",
                    "content": "GDP grew 5% in 2023 driven by strong industrial output.",
                    "page_start": 1,
                    "page_end": 5,
                }
            ],
        }

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["citations"][0]["confidence"] == "direct"

    async def test_verify_summary_counts(self, client: AsyncClient) -> None:
        request_body = {
            "text": (
                "GDP grew 5% [ref:report:p1-5]. "
                "Trade increased [ref:trade:p10]."
            ),
            "context_chunks": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "report",
                    "content": "GDP grew 5% in 2023 driven by strong industrial output.",
                    "page_start": 1,
                    "page_end": 5,
                },
                {
                    "chunk_id": "chunk-002",
                    "document_id": "trade",
                    "content": "Trade increased significantly compared to prior years.",
                    "page_start": 10,
                    "page_end": 10,
                },
            ],
        }

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["total"] == 2

    async def test_verify_matched_chunks_in_response(self, client: AsyncClient) -> None:
        # 使用长且高度相似的句子+分块以超过 0.85 阈值
        # 尽管 [ref:...] 标记会向句子添加额外 token。
        content = (
            "GDP grew five percent in the year driven by strong industrial "
            "output in the manufacturing sector that saw significant growth"
        )
        request_body = {
            "text": f"{content} [ref:report:p1-5].",
            "context_chunks": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "report",
                    "content": content,
                    "page_start": 1,
                    "page_end": 5,
                }
            ],
        }

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 200
        data = response.json()

        matched = data["citations"][0]["matched_chunks"]
        assert len(matched) >= 1
        assert matched[0]["chunk_id"] == "chunk-001"
        assert matched[0]["document_id"] == "report"
        assert matched[0]["page_start"] == 1
        assert matched[0]["page_end"] == 5
        assert "similarity" in matched[0]

    async def test_verify_empty_text_returns_400(self, client: AsyncClient) -> None:
        request_body = {"text": "", "context_chunks": []}

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 400

    async def test_verify_no_context_chunks(self, client: AsyncClient) -> None:
        request_body = {
            "text": "Some claim [ref:doc:p10].",
            "context_chunks": [],
        }

        response = await client.post("/internal/citations/verify", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["confidence"] == "uncertain"


class TestListCitationsEndpoint:
    """M6-16: GET /api/tasks/{task_id}/output/citations。"""

    async def test_list_citations_returns_stored_data(self, client: AsyncClient) -> None:
        vc = VerifiedCitation(
            ref_id="test:1",
            sentence="Test sentence.",
            sentence_index=0,
            confidence="direct",
            matched_chunks=[],
        )
        result = VerificationResult(
            citations=[vc],
            summary=CitationVerifier()._build_summary([vc]),
        )
        _store_verification_result("task-001", result)

        response = await client.get("/api/tasks/task-001/output/citations")
        assert response.status_code == 200
        data = response.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["ref_id"] == "test:1"
        assert data["citations"][0]["confidence"] == "direct"
        assert "summary" in data

    async def test_list_citations_with_confidence_filter(self, client: AsyncClient) -> None:
        vc1 = VerifiedCitation(
            ref_id="a:1", sentence="A", sentence_index=0, confidence="direct",
            matched_chunks=[],
        )
        vc2 = VerifiedCitation(
            ref_id="b:2", sentence="B", sentence_index=1, confidence="fuzzy",
            matched_chunks=[],
        )
        result = VerificationResult(
            citations=[vc1, vc2],
            summary=CitationVerifier()._build_summary([vc1, vc2]),
        )
        _store_verification_result("task-002", result)

        response = await client.get(
            "/api/tasks/task-002/output/citations?confidence=direct"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["confidence"] == "direct"

    async def test_list_citations_empty_task(self, client: AsyncClient) -> None:
        response = await client.get("/api/tasks/nonexistent/output/citations")
        assert response.status_code == 200
        data = response.json()
        assert data["citations"] == []
        assert data["summary"]["total"] == 0


class TestCitationDetailEndpoint:
    """M6-17/M6-18: GET /api/tasks/{task_id}/output/citations/{citation_id}。"""

    async def test_citation_detail_returns_full_info(self, client: AsyncClient) -> None:
        mc = MatchedChunk(
            chunk_id="c-001",
            document_id="report",
            page_start=1,
            page_end=5,
            excerpt="GDP grew 5%.",
            similarity=0.95,
        )
        vc = VerifiedCitation(
            ref_id="report:p1-5",
            sentence="GDP grew 5%.",
            sentence_index=0,
            confidence="direct",
            matched_chunks=[mc],
        )
        result = VerificationResult(
            citations=[vc],
            summary=CitationVerifier()._build_summary([vc]),
        )
        records = _store_verification_result("task-003", result)

        citation_id = records[0]["id"]
        response = await client.get(
            f"/api/tasks/task-003/output/citations/{citation_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ref_id"] == "report:p1-5"
        assert data["confidence"] == "direct"
        assert data["source"]["document_id"] == "report"
        assert data["source"]["page_start"] == 1
        assert data["verified_by"] is not None

    async def test_citation_detail_not_found(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/tasks/task-999/output/citations/nonexistent-id"
        )
        assert response.status_code == 404
        data = response.json()
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "NOT_FOUND"
