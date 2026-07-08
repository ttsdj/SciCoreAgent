FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY biocoreagent ./biocoreagent
COPY pico ./pico
COPY corecoder ./corecoder
COPY mcp_servers ./mcp_servers

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

WORKDIR /workspace

ENTRYPOINT ["biocoreagent-v2"]
CMD ["--help"]
