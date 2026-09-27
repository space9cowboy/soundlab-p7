FROM python:3.11-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin soundlab
COPY requirements/train.txt /tmp/train.txt
RUN pip install --no-cache-dir -r /tmp/train.txt
WORKDIR /app
COPY soundlab_p7 soundlab_p7
COPY train train
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001
ENTRYPOINT ["python", "-m", "train.entrainer"]
