FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ai.txt ./
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi && \
    pip install --no-cache-dir pip==26.2.2 && \
    pip install --no-cache-dir -r requirements.txt -r requirements-ai.txt
COPY --chown=10001:10001 investwatch ./investwatch
RUN useradd --uid 10001 --no-create-home investwatch && mkdir /data && chown 10001:10001 /data
USER 10001
ENV IW_DATA=/data
CMD ["python","-m","uvicorn","investwatch.api:create_app","--factory","--host","0.0.0.0","--port","8000","--workers","1"]
