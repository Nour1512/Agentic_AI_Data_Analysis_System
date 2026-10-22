"""
config.py
---------
Centralized configuration loader for the ETL pipeline.

All MongoDB and SQL Server connection details are read from environment
variables (populated from a local `.env` file via python-dotenv) instead of
being hardcoded in each script. This lets anyone clone the project, create
their own `.env` from `.env.example`, and run the pipeline against their own
local MongoDB / SQL Server instances without editing any code.
"""

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import create_engine

# Load variables from a .env file in the project root (if present).
# Real environment variables (e.g. set in CI) always take precedence.
load_dotenv()

# ---------------------------------------------------------------------------
# MongoDB settings
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "egyptian_ecommerce")


def get_mongo_client():
    """Return a MongoClient built from MONGO_URI."""
    return MongoClient(MONGO_URI)


def get_mongo_db():
    """Return the target MongoDB database object (MONGO_DB_NAME)."""
    return get_mongo_client()[MONGO_DB_NAME]


# ---------------------------------------------------------------------------
# SQL Server settings
# ---------------------------------------------------------------------------
SQLSERVER_DRIVER = os.getenv("SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")
SQLSERVER_HOST = os.getenv("SQLSERVER_HOST", "localhost")
SQLSERVER_PORT = os.getenv("SQLSERVER_PORT", "")  # optional, e.g. 1433
SQLSERVER_DATABASE = os.getenv("SQLSERVER_DATABASE", "egyptian_ecommerce_dw")
SQLSERVER_TRUSTED_CONNECTION = os.getenv("SQLSERVER_TRUSTED_CONNECTION", "yes")
SQLSERVER_USER = os.getenv("SQLSERVER_USER", "")
SQLSERVER_PASSWORD = os.getenv("SQLSERVER_PASSWORD", "")


def _build_sqlserver_url(database: str) -> str:
    """Build a SQLAlchemy/pyodbc connection URL for the given SQL Server database."""
    host = SQLSERVER_HOST
    if SQLSERVER_PORT:
        host = f"{host},{SQLSERVER_PORT}"

    driver = quote_plus(SQLSERVER_DRIVER)

    if SQLSERVER_TRUSTED_CONNECTION.strip().lower() in ("yes", "true", "1"):
        # Windows Authentication (trusted connection) — no username/password needed.
        return (
            f"mssql+pyodbc://@{host}/{database}"
            f"?driver={driver}&trusted_connection=yes&TrustServerCertificate=yes"
        )

    # SQL Server Authentication (username/password)
    user = quote_plus(SQLSERVER_USER)
    password = quote_plus(SQLSERVER_PASSWORD)
    return (
        f"mssql+pyodbc://{user}:{password}@{host}/{database}"
        f"?driver={driver}&TrustServerCertificate=yes"
    )


def get_master_engine():
    """Engine connected to the 'master' DB — used only to create the target DB."""
    return create_engine(_build_sqlserver_url("master"), isolation_level="AUTOCOMMIT")


def get_dw_engine(fast_executemany: bool = False):
    """Engine connected to the target data-warehouse database (SQLSERVER_DATABASE)."""
    return create_engine(
        _build_sqlserver_url(SQLSERVER_DATABASE),
        fast_executemany=fast_executemany,
    )
