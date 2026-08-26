#!/bin/sh
# The data directory comes from a host bind mount, so it arrives owned by whoever
# created it — usually root. Fix it here, once, and only then drop privileges;
# doing it by hand on every new host is a trap nobody remembers.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data
    chown -R bot:bot /app/data
    exec setpriv --reuid=bot --regid=bot --init-groups "$@"
fi

exec "$@"
