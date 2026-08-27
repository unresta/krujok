#!/bin/sh
# The data directory arrives from a host bind mount owned by whoever created it,
# usually root. Fix it once here, then drop privileges — same trick as the main
# bot. The main bot's database is mounted read-only and is deliberately left
# alone: chown would fail on it, and support must never write there anyway.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data
    chown -R support:support /app/data
    exec setpriv --reuid=support --regid=support --init-groups "$@"
fi

exec "$@"
