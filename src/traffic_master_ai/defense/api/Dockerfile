FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies and optimize caching
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "hatchling" \
    && pip install --no-cache-dir --no-deps -e ".[defense_api]" \
    || pip install --no-cache-dir fastapi uvicorn redis pydantic

# Copy source code after dependencies are installed
COPY src ./src

# Final installation to ensure all entry points are set correctly
RUN pip install --no-cache-dir ".[defense_api]"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
