from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.catalog_nav import format_catalog_button


def main_menu_kb(reviews_url: str, support_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Купить канал", callback_data="buy"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Отзывы", url=reviews_url),
    )
    builder.row(InlineKeyboardButton(text="🧺 Корзина", callback_data="cart"))
    if support_username:
        builder.row(
            InlineKeyboardButton(
                text="💬 Поддержка",
                url=f"https://t.me/{support_username}",
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(text="💬 Поддержка", callback_data="support"),
        )
    builder.row(
        InlineKeyboardButton(text="🛡 Гарантии", callback_data="guarantees"),
        InlineKeyboardButton(text="📜 Соглашение", callback_data="agreement"),
    )
    return builder.as_markup()


def catalog_kb(
    categories: list[dict],
    counts: dict[int, int],
    leaves: dict[int, bool],
    parent_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        cid = cat["id"]
        is_leaf = leaves.get(cid, True)
        label = format_catalog_button(
            cat["name"],
            is_leaf=is_leaf,
            price=cat.get("price") or 0,
            count=counts.get(cid, 0),
        )
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"cat:{cid}"),
        )
    if parent_id:
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_back:{parent_id}"),
        )
    else:
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return builder.as_markup()


def category_detail_kb(category_id: int, parent_id: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить в корзину",
            callback_data=f"add:{category_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="🧺 Корзина", callback_data="cart"),
    )
    if parent_id:
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_back:{parent_id}"),
        )
    else:
        builder.row(InlineKeyboardButton(text="◀️ Каталог", callback_data="buy"))
    builder.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main"))
    return builder.as_markup()


def cart_kb(items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        name = item.get("path") or item.get("name", "Товар")
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {name} x{item['quantity']}",
                callback_data=f"cart_remove:{item['category_id']}",
            )
        )
    if items:
        builder.row(
            InlineKeyboardButton(text="💳 Оплатить", callback_data="checkout"),
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return builder.as_markup()


def payment_methods_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 ЮKassa (руб.)", callback_data="pay:yookassa"),
    )
    builder.row(
        InlineKeyboardButton(text="🪙 Криптовалюта", callback_data="pay:crypto"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Корзина", callback_data="cart"))
    return builder.as_markup()


def crypto_assets_kb(networks: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in networks:
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"crypto:{key}"),
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="checkout"))
    return builder.as_markup()


def payment_order_kb(
    order_id: int,
    payment_url: str | None = None,
    is_crypto: bool = False,
    manual_check: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_crypto:
        builder.row(
            InlineKeyboardButton(
                text="💳 Перейти к оплате",
                callback_data=f"pay_go:{order_id}",
            )
        )
    elif payment_url:
        builder.row(
            InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url),
        )
    if manual_check:
        builder.row(
            InlineKeyboardButton(
                text="🔍 Проверить оплату",
                callback_data=f"check_pay:{order_id}",
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔍 Проверить оплату",
                callback_data=f"check_yoo:{order_id}",
            )
        )
    builder.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main"))
    return builder.as_markup()


def admin_payment_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=f"adm:confirm:{order_id}",
        ),
        InlineKeyboardButton(
            text="❌ Отменить",
            callback_data=f"adm:cancel:{order_id}",
        ),
    )
    return builder.as_markup()


def admin_crypto_wallets_kb() -> InlineKeyboardMarkup:
    from constants import CRYPTO_NETWORKS

    builder = InlineKeyboardBuilder()
    for key, label, setting_key in CRYPTO_NETWORKS:
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"adm:crypto:{setting_key}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Админ", callback_data="adm:main"))
    return builder.as_markup()


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📁 Категории", callback_data="adm:categories"))
    builder.row(InlineKeyboardButton(text="📦 Загрузить товары", callback_data="adm:upload"))
    builder.row(InlineKeyboardButton(text="🪙 Крипто-кошельки", callback_data="adm:crypto_wallets"))
    builder.row(InlineKeyboardButton(text="📥 Скачать проданные", callback_data="adm:download_sold"))
    builder.row(InlineKeyboardButton(text="🔐 Seed-фраза", callback_data="adm:seed"))
    builder.row(InlineKeyboardButton(text="🏷 Пометить проданным", callback_data="adm:sell"))
    builder.row(InlineKeyboardButton(text="📋 Заказы", callback_data="adm:orders"))
    builder.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings"))
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"))
    return builder.as_markup()


