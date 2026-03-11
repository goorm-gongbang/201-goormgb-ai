FROM python:3.12-slim

WORKDIR /app

# pyproject.toml로 의존성 일원화 관리
COPY pyproject.toml .
RUN pip install --no-cache-dir .[defense_api]

COPY src ./src

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
