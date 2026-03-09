FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic

COPY src ./src

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "traffic_master_ai.defense.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
