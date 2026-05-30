FROM python:3.12-slim AS builder
ARG SERVICE_DIR=.

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY shared /shared
COPY ${SERVICE_DIR}/pyproject.toml .
RUN sed -i 's|path = "../shared"|path = "/shared"|g' pyproject.toml && uv pip install --system --no-cache .

FROM python:3.12-slim
ARG SERVICE_DIR=.

WORKDIR /app
RUN groupadd -r policyai && useradd -r -g policyai policyai

RUN pip install --no-cache-dir uv

COPY --from=builder /usr/local /usr/local

COPY ${SERVICE_DIR}/pyproject.toml .
RUN uv pip install --system --no-deps .

COPY ${SERVICE_DIR}/. .

RUN chown -R policyai:policyai /app
USER policyai

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]