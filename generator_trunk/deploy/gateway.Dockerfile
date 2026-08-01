# Tag retained for reviewability; digest is the immutable multi-platform index.
FROM eclipse-temurin:25-jdk@sha256:201fbb8886b2d273218aa3a192f0afbf7b5ff65ee8cc6ef47f5dce2171f013ea

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       python3 \
       python3-grpcio \
       python3-grpc-tools \
       python3-pg8000 \
       postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY generator_trunk ./generator_trunk
COPY Core_trunk ./Core_trunk
COPY Reader_trunk ./Reader_trunk
COPY Executor_trunk ./Executor_trunk
COPY Analyzer_trunk ./Analyzer_trunk

WORKDIR /workspace/generator_trunk
RUN python3 -m bundle.gateway.codegen

EXPOSE 8787

CMD ["python3", "bundle_gateway.py", \
     "--host", "0.0.0.0", \
     "--port", "8787", \
     "--transport", "grpc", \
     "--runs-root", "/var/lib/fwbundle-gateway/runs", \
     "--tokens-file", "/run/secrets/gateway_tokens", \
     "--tls-cert", "/run/secrets/gateway_tls_cert", \
     "--tls-key", "/run/secrets/gateway_tls_key"]
