#!/bin/sh
# Executa a crontab versionada como usuário não-privilegiado.
set -eu

exec supercronic -passthrough-logs /etc/reidofeno/crontab
