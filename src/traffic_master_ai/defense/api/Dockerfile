FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy package metadata and source before install so the wheel is built
# from the actual application contents in one step.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "hatchling" \
    && pip install --no-cache-dir ".[defense_api]" \
    && python -c "import httpx, fastapi, uvicorn, jwt; print('dependency check ok')"

RUN mkdir -p /app/logs && chown -R 1000:1000 /app/logs

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
