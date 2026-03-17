FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies and include README for metadata generation
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "hatchling" \
    && pip install --no-cache-dir ".[defense_api]"

# Copy source code
COPY src ./src

# Install again to ensure entry points are mapped correctly (if needed by hatch)
RUN pip install --no-cache-dir ".[defense_api]"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
