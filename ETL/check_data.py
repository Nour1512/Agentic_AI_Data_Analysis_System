import pandas as pd

from config import get_dw_engine

engine = get_dw_engine()

# استعلام لاختبار الربط بين 4 جداول (العملاء، الطلبات، العناصر، والمنتجات)
query = """
SELECT TOP 5
    c.first_name + ' ' + c.last_name AS customer_name,
    c.total_lifetime_spend,
    o.order_id,
    o.order_date,
    p.product_name,
    oi.quantity,
    oi.line_total
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
ORDER BY o.order_date DESC;
"""

df = pd.read_sql(query, engine)
print("--- Test Query Results (Joins & Relations Active) ---")
print(df)
