FROM python:3.11-slim AS construction
COPY requirements/api.txt /tmp/api.txt
RUN pip install --no-cache-dir --prefix=/installation -r /tmp/api.txt

FROM python:3.11-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin soundlab
COPY --from=construction /installation /usr/local
WORKDIR /app
COPY soundlab_p7 soundlab_p7
COPY api api
COPY deploy/tendances /app/donnees
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TENDANCES_CHEMIN=/app/donnees/tendances.parquet MODELE_URI=/artefacts PORT=8000
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=2)"
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
