FROM python:3.11-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin soundlab
COPY requirements/derive.txt /tmp/derive.txt
RUN pip install --no-cache-dir -r /tmp/derive.txt
WORKDIR /app
COPY monitoring monitoring
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001
ENTRYPOINT ["python", "-m", "monitoring.derive"]
