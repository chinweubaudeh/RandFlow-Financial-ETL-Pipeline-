RandFlow: fully typed staging tables with PK/FK constraints.
-- Run as database owner (randflow_user). Executed automatically by src/load.py.
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;

CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id VARCHAR(25) PRIMARY KEY,
    full_name TEXT,
    email_address TEXT,
    phone_number TEXT,
    city TEXT,
    join_date DATE,
    customer_segment TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.accounts (
    account_id VARCHAR(25) PRIMARY KEY,
    customer_id VARCHAR(25) NOT NULL REFERENCES staging.customers(customer_id),
    account_type TEXT,
    currency CHAR(3),
    opening_balance NUMERIC(18,2),
    open_date DATE,
    account_status TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.transactions (
    transaction_id VARCHAR(25) PRIMARY KEY,
    account_id VARCHAR(25) NOT NULL REFERENCES staging.accounts(account_id),
    transaction_date DATE NOT NULL,
    transaction_type TEXT NOT NULL,
    description TEXT,
    category TEXT,
    amount NUMERIC(18,2) NOT NULL CHECK (amount >= 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'ZAR'),
    channel TEXT,
    status TEXT,
    signed_amount NUMERIC(18,2) NOT NULL,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_customer_id ON staging.accounts (customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON staging.transactions (account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date_status ON staging.transactions (transaction_date, status);
```