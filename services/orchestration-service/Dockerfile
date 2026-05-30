FROM python:3.12-slim
ARG SERVICE_DIR=.

WORKDIR /app
RUN groupadd -r policyai && useradd -r -g policyai policyai
RUN pip install --no-cache-dir uv

COPY shared /shared
COPY ${SERVICE_DIR}/pyproject.toml .
RUN sed -i 's|path = "../../shared"|path = "/shared"|g' pyproject.toml && uv pip install --system .

COPY ${SERVICE_DIR}/. .

RUN mkdir -p /var/run/celery && chown -R policyai:policyai /app /var/run/celery
USER policyai

EXPOSE 8003
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

CMD ["uvicorn", "orchestration_service.app:app", "--host", "0.0.0.0", "--port", "8003"]