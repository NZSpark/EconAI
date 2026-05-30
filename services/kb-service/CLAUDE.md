# CLAUDE.md — kb-service (M3)

## Role

Embedding, vector indexing (Milvus/Qdrant), BM25 keyword search, hybrid search pipeline (RRF fusion + BGE-Reranker). KB lifecycle management (archive/restore at document and project level).

## Directory structure

```
services/kb-service/
├── Dockerfile
├── pyproject.toml
├── kb_service/
│   ├── app.py               # FastAPI: project/org search, internal search, index CRUD, lifecycle
│   ├── config.py             # Vector DB type, embedding model, hybrid search params
│   ├── embedding.py          # Embedding client (text2vec/m3e) with Redis cache
│   ├── vector_store.py       # Abstract vector store interface
│   ├── milvus_store.py       # Milvus impl: 1024-dim, IVF_FLAT index
│   ├── qdrant_store.py       # Qdrant impl (alternative)
│   ├── bm25.py               # BM25 via PostgreSQL Full-Text Search (GIN index)
│   ├── hybrid_search.py      # Pipeline: vector(top-50) + BM25(top-50) → RRF(k=60) → top-30 → Reranker → top-10
│   ├── reranker.py           # BGE-Reranker cross-encoder + NoopReranker fallback
│   ├── indexer.py            # Indexing pipeline: chunks → embed → vector store + BM25 index
│   ├── lifecycle.py          # Archive/restore (document-level + project-level)
│   └── deps.py               # Factory functions for DI
```

## Hybrid search pipeline

```
Parallel:
  Vector semantic search  → top-50
  BM25 keyword search     → top-50
         ↓
  RRF fusion (k=60)     → top-30
         ↓
  BGE-Reranker          → top-10
```

## Search modes

- `hybrid` (default): full pipeline above
- `vector`: semantic only
- `bm25`: keyword text search only

## Key dependencies

- httpx (calls other services)
- asyncpg + redis
- `policyai-shared`

## Indexing trigger

Listens for `kb:index:request` events from document-service. Also supports direct API calls.

## Run / test

```bash
uv run uvicorn kb_service.app:app --host 0.0.0.0 --port 8002 --reload
pytest --tb=short && mypy . --strict && ruff check .
```

## Requirements

Milvus (or Qdrant) must be healthy before this service can index/search.
