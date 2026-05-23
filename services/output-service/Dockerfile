FROM python:3.12-slim
ARG SERVICE_DIR=.

WORKDIR /app
RUN groupadd -r econai && useradd -r -g econai econai
RUN pip install --no-cache-dir uv

COPY shared /shared
COPY ${SERVICE_DIR}/pyproject.toml .
RUN sed -i 's|path = "../../shared"|path = "/shared"|g' pyproject.toml && uv pip install --system .

COPY ${SERVICE_DIR}/. .

RUN chown -R econai:econai /app
USER econai

EXPOSE 8006
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8006/health')"

CMD ["uvicorn", "output_service.app:app", "--host", "0.0.0.0", "--port", "8006"]