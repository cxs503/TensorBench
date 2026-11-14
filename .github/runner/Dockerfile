FROM python:3.11-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m pip install --no-cache-dir pytest jsonschema

WORKDIR /workspace
USER 65532:65532
