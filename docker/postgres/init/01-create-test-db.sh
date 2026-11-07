#!/bin/sh
# Runs once, on the first start of an empty data volume.
# Creates a separate database for pytest so tests never touch development data.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "CREATE DATABASE \"${POSTGRES_DB}_test\" OWNER \"$POSTGRES_USER\";"
