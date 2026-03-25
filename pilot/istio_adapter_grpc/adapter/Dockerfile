FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files and generate Python code
COPY protos/ ./protos/
RUN python -m grpc_tools.protoc \
    -I./protos \
    --python_out=. \
    --grpc_python_out=. \
    ./protos/ext_authz.proto

# Copy application code
COPY main.py .

# Environment defaults
ENV AI_DEFENSE_URL="http://ai-defense:8000/evaluate"
ENV AI_DEFENSE_TIMEOUT_SEC="0.8"
ENV GRPC_PORT="9001"
ENV GRPC_WORKERS="10"
ENV TM_AUTHZ_CHECK_METHODS="POST,GET"
ENV TM_AUTHZ_CHECK_PATH_PREFIXES="/queue/,/seat/"

EXPOSE 9001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:9001'); grpc.channel_ready_future(channel).result(timeout=2)" || exit 1

CMD ["python", "main.py"]
