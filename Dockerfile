FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir build && python -m build

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/dist .
RUN pip install --no-cache-dir pulsar-*.whl
COPY . .
CMD ["pulsar", "daemon", "start", "--config", "config.yaml"]
