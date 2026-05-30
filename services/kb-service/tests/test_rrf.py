"""测试辅助函数。"""

from __future__ import annotations

from kb_service.hybrid_search import HybridSearcher


class TestRRFFusion:
    """测试辅助函数。"""

    def test_rrf_empty_inputs(self) -> None:
        result = HybridSearcher._rrf_fusion([], [])
        assert result == []

    def test_rrf_vector_only(self) -> None:
        vec_results = [
            {"chunk_id": "a", "score": 0.9, "content": "text a"},
            {"chunk_id": "b", "score": 0.8, "content": "text b"},
        ]
        result = HybridSearcher._rrf_fusion(vec_results, [], k=60)
        assert len(result) == 2
        assert result[0]["chunk_id"] == "a"
        assert result[1]["chunk_id"] == "b"

    def test_rrf_bm25_only(self) -> None:
        bm25_results = [
            {"chunk_id": "x", "score": 10.0, "content": "text x"},
            {"chunk_id": "y", "score": 5.0, "content": "text y"},
        ]
        result = HybridSearcher._rrf_fusion([], bm25_results, k=60)
        assert len(result) == 2
        assert result[0]["chunk_id"] == "x"
        assert result[1]["chunk_id"] == "y"

    def test_rrf_fusion_combines_results(self) -> None:
        vec_results = [
            {"chunk_id": "c1", "score": 0.95, "content": "vector top"},
            {"chunk_id": "c2", "score": 0.80, "content": "vector second"},
            {"chunk_id": "c3", "score": 0.70, "content": "vector third"},
        ]
        bm25_results = [
            {"chunk_id": "c2", "score": 8.0, "content": "bm25 top"},  # same as vec #2
            {"chunk_id": "c4", "score": 6.0, "content": "bm25 second"},
            {"chunk_id": "c1", "score": 4.0, "content": "bm25 third"},  # same as vec #1
        ]

        result = HybridSearcher._rrf_fusion(vec_results, bm25_results, k=60)
        # c2 appears in both lists → higher combined score
        ids = [r["chunk_id"] for r in result]
        assert len(ids) == 4  # c1, c2, c3, c4 — unique
        assert "c1" in ids
        assert "c2" in ids
        assert "c3" in ids
        assert "c4" in ids

    def test_rrf_chunk_appearing_in_both_lists_ranks_higher(self) -> None:
        """A chunk appearing in both vector and BM25 results should benefit from both rankings."""
        vec_results = [
            {"chunk_id": "shared", "score": 0.5, "content": "in both"},
            {"chunk_id": "vec_only", "score": 0.9, "content": "vector only"},
        ]
        bm25_results = [
            {"chunk_id": "shared", "score": 100.0, "content": "in both"},
            {"chunk_id": "bm25_only", "score": 50.0, "content": "bm25 only"},
        ]

        result = HybridSearcher._rrf_fusion(vec_results, bm25_results, k=60)

        # 'shared' should be ranked first (appears as #1 in both)
        assert result[0]["chunk_id"] == "shared"

    def test_rrf_k_parameter_affects_scores(self) -> None:
        """Larger k reduces score differences between ranks."""
        results = [
            {"chunk_id": "a", "score": 1.0, "content": "first"},
            {"chunk_id": "b", "score": 0.9, "content": "second"},
        ]

        r1 = HybridSearcher._rrf_fusion(results, [], k=1)
        r2 = HybridSearcher._rrf_fusion(results, [], k=100)

        # Ratio between 1st and 2nd place scores
        ratio1 = r1[0]["score"] / r1[1]["score"]
        ratio2 = r2[0]["score"] / r2[1]["score"]
        # With k=1, the ratio is more extreme: (1/2) / (1/3) = 1.5
        # With k=100, the ratio is closer to 1: (1/101) / (1/102) ≈ 1.01
        assert ratio1 > ratio2

    def test_rrf_preserves_content_field(self) -> None:
        vec_results = [{"chunk_id": "c1", "score": 0.9, "content": "hello world"}]
        result = HybridSearcher._rrf_fusion(vec_results, [], k=60)
        assert result[0]["content"] == "hello world"

    def test_rrf_handles_ties_gracefully(self) -> None:
        vec_results = [{"chunk_id": c, "score": 0.5, "content": c} for c in ["a", "b", "c", "d", "e"]]
        bm25_results = [{"chunk_id": c, "score": 1.0, "content": c} for c in ["e", "d", "c", "b", "a"]]

        result = HybridSearcher._rrf_fusion(vec_results, bm25_results, k=60)
        assert len(result) == 5

    def test_rrf_score_is_monotonic(self) -> None:
        """Scores should be strictly decreasing (or equal) in order."""
        vec_results = [
            {"chunk_id": f"c{i}", "score": 1.0 - i * 0.1, "content": str(i)}
            for i in range(10)
        ]
        result = HybridSearcher._rrf_fusion(vec_results, [], k=60)
        scores = [r["score"] for r in result]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Score not monotonic at index {i}: {scores[i]} < {scores[i+1]}"
