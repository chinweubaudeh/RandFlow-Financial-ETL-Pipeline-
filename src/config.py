from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

INPUT_DIR = ROOT / "data" / "input"
RAW_DIR = ROOT / "data" / "raw"
REJECTED_DIR = ROOT / "data" / "rejected"
REPORTS_DIR = ROOT / "data" / "reports"
SQL_DIR = ROOT / "sql"
EXPECTED_FILES = ("customers.csv", "accounts.csv", "transactions.csv")


def database_url() -> URL:
    """URL.create handles special characters in passwords safely."""
    needed = ("DB_NAME", "DB_USER", "DB_PASSWORD")
    missing = [key for key in needed if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing database settings in .env: {', '.join(missing)}")
    return URL.create(
        drivername="postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
    )


def drive_settings() -> tuple[str, Path]:
    folder = os.getenv("DRIVE_FOLDER_ID", "").strip()
    key_setting = os.getenv("SERVICE_ACCOUNT_FILE", "credentials/service_account.json")
    key_path = Path(key_setting)
    if not key_path.is_absolute():
        key_path = ROOT / key_path
    if not folder or folder == "YOUR_GOOGLE_DRIVE_FOLDER_ID":
        raise RuntimeError("Set DRIVE_FOLDER_ID (folder ID only) in .env")
    if not key_path.is_file():
        raise FileNotFoundError(f"Service-account JSON missing: {key_path}")
    return folder, key_path