def admin_categories_kb(
    categories: list[dict],
    *,
    container_id: int | None = None,
    back_callback: str = "adm:categories",
    leaves: dict[int, bool] | None = None,
    counts: dict[int, int] | None = None,
    add_child_label: str = "➕ Подкатегория",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if container_id is None:
        btn = "➕ Ещё категория" if categories else "➕ Категория"
        builder.row(InlineKeyboardButton(text=btn, callback_data="adm:cat_new"))
    else:
        builder.row(
            InlineKeyboardButton(
                text=add_child_label,
                callback_data=f"adm:cat_new:{container_id}",
            ),
        )
    leaves = leaves or {}
    counts = counts or {}
    for cat in categories:
        status = "✅" if cat["is_active"] else "❌"
        if leaves.get(cat["id"], True) and (cat.get("price") or 0) > 0:
            extra = f" ({cat['price']:.0f}₽, {counts.get(cat['id'], 0)} шт.)"
        elif leaves.get(cat["id"], True):
            extra = f" ({counts.get(cat['id'], 0)} шт.)"
        else:
            extra = " →"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {cat['name']}{extra}",
                callback_data=f"adm:cat:{cat['id']}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback),
    )
    builder.row(InlineKeyboardButton(text="◀️ Админ", callback_data="adm:main"))
    return builder.as_markup()


def admin_category_kb(
    category_id: int,
    is_active: bool,
    *,
    is_leaf: bool,
    can_add_child: bool,
    parent_id: int | None,
    add_child_label: str = "➕ Подкатегория",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:edit:{category_id}:name"),
        InlineKeyboardButton(text="📝 Описание", callback_data=f"adm:edit:{category_id}:description"),
    )
    if is_leaf:
        builder.row(
            InlineKeyboardButton(text="💰 Цена", callback_data=f"adm:edit:{category_id}:price"),
            InlineKeyboardButton(
                text="🔴 Выкл." if is_active else "🟢 Вкл.",
                callback_data=f"adm:toggle:{category_id}",
            ),
        )
        builder.row(
            InlineKeyboardButton(text="📤 Загрузить TXT", callback_data=f"adm:upload:{category_id}"),
            InlineKeyboardButton(text="📋 Товары", callback_data=f"adm:products:{category_id}"),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔴 Выкл." if is_active else "🟢 Вкл.",
                callback_data=f"adm:toggle:{category_id}",
            ),
            InlineKeyboardButton(
                text="📂 Подкатегории",
                callback_data=f"adm:children:{category_id}",
            ),
        )
    if can_add_child:
        builder.row(
            InlineKeyboardButton(
                text=add_child_label,
                callback_data=f"adm:cat_new:{category_id}",
            ),
        )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:del:{category_id}"),
    )
    if parent_id:
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"adm:children:{parent_id}",
            ),
        )
    else:
        builder.row(InlineKeyboardButton(text="◀️ Категории", callback_data="adm:categories"))
    return builder.as_markup()


def admin_upload_pick_kb(
    categories: list[dict],
    leaves: dict[int, bool],
    parent_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        if not leaves.get(cat["id"], False):
            builder.row(
                InlineKeyboardButton(
                    text=f"{cat['name']} →",
                    callback_data=f"adm:upload_nav:{cat['id']}",
                ),
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text=f"📤 {cat['name']}",
                    callback_data=f"adm:upload:{cat['id']}",
                ),
            )
    if parent_id is not None:
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"adm:upload_back:{parent_id}",
            ),
        )
    else:
        builder.row(InlineKeyboardButton(text="◀️ Админ", callback_data="adm:main"))
    return builder.as_markup()


def admin_settings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    keys = [
        ("welcome_text", "Приветствие"),
        ("reviews_url", "Ссылка отзывов"),
        ("support_username", "Поддержка"),
        ("guarantees_text", "Гарантии"),
        ("agreement_text", "Соглашение"),
    ]
    for key, label in keys:
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"adm:set:{key}"),
        )
    builder.row(InlineKeyboardButton(text="◀️ Админ", callback_data="adm:main"))
    return builder.as_markup()


def admin_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return admin_payment_kb(order_id)


def back_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main"))
    return builder.as_markup()


def admin_after_create_kb(parent_id: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if parent_id is not None:
        builder.row(
            InlineKeyboardButton(
                text="➕ Ещё подкатегория",
                callback_data=f"adm:cat_new:{parent_id}",
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="📂 К списку разделов",
                callback_data=f"adm:children:{parent_id}",
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="➕ Ещё категория", callback_data="adm:cat_new"),
        )
        builder.row(
            InlineKeyboardButton(text="📂 К категориям", callback_data="adm:categories"),
        )
    builder.row(InlineKeyboardButton(text="◀️ Админ", callback_data="adm:main"))
    return builder.as_markup()
