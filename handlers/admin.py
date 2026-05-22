from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database import Database
from constants import CRYPTO_NETWORKS
from keyboards.inline import (
    admin_categories_kb,
    admin_category_kb,
    admin_crypto_wallets_kb,
    admin_main_kb,
    admin_order_kb,
    admin_settings_kb,
    back_main_kb,
)
from services.delivery import deliver_order
from states import AdminCategory, AdminManualSell, AdminProducts, AdminSettings

router = Router()


async def admin_filter(callback_or_message, db: Database) -> bool:
    user_id = callback_or_message.from_user.id
    return await db.is_admin(user_id)


@router.message(Command("admin"))
async def cmd_admin(message: Message, db: Database) -> None:
    if not await db.is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    await message.answer("🔧 <b>Админ-панель</b>", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm:main")
async def cb_admin_main(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("🔧 <b>Админ-панель</b>", reply_markup=admin_main_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:categories")
async def cb_admin_categories(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    categories = await db.get_categories(active_only=False)
    await callback.message.edit_text(
        "📁 <b>Категории</b>", reply_markup=admin_categories_kb(categories)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:cat_new")
async def cb_cat_new(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminCategory.name)
    await callback.message.answer("Введите название категории:")
    await callback.answer()


@router.message(AdminCategory.name)
async def admin_cat_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminCategory.description)
    await message.answer("Введите описание категории:")


@router.message(AdminCategory.description)
async def admin_cat_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(AdminCategory.price)
    await message.answer("Введите цену за канал (в рублях):")


@router.message(AdminCategory.price)
async def admin_cat_price(message: Message, state: FSMContext, db: Database) -> None:
    try:
        price = float(message.text.replace(",", ".").strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректную цену:")
        return
    data = await state.get_data()
    cat_id = await db.create_category(data["name"], data["description"], price)
    await state.clear()
    await message.answer(
        f"✅ Категория создана (ID: {cat_id})\n\n"
        f"Загрузите товары: /admin → Загрузить TXT\n"
        f"Формат строки:\n"
        f"<code>логин:пароль:резервка:пароль:ключ2фа:ссылка</code>",
        reply_markup=admin_main_kb(),
    )


@router.callback_query(F.data.startswith("adm:cat:"))
async def cb_admin_cat_detail(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    category_id = int(callback.data.split(":")[2])
    cat = await db.get_category(category_id)
    if not cat:
        await callback.answer("Не найдено", show_alert=True)
        return
    count = await db.count_available(category_id)
    text = (
        f"📦 <b>{cat['name']}</b> (ID: {cat['id']})\n\n"
        f"{cat['description']}\n\n"
        f"💰 {cat['price']:.0f} ₽ | 📊 {count} шт. в наличии"
    )
    await callback.message.edit_text(
        text, reply_markup=admin_category_kb(category_id, bool(cat["is_active"]))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:toggle:"))
async def cb_toggle_category(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    category_id = int(callback.data.split(":")[2])
    cat = await db.get_category(category_id)
    await db.update_category(category_id, is_active=0 if cat["is_active"] else 1)
    await cb_admin_cat_detail(callback, db)


@router.callback_query(F.data.startswith("adm:del:"))
async def cb_delete_category(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    category_id = int(callback.data.split(":")[2])
    await db.delete_category(category_id)
    await callback.answer("Категория удалена")
    await cb_admin_categories(callback, db)


@router.callback_query(F.data.startswith("adm:edit:"))
async def cb_edit_category(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    category_id, field = int(parts[2]), parts[3]
    await state.set_state(AdminCategory.edit_value)
    await state.update_data(category_id=category_id, field=field)
    labels = {"name": "название", "description": "описание", "price": "цену"}
    await callback.message.answer(f"Введите новое значение ({labels.get(field, field)}):")
    await callback.answer()


@router.message(AdminCategory.edit_value)
async def admin_edit_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    field, category_id = data["field"], data["category_id"]
    value = message.text.strip()
    if field == "price":
        try:
            value = float(value.replace(",", "."))
        except ValueError:
            await message.answer("Введите число:")
            return
    await db.update_category(category_id, **{field: value})
    await state.clear()
    await message.answer("✅ Обновлено", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm:upload")
async def cb_upload_menu(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    categories = await db.get_categories(active_only=False)
    if not categories:
        await callback.answer("Сначала создайте категорию", show_alert=True)
        return
    from keyboards.inline import admin_categories_kb

    await callback.message.edit_text(
        "Выберите категорию для загрузки товаров:",
        reply_markup=admin_categories_kb(categories),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upload:"))
async def cb_upload_category(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    category_id = int(callback.data.split(":")[2])
    await state.set_state(AdminProducts.waiting_file)
    await state.update_data(category_id=category_id)
    await callback.message.answer(
        "Отправьте TXT-файл.\n"
        "1 строка = 1 товар\n"
        "Формат: <code>логин:пароль:резервка:пароль:ключ2фа:ссылка</code>"
    )
    await callback.answer()


@router.message(AdminProducts.waiting_file, F.document)
async def admin_upload_file(message: Message, state: FSMContext, db: Database) -> None:
    if not message.document.file_name.endswith(".txt"):
        await message.answer("Нужен файл .txt")
        return
    data = await state.get_data()
    category_id = data["category_id"]
    file = await message.bot.download(message.document)
    content = file.read().decode("utf-8", errors="ignore")
    lines = content.splitlines()
    added = await db.bulk_add_products(category_id, lines)
    await state.clear()
    await message.answer(
        f"✅ Загружено {added} товаров из {len(lines)} строк",
        reply_markup=admin_main_kb(),
    )


@router.callback_query(F.data.startswith("adm:products:"))
async def cb_list_products(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    category_id = int(callback.data.split(":")[2])
    products = await db.list_products(category_id, limit=15)
    if not products:
        await callback.answer("Нет товаров", show_alert=True)
        return
    lines = [f"ID {p['id']}: {p['login']} ({p['status']})" for p in products]
    await callback.message.answer(
        "📋 <b>Товары (первые 15):</b>\n" + "\n".join(lines)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:sell")
async def cb_manual_sell(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminManualSell.waiting_product_id)
    await callback.message.answer("Введите ID товара для пометки как проданный:")
    await callback.answer()


@router.message(AdminManualSell.waiting_product_id)
async def admin_manual_sell(message: Message, state: FSMContext, db: Database) -> None:
    try:
        product_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID:")
        return
    ok = await db.mark_product_sold_manual(product_id)
    await state.clear()
    if ok:
        await message.answer("✅ Товар помечен как проданный", reply_markup=admin_main_kb())
    else:
        await message.answer("❌ Товар не найден или уже продан")


@router.callback_query(F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "⚙️ <b>Настройки бота</b>", reply_markup=admin_settings_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:set:"))
async def cb_set_setting(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[2]
    await state.set_state(AdminSettings.waiting_value)
    await state.update_data(setting_key=key)
    await callback.message.answer(f"Введите новое значение для «{key}»:")
    await callback.answer()


@router.message(AdminSettings.waiting_value)
async def admin_set_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    key = data["setting_key"]
    await db.set_setting(key, message.text.strip())
    await state.clear()
    if key.startswith("crypto_"):
        await message.answer("✅ Адрес сохранён", reply_markup=admin_crypto_wallets_kb())
    else:
        await message.answer("✅ Сохранено", reply_markup=admin_settings_kb())


@router.callback_query(F.data == "adm:orders")
async def cb_orders(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    orders = await db.get_pending_orders()
    if not orders:
        await callback.answer("Нет ожидающих заказов", show_alert=True)
        return
    for order in orders[:10]:
        summary = await db.format_order_summary(order["id"])
        status_label = {
            "pending": "⏳ Ожидает",
            "awaiting_confirmation": "🔍 На проверке",
        }.get(order["status"], order["status"])
        await callback.message.answer(
            summary + f"\n\nСтатус: {status_label}",
            reply_markup=admin_order_kb(order["id"]),
        )
    await callback.answer()


@router.callback_query(F.data == "adm:crypto_wallets")
async def cb_crypto_wallets(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    lines = ["🪙 <b>Крипто-кошельки</b>\n"]
    for _, label, setting_key in CRYPTO_NETWORKS:
        addr = await db.get_setting(setting_key)
        preview = addr[:20] + "..." if len(addr) > 20 else (addr or "не задан")
        lines.append(f"{label}: <code>{preview}</code>")
    lines.append("\nНажмите сеть, чтобы изменить адрес:")
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=admin_crypto_wallets_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:crypto:"))
async def cb_edit_crypto_wallet(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    setting_key = callback.data.split(":", 2)[2]
    label = next((l for _, l, s in CRYPTO_NETWORKS if s == setting_key), setting_key)
    await state.set_state(AdminSettings.waiting_value)
    await state.update_data(setting_key=setting_key)
    current = await db.get_setting(setting_key)
    await callback.message.answer(
        f"Введите адрес для <b>{label}</b>:\n\n"
        f"Текущий: <code>{current or 'не задан'}</code>"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:confirm:"))
async def cb_confirm_order(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.split(":")[2])
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("Уже оплачен", show_alert=True)
        return
    if order["status"] == "cancelled":
        await callback.answer("Заказ отменён", show_alert=True)
        return
    ok = await deliver_order(callback.bot, db, order_id, order["user_id"])
    if ok:
        await callback.message.edit_text(f"✅ Заказ #{order_id} подтверждён, данные отправлены покупателю")
    else:
        await callback.answer("Ошибка выдачи (возможно, нет зарезервированных товаров)", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cancel:"))
async def cb_cancel_order(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.split(":")[2])
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("Заказ уже оплачен", show_alert=True)
        return
    if order["status"] == "cancelled":
        await callback.answer("Уже отменён", show_alert=True)
        return
    ok = await db.cancel_order(order_id)
    if not ok:
        await callback.answer("Не удалось отменить", show_alert=True)
        return
    try:
        await callback.bot.send_message(
            order["user_id"],
            f"❌ <b>Оплата отменена</b>\n\nЗаказ #{order_id} не подтверждён администратором.",
        )
    except Exception:
        pass
    await callback.message.edit_text(f"❌ Заказ #{order_id} отменён")
    await callback.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    import aiosqlite
    from config import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM products WHERE status = 'available'"
        ) as cur:
            avail = (await cur.fetchone())[0]
        async with conn.execute(
            "SELECT COUNT(*) FROM products WHERE status = 'sold'"
        ) as cur:
            sold = (await cur.fetchone())[0]
        async with conn.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'paid'"
        ) as cur:
            orders = (await cur.fetchone())[0]
        async with conn.execute(
            "SELECT COALESCE(SUM(total), 0) FROM orders WHERE status = 'paid'"
        ) as cur:
            revenue = (await cur.fetchone())[0]

    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"📦 В наличии: {avail}\n"
        f"✅ Продано: {sold}\n"
        f"🧾 Заказов: {orders}\n"
        f"💰 Выручка: {revenue:.0f} ₽",
        reply_markup=admin_main_kb(),
    )
    await callback.answer()
