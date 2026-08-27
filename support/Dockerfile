FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SUPPORT_DB_PATH=/app/data/support.db \
    MAIN_DB_PATH=/app/main/bot.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Starts as root only to take ownership of the mounted data directory, then the
# entrypoint drops to this user for the bot itself.
RUN useradd --create-home --uid 10002 support && mkdir -p /app/data && chown -R support /app

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-u", "bot.py"]
