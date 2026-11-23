Offline tests: synthetic fixtures always run in CI; supplied CSV tests run locally."""
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from src.config import EXPECTED_FILES, INPUT_DIR
from src.transform import _standardize, parse_money, transform_all

SOURCE_DATA_PRESENT = all((INPUT_DIR / name).is_file() for name in EXPECTED_FILES)


def test_money_decimal_precision():
    assert parse_money("100.10") == Decimal("100.10")
    assert parse_money("") is None
    assert parse_money("n/a") is None
    assert parse_money("-15.00") == Decimal("-15.00")


def _synthetic_inputs(tmp_path: Path) -> dict[str, Path]:
    data = {
        "customers.csv": pd.DataFrame([
            {"Customer ID": "C1", "Full Name": "ADA SAMPLE", "Email Address": " ADA@EXAMPLE.ORG ",
             "Phone Number": "0123", "City": "Cape Town", "Join Date": "2026-01-01", "Customer Segment": "Retail"},
        ]),
        "accounts.csv": pd.DataFrame([
            {"Account ID": "A1", "Customer ID": "C1", "Account Type": "Savings",
             "Currency": "ZAR", "Opening Balance": "100.00", "Open Date": "2026-01-02",
             "Account Status": "active"},
        ]),
        "transactions.csv": pd.DataFrame([
            {"Transaction ID": "T1", "Account ID": "A1", "Transaction Date": "2026-02-03",
             "Transaction Type": "deposit", "Description": "Pay", "Category": "Income",
             "Amount": "-200.25", "Currency": "ZAR", "Channel": "atm", "Status": "completed"},
            {"Transaction ID": "T2", "Account ID": "A1", "Transaction Date": "2026-02-04",
             "Transaction Type": "purchase", "Description": "Shop", "Category": "Shopping",
             "Amount": "10.20", "Currency": "ZAR", "Channel": "pos", "Status": "completed"},
            {"Transaction ID": "T3", "Account ID": "A1", "Transaction Date": "not-a-date",
             "Transaction Type": "fee", "Description": "Bank fee", "Category": "Fees",
             "Amount": "1.00", "Currency": "ZAR", "Channel": "online", "Status": "failed"},
        ]),
    }
    result = {}
    for name, frame in data.items():
        path = tmp_path / name
        frame.to_csv(path, index=False)
        result[name] = path
    return result


def test_synthetic_etl_without_external_services(tmp_path):
    clean, rejects, report = transform_all(_synthetic_inputs(tmp_path))
    assert len(clean["customers.csv"]) == 1
    assert len(clean["accounts.csv"]) == 1
    tx = clean["transactions.csv"].set_index("transaction_id")
    assert len(tx) == 2
    assert tx.loc["T1", "signed_amount"] == Decimal("200.25")
    assert tx.loc["T2", "signed_amount"] == Decimal("-10.20")
    assert tx.loc["T1", "channel"] == "ATM"
    assert tx.loc["T2", "channel"] == "POS"
    assert len(rejects["transactions.csv"]) == 1
    assert report["transactions.csv"]["negative_deposits_refunds_corrected"] == 1


def test_missing_column_is_detected():
    with pytest.raises(ValueError, match="Missing required columns"):
        _standardize(pd.DataFrame({"Transaction ID": ["T1"]}), "transactions.csv")


def test_conflicting_primary_key_is_detected():
    dup = pd.DataFrame([
        {"Customer ID": "C1", "Full Name": "Alice", "Email Address": "a@example.com",
         "Phone Number": "000", "City": "Johannesburg", "Join Date": "2026-01-01", "Customer Segment": "Retail"},
        {"Customer ID": "C1", "Full Name": "Bob", "Email Address": "b@example.com",
         "Phone Number": "001", "City": "Durban", "Join Date": "2026-01-01", "Customer Segment": "Retail"},
    ])
    with pytest.raises(ValueError, match="Conflicting records"):
        _standardize(dup, "customers.csv")


@pytest.mark.skipif(not SOURCE_DATA_PRESENT, reason="Source CSVs are intentionally excluded from GitHub")
def test_supplied_dataset_cleaned_counts():
    paths = {name: INPUT_DIR / name for name in EXPECTED_FILES}
    clean, rejects, report = transform_all(paths)
    assert [report[name]["raw_rows"] for name in EXPECTED_FILES] == [152, 221, 2025]
    assert [report[name]["exact_duplicate_rows_dropped"] for name in EXPECTED_FILES] == [2, 1, 25]
    assert [len(clean[name]) for name in EXPECTED_FILES] == [150, 220, 1930]
    assert len(rejects["transactions.csv"]) == 70
    assert report["transactions.csv"]["invalid_transaction_date"] == 29
    assert report["transactions.csv"]["missing_or_invalid_amount"] == 42
    assert report["transactions.csv"]["negative_deposits_refunds_corrected"] == 5
    assert clean["transactions.csv"]["transaction_id"].is_unique
    assert set(clean["accounts.csv"]["customer_id"]).issubset(set(clean["customers.csv"]["customer_id"]))
    assert set(clean["transactions.csv"]["account_id"]).issubset(set(clean["accounts.csv"]["account_id"]))


@pytest.mark.skipif(not SOURCE_DATA_PRESENT, reason="Source CSVs are intentionally excluded from GitHub")
def test_supplied_dataset_transaction_signs_and_channels():
    paths = {name: INPUT_DIR / name for name in EXPECTED_FILES}
    clean, _, _ = transform_all(paths)
    trans = clean["transactions.csv"]
    out = trans[trans["transaction_type"].isin(["Purchase", "Withdrawal", "Transfer", "Fee"])]
    ins = trans[trans["transaction_type"].isin(["Deposit", "Refund"])]
    assert out["signed_amount"].map(lambda x: x <= 0).all()
    assert ins["signed_amount"].map(lambda x: x >= 0).all()
    assert set(trans["channel"]).issubset({"ATM", "POS", "EFT", "Online", "Mobile App"})