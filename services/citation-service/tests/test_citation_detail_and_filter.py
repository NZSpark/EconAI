"""Tests for citation listing, filtering, and detail (User Manual §6.2, §6.3).

Black-box tests: all tests go through the HTTP API endpoints
  GET /api/tasks/{task_id}/output/citations          — citation list
  GET /api/tasks/{task_id}/output/citations/{id}     — single citation detail

User Manual §6.2 (查看引用来源):
- 点击报告中的引用角标，弹出引用详情 Popover
- 置信度标签（绿/黄/红）
- 来源文档名称
- 页码范围
- 原文摘录
- AI生成的引用句子

User Manual §6.3 (引用列表面板):
- 按置信度过滤：全部 / 直接引用 / 模糊引用 / 不确定
- 每个引用卡片显示详细信息
- 顶部显示引用统计（总数、各置信度数量）

Gaps found:
  GAP-B: 引用列表端点不返回 summary/统计信息
         用户手册 §6.3: "顶部显示引用统计（总数、各置信度数量）"
         当前 GET /api/tasks/{task_id}/output/citations 返回纯数组

  GAP-C: 引用列表中的 citation 没有 id 字段
         用户手册 §6.2: 用户点击角标 → 调用 detail 端点
         当前 VerifiedCitationResponse 只有 ref_id，没有 id
         detail 端点需要 id 参数，但 list 不返回 id
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from citation_service.app import _citation_store, _store_verification_result, app
from citation_service.verifier import (
    VerificationResult,
    VerificationSummary,
    VerifiedCitation,
)


# ---------------------------------------------------------------------------
# Helpers: setup citations via the internal store
# ---------------------------------------------------------------------------


def _setup_sample_citations(task_id: str) -> list[dict]:
    """Seed the citation store with sample verified citations for a task.

    This mimics what happens after a successful /internal/citations/verify call
    which persists results into the store that the public API reads from.
    """
    vc_list = [
        VerifiedCitation(
            ref_id="doc1:p1-3",
            sentence="数字贸易规则正在成为国际贸易谈判的核心议题。",
            sentence_index=0,
            confidence="direct",
            matched_chunks=[],
        ),
        VerifiedCitation(
            ref_id="doc1:p5",
            sentence="关税壁垒对发展中国家的影响尤为显著。",
            sentence_index=1,
            confidence="fuzzy",
            matched_chunks=[],
        ),
        VerifiedCitation(
            ref_id="doc2:p10-12",
            sentence="WTO框架下的电子商务谈判进展缓慢。",
            sentence_index=2,
            confidence="uncertain",
            matched_chunks=[],
        ),
        VerifiedCitation(
            ref_id="doc1:p7-8",
            sentence="跨境数据流动规则需要国际协调。",
            sentence_index=3,
            confidence="direct",
            matched_chunks=[],
        ),
    ]
    result = VerificationResult(
        citations=vc_list,
        summary=VerificationSummary(total=4, direct=2, fuzzy=1, uncertain=1),
    )
    return _store_verification_result(task_id, result)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for citation-service."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def clear_store():
    """Clear the in-memory citation store before each test."""
    _citation_store.clear()


# ===========================================================================
# §6.3 引用列表面板 — 列出所有引用 (should pass — already implemented)
# ===========================================================================


class TestCitationList:
    """User Manual §6.3: 引用列表面板 — list citations."""

    @pytest.mark.asyncio
    async def test_list_returns_all_citations(self, client: AsyncClient) -> None:
        """Listing citations returns all stored citations for a task."""
        task_id = "task-list-all"
        _setup_sample_citations(task_id)

        resp = await client.get(f"/api/tasks/{task_id}/output/citations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "citations" in data
        assert "summary" in data
        assert len(data["citations"]) == 4

    @pytest.mark.asyncio
    async def test_list_empty_for_no_citations(self, client: AsyncClient) -> None:
        """Listing citations for a task with no citations returns an empty list."""
        resp = await client.get("/api/tasks/nonexistent-task/output/citations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["citations"] == []
        assert data["summary"]["total"] == 0

    @pytest.mark.asyncio
    async def test_each_citation_has_required_fields(self, client: AsyncClient) -> None:
        """Each citation in the list should have id, ref_id, sentence, confidence fields."""
        task_id = "task-schema"
        _setup_sample_citations(task_id)

        resp = await client.get(f"/api/tasks/{task_id}/output/citations")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = {"id", "ref_id", "sentence", "sentence_index", "confidence", "matched_chunks"}
        for citation in data["citations"]:
            missing = required_fields - set(citation.keys())
            assert not missing, f"Missing fields: {missing}"


# ===========================================================================
# §6.3 按置信度过滤 (should pass — already implemented)
# ===========================================================================


class TestCitationConfidenceFilter:
    """User Manual §6.3: 按置信度过滤：全部 / 直接引用 / 模糊引用 / 不确定."""

    @pytest.mark.asyncio
    async def test_filter_direct(self, client: AsyncClient) -> None:
        """Filtering by 'direct' returns only green/直接引用 citations."""
        task_id = "task-filter-direct"
        _setup_sample_citations(task_id)

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations?confidence=direct"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["citations"]) == 2
        for c in data["citations"]:
            assert c["confidence"] == "direct"

    @pytest.mark.asyncio
    async def test_filter_fuzzy(self, client: AsyncClient) -> None:
        """Filtering by 'fuzzy' returns only yellow/模糊引用 citations."""
        task_id = "task-filter-fuzzy"
        _setup_sample_citations(task_id)

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations?confidence=fuzzy"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["citations"]) == 1
        for c in data["citations"]:
            assert c["confidence"] == "fuzzy"

    @pytest.mark.asyncio
    async def test_filter_uncertain(self, client: AsyncClient) -> None:
        """Filtering by 'uncertain' returns only red/不确定 citations."""
        task_id = "task-filter-uncertain"
        _setup_sample_citations(task_id)

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations?confidence=uncertain"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["citations"]) == 1
        for c in data["citations"]:
            assert c["confidence"] == "uncertain"


# ===========================================================================
# §6.2 查看引用来源 — 单个引用详情 (should pass — already implemented)
# ===========================================================================


class TestCitationDetail:
    """User Manual §6.2: 查看引用来源 — single citation detail Popover."""

    @pytest.mark.asyncio
    async def test_detail_returns_full_info(self, client: AsyncClient) -> None:
        """Citation detail returns ref_id, confidence, sentence, verified_at."""
        task_id = "task-detail"
        records = _setup_sample_citations(task_id)
        citation_id = records[0]["id"]

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations/{citation_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ref_id"] == "doc1:p1-3"
        assert data["confidence"] == "direct"
        assert "sentence" in data
        assert "verified_at" in data
        assert "verified_by" in data

    @pytest.mark.asyncio
    async def test_detail_not_found_returns_404(self, client: AsyncClient) -> None:
        """Requesting a non-existent citation returns 404."""
        task_id = "task-detail-nf"
        _setup_sample_citations(task_id)

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations/nonexistent-uuid"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_direct_citation_has_correct_confidence(self, client: AsyncClient) -> None:
        """A direct citation should have confidence 'direct' (绿色)."""
        task_id = "task-direct-label"
        records = _setup_sample_citations(task_id)
        direct = [r for r in records if r["confidence"] == "direct"]
        citation_id = direct[0]["id"]

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations/{citation_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["confidence"] == "direct"

    @pytest.mark.asyncio
    async def test_uncertain_citation_has_no_source(self, client: AsyncClient) -> None:
        """Uncertain (红色) citation has no matched source chunks."""
        task_id = "task-uncertain-source"
        records = _setup_sample_citations(task_id)
        uncertain = [r for r in records if r["confidence"] == "uncertain"]
        citation_id = uncertain[0]["id"]

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations/{citation_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["confidence"] == "uncertain"
        assert data["source"] is None


# ===========================================================================
# GAP TESTS — these SHOULD FAIL because the feature is missing from the API
# ===========================================================================


class TestCitationListSummaryMissing:
    """GAP-B: 用户手册 §6.3 明确要求"顶部显示引用统计（总数、各置信度数量）"。

    当前 GET /api/tasks/{task_id}/output/citations 返回 list[VerifiedCitationResponse]，
    即一个纯数组，不包含任何 summary/statistics 信息。
    前端需要自己遍历数组来统计各置信度数量，与手册描述不符。

    期望: list endpoint 应该返回包装对象，包含 citations 数组 + summary 统计信息，
    类似于 verify endpoint 的响应格式。
    """

    @pytest.mark.asyncio
    async def test_list_endpoint_returns_summary(self, client: AsyncClient) -> None:
        """GAP: 引用列表端点应该返回 summary 统计信息。

        这个测试会失败，因为当前返回的是纯数组，没有 summary 字段。
        """
        task_id = "task-gap-summary"
        _setup_sample_citations(task_id)

        resp = await client.get(f"/api/tasks/{task_id}/output/citations")
        assert resp.status_code == 200
        data = resp.json()

        # 期望: data 是一个对象 {citations: [...], summary: {total, direct, fuzzy, uncertain}}
        assert isinstance(data, dict), (
            f"GAP: Citation list endpoint returns a plain array. "
            f"User Manual §6.3 says '顶部显示引用统计（总数、各置信度数量）'. "
            f"Expected an object with 'citations' and 'summary' fields."
        )
        assert "summary" in data, (
            "GAP: Citation list missing 'summary'. "
            "Expected summary with total/direct/fuzzy/uncertain counts per §6.3."
        )
        assert "citations" in data
        summary = data["summary"]
        assert "total" in summary
        assert "direct" in summary
        assert "fuzzy" in summary
        assert "uncertain" in summary
        # summary 的 total 应该等于 citations 的数量
        assert summary["total"] == len(data["citations"])

    @pytest.mark.asyncio
    async def test_list_endpoint_summary_matches_filtered_results(self, client: AsyncClient) -> None:
        """GAP: 过滤后的引用列表也应该返回对应的 summary。

        当用户选择只看"直接引用"时，summary 应该反映过滤后的统计。
        """
        task_id = "task-gap-filtered-summary"
        _setup_sample_citations(task_id)

        resp = await client.get(
            f"/api/tasks/{task_id}/output/citations?confidence=direct"
        )
        assert resp.status_code == 200
        data = resp.json()

        # 过滤后的响应也应该有 summary
        assert isinstance(data, dict), (
            "GAP: Filtered citation list should also return object with summary. "
            "Even when filtering by confidence, the summary should reflect the filter."
        )
        assert "summary" in data
        assert data["summary"]["total"] == 2  # 2 direct citations
        assert data["summary"]["direct"] == 2


class TestCitationListIdMissing:
    """GAP-C: 引用列表中的 citation 没有 id 字段。

    用户手册 §6.2 描述用户点击报告中的引用角标 [1] 查看详情。
    这意味着流程是: list → 获取 citation id → 调用 detail 端点。
    
    当前 VerifiedCitationResponse 只有 ref_id，没有 id。
    detail 端点 (GET .../citations/{citation_id}) 需要 id，
    但 list 不返回 id，导致前端无法从 list 中获取 id 来调用 detail。

    期望: 每个 citation 在 list 响应中应包含 id 字段。
    """

    @pytest.mark.asyncio
    async def test_list_citation_has_id_field(self, client: AsyncClient) -> None:
        """GAP: 列表中的每个 citation 应该包含 id 字段。

        这个测试会失败，因为当前 VerifiedCitationResponse 没有 id 字段。
        """
        task_id = "task-gap-id"
        _setup_sample_citations(task_id)

        resp = await client.get(f"/api/tasks/{task_id}/output/citations")
        assert resp.status_code == 200
        data = resp.json()

        # 如果 GAP-B 也失败，data 是数组；如果 GAP-B 修复了，data 是对象
        citations = data if isinstance(data, list) else data.get("citations", [])

        assert len(citations) > 0, "Expected at least one citation for this test"
        for citation in citations:
            assert "id" in citation, (
                f"GAP: Citation missing 'id' field. "
                f"User Manual §6.2: user clicks citation badge to view detail. "
                f"The detail endpoint requires citation id, but the list doesn't return it. "
                f"Current citation keys: {list(citation.keys())}"
            )
            assert citation["id"], "Citation id should not be empty"

    @pytest.mark.asyncio
    async def test_can_use_id_from_list_to_call_detail(self, client: AsyncClient) -> None:
        """GAP: 从 list 获取的 id 应该能用于 detail 端点。

        完整的用户流程: list → 获取 id → detail。如果 list 不返回 id，
        这个链路就断了。
        """
        task_id = "task-gap-id-detail"
        _setup_sample_citations(task_id)

        resp = await client.get(f"/api/tasks/{task_id}/output/citations")
        assert resp.status_code == 200
        data = resp.json()

        citations = data if isinstance(data, list) else data.get("citations", [])
        assert len(citations) > 0

        # 尝试用 list 返回的第一个 citation 的 id 调用 detail
        citation_id = citations[0].get("id")
        assert citation_id, (
            "GAP: Cannot get citation id from list response. "
            "Without id, the detail endpoint is unreachable from the list."
        )

        detail_resp = await client.get(
            f"/api/tasks/{task_id}/output/citations/{citation_id}"
        )
        assert detail_resp.status_code == 200


# ===========================================================================
# §6.3 引用统计 — verify endpoint returns summary (should pass — already implemented)
# ===========================================================================


class TestCitationVerifySummary:
    """User Manual §6.3: verify endpoint 返回的 summary 用于统计栏."""

    @pytest.mark.asyncio
    async def test_verify_returns_summary_counts(self, client: AsyncClient) -> None:
        """POST /internal/citations/verify should return summary with confidence counts."""
        resp = await client.post(
            "/internal/citations/verify",
            json={
                "text": (
                    "GDP grew 5% [ref:report:1-5]. "
                    "Trade increased [ref:trade:10]."
                ),
                "context_chunks": [
                    {
                        "chunk_id": "c1",
                        "document_id": "report",
                        "content": "GDP grew 5% in 2023 driven by industrial output.",
                        "page_start": 1,
                        "page_end": 5,
                    }
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        summary = data["summary"]
        assert "total" in summary
        assert "direct" in summary
        assert "fuzzy" in summary
        assert "uncertain" in summary
        assert summary["total"] == summary["direct"] + summary["fuzzy"] + summary["uncertain"]
        assert summary["total"] == len(data["citations"])
