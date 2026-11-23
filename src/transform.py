from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from .config import EXPECTED_FILES

PRIMARY_KEYS = {
    "customers.csv": "customer_id",
    "accounts.csv": "account_id",
    "transactions.csv": "transaction_id",
}
REQUIRED_COLUMNS = {
    "customers.csv": [
        "customer_id", "full_name", "email_address", "phone_number", "city",
        "join_date", "customer_segment"
    ],
    "accounts.csv": [
        "account_id", "customer_id", "account_type", "currency", "opening_balance",
        "open_date", "account_status"
    ],
    "transactions.csv": [
        "transaction_id", "account_id", "transaction_date", "transaction_type",
        "description", "category", "amount", "currency", "channel", "status"
    ],
}
OUT_TYPES = {"Purchase", "Withdrawal", "Transfer", "Fee"}
IN_TYPES = {"Deposit", "Refund"}
ALL_TYPES = OUT_TYPES | IN_TYPES


def parse_money(value: Any) -> Decimal | None:
    """Keep money as exact Decimal, never binary floating point."""
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    try:
        money = Decimal(str(value).strip().replace(",", ""))
        if not money.is_finite():
            return None
        return money.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def read_source(path: Path) -> pd.DataFrame:
    # Force text to preserve primary keys, phone numbers and intentional blanks.
    return pd.read_csv(path, dtype="string", keep_default_na=False, encoding="utf-8-sig")


