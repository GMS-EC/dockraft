# Multi-JRE runtime using official Eclipse Temurin JREs (Java 17, Java 21 & Java 25)
FROM eclipse-temurin:17-jre AS jre-17
FROM eclipse-temurin:21-jre AS jre-21
FROM eclipse-temurin:25-jre AS jre-25

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Install system utilities and Bedrock C++ dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libcurl4 \
    libssl3 \
    ca-certificates \
    unzip \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy official Eclipse Temurin Java 17, 21, and 25 runtimes
COPY --from=jre-17 /opt/java/openjdk /opt/java/java-17
COPY --from=jre-21 /opt/java/openjdk /opt/java/java-21
COPY --from=jre-25 /opt/java/openjdk /opt/java/java-25

# Link default system Java to Java 25 (supports all modern MC versions including 25.x / 26.x)
RUN ln -s /opt/java/java-25/bin/java /usr/local/bin/java

# Setup work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/
COPY web/ ./web/

# Prepare server data and backups volume directories
RUN mkdir -p /server_data /server_backups
ENV DATA_DIR="/server_data"
ENV BACKUPS_DIR="/server_backups"
ENV ADMIN_USER="admin"
ENV HOST="0.0.0.0"
ENV PORT="8000"

# Expose ports:
# 8000: Web Panel
# 25565: Minecraft Java TCP
# 19132/udp: Minecraft Bedrock UDP
EXPOSE 8000 25565 19132/udp

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
