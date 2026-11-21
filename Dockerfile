FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
RUN pip install --no-cache-dir --disable-pip-version-check numpy==2.5.5
WORKDIR /app
COPY sentinel/ /app/sentinel/
USER 65534:65534
ENTRYPOINT ["python3", "-B", "-u", "-m", "sentinel.main"]
