import pandas as pd
from sqlalchemy import text
from ETL.Transform import transform_data
from config import get_mongo_db, get_master_engine, get_dw_engine, SQLSERVER_DATABASE

# =========================================================
# 1. FETCH & TRANSFORM DATA FROM MONGO
# =========================================================
print("1/3 Fetching and Transforming Data from MongoDB...")
mongo_db = get_mongo_db()

collections = [
    "customer_segments",
    "categories",
    "suppliers",
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
]

extracted_data = {}
for col_name in collections:
    cursor = mongo_db[col_name].find({}, {"_id": 0})
    extracted_data[col_name] = pd.DataFrame(list(cursor))

transformed_data = transform_data(extracted_data)

# =========================================================
# 2. AUTO-CREATE DATABASE IF NOT EXISTS
# =========================================================
print("\n2/3 Connecting to SQL Server...")

# Connect to the default 'master' database to create the target DB
master_engine = get_master_engine()

with master_engine.connect() as conn:
    conn.execute(
        text(
            f"IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'{SQLSERVER_DATABASE}') "
            f"CREATE DATABASE [{SQLSERVER_DATABASE}];"
        )
    )
print(f"✓ Database '{SQLSERVER_DATABASE}' is ready!")

# =========================================================
# 3. CONNECT TO DATABASE & CREATE SCHEMA WITH FOREIGN KEYS
# =========================================================
engine = get_dw_engine(fast_executemany=True)

ddl_script = """
IF OBJECT_ID('payments', 'U') IS NOT NULL DROP TABLE payments;
IF OBJECT_ID('order_items', 'U') IS NOT NULL DROP TABLE order_items;
IF OBJECT_ID('orders', 'U') IS NOT NULL DROP TABLE orders;
IF OBJECT_ID('products', 'U') IS NOT NULL DROP TABLE products;
IF OBJECT_ID('customers', 'U') IS NOT NULL DROP TABLE customers;
IF OBJECT_ID('suppliers', 'U') IS NOT NULL DROP TABLE suppliers;
IF OBJECT_ID('categories', 'U') IS NOT NULL DROP TABLE categories;
IF OBJECT_ID('customer_segments', 'U') IS NOT NULL DROP TABLE customer_segments;

CREATE TABLE customer_segments (
    segment_id INT PRIMARY KEY,
    segment_name VARCHAR(100),
    description VARCHAR(MAX),
    min_lifetime_value DECIMAL(18,2),
    max_lifetime_value DECIMAL(18,2)
);

CREATE TABLE categories (
    category_id INT PRIMARY KEY,
    category_name VARCHAR(100),
    description VARCHAR(MAX),
    parent_category_id INT NULL,
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);

CREATE TABLE suppliers (
    supplier_id INT PRIMARY KEY,
    supplier_name VARCHAR(150),
    contact_name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(50),
    country VARCHAR(50),
    city VARCHAR(50),
    address VARCHAR(MAX),
    supplier_rating DECIMAL(3,2),
    created_at DATETIME
);

CREATE TABLE customers (
    customer_id INT PRIMARY KEY,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(100),
    gender VARCHAR(20),
    date_of_birth DATE,
    registration_date DATETIME,
    segment_id INT,
    city VARCHAR(50),
    state VARCHAR(50),
    country VARCHAR(50),
    total_orders INT DEFAULT 0,
    total_lifetime_spend DECIMAL(18,2) DEFAULT 0.00,
    last_order_date DATETIME NULL,
    FOREIGN KEY (segment_id) REFERENCES customer_segments(segment_id)
);

CREATE TABLE products (
    product_id INT PRIMARY KEY,
    product_name VARCHAR(200),
    category_id INT,
    supplier_id INT,
    brand VARCHAR(100),
    description VARCHAR(MAX),
    unit_price DECIMAL(18,2),
    cost_price DECIMAL(18,2),
    weight DECIMAL(10,2),
    stock_quantity INT,
    reorder_level INT,
    product_status VARCHAR(50),
    created_at DATETIME,
    updated_at DATETIME,
    profit_margin DECIMAL(18,2),
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    customer_id INT,
    order_date DATETIME,
    order_status VARCHAR(50),
    payment_status VARCHAR(50),
    subtotal DECIMAL(18,2),
    discount_amount DECIMAL(18,2),
    tax_amount DECIMAL(18,2),
    shipping_cost DECIMAL(18,2),
    total_amount DECIMAL(18,2),
    currency VARCHAR(10),
    shipping_address VARCHAR(MAX),
    billing_address VARCHAR(MAX),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id INT PRIMARY KEY,
    order_id INT,
    product_id INT,
    quantity INT,
    unit_price DECIMAL(18,2),
    discount_amount DECIMAL(18,2),
    tax_amount DECIMAL(18,2),
    line_total DECIMAL(18,2),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE payments (
    payment_id INT PRIMARY KEY,
    order_id INT,
    payment_date DATETIME,
    payment_method VARCHAR(50),
    amount DECIMAL(18,2),
    currency VARCHAR(10),
    payment_status VARCHAR(50),
    transaction_reference VARCHAR(100),
    failure_reason VARCHAR(MAX),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
"""

with engine.connect() as conn:
    for statement in ddl_script.split(";"):
        if statement.strip():
            conn.execute(text(statement))
    conn.commit()

print("✓ Tables and Foreign Keys created successfully!")

# =========================================================
# 4. LOAD DATA IN SEQUENTIAL ORDER
# =========================================================
print("\n3/3 Loading Transformed Data into SQL Server...")

loading_order = [
    "customer_segments",
    "categories",
    "suppliers",
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
]

for table_name in loading_order:
    df = transformed_data[table_name]
    df.to_sql(table_name, con=engine, if_exists="append", index=False)
    print(f" Successfully loaded {len(df):<6} rows into '{table_name}'")

print("\nETL Pipeline Completed Successfully!")
