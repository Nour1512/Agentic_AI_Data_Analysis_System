import csv
import os
import random
import zipfile
from datetime import datetime, timedelta

# Set random seed for reproducibility
random.seed(42)

OUTPUT_DIR = "egyptian_ecommerce_csvs"
ZIP_NAME = "egyptian_ecommerce_dataset.zip"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------
# CONSTANTS & EGYPTIAN DOMAIN DATA
# ---------------------------------------------------------

CITIES_GOVERNORATES = [
    ("Cairo", "Cairo"),
    ("Giza", "Giza"),
    ("6th of October", "Giza"),
    ("Alexandria", "Alexandria"),
    ("Mansoura", "Dakahlia"),
    ("Tanta", "Gharbia"),
    ("Zagazig", "Sharqia"),
    ("Ismailia", "Ismailia"),
    ("Suez", "Suez"),
    ("Port Said", "Port Said"),
    ("Aswan", "Aswan"),
    ("Luxor", "Luxor"),
    ("Minya", "Minya"),
    ("Assiut", "Assiut"),
    ("Sohag", "Sohag"),
    ("Damietta", "Damietta"),
    ("Hurghada", "Red Sea"),
    ("Sharm El Sheikh", "South Sinai"),
]

FIRST_NAMES_MALE = [
    "Ahmed", "Mohamed", "Omar", "Youssef", "Mostafa", "Mahmoud", "Karim", "Tarek",
    "Khaled", "Hassan", "Amr", "Hussein", "Ibrahim", "Hazem", "Ziad", "Sherif",
    "Eslam", "Yasser", "Hamza", "Ali"
]

FIRST_NAMES_FEMALE = [
    "Nour", "Salma", "Mariam", "Aya", "Sarah", "Menna", "Fatima", "Dina",
    "Nada", "Rana", "Yasmin", "Reem", "Habiba", "Hoda", "Farida", "Shahd",
    "Omnia", "Malak", "Noha", "Rania"
]

LAST_NAMES = [
    "Hassan", "Ali", "Mahmoud", "Ibrahim", "Adel", "Samir", "Ahmed", "El-Din",
    "Mansour", "Abdel-Rahman", "Fawzy", "Fathy", "Hamdy", "Shafik", "Badawy",
    "Hegazy", "Nabil", "Radi", "Said", "Soliman"
]

STREET_TYPES = [
    "El-Tahrir St.", "El-Nasr Ave.", "Nile Corniche", "El-Geish St.",
    "Pyramids Rd.", "El-Thawra St.", "9th St.", "Abbas El-Akkad St.",
    "Makram Ebeid St."
]

PAYMENT_METHODS = [
    "Cash on Delivery", "Credit Card", "Debit Card", "Mobile Wallet",
    "Bank Transfer", "Fawry"
]

def random_date(start, end):
    delta = end - start
    random_days = random.randint(0, delta.days)
    random_seconds = random.randint(0, 86399)
    return start + timedelta(days=random_days, seconds=random_seconds)

def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

def fmt_date(dt):
    return dt.strftime("%Y-%m-%d") if dt else ""

# ---------------------------------------------------------
# 1. CUSTOMER_SEGMENTS
# ---------------------------------------------------------
segments_data = [
    (1, "New", "Recently registered users (registered within last 30 days)", 0.00, 1500.00),
    (2, "Regular", "Consistent shoppers with average order values", 1500.01, 10000.00),
    (3, "Loyal", "Repeat customers with high lifetime order frequency", 10000.01, 35000.00),
    (4, "Premium", "Top-tier spenders driving major revenue share", 35000.01, 250000.00),
    (5, "At Risk", "Previously active buyers who have not purchased recently", 5000.00, 30000.00),
]

