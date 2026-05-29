#!/bin/bash
set -e

# ── 1. Start internal PostgreSQL (if not using external DB) ──
if [ "${POSTGRES_DSN#*@localhost}" != "$POSTGRES_DSN" ] || \
   [ "${POSTGRES_DSN#*@127.0.0.1}" != "$POSTGRES_DSN" ]; then

    echo "=== Starting internal PostgreSQL ==="

    # Initialize PostgreSQL data directory if needed
    if [ ! -d /var/lib/postgresql/15/main ]; then
        PG_MAJOR=$(ls /usr/lib/postgresql/ 2>/dev/null | head -1 || echo "15")
        pg="/usr/lib/postgresql/$PG_MAJOR/bin"

        mkdir -p /var/lib/postgresql/data
        chown postgres:postgres /var/lib/postgresql/data
        sudo -u postgres "$pg/initdb" -D /var/lib/postgresql/data

        # Configure to listen and allow local connections
        echo "host all  all  127.0.0.1/32  md5" >> /var/lib/postgresql/data/pg_hba.conf
        echo "host all  all  ::1/128       md5" >> /var/lib/postgresql/data/pg_hba.conf
        echo "local all  all               trust" >> /var/lib/postgresql/data/pg_hba.conf
    fi

    PG_MAJOR=$(ls /usr/lib/postgresql/ 2>/dev/null | head -1 || echo "15")
    pg="/usr/lib/postgresql/$PG_MAJOR/bin"

    # Start PostgreSQL
    sudo -u postgres "$pg/pg_ctl" -D /var/lib/postgresql/data -l /var/log/postgresql.log start

    # Wait for PostgreSQL to be ready
    for i in $(seq 1 30); do
        if sudo -u postgres "$pg/pg_isready" -q 2>/dev/null; then
            break
        fi
        sleep 0.5
    done

    # Create user and database if they don't exist
    sudo -u postgres psql -c "SELECT 1" >/dev/null 2>&1 || true
    sudo -u postgres psql -c "CREATE USER spa WITH PASSWORD 'spa_password' SUPERUSER;" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE \"software-engineering\" OWNER spa;" 2>/dev/null || true

    # Run init SQL
    sudo -u postgres psql -d "software-engineering" -f /app/init-db.sql 2>/dev/null || true

    echo "=== PostgreSQL ready ==="
fi

# ── 2. Start backend ──
echo "=== Starting Student Productivity Agent backend ==="
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
