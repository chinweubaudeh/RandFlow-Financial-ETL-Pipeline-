Query 1: Validate counts against the sample input: 150, 220, 1930.
SELECT 'customers' AS source, COUNT(*) AS rows FROM staging.customers
UNION ALL
SELECT 'accounts', COUNT(*) FROM staging.accounts
UNION ALL
SELECT 'transactions', COUNT(*) FROM staging.transactions;

-- Query 2: Monthly ZAR cash flow (completed transactions only).
SELECT * FROM warehouse.vw_monthly_cashflow ORDER BY month;

-- Query 3: Spending by category. Only money OUT; pending/failed excluded.
SELECT category, COUNT(*) AS transactions, SUM(-signed_amount) AS spend_zar
FROM warehouse.vw_completed_transactions
WHERE signed_amount < 0
GROUP BY category ORDER BY spend_zar DESC;

-- Query 4: Completed transactions by customer segment.
SELECT customer_segment, COUNT(*) AS transactions,
       SUM(signed_amount) AS net_cashflow_zar
FROM warehouse.vw_completed_transactions
GROUP BY customer_segment ORDER BY transactions DESC;

-- Query 5: Most active customers by total spend.
SELECT customer_id, customer_segment, completed_transactions, total_spend_zar
FROM warehouse.vw_customer_activity
ORDER BY total_spend_zar DESC LIMIT 10;

-- Query 6: All transaction statuses (including not posted).
SELECT status, COUNT(*) AS transaction_count
FROM staging.transactions GROUP BY status ORDER BY transaction_count DESC;

-- Query 7: Account status distribution.
SELECT account_status, COUNT(*) AS accounts
FROM staging.accounts GROUP BY account_status ORDER BY accounts DESC;

-- Query 8: Verify no duplicate IDs and foreign-key violations.
SELECT (SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM staging.customers) AS duplicate_customers,
       (SELECT COUNT(*) - COUNT(DISTINCT account_id) FROM staging.accounts) AS duplicate_accounts,
       (SELECT COUNT(*) - COUNT(DISTINCT transaction_id) FROM staging.transactions) AS duplicate_transactions,
       (SELECT COUNT(*) FROM staging.accounts a LEFT JOIN staging.customers c ON c.customer_id=a.customer_id WHERE c.customer_id IS NULL) AS orphan_accounts,
       (SELECT COUNT(*) FROM staging.transactions t LEFT JOIN staging.accounts a ON a.account_id=t.account_id WHERE a.account_id IS NULL) AS orphan_transactions;
```