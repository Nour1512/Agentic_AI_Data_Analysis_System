import pandas as pd


def transform_data(extracted_data):
    """نقوم باستلام القاموس الذي يحتوي على الـ 8 DataFrames ونعالج كل جدول"""
    print("=" * 50)
    print("Starting Transformation Phase...")
    print("=" * 50)

    # عمل نسخة مستقلة لتفادي التعديل على البيانات الخام
    transformed = {
        col_name: df.copy() for col_name, df in extracted_data.items()
    }

    # ---------------------------------------------------------
    # 1. توحيد صيغ التواريخ (Date Formatting)
    # ---------------------------------------------------------
    print("[1/4] Formatting Date Columns...")

    # تحويل التواريخ في جدول العملاء
    if "customers" in transformed and not transformed["customers"].empty:
        transformed["customers"]["registration_date"] = pd.to_datetime(
            transformed["customers"]["registration_date"], errors="coerce"
        )
        transformed["customers"]["date_of_birth"] = pd.to_datetime(
            transformed["customers"]["date_of_birth"], errors="coerce"
        )

    # تحويل التواريخ في جدول الطلبات
    if "orders" in transformed and not transformed["orders"].empty:
        transformed["orders"]["order_date"] = pd.to_datetime(
            transformed["orders"]["order_date"], errors="coerce"
        )

    # تحويل التواريخ في جدول المدفوعات
    if "payments" in transformed and not transformed["payments"].empty:
        transformed["payments"]["payment_date"] = pd.to_datetime(
            transformed["payments"]["payment_date"], errors="coerce"
        )

    # ---------------------------------------------------------
    # 2. فحص وتصفية سلامة العلاقات (Referential Integrity)
    # ---------------------------------------------------------
    print("[2/4] Validating Foreign Key Relationships...")

    # أ) التأكد من أن كل الطلبات تابعة لعملاء موجودين بالفعل
    valid_customer_ids = set(transformed["customers"]["customer_id"].dropna())
    initial_orders_cnt = len(transformed["orders"])
    transformed["orders"] = transformed["orders"][
        transformed["orders"]["customer_id"].isin(valid_customer_ids)
    ]
    dropped_orders = initial_orders_cnt - len(transformed["orders"])
    if dropped_orders > 0:
        print(f"   ⚠ Dropped {dropped_orders} orders with missing customers.")

    # ب) التأكد من أن تفاصيل الطلبات (order_items) تابعة لطلبات ومنتجات موجودة
    valid_order_ids = set(transformed["orders"]["order_id"].dropna())
    valid_product_ids = set(transformed["products"]["product_id"].dropna())

    transformed["order_items"] = transformed["order_items"][
        transformed["order_items"]["order_id"].isin(valid_order_ids)
        & transformed["order_items"]["product_id"].isin(valid_product_ids)
    ]

    # ج) التأكد من أن المدفوعات (payments) تابعة لطلبات موجودة
    transformed["payments"] = transformed["payments"][
        transformed["payments"]["order_id"].isin(valid_order_ids)
    ]

    # ---------------------------------------------------------
    # 3. إثراء البيانات وحساب المتغيرات الجديدة (Feature Engineering)
    # ---------------------------------------------------------
    print("[3/4] Calculating Derived Features...")

    # أ) حساب هامش الربح لكل منتج
    if (
        "unit_price" in transformed["products"].columns
        and "cost_price" in transformed["products"].columns
    ):
        transformed["products"]["profit_margin"] = (
            transformed["products"]["unit_price"]
            - transformed["products"]["cost_price"]
        ).round(2)

    # ب) حساب مؤشرات العميل الإجمالية (Lifetime Spend & Total Orders)
    customer_aggregates = (
        transformed["orders"]
        .groupby("customer_id")
        .agg(
            total_orders=("order_id", "count"),
            total_lifetime_spend=("total_amount", "sum"),
            last_order_date=("order_date", "max"),
        )
        .reset_index()
    )

    # دمج المؤشرات المحسوبة مع جدول العملاء
    transformed["customers"] = pd.merge(
        transformed["customers"],
        customer_aggregates,
        on="customer_id",
        how="left",
    )

    # معالجة القيم الفارغة للعملاء الذين ليس لديهم طلبات بعد
    transformed["customers"]["total_orders"] = (
        transformed["customers"]["total_orders"].fillna(0).astype(int)
    )
    transformed["customers"]["total_lifetime_spend"] = (
        transformed["customers"]["total_lifetime_spend"].fillna(0.0).round(2)
    )

    # ---------------------------------------------------------
    # 4. تنظيف النصوص والتأكد من عدم وجود قيم شاذة
    # ---------------------------------------------------------
    print("[4/4] Cleaning Text and Replacing NaNs...")

    for name, df in transformed.items():
        # إزالة المسافات الزائدة من أعمدة النصوص
        string_cols = df.select_dtypes(include=["object"]).columns
        for col in string_cols:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": None, "None": None, "": None})

    print("=" * 50)
    print("✓ Data Transformation Completed Successfully!")
    print("=" * 50)

    return transformed


# ---------------------------------------------------------
# مثال لتشغيل خطوة الـ Transform بعد الـ Extract مباشرة:
# ---------------------------------------------------------
if __name__ == "__main__":
    # 1. الاتصال بـ MongoDB واستخراج البيانات الخام (باستخدام إعدادات .env)
    from config import get_mongo_db

    db = get_mongo_db()

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

    print("Fetching raw data from MongoDB...")
    extracted_data = {}
    for col_name in collections:
        cursor = db[col_name].find({}, {"_id": 0})
        extracted_data[col_name] = pd.DataFrame(list(cursor))

    # 2. تشغيل عملية التحويل
    transformed_data = transform_data(extracted_data)

    # 3. طباعة ملخص النتائج للتأكد من نجاح العملية
    print("\n--- Transformed Data Summary ---")
    for name, df in transformed_data.items():
        print(f"Table: {name:<20} | Total Rows: {len(df):<6}")