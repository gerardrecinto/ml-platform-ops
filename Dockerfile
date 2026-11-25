FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY registry ./registry
RUN pip install --no-cache-dir . && useradd -u 10001 -r app
USER 10001
ENV REGISTRY=/app/registry/registry.json PORT=8080
EXPOSE 8080
CMD ["python", "-m", "mlplat.service"]
