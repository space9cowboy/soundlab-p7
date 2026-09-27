FROM ghcr.io/mlflow/mlflow:v2.18.0
RUN pip install --no-cache-dir psycopg2-binary==2.9.10
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin mlflow && mkdir -p /mlflow && chown 10001 /mlflow
USER 10001
