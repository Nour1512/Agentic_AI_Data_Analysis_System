import os
import pandas as pd

from config import get_mongo_db

# Connect to MongoDB using MONGO_URI / MONGO_DB_NAME from .env
db = get_mongo_db()

# Primary Keys mapping for the 8 active collections (shipments removed)
PRIMARY_KEYS = {
    "customer_segments": "segment_id",
    "customers": "customer_id",
    "categories": "category_id",
    "suppliers": "supplier_id",
    "products": "product_id",
    "orders": "order_id",
    "order_items": "order_item_id",
    "payments": "payment_id",
}

base_dir = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(base_dir, "egyptian_ecommerce_csvs")

if not os.path.isdir(folder_path):
    raise FileNotFoundError(f"CSV folder not found: {folder_path}")

for file_name in os.listdir(folder_path):
    if file_name.endswith(".csv"):
        collection_name = file_name.replace(".csv", "")
        file_path = os.path.join(folder_path, file_name)

        # 1. Read CSV
        df = pd.read_csv(file_path)

        # 2. Replace NaN values with None (BSON null)
        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")

        if records:
            # 3. Drop existing collection to prevent duplication on re-run
            db[collection_name].drop()

            # 4. Create Unique Index if primary key is defined
            pk_field = PRIMARY_KEYS.get(collection_name)
            if pk_field:
                db[collection_name].create_index(pk_field, unique=True)

            # 5. Insert clean records
            db[collection_name].insert_many(records)
            print(
                f"Successfully imported {len(records)} unique records into '{collection_name}'"
            )
