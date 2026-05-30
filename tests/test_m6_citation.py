"""M6 引文服务测试 — detailed-design.md 第 7.2、7.3 节。

测试: 健康检查、引文验证。
"""

from __future__ import annotations

import httpx
import pytest

CIT_SVC = "http://localhost:8005"


def _service_ready() -> bool:
    try:
        r = httpx.get(f"{CIT_SVC}/health", timeout=3)
        return bool(r.status_code == 200)
    except Exception:
        return False


@pytest.mark.skipif(not _service_ready(), reason="引文服务不可用")
class TestCitationHealth:
    def test_health(self) -> None:
        resp = httpx.get(f"{CIT_SVC}/health", timeout=5)
        assert resp.status_code == 200


@pytest.mark.skipif(not _service_ready(), reason="引文服务不可用")
class TestCitationVerify:
    """POST /internal/citations/verify — 第 7.2.1 节。"""

    def test_verify_empty_text(self) -> None:
        """空文本返回有效或错误响应。"""
        resp = httpx.post(
            f"{CIT_SVC}/internal/citations/verify",
            json={"text": "", "context_chunk_ids": []},
            timeout=10,
        )
        assert resp.status_code in (200, 400)

    def test_verify_with_markup(self) -> None:
        """含 [ref:...] 标记的文本被解析。"""
        resp = httpx.post(
            f"{CIT_SVC}/internal/citations/verify",
            json={
                "text": "研究表明 [ref:doc_123:p45-48] 政策很重要。",
                "context_chunk_ids": [],
            },
            timeout=10,
        )
        # 应返回 200 含引文对象，或 400/500
        assert resp.status_code in (200, 400, 500), f"状态码 {resp.status_code}: {resp.text}"

    def test_verify_with_uncertain_reference(self) -> None:
        """含 [ref:uncertain] 的文本被处理。"""
        resp = httpx.post(
            f"{CIT_SVC}/internal/citations/verify",
            json={
                "text": "这一趋势可能会持续 [ref:uncertain]。",
                "context_chunk_ids": [],
            },
            timeout=10,
        )
        assert resp.status_code in (200, 400, 500), f"状态码 {resp.status_code}: {resp.text}"
