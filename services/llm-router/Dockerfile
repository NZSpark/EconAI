FROM python:3.12-slim
ARG SERVICE_DIR=.

WORKDIR /app
RUN groupadd -r policyai && useradd -r -g policyai policyai
RUN pip install --no-cache-dir uv

COPY shared /shared
COPY ${SERVICE_DIR}/pyproject.toml .
RUN sed -i 's|path = "../../shared"|path = "/shared"|g' pyproject.toml && uv pip install --system .

COPY ${SERVICE_DIR}/. .

RUN chown -R policyai:policyai /app
USER policyai

EXPOSE 8004
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')"

CMD ["uvicorn", "llm_router.app:app", "--host", "0.0.0.0", "--port", "8004"]