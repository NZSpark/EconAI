FROM python:3.12-slim

WORKDIR /app
RUN groupadd -r econai && useradd -r -g econai econai
RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY . .

RUN chown -R econai:econai /app
USER econai

EXPOSE 8004
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')"

CMD ["uvicorn", "llm_router.app:app", "--host", "0.0.0.0", "--port", "8004"]