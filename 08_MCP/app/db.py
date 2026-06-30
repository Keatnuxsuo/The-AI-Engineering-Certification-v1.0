import aiosqlite

# name, description, price, category, weight_kg, length_cm, width_cm, height_cm
PRODUCTS = [
    ("Whisker Wand", "Interactive feather toy on a flexible wand", 9.99, "toys", 0.15, 35, 8, 5),
    ("Catnip Mouse", "Organic catnip-stuffed plush mouse", 4.99, "toys", 0.05, 12, 8, 6),
    ("Laser Pointer Pro", "Red-dot laser with adjustable patterns", 12.99, "toys", 0.10, 15, 10, 4),
    ("Cozy Cat Bed", "Soft donut-shaped bed for curling up", 29.99, "beds", 1.20, 60, 60, 20),
    ("Window Hammock", "Suction-cup window perch with fleece lining", 24.99, "beds", 0.80, 55, 30, 5),
    ("Salmon Treats", "Freeze-dried wild salmon bites, 100g", 7.99, "food", 0.12, 15, 10, 8),
    ("Tuna Crunchies", "Crunchy tuna-flavored dental treats, 80g", 5.99, "food", 0.10, 14, 10, 7),
    (
        "Scratching Post Tower",
        "3-tier sisal scratching post with platforms",
        49.99,
        "furniture",
        4.50,
        45,
        45,
        90,
    ),
]

PRODUCT_SHIPPING_BY_NAME = {
    name: (weight_kg, length_cm, width_cm, height_cm)
    for name, _, _, _, weight_kg, length_cm, width_cm, height_cm in PRODUCTS
}


async def init_db(db: aiosqlite.Connection):
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id TEXT PRIMARY KEY,
            client_info_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS authorization_codes (
            code TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            expires_at REAL NOT NULL,
            code_challenge TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            redirect_uri_provided_explicitly INTEGER NOT NULL,
            resource TEXT,
            username TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS access_tokens (
            token TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            expires_at REAL,
            resource TEXT
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            expires_at REAL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            weight_kg REAL NOT NULL DEFAULT 1.0,
            length_cm REAL NOT NULL DEFAULT 20,
            width_cm REAL NOT NULL DEFAULT 15,
            height_cm REAL NOT NULL DEFAULT 10
        );
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            UNIQUE(username, product_id)
        );
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending_authorizations (
            request_id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            code_challenge TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            redirect_uri_provided_explicitly INTEGER NOT NULL,
            resource TEXT,
            state TEXT,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS token_users (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL
        );
        """
    )

    await _migrate_product_shipping_columns(db)

    # Seed products if empty
    cursor = await db.execute("SELECT COUNT(*) FROM products")
    (count,) = await cursor.fetchone()
    if count == 0:
        await db.executemany(
            """INSERT INTO products
               (name, description, price, category, weight_kg, length_cm, width_cm, height_cm)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            PRODUCTS,
        )
    else:
        await _backfill_product_shipping(db)
    await db.commit()


async def _migrate_product_shipping_columns(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(products)")
    columns = {row[1] for row in await cursor.fetchall()}
    migrations = [
        ("weight_kg", "REAL NOT NULL DEFAULT 1.0"),
        ("length_cm", "REAL NOT NULL DEFAULT 20"),
        ("width_cm", "REAL NOT NULL DEFAULT 15"),
        ("height_cm", "REAL NOT NULL DEFAULT 10"),
    ]
    for column, definition in migrations:
        if column not in columns:
            await db.execute(f"ALTER TABLE products ADD COLUMN {column} {definition}")


async def _backfill_product_shipping(db: aiosqlite.Connection) -> None:
    for name, (weight_kg, length_cm, width_cm, height_cm) in PRODUCT_SHIPPING_BY_NAME.items():
        await db.execute(
            """UPDATE products
               SET weight_kg = ?, length_cm = ?, width_cm = ?, height_cm = ?
               WHERE name = ?""",
            (weight_kg, length_cm, width_cm, height_cm, name),
        )
