# syntax=docker/dockerfile:1

# Voice Agent Dockerfile
# This builds the voice agent package for deployment.

# Use the official UV Python base image with Python 3.13 on Debian Bookworm
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

# Keeps Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the root workspace files first
COPY pyproject.toml uv.lock ./

# Copy shared package (voice_agent depends on it)
COPY packages/shared/pyproject.toml packages/shared/
COPY packages/shared/src packages/shared/src

# Copy voice_agent package
COPY packages/voice_agent/pyproject.toml packages/voice_agent/
COPY packages/voice_agent/src packages/voice_agent/src

# Install dependencies
RUN uv sync --locked

# Copy remaining files (tests, etc.)
COPY packages/voice_agent packages/voice_agent
COPY .env.local .env.local

# Change ownership to non-privileged user
RUN chown -R appuser:appuser /app

USER appuser

# Pre-download ML models
WORKDIR /app/packages/voice_agent
RUN uv run python src/agent.py download-files

# Run the agent
CMD ["uv", "run", "python", "src/agent.py", "start"]