with open(f"{OUTPUT_DIR}/customer_segments.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["segment_id", "segment_name", "description", "min_lifetime_value", "max_lifetime_value"])
    for row in segments_data:
        writer.writerow(row)

# ---------------------------------------------------------
# 2. CATEGORIES
# ---------------------------------------------------------
raw_categories = [
    (1, "Electronics", "Electronic devices and gadgetry", None),
    (2, "Smartphones & Mobile", "Mobile devices and smartphones", 1),
    (3, "Laptops & Computers", "Personal computers and notebooks", 1),
    (4, "Audio & Accessories", "Headphones, speakers, and cables", 1),
    (5, "Tablets", "Portable tablet computers", 1),
    (6, "Home Appliances", "Electrical equipment for household tasks", None),
    (7, "Kitchen Appliances", "Ovens, microwaves, blenders, and fryers", 6),
    (8, "Cleaning Appliances", "Vacuum cleaners and steam mops", 6),
    (9, "Cooling & Heating", "Air conditioners, fans, and heaters", 6),
    (10, "Fashion", "Clothing, footwear, and apparel", None),
    (11, "Men's Wear", "Clothing items for men", 10),
    (12, "Women's Wear", "Clothing items for women", 10),
    (13, "Footwear", "Shoes, sneakers, and formal footwear", 10),
    (14, "Watches & Jewelry", "Timepieces and fashion accessories", 10),
    (15, "Beauty & Personal Care", "Cosmetics, skincare, and grooming", None),
    (16, "Skincare", "Facial serums, cleansers, and creams", 15),
    (17, "Haircare", "Shampoos, oils, and styling products", 15),
    (18, "Fragrances", "Perfumes, colognes, and body sprays", 15),
    (19, "Home & Living", "Furniture, decor, and home essentials", None),
    (20, "Furniture", "Tables, chairs, desks, and storage", 19),
    (21, "Bedding & Bath", "Sheets, pillows, towels, and mats", 19),
    (22, "Cookware & Dining", "Pots, pans, dinnerware, and cutlery", 19),
    (23, "Supermarket & Groceries", "Packaged goods and household consumables", None),
    (24, "Beverages", "Coffee, tea, juices, and soft drinks", 23),
    (25, "Snacks & Confectionery", "Biscuits, chocolates, and crisps", 23),
    (26, "Pantry Essentials", "Oils, rice, pasta, and canned items", 23),
    (27, "Sports & Fitness", "Exercise gear and athletic equipment", None),
    (28, "Fitness Equipment", "Dumbbells, mats, and bands", 27),
    (29, "Outdoor & Camping", "Tents, backpacks, and lanterns", 27),
    (30, "Automotive Accessories", "Car maintenance and interior gadgets", None),
    (31, "Car Care", "Washes, polishes, and microfibers", 30),
    (32, "Car Electronics", "Dash cams, chargers, and Bluetooth adapters", 30),
    (33, "Books & Stationery", "Reading materials and office supplies", None),
    (34, "Niche Antiques", "Empty category reserved for catalog expansion", None),
]

categories_rows = []
for c in raw_categories:
    cat_id, name, desc, parent = c
    categories_rows.append([cat_id, name, desc, parent if parent else ""])

with open(f"{OUTPUT_DIR}/categories.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["category_id", "category_name", "description", "parent_category_id"])
    writer.writerows(categories_rows)

# ---------------------------------------------------------
# 3. SUPPLIERS
# ---------------------------------------------------------
supplier_prefixes = ["Cairo", "Nile", "Delta", "Alexandria", "Pyramids", "Pharaohs", "Suez", "Giza"]
supplier_suffixes = ["Trading", "Electronics", "Imports", "Distributors", "Supplies", "Industries", "Group"]

suppliers_rows = []
num_suppliers = 60
for sid in range(1, num_suppliers + 1):
    sname = f"{random.choice(supplier_prefixes)} {random.choice(supplier_suffixes)} S.A.E."
    cname = f"{random.choice(FIRST_NAMES_MALE)} {random.choice(LAST_NAMES)}"
    email = f"contact@{sname.lower().replace(' ', '').replace('.', '')}.eg" if sid % 12 != 0 else ""
    phone = f"+2010{random.randint(10000000, 99999999)}" if sid % 15 != 0 else ""
    city, _ = random.choice(CITIES_GOVERNORATES)
    addr = f"{random.randint(1, 120)} {random.choice(STREET_TYPES)}, {city}"
    rating = round(random.uniform(2.5, 5.0), 1)
    c_date = random_date(datetime(2021, 1, 1), datetime(2023, 1, 1))

    suppliers_rows.append([sid, sname, cname, email, phone, "Egypt", city, addr, rating, fmt_dt(c_date)])

with open(f"{OUTPUT_DIR}/suppliers.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["supplier_id", "supplier_name", "contact_name", "email", "phone", "country", "city", "address", "supplier_rating", "created_at"])
    writer.writerows(suppliers_rows)

# ---------------------------------------------------------
# 4. CUSTOMERS
# ---------------------------------------------------------
num_customers = 2000
customers_rows = []
customer_ids = list(range(1001, 1001 + num_customers))

dataset_end_date = datetime(2025, 12, 31, 23, 59, 59)
one_month_cutoff = datetime(2025, 12, 1, 0, 0, 0)

customer_reg_dates = {}

for cid in customer_ids:
    gender = random.choice(["Male", "Female"])
    fname = random.choice(FIRST_NAMES_MALE) if gender == "Male" else random.choice(FIRST_NAMES_FEMALE)
    lname = random.choice(LAST_NAMES)
    clean_fname = fname.lower().replace(" ", "")
    clean_lname = lname.lower().replace(" ", "")
    email = f"{clean_fname}.{clean_lname}{random.randint(10, 999)}@gmail.com"

    dob = random_date(datetime(1965, 1, 1), datetime(2004, 12, 31))

    # Segment assignment
    seg_id = random.choices([1, 2, 3, 4, 5], weights=[0.25, 0.45, 0.15, 0.05, 0.10])[0]

    # Integrated registration date logic based on segment_id:
    # Segment 1 ("New") -> Registered within last 30 days (Dec 1, 2025 to Dec 31, 2025)
    # Segments 2-5 -> Registered older than 30 days (Jan 1, 2022 to Nov 30, 2025)
    if seg_id == 1:
        reg_date = random_date(one_month_cutoff, dataset_end_date)
    else:
        reg_date = random_date(datetime(2022, 1, 1), datetime(2025, 11, 30))

    customer_reg_dates[cid] = reg_date
    city, state = random.choice(CITIES_GOVERNORATES)

    customers_rows.append([
        cid, fname, lname, email, gender, fmt_date(dob),
        fmt_dt(reg_date), seg_id, city, state, "Egypt"
    ])

with open(f"{OUTPUT_DIR}/customers.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "customer_id", "first_name", "last_name", "email", "gender",
        "date_of_birth", "registration_date", "segment_id", "city", "state", "country"
    ])
    writer.writerows(customers_rows)

# ---------------------------------------------------------
# 5. PRODUCTS
# ---------------------------------------------------------
num_products = 600
products_rows = []
product_ids = list(range(501, 501 + num_products))

product_catalog_templates = [
    ("Smartphone Galaxy A", 2, "Samsung", 8000, 18000),
    ("Ultra Laptop Pro", 3, "Lenovo", 22000, 45000),
    ("Wireless Earbuds ANC", 4, "Anker", 1200, 4500),
    ("Smart Tablet 10-inch", 5, "Xiaomi", 6000, 14000),
    ("Digital Air Fryer 5.5L", 7, "Tornado", 3500, 7500),
    ("Espresso Coffee Maker", 7, "DeLonghi", 5000, 16000),
    ("Robot Vacuum Cleaner", 8, "Roborock", 12000, 28000),
    ("Inverter Air Conditioner 1.5HP", 9, "Carrier", 18000, 32000),
    ("Cotton Graphic T-Shirt", 11, "Defacto", 350, 850),
    ("Slim Fit Denim Jeans", 11, "Town Team", 650, 1400),
    ("Casual Summer Dress", 12, "Ravin", 800, 1900),
    ("Leather Running Shoes", 13, "Active", 1200, 3200),
    ("Stainless Steel Watch", 14, "Casio", 2500, 7500),
    ("Hydrating Face Serum 30ml", 16, "L'Oreal", 450, 950),
    ("Nourishing Hair Mask", 17, "Bless", 220, 550),
    ("Eau de Parfum 100ml", 18, "Zara", 1100, 2800),
    ("Modern Ergonomic Desk", 20, "Hub Furniture", 4500, 11000),
    ("Cotton Bed Sheet Set", 21, "Egyptian Cotton Co.", 900, 2200),
    ("Non-Stick Cookware Set 10Pcs", 22, "El-Zenouki", 3200, 8500),
    ("Premium Roast Coffee Beans 250g", 24, "Abu Auf", 180, 420),
    ("Dark Chocolate Bar 100g", 25, "Corona", 45, 110),
    ("Extra Virgin Olive Oil 1L", 26, "Wadi Food", 320, 680),
    ("Adjustable Dumbbell Set 20kg", 28, "TopFit", 2200, 5200),
    ("Microfiber Car Wash Towel", 31, "ArmorAll", 120, 310)
]

for pid in product_ids:
    tmpl = random.choice(product_catalog_templates)
    p_name = f"{tmpl[0]} Mod-{random.randint(100, 999)}"
    cat_id = tmpl[1]
    supp_id = random.randint(1, num_suppliers)
    brand = tmpl[2]

    unit_price = round(random.uniform(tmpl[3], tmpl[4]), 2)
    cost_margin = random.uniform(0.55, 0.85)
    cost_price = round(unit_price * cost_margin, 2)
    weight = round(random.uniform(0.2, 18.0), 2)

    if pid % 20 == 0:
        stock = 0
    elif pid % 12 == 0:
        stock = random.randint(1, 5)
    else:
        stock = random.randint(15, 250)

    reorder_lvl = random.randint(5, 20)
    p_status = random.choices(["Active", "Inactive", "Discontinued"], weights=[0.88, 0.08, 0.04])[0]

    p_created = random_date(datetime(2022, 1, 1), datetime(2024, 6, 1))
    p_updated = random_date(p_created, datetime(2025, 12, 31))

    products_rows.append([
        pid, p_name, cat_id, supp_id, brand,
        f"High quality {p_name} supplied for Egyptian market",
        unit_price, cost_price, weight, stock, reorder_lvl, p_status,
        fmt_dt(p_created), fmt_dt(p_updated)
    ])

with open(f"{OUTPUT_DIR}/products.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "product_id", "product_name", "category_id", "supplier_id", "brand",
        "description", "unit_price", "cost_price", "weight", "stock_quantity",
        "reorder_level", "product_status", "created_at", "updated_at"
    ])
    writer.writerows(products_rows)

product_dict = {row[0]: row[6] for row in products_rows}

# ---------------------------------------------------------
# 6, 7, 8. ORDERS, ORDER_ITEMS, PAYMENTS
# ---------------------------------------------------------
num_orders = 12000
orders_rows = []
order_items_rows = []
payments_rows = []

order_item_id_counter = 1
payment_id_counter = 1

active_customer_ids = random.sample(customer_ids, k=int(len(customer_ids) * 0.85))

for oid in range(10001, 10001 + num_orders):
    cid = random.choice(active_customer_ids)
    c_reg_date = customer_reg_dates[cid]

    # Order date occurs logically after customer's registration date
    o_date = random_date(max(c_reg_date, datetime(2023, 1, 1)), dataset_end_date)

    o_status = random.choices(["Delivered", "Shipped", "Processing", "Pending", "Cancelled", "Returned"],
                              weights=[0.68, 0.10, 0.08, 0.04, 0.06, 0.04])[0]

    if o_status in ["Delivered", "Shipped", "Returned"]:
        p_status = "Paid" if o_status != "Returned" else "Refunded"
    elif o_status in ["Processing", "Pending"]:
        p_status = random.choices(["Paid", "Pending", "Failed"], weights=[0.70, 0.20, 0.10])[0]
    else:
        p_status = random.choices(["Refunded", "Failed", "Pending"], weights=[0.40, 0.40, 0.20])[0]

    num_items = random.choices([1, 2, 3, 4, 5], weights=[0.45, 0.30, 0.15, 0.07, 0.03])[0]
    selected_pids = random.sample(product_ids, k=num_items)

    order_subtotal = 0.0
    order_discount_acc = 0.0
    order_tax_acc = 0.0

    for pid in selected_pids:
        unit_p = product_dict[pid]
        qty = random.randint(1, 4)
        base_line = round(qty * unit_p, 2)

        item_disc = round(base_line * random.uniform(0.05, 0.20), 2) if random.random() < 0.25 else 0.0
        item_tax = round((base_line - item_disc) * 0.14, 2)
        line_tot = round(base_line - item_disc + item_tax, 2)

        order_subtotal += base_line
        order_discount_acc += item_disc
        order_tax_acc += item_tax

        order_items_rows.append([
            order_item_id_counter, oid, pid, qty, unit_p, item_disc, item_tax, line_tot
        ])
        order_item_id_counter += 1

    shipping_cost = random.choice([0.0, 50.0, 75.0, 120.0])
    total_amt = round(order_subtotal - order_discount_acc + order_tax_acc + shipping_cost, 2)

    city, _ = random.choice(CITIES_GOVERNORATES)
    addr = f"{random.randint(1, 150)} {random.choice(STREET_TYPES)}, {city}"

    orders_rows.append([
        oid, cid, fmt_dt(o_date), o_status, p_status,
        round(order_subtotal, 2), round(order_discount_acc, 2),
        round(order_tax_acc, 2), shipping_cost, total_amt,
        "EGP", addr, addr
    ])

    pmethod = random.choice(PAYMENT_METHODS)
    pay_date = o_date + timedelta(minutes=random.randint(2, 120))
    tx_ref = f"TXN-EGY-{oid}-{random.randint(10000, 99999)}"

    if p_status == "Paid":
        payments_rows.append([payment_id_counter, oid, fmt_dt(pay_date), pmethod, total_amt, "EGP", "Success", tx_ref, ""])
        payment_id_counter += 1
    elif p_status == "Failed":
        payments_rows.append([payment_id_counter, oid, fmt_dt(pay_date), pmethod, total_amt, "EGP", "Failed", tx_ref, random.choice(["Insufficient Funds", "3D Secure Authentication Failed", "Network Timeout", "Gateway Declined"])])
        payment_id_counter += 1
    elif p_status == "Refunded":
        payments_rows.append([payment_id_counter, oid, fmt_dt(pay_date), pmethod, total_amt, "EGP", "Success", tx_ref, ""])
        payment_id_counter += 1
        payments_rows.append([payment_id_counter, oid, fmt_dt(pay_date + timedelta(days=2)), pmethod, total_amt, "EGP", "Refunded", f"{tx_ref}-REF", "Customer Return Approved"])
        payment_id_counter += 1

# Write CSV files
with open(f"{OUTPUT_DIR}/orders.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "order_id", "customer_id", "order_date", "order_status", "payment_status",
        "subtotal", "discount_amount", "tax_amount", "shipping_cost", "total_amount",
        "currency", "shipping_address", "billing_address"
    ])
    writer.writerows(orders_rows)

with open(f"{OUTPUT_DIR}/order_items.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "order_item_id", "order_id", "product_id", "quantity", "unit_price",
        "discount_amount", "tax_amount", "line_total"
    ])
    writer.writerows(order_items_rows)

with open(f"{OUTPUT_DIR}/payments.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "payment_id", "order_id", "payment_date", "payment_method", "amount",
        "currency", "payment_status", "transaction_reference", "failure_reason"
    ])
    writer.writerows(payments_rows)

# ---------------------------------------------------------
# COMPRESS TO ZIP ARCHIVE
# ---------------------------------------------------------
csv_files = [
    "customer_segments.csv",
    "categories.csv",
    "suppliers.csv",
    "customers.csv",
    "products.csv",
    "orders.csv",
    "order_items.csv",
    "payments.csv"
]

with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zipf:
    for file in csv_files:
        file_path = os.path.join(OUTPUT_DIR, file)
        zipf.write(file_path, arcname=file)

print(f"Successfully generated all {len(csv_files)} CSV files in '{OUTPUT_DIR}/' and compressed into '{ZIP_NAME}'.")