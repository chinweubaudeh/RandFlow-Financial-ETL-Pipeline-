Analytics layer: only COMPLETED transactions count as posted cash flows.
CREATE OR REPLACE VIEW warehouse.vw_completed_transactions AS
SELECT
    t.transaction_id,
    t.account_id,
    a.customer_id,
    c.customer_segment,
    c.city,
    t.transaction_date,
    t.transaction_type,
    t.category,
    t.channel,
    t.amount,
    t.signed_amount,
    t.currency
FROM staging.transactions AS t
JOIN staging.accounts AS a ON a.account_id = t.account_id
JOIN staging.customers AS c ON c.customer_id = a.customer_id
WHERE t.status = 'Completed';

CREATE OR REPLACE VIEW warehouse.vw_monthly_cashflow AS
SELECT
    date_trunc('month', transaction_date)::date AS month,
    COUNT(*) AS completed_transactions,
    SUM(CASE WHEN signed_amount > 0 THEN signed_amount ELSE 0 END)::numeric(18,2) AS inflow_zar,
    SUM(CASE WHEN signed_amount < 0 THEN -signed_amount ELSE 0 END)::numeric(18,2) AS outflow_zar,
    SUM(signed_amount)::numeric(18,2) AS net_cashflow_zar
FROM warehouse.vw_completed_transactions
GROUP BY 1;

CREATE OR REPLACE VIEW warehouse.vw_customer_activity AS
SELECT
    customer_id,
    customer_segment,
    city,
    COUNT(*) AS completed_transactions,
    SUM(CASE WHEN signed_amount < 0 THEN -signed_amount ELSE 0 END)::numeric(18,2) AS total_spend_zar,
    SUM(signed_amount)::numeric(18,2) AS net_cashflow_zar
FROM warehouse.vw_completed_transactions
GROUP BY customer_id, customer_segment, city;
