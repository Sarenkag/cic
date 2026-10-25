FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CIC_CONFIG=/app/config/cic.yaml CIC_DATA=/data TZ=Europe/London

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --system --uid 10001 --home /app cic \
 && mkdir -p /data && chown cic:cic /data

COPY app ./app
COPY config ./config

USER cic
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/zdrowie',timeout=4).status==200 else 1)"
CMD ["python", "-m", "app.main"]
