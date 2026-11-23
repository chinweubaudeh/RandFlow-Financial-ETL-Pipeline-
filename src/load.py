from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from .config import EXPECTED_FILES, SQL_DIR, database_url


def _execute_sql_file(conn, file_path: Path) -> None:
    for statement in file_path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            conn.exec_driver_sql(statement)


def load_all(clean: dict[str, pd.DataFrame]) -> dict[str, int]:
    """All 3 tables change together; on any error, PostgreSQL rolls back."""
    engine = create_engine(database_url(), pool_pre_ping=True, future=True)
    loaded: dict[str, int] = {}
    try:
        with engine.begin() as conn:
            _execute_sql_file(conn, SQL_DIR / "01_schema.sql")
            # Full snapshot refresh is appropriate for these three small Drive CSVs.
            # We include ALL referenced tables so PostgreSQL's FK checks allow TRUNCATE.
            conn.execute(text(
                "TRUNCATE TABLE staging.transactions, staging.accounts, staging.customers"
            ))
            for name in EXPECTED_FILES:  # parent -> child insertion order
                table_name = Path(name).stem
                frame = clean[name].copy()
                # Convert NaT / pandas NA into SQL NULL and make dates native.
                for col in ("join_date", "open_date", "transaction_date"):
                    if col in frame:
                        frame[col] = frame[col].astype(object).where(frame[col].notna(), None)
                frame = frame.astype(object).where(frame.notna(), None)
                frame.to_sql(
                    name=table_name,
                    con=conn, schema="staging", if_exists="append", index=False,
                    method="multi", chunksize=500,
                )
                loaded[table_name] = len(frame)
            _execute_sql_file(conn, SQL_DIR / "02_views.sql")
            for name in EXPECTED_FILES:
                table = Path(name).stem
                db_count = conn.execute(text(f"SELECT COUNT(*) FROM staging.{table}")).scalar_one()
                if db_count != loaded[table]:
                    raise RuntimeError(f"Count mismatch in staging.{table}: {db_count} != {loaded[table]}")
    finally:
        engine.dispose()
    return loaded