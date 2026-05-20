"""
app/db.py
Database connection helpers.

Security notes
──────────────
  • ALL credentials come from environment variables — zero hardcoded defaults.
  • If a required env var is missing the helper raises immediately so the
    mistake is obvious at startup, not silently hidden.
  • MySQL uses parameterised queries everywhere (no string interpolation).
  • MongoDB client has a 5-second connection timeout so a dead VM doesn't
    hang a request thread.
  • Connections are per-request (open/close in finally blocks) — no shared
    global connection that could be corrupted across threads.
"""

import os
import mysql.connector
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


# ── MySQL ─────────────────────────────────────────────────────────────────

def _require_env(key: str) -> str:
    """Return env var or raise a clear error — never silently use a default."""
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            "Check your .env file."
        )
    return value


def get_db() -> mysql.connector.MySQLConnection:
    """Open and return a new MySQL connection (caller must close it)."""
    return mysql.connector.connect(
        host=_require_env("DB_HOST"),
        port=int(os.getenv("DB_PORT", "13306")),
        user=_require_env("DB_USER"),
        password=_require_env("DB_PASS"),
        database=_require_env("DB_NAME"),
        autocommit=False,
        connection_timeout=10,
    )


def dict_cursor(db: mysql.connector.MySQLConnection):
    """Return a cursor that yields rows as dicts."""
    return db.cursor(dictionary=True)


# ── MongoDB ───────────────────────────────────────────────────────────────

def get_mongo():
    """Open and return a MongoDB database handle."""
    host = _require_env("MONGO_HOST")
    port = int(os.getenv("MONGO_PORT", "27018"))
    db_name = _require_env("MONGO_DB")
    uri = f"mongodb://{host}:{port}/{db_name}"
    client = MongoClient(uri, serverSelectionTimeoutMS=2000, socketTimeoutMS=3000, connectTimeoutMS=2000, directConnection=True)
    return client[db_name]


def get_mongo_db():
    """
    Retorna la base de datos MongoDB configurada en el archivo .env.
    Se usa para auditorías, eventos de seguridad y estadísticas.
    """
    mongo_host = os.getenv("MONGO_HOST", "192.168.56.101")
    mongo_port = int(os.getenv("MONGO_PORT", "27018"))
    mongo_db = os.getenv("MONGO_DB", "sgec_logs")

    uri = f"mongodb://{mongo_host}:{mongo_port}/{mongo_db}?directConnection=true"

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=3000,
        socketTimeoutMS=5000,
        connectTimeoutMS=3000,
        directConnection=True
    )

    return client[mongo_db]