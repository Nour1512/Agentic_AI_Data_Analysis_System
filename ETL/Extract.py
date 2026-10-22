import pandas as pd

from config import get_mongo_db

# 1. الاتصال بقاعدة بيانات MongoDB (باستخدام إعدادات .env)
db = get_mongo_db()

# قائمة المجموعات الـ 8 المستهدفة
collections = [
    "customer_segments",
    "customers",
    "categories",
    "suppliers",
    "products",
    "orders",
    "order_items",
    "payments",
]

# 2. استخراج البيانات وتخزينها في Dictionary
extracted_data = {}

for col_name in collections:
    # استبعاد حقل _id التلقائي لمنع التعارض لاحقاً
    cursor = db[col_name].find({}, {"_id": 0})
    df = pd.DataFrame(list(cursor))
    extracted_data[col_name] = df
    print(f"✓ Extracted {len(df)} records from '{col_name}'")

# معاينة أول 5 صفوف من جدول العملاء للتأكد من نجاح الاستخراج
print("\n--- Preview: Customers DataFrame ---")
print(extracted_data["customers"].head())
