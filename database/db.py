import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from config import DATABASE_PATH, SOLD_EXPORT_DIR
from services.catalog_nav import MAX_CATEGORY_DEPTH


class Database:
    def __init__(self, path: Path = DATABASE_PATH):
        self.path = path
        self._lock = asyncio.Lock()
        self.encryptor = None

    def _enc_fields(self, data: dict) -> dict:
        if self.encryptor and self.encryptor.enabled:
            return self.encryptor.encrypt_product(data)
        return data

    def _dec_row(self, row: dict) -> dict:
        if self.encryptor and self.encryptor.enabled:
            return self.encryptor.decrypt_product(row)
        return row

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        SOLD_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await self._init_schema(db)
            await self._seed_defaults(db)
            for admin_id in __import__("config").ADMIN_IDS:
                await db.execute(
                    "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,)
                )
            await db.commit()
            await self._migrate_categories(db)

    async def _migrate_categories(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(categories)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "parent_id" not in cols:
            await db.execute(
                "ALTER TABLE categories ADD COLUMN parent_id INTEGER DEFAULT NULL"
            )

    async def _init_schema(self, db: aiosqlite.Connection) -> None:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                price REAL NOT NULL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                login TEXT NOT NULL,
                password TEXT NOT NULL,
                backup_email TEXT DEFAULT '',
                backup_password TEXT DEFAULT '',
                twofa_key TEXT DEFAULT '',
                channel_link TEXT DEFAULT '',
                status TEXT DEFAULT 'available',
                order_id INTEGER,
                reserved_until TEXT,
                sold_at TEXT,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );

            CREATE INDEX IF NOT EXISTS idx_products_category_status
                ON products(category_id, status);

            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, category_id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total REAL NOT NULL,
                payment_method TEXT NOT NULL,
                crypto_asset TEXT,
                status TEXT DEFAULT 'pending',
                external_payment_id TEXT,
                payment_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            );
            """
        )

    async def _seed_defaults(self, db: aiosqlite.Connection) -> None:
        defaults = {
            "welcome_text": __import__("config").WELCOME_TEXT,
            "reviews_url": __import__("config").REVIEWS_URL,
            "support_username": __import__("config").SUPPORT_USERNAME,
            "guarantees_text": (
                "🛡 <b>Гарантии</b>\n\n"
                "• Замена в течение 24 часов при проблемах с доступом\n"
                "• Проверка канала перед выдачей\n"
                "• Поддержка после покупки"
            ),
            "agreement_text": (
                "📜 <b>Пользовательское соглашение</b>\n\n"
                "1. Товар выдаётся в электронном виде после оплаты\n"
                "2. Возврат средств не предусмотрен после выдачи данных\n"
                "3. Покупатель обязан сменить все пароли после получения\n"
                "4. Администрация не несёт ответственности за действия покупателя с аккаунтом"
            ),
            "crypto_usdt_trc20": "",
            "crypto_usdt_bep20": "",
            "crypto_usdt_erc20": "",
            "crypto_usdt_aptos": "",
            "crypto_usdt_ton": "",
            "crypto_usdt_solana": "",
        }
        for key, value in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    # --- Settings ---

    async def get_setting(self, key: str, default: str = "") -> str:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()

    # --- Admins ---

    async def is_admin(self, user_id: int) -> bool:
        if user_id in __import__("config").ADMIN_IDS:
            return True
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
            ) as cur:
                return await cur.fetchone() is not None

    async def add_admin(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
            )
            await db.commit()

    # --- Categories (tree: категория → подкатегория → подподкатегория) ---

    async def get_category(self, category_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM categories WHERE id = ?", (category_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_children(
        self, parent_id: int | None = None, active_only: bool = True
    ) -> list[dict]:
        query = "SELECT * FROM categories WHERE "
        params: list[Any] = []
        if parent_id is None:
            query += "parent_id IS NULL"
        else:
            query += "parent_id = ?"
            params.append(parent_id)
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY sort_order, id"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_categories(self, active_only: bool = True) -> list[dict]:
        return await self.get_children(None, active_only=active_only)

    async def has_children(self, category_id: int, active_only: bool = False) -> bool:
        async with aiosqlite.connect(self.path) as db:
            q = "SELECT 1 FROM categories WHERE parent_id = ?"
            if active_only:
                q += " AND is_active = 1"
            q += " LIMIT 1"
            async with db.execute(q, (category_id,)) as cur:
                return await cur.fetchone() is not None

    async def is_leaf(self, category_id: int) -> bool:
        return not await self.has_children(category_id)

    async def get_category_depth(self, category_id: int) -> int:
        depth = 0
        current_id = category_id
        while True:
            cat = await self.get_category(current_id)
            if not cat or not cat.get("parent_id"):
                return depth
            depth += 1
            current_id = cat["parent_id"]

    async def can_add_child(self, category_id: int) -> bool:
        if await self.get_category_depth(category_id) >= MAX_CATEGORY_DEPTH:
            return False
        if await self.has_children(category_id):
            return False
        if await self.is_leaf(category_id):
            direct = await self.count_available(category_id)
            if direct > 0:
                return False
        return True

    async def get_category_path(self, category_id: int) -> str:
        names: list[str] = []
        current_id: int | None = category_id
        while current_id:
            cat = await self.get_category(current_id)
            if not cat:
                break
            names.insert(0, cat["name"])
            current_id = cat.get("parent_id")
        return " → ".join(names) if names else ""

    async def create_category(
        self,
        name: str,
        description: str,
        price: float,
        parent_id: int | None = None,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO categories (name, description, price, parent_id) "
                "VALUES (?, ?, ?, ?)",
                (name, description, price, parent_id),
            )
            await db.commit()
            return cur.lastrowid

    async def update_category(self, category_id: int, **fields: Any) -> None:
        allowed = {"name", "description", "price", "is_active", "sort_order", "parent_id"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [category_id]
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE categories SET {sets} WHERE id = ?", values
            )
            await db.commit()

    async def delete_category(self, category_id: int) -> None:
        children = await self.get_children(category_id, active_only=False)
        for child in children:
            await self.delete_category(child["id"])
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM products WHERE category_id = ?", (category_id,))
            await db.execute("DELETE FROM cart WHERE category_id = ?", (category_id,))
            await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            await db.commit()

    async def count_available(self, category_id: int) -> int:
        if await self.is_leaf(category_id):
            async with aiosqlite.connect(self.path) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM products WHERE category_id = ? AND status = 'available'",
                    (category_id,),
                ) as cur:
                    row = await cur.fetchone()
                    return row[0] if row else 0
        total = 0
        for child in await self.get_children(category_id, active_only=True):
            total += await self.count_available(child["id"])
        return total

    async def count_available_map(self, category_ids: list[int]) -> dict[int, int]:
        return {cid: await self.count_available(cid) for cid in category_ids}

    # --- Products ---

    @staticmethod
    def parse_product_line(line: str) -> dict | None:
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        parts = line.split(":")
        if len(parts) < 6:
            return None
        return {
            "login": parts[0],
            "password": parts[1],
            "backup_email": parts[2],
            "backup_password": parts[3],
            "twofa_key": parts[4],
            "channel_link": ":".join(parts[5:]),
        }

    async def bulk_add_products(self, category_id: int, lines: list[str]) -> int:
        if not await self.is_leaf(category_id):
            return 0
        added = 0
        async with aiosqlite.connect(self.path) as db:
            for line in lines:
                parsed = self.parse_product_line(line)
                if not parsed:
                    continue
                enc = self._enc_fields(parsed)
                await db.execute(
                    """INSERT INTO products
                    (category_id, login, password, backup_email, backup_password,
                     twofa_key, channel_link, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'available')""",
                    (
                        category_id,
                        enc["login"],
                        enc["password"],
                        enc["backup_email"],
                        enc["backup_password"],
                        enc["twofa_key"],
                        enc["channel_link"],
                    ),
                )
                added += 1
            await db.commit()
        return added

    async def get_product(self, product_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ) as cur:
                row = await cur.fetchone()
                return self._dec_row(dict(row)) if row else None

    async def get_all_products_raw(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM products") as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def update_product_fields(self, product_id: int, fields: dict) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE products SET login=?, password=?, backup_email=?,
                backup_password=?, twofa_key=?, channel_link=? WHERE id=?""",
                (
                    fields["login"],
                    fields["password"],
                    fields["backup_email"],
                    fields["backup_password"],
                    fields["twofa_key"],
                    fields["channel_link"],
                    product_id,
                ),
            )
            await db.commit()

    async def mark_product_sold_manual(self, product_id: int) -> bool:
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM products WHERE id = ? AND status = 'available'",
                    (product_id,),
                ) as cur:
                    product = await cur.fetchone()
                    if not product:
                        return False
                    product_dict = self._dec_row(dict(product))
                sold_at = datetime.utcnow().isoformat()
                await db.execute(
                    "UPDATE products SET status = 'sold', sold_at = ?, order_id = NULL "
                    "WHERE id = ? AND status = 'available'",
                    (sold_at, product_id),
                )
                await db.commit()
                if db.total_changes == 0:
                    return False
        await self._export_sold_product(product_dict, order_id=None)
        return True

    async def list_products(
        self, category_id: int, status: str = "available", limit: int = 20
    ) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, login, status FROM products WHERE category_id = ? AND status = ? "
                "ORDER BY id LIMIT ?",
                (category_id, status, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [self._dec_row(dict(r)) for r in rows]

    # --- Cart ---

    async def get_cart(self, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT c.*, cat.name, cat.price, cat.description
                FROM cart c
                JOIN categories cat ON cat.id = c.category_id
                WHERE c.user_id = ?""",
                (user_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def add_to_cart(
        self, user_id: int, category_id: int, quantity: int
    ) -> tuple[bool, str]:
        available = await self.count_available(category_id)
        if available < quantity:
            return False, f"Доступно только {available} шт."
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT quantity FROM cart WHERE user_id = ? AND category_id = ?",
                (user_id, category_id),
            ) as cur:
                existing = await cur.fetchone()
            new_qty = (existing[0] if existing else 0) + quantity
            if new_qty > available:
                return False, f"В корзине уже есть товары. Максимум: {available} шт."
            if existing:
                await db.execute(
                    "UPDATE cart SET quantity = ? WHERE user_id = ? AND category_id = ?",
                    (new_qty, user_id, category_id),
                )
            else:
                await db.execute(
                    "INSERT INTO cart (user_id, category_id, quantity) VALUES (?, ?, ?)",
                    (user_id, category_id, quantity),
                )
            await db.commit()
        return True, "Добавлено в корзину"

    async def update_cart_item(
        self, user_id: int, category_id: int, quantity: int
    ) -> tuple[bool, str]:
        if quantity <= 0:
            await self.remove_from_cart(user_id, category_id)
            return True, "Удалено из корзины"
        available = await self.count_available(category_id)
        if quantity > available:
            return False, f"Доступно только {available} шт."
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE cart SET quantity = ? WHERE user_id = ? AND category_id = ?",
                (quantity, user_id, category_id),
            )
            await db.commit()
        return True, "Корзина обновлена"

    async def remove_from_cart(self, user_id: int, category_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM cart WHERE user_id = ? AND category_id = ?",
                (user_id, category_id),
            )
            await db.commit()

    async def clear_cart(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
            await db.commit()

    async def cart_total(self, user_id: int) -> float:
        items = await self.get_cart(user_id)
        return sum(item["quantity"] * item["price"] for item in items)

    # --- Orders & fulfillment ---

    async def create_order(
        self,
        user_id: int,
        items: list[dict],
        total: float,
        payment_method: str,
        crypto_asset: str | None = None,
        external_payment_id: str | None = None,
        payment_url: str | None = None,
    ) -> int | None:
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    for item in items:
                        async with db.execute(
                            "SELECT COUNT(*) FROM products "
                            "WHERE category_id = ? AND status = 'available'",
                            (item["category_id"],),
                        ) as cur:
                            count = (await cur.fetchone())[0]
                        if count < item["quantity"]:
                            await db.execute("ROLLBACK")
                            return None

                    cur = await db.execute(
                        """INSERT INTO orders
                        (user_id, total, payment_method, crypto_asset,
                         external_payment_id, payment_url, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                        (
                            user_id,
                            total,
                            payment_method,
                            crypto_asset,
                            external_payment_id,
                            payment_url,
                        ),
                    )
                    order_id = cur.lastrowid

                    reserve_until = (
                        datetime.utcnow() + timedelta(minutes=__import__("config").RESERVE_MINUTES)
                    ).isoformat()

                    for item in items:
                        await db.execute(
                            "INSERT INTO order_items (order_id, category_id, quantity, price) "
                            "VALUES (?, ?, ?, ?)",
                            (order_id, item["category_id"], item["quantity"], item["price"]),
                        )
                        await db.execute(
                            """UPDATE products SET status = 'reserved', order_id = ?,
                            reserved_until = ?
                            WHERE id IN (
                                SELECT id FROM products
                                WHERE category_id = ? AND status = 'available'
                                ORDER BY id LIMIT ?
                            )""",
                            (order_id, reserve_until, item["category_id"], item["quantity"]),
                        )

                    await db.execute("COMMIT")
                    return order_id
                except Exception:
                    await db.execute("ROLLBACK")
                    raise

    async def get_order(self, order_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_order_items(self, order_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT oi.*, c.name as category_name
                FROM order_items oi
                JOIN categories c ON c.id = oi.category_id
                WHERE oi.order_id = ?""",
                (order_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def update_order_payment(
        self, order_id: int, external_payment_id: str, payment_url: str
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE orders SET external_payment_id = ?, payment_url = ? WHERE id = ?",
                (external_payment_id, payment_url, order_id),
            )
            await db.commit()

    async def get_pending_orders(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM orders WHERE status IN ('pending', 'awaiting_confirmation')"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def set_order_awaiting_confirmation(self, order_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE orders SET status = 'awaiting_confirmation' "
                "WHERE id = ? AND status = 'pending'",
                (order_id,),
            )
            await db.commit()
            return cur.rowcount > 0

    async def cancel_order(self, order_id: int) -> bool:
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                async with db.execute(
                    "SELECT status FROM orders WHERE id = ?", (order_id,)
                ) as cur:
                    row = await cur.fetchone()
                if not row or row[0] in ("paid", "cancelled"):
                    return False
                await db.execute(
                    "UPDATE products SET status = 'available', order_id = NULL, "
                    "reserved_until = NULL WHERE order_id = ? AND status = 'reserved'",
                    (order_id,),
                )
                await db.execute(
                    "UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,)
                )
                await db.commit()
        return True

    async def format_order_summary(self, order_id: int) -> str:
        order = await self.get_order(order_id)
        if not order:
            return ""
        items = await self.get_order_items(order_id)
        total_qty = sum(i["quantity"] for i in items)
        lines = []
        for i in items:
            path = await self.get_category_path(i["category_id"])
            lines.append(f"• {path} — {i['quantity']} шт. × {i['price']:.0f} ₽")
        method = order["payment_method"]
        if method == "crypto" and order.get("crypto_asset"):
            from constants import CRYPTO_LABELS

            method = f"Крипто ({CRYPTO_LABELS.get(order['crypto_asset'], order['crypto_asset'])})"
        elif method == "yookassa":
            method = "ЮKassa"
        return (
            f"🧾 <b>Заказ #{order_id}</b>\n"
            f"👤 Покупатель: <code>{order['user_id']}</code>\n"
            f"💰 Сумма: <b>{order['total']:.0f} ₽</b>\n"
            f"📦 Аккаунтов: <b>{total_qty}</b> шт.\n"
            f"💳 Способ: {method}\n\n"
            f"<b>Категории:</b>\n" + "\n".join(lines)
        )

    async def cancel_expired_orders(self) -> list[int]:
        now = datetime.utcnow().isoformat()
        cancelled = []
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """SELECT id FROM orders o
                    WHERE o.status = 'pending'
                    AND EXISTS (
                        SELECT 1 FROM products p
                        WHERE p.order_id = o.id AND p.reserved_until < ?
                    )""",
                    (now,),
                ) as cur:
                    order_ids = [r[0] for r in await cur.fetchall()]

                for oid in order_ids:
                    await db.execute(
                        "UPDATE products SET status = 'available', order_id = NULL, "
                        "reserved_until = NULL WHERE order_id = ? AND status = 'reserved'",
                        (oid,),
                    )
                    await db.execute(
                        "UPDATE orders SET status = 'cancelled' WHERE id = ?", (oid,)
                    )
                    cancelled.append(oid)
                await db.commit()
        return cancelled

    async def fulfill_order(self, order_id: int) -> list[dict] | None:
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")
                try:
                    async with db.execute(
                        "SELECT status FROM orders WHERE id = ?", (order_id,)
                    ) as cur:
                        order_row = await cur.fetchone()
                    if not order_row or order_row["status"] == "paid":
                        await db.execute("ROLLBACK")
                        return None

                    async with db.execute(
                        "SELECT * FROM products WHERE order_id = ? AND status = 'reserved'",
                        (order_id,),
                    ) as cur:
                        products = [
                            self._dec_row(dict(r)) for r in await cur.fetchall()
                        ]

                    if not products:
                        await db.execute("ROLLBACK")
                        return None

                    sold_at = datetime.utcnow().isoformat()
                    for p in products:
                        updated = await db.execute(
                            "UPDATE products SET status = 'sold', sold_at = ? "
                            "WHERE id = ? AND status = 'reserved'",
                            (sold_at, p["id"]),
                        )
                        if updated.rowcount == 0:
                            await db.execute("ROLLBACK")
                            return None

                    await db.execute(
                        "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ? AND status != 'paid'",
                        (sold_at, order_id),
                    )
                    await db.execute("COMMIT")
                except Exception:
                    await db.execute("ROLLBACK")
                    raise

        for product in products:
            await self._export_sold_product(product, order_id)
        return products

    async def _export_sold_product(self, product: dict, order_id: int | None) -> None:
        from services.sold_archive import append_sold_line

        append_sold_line(
            product["login"],
            product["password"],
            product["backup_email"],
            product["backup_password"],
            product["twofa_key"],
            product["channel_link"],
            order_id=order_id,
        )

    @staticmethod
    def format_product_delivery(product: dict, index: int) -> str:
        return (
            f"<b>Канал #{index}</b>\n"
            f"👤 Логин: <code>{product['login']}</code>\n"
            f"🔑 Пароль: <code>{product['password']}</code>\n"
            f"📧 Резервная почта: <code>{product['backup_email']}</code>\n"
            f"🔐 Пароль почты: <code>{product['backup_password']}</code>\n"
            f"🔒 Ключ 2FA: <code>{product['twofa_key']}</code>\n"
            f"🔗 Ссылка: {product['channel_link']}\n"
        )
