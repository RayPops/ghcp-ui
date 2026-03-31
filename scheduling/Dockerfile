FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/
COPY data/ data/

RUN pip install --no-cache-dir -e .

EXPOSE 3002

CMD ["python", "-m", "app.mcp_server"]
