"""Knowledge base lifecycle management: archive, restore, delete, reindex."""

from __future__ import annotations

import logging
from typing import Any

from kb_service.indexer import IndexPipeline

logger = logging.getLogger(__name__)

# In-memory archive state for testing/development
# In production this would be persisted to PostgreSQL
_archived_projects: set[str] = set()
_archived_documents: set[str] = set()


class LifecycleManager:
    """Manages KB lifecycle operations: archive, restore, delete, batch reindex."""

    def __init__(self, pipeline: IndexPipeline) -> None:
        self.pipeline = pipeline

    async def archive_project(self, project_id: str) -> dict[str, str]:
        """Archive project: mark all its document indices as archived."""
        _archived_projects.add(project_id)
        logger.info("Project %s archived", project_id)
        return {"status": "archived", "message": f"Project {project_id} archived"}

    async def restore_project(self, project_id: str) -> dict[str, str]:
        """Restore project: restore its indices from archived to active."""
        _archived_projects.discard(project_id)
        logger.info("Project %s restored", project_id)
        return {"status": "active", "message": f"Project {project_id} restored"}

    async def archive_document(self, document_id: str) -> dict[str, str]:
        """Archive a single document's indices."""
        _archived_documents.add(document_id)
        logger.info("Document %s archived", document_id)
        return {"status": "archived", "message": f"Document {document_id} archived"}

    async def restore_document(self, document_id: str) -> dict[str, str]:
        """Restore a single document's indices."""
        _archived_documents.discard(document_id)
        logger.info("Document %s restored", document_id)
        return {"status": "active", "message": f"Document {document_id} restored"}

    async def delete_document(self, document_id: str) -> dict[str, Any]:
        """Cascade delete: remove chunks + vectors + BM25 index for a document."""
        count = await self.pipeline.delete_document(document_id)
        _archived_documents.discard(document_id)
        logger.info("Document %s deleted (%d vectors removed)", document_id, count)
        return {"status": "deleted", "message": f"Document {document_id} deleted", "deleted_vectors": count}

    async def delete_project(self, project_id: str) -> dict[str, Any]:
        """Cascade delete all indices for a project."""
        count = await self.pipeline.delete_project(project_id)
        _archived_projects.discard(project_id)
        logger.info("Project %s deleted (%d vectors removed)", project_id, count)
        return {"status": "deleted", "message": f"Project {project_id} deleted", "deleted_vectors": count}

    async def reindex_project(
        self,
        project_id: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Batch reindex all chunks for a project."""
        count = await self.pipeline.reindex_chunks(chunks)
        return {"status": "reindexed", "message": f"Project {project_id} reindexed", "indexed_chunks": count}

    @staticmethod
    def is_archived(project_id: str) -> bool:
        return project_id in _archived_projects

    @staticmethod
    def is_document_archived(document_id: str) -> bool:
        return document_id in _archived_documents
