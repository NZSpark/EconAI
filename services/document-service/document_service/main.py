"""文档服务入口。

用法:
    uvicorn document_service.main:app --host 0.0.0.0 --port 8001

Celery worker:
    celery -A document_service.celery_app worker --loglevel=info -Q document
"""

from __future__ import annotations

from document_service.app import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
