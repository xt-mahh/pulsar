FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir mcp httpx pydantic pyyaml loguru click rich aiosqlite jinja2 Pillow python-crontab

COPY . .

RUN mkdir -p data/logs data/state

EXPOSE 8910

CMD ["python", "-m", "interaction.cli.main", "run"]