def _standardize(raw: pd.DataFrame, file_name: str) -> tuple[pd.DataFrame, dict]:
    if file_name not in EXPECTED_FILES:
        raise ValueError(f"Unexpected source filename: {file_name}")
    df = raw.copy()
    df.columns = [re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_") for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError(f"Duplicate column names after normalization in {file_name}")
    missing = set(REQUIRED_COLUMNS[file_name]) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {file_name}: {sorted(missing)}")
    df = df[REQUIRED_COLUMNS[file_name]].copy()
    for col in df.columns:
        df[col] = df[col].astype("string").str.strip().replace(r"^\s*$", pd.NA, regex=True)
    original = len(df)
    df = df.dropna(how="all")
    all_blank = original - len(df)
    df = df.drop_duplicates()
    exact_duplicates = original - all_blank - len(df)

    pk = PRIMARY_KEYS[file_name]
    if df[pk].isna().any():
        raise ValueError(f"Missing primary key in {file_name}: {int(df[pk].isna().sum())} rows")
    # Conflicting IDs are not silently overwritten.
    if df[pk].duplicated().any():
        raise ValueError(f"Conflicting records for primary key {pk} in {file_name}")
    summary = {
        "raw_rows": original,
        "blank_rows_dropped": all_blank,
        "exact_duplicate_rows_dropped": exact_duplicates,
        "unique_rows": len(df),
    }
    return df, summary


def _timestamp_series(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(df[column], format="%Y-%m-%d", errors="coerce")


def _audit(df: pd.DataFrame, source_file: str, loaded_at: datetime) -> pd.DataFrame:
    df["source_file"] = source_file
    df["loaded_at"] = loaded_at
    return df


def transform_all(
    paths: dict[str, Path],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict]:
    """Returns (clean tables, rejected CSV rows, JSON-serializable report)."""
    now = datetime.now(timezone.utc)
    source_frames = {name: read_source(paths[name]) for name in EXPECTED_FILES}
    data: dict[str, pd.DataFrame] = {}
    rejects: dict[str, pd.DataFrame] = {}
    report: dict[str, dict] = {}
    for name in EXPECTED_FILES:
        data[name], report[name] = _standardize(source_frames[name], name)

    # 1) Customers: keep missing emails and invalid dates as database NULL.
    c = data["customers.csv"]
    c["full_name"] = c["full_name"].str.title()
    c["email_address"] = c["email_address"].str.lower()
    c["customer_segment"] = c["customer_segment"].str.title()
    parsed = _timestamp_series(c, "join_date")
    report["customers.csv"]["invalid_join_dates_set_null"] = int(parsed.isna().sum())
    report["customers.csv"]["missing_email_addresses"] = int(c["email_address"].isna().sum())
    c["join_date"] = parsed.dt.date
    data["customers.csv"] = _audit(c, "customers.csv", now)

    # 2) Accounts: opening_balance may be negative for credit cards, or NULL.
    a = data["accounts.csv"]
    a["account_type"] = a["account_type"].str.title()
    a["account_status"] = a["account_status"].str.title()
    a["currency"] = a["currency"].str.upper()
    a["opening_balance"] = a["opening_balance"].map(parse_money)
    parsed = _timestamp_series(a, "open_date")
    report["accounts.csv"]["invalid_open_dates_set_null"] = int(parsed.isna().sum())
    report["accounts.csv"]["missing_opening_balances"] = int(a["opening_balance"].isna().sum())
    a["open_date"] = parsed.dt.date
    orphan_accounts = ~a["customer_id"].isin(c["customer_id"])
    if orphan_accounts.any():
        rejects["accounts.csv"] = a.loc[orphan_accounts].assign(reject_reason="unknown_customer_id")
        a = a.loc[~orphan_accounts].copy()
    report["accounts.csv"]["unknown_customer_ids_rejected"] = int(orphan_accounts.sum())
    data["accounts.csv"] = _audit(a, "accounts.csv", now)

    # 3) Transactions: invalid date/amount/type/account IDs are rejected.
    t = data["transactions.csv"]
    t["transaction_type"] = t["transaction_type"].str.title()
    t["status"] = t["status"].str.title()
    t["category"] = t["category"].str.title()
    t["description"] = t["description"].str.title()
    t["currency"] = t["currency"].str.upper()
    channels = {"atm": "ATM", "eft": "EFT", "pos": "POS", "online": "Online", "mobile app": "Mobile App"}
    t["channel"] = t["channel"].map(lambda x: channels.get(str(x).strip().lower(), str(x)) if pd.notna(x) else None)
    dates = _timestamp_series(t, "transaction_date")
    amounts = t["amount"].map(parse_money)
    bad_date = dates.isna()
    bad_amount = amounts.isna()
    bad_type = ~t["transaction_type"].isin(ALL_TYPES)
    bad_account = ~t["account_id"].isin(a["account_id"])
    bad_currency = t["currency"] != "ZAR"
    bad_currency = bad_currency.fillna(True)

    reason_flags = {
        "invalid_transaction_date": bad_date,
        "missing_or_invalid_amount": bad_amount,
        "unknown_transaction_type": bad_type,
        "unknown_account_id": bad_account,
        "unsupported_currency": bad_currency,
    }
    invalid = pd.Series(False, index=t.index)
    for reason, mask in reason_flags.items():
        report["transactions.csv"][reason] = int(mask.sum())
        invalid |= mask

    if invalid.any():
        bad = t.loc[invalid].copy()
        bad["reject_reason"] = [
            "; ".join(reason for reason, flag in reason_flags.items() if bool(flag.loc[idx]))
            for idx in bad.index
        ]
        rejects["transactions.csv"] = bad

    t = t.loc[~invalid].copy()
    good_amount = amounts.loc[~invalid]
    sign_fixed = (t["transaction_type"].isin(IN_TYPES) & good_amount.map(lambda x: x < 0)).sum()
    report["transactions.csv"]["negative_deposits_refunds_corrected"] = int(sign_fixed)
    t["amount"] = good_amount.map(abs)
    t["signed_amount"] = [
        -amt if typ in OUT_TYPES else amt
        for typ, amt in zip(t["transaction_type"], t["amount"])
    ]
    t["transaction_date"] = dates.loc[~invalid].dt.date
    report["transactions.csv"]["rows_rejected"] = int(invalid.sum())
    data["transactions.csv"] = _audit(t, "transactions.csv", now)

    for name in EXPECTED_FILES:
        report[name]["clean_rows"] = len(data[name])
        report[name]["rejected_rows"] = len(rejects.get(name, []))
    return data, rejects, report
