FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/app/data/bot.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The database lives on a volume, so `docker compose down` never eats balances.
RUN useradd --create-home --uid 10001 bot && mkdir -p /app/data && chown -R bot /app
USER bot

CMD ["python", "-u", "bot.py"]
