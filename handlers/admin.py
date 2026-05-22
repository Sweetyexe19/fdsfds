from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

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
from services.catalog_nav import level_name
from services.delivery import deliver_order
from services.encryption import DataEncryptor
from services.sold_archive import archive_exists, clear_archive, get_archive_path
from states import AdminCategory, AdminManualSell, AdminProducts, AdminSeed, AdminSettings
from keyboards.inline import admin_upload_pick_kb

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


async def _admin_list_categories(
    callback: CallbackQuery,
    db: Database,
    container_id: int | None,
    title: str,
    back_callback: str,
) -> None:
    categories = await db.get_children(container_id, active_only=False)
    ids = [c["id"] for c in categories]
    leaves = {cid: await db.is_leaf(cid) for cid in ids}
    counts = await db.count_available_map(ids)
    await callback.message.edit_text(
        title,
        reply_markup=admin_categories_kb(
            categories,
            container_id=container_id,
            back_callback=back_callback,
            leaves=leaves,
            counts=counts,
        ),
    )


@router.callback_query(F.data == "adm:categories")
async def cb_admin_categories(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    await _admin_list_categories(
        callback, db, None, "📁 <b>Категории</b>", "adm:main"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:children:"))
async def cb_admin_children(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    container_id = int(callback.data.split(":")[2])
    cat = await db.get_category(container_id)
    if not cat:
        await callback.answer("Не найдено", show_alert=True)
        return
    path = await db.get_category_path(container_id)
    parent = cat.get("parent_id")
    back = "adm:categories" if parent is None else f"adm:children:{parent}"
    await _admin_list_categories(
        callback, db, container_id, f"📁 <b>{path}</b>\n\nПодразделы:", back
    )
    await callback.answer()


@router.callback_query(F.data == "adm:cat_new")
async def cb_cat_new_root(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminCategory.name)
    await state.update_data(parent_id=None)
    await callback.message.answer(f"Введите название {level_name(0)}:")
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cat_new:"))
async def cb_cat_new_child(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    parent_id = int(callback.data.split(":")[3])
    if not await db.can_add_child(parent_id):
        await callback.answer("Нельзя добавить подраздел", show_alert=True)
        return
    parent = await db.get_category(parent_id)
    depth = await db.get_category_depth(parent_id) + 1
    await state.set_state(AdminCategory.name)
    await state.update_data(parent_id=parent_id)
    await callback.message.answer(
        f"Новая {level_name(depth)} в «{parent['name']}».\nВведите название:"
    )
    await callback.answer()


@router.message(AdminCategory.name)
async def admin_cat_name(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminCategory.description)
    await message.answer("Введите описание:")


@router.message(AdminCategory.description)
async def admin_cat_description(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(description=message.text.strip())
    data = await state.get_data()
    parent_id = data.get("parent_id")
    if parent_id and not await db.can_add_child(parent_id):
        await state.clear()
        await message.answer("❌ Достигнут максимальный уровень вложенности")
        return
    await state.set_state(AdminCategory.price)
    await message.answer(
        "Введите цену за канал в рублях:\n"
        "(0 — если планируете добавить подкатегории без товаров здесь)"
    )


@router.message(AdminCategory.price)
async def admin_cat_price(message: Message, state: FSMContext, db: Database) -> None:
    try:
        price = float(message.text.replace(",", ".").strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректную цену (0 или больше):")
        return
    data = await state.get_data()
    parent_id = data.get("parent_id")
    cat_id = await db.create_category(
        data["name"], data["description"], price, parent_id=parent_id
    )
    await state.clear()
    path = await db.get_category_path(cat_id)
    hint = (
        "Добавьте подкатегории или загрузите TXT на этот уровень."
        if price == 0
        else "Загрузите товары: /admin → Загрузить TXT"
    )
    await message.answer(
        f"✅ Создано: <b>{path}</b> (ID: {cat_id})\n\n{hint}\n\n"
        f"Формат: <code>логин:пароль:резервка:пароль:ключ2фа:ссылка</code>",
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
    path = await db.get_category_path(category_id)
    is_leaf = await db.is_leaf(category_id)
    can_child = await db.can_add_child(category_id)
    count = await db.count_available(category_id)
    depth = await db.get_category_depth(category_id)

    if is_leaf:
        price = cat.get("price") or 0
        text = (
            f"📦 <b>{path}</b> (ID: {cat['id']})\n"
            f"Уровень: {level_name(depth)}\n\n"
            f"{cat['description']}\n\n"
            f"💰 {price:.0f} ₽ | 📊 {count} шт."
        )
    else:
        text = (
            f"📁 <b>{path}</b> (ID: {cat['id']})\n"
            f"Уровень: {level_name(depth)} (есть подразделы)\n\n"
            f"{cat['description']}\n\n"
            f"📊 Всего в разделе: {count} шт."
        )
    await callback.message.edit_text(
        text,
        reply_markup=admin_category_kb(
            category_id,
            bool(cat["is_active"]),
            is_leaf=is_leaf,
            can_add_child=can_child,
            parent_id=cat.get("parent_id"),
        ),
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


async def _admin_upload_picker(
    callback: CallbackQuery,
    db: Database,
    container_id: int | None,
    back_callback: str,
) -> None:
    categories = await db.get_children(container_id, active_only=False)
    if not categories:
        await callback.message.edit_text(
            "Нет разделов. Создайте категорию.",
            reply_markup=admin_main_kb(),
        )
        return
    ids = [c["id"] for c in categories]
    leaves = {cid: await db.is_leaf(cid) for cid in ids}
    await callback.message.edit_text(
        "📦 <b>Загрузка товаров</b>\n\nВыберите раздел (лист с товарами):",
        reply_markup=admin_upload_pick_kb(
            categories, leaves, parent_id=container_id
        ),
    )


@router.callback_query(F.data == "adm:upload")
async def cb_upload_menu(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    root = await db.get_children(None, active_only=False)
    if not root:
        await callback.answer("Сначала создайте категорию", show_alert=True)
        return
    await _admin_upload_picker(callback, db, None, "adm:main")
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upload_nav:"))
async def cb_upload_nav(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    container_id = int(callback.data.split(":")[2])
    await _admin_upload_picker(callback, db, container_id, f"adm:upload_back:{container_id}")
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upload_back:"))
async def cb_upload_back(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    ref_id = int(callback.data.split(":")[2])
    cat = await db.get_category(ref_id)
    list_parent = cat.get("parent_id") if cat else None
    await _admin_upload_picker(callback, db, list_parent, "adm:main")
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upload:"))
async def cb_upload_category(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    category_id = int(callback.data.split(":")[2])
    if not await db.is_leaf(category_id):
        await callback.answer(
            "Загрузка только в конечный раздел без подкатегорий",
            show_alert=True,
        )
        return
    path = await db.get_category_path(category_id)
    await state.set_state(AdminProducts.waiting_file)
    await state.update_data(category_id=category_id)
    await callback.message.answer(
        f"📤 Загрузка в <b>{path}</b>\n\n"
        "Отправьте TXT-файл (1 строка = 1 товар):\n"
        "<code>логин:пароль:резервка:пароль:ключ2фа:ссылка</code>"
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
    if not await db.is_leaf(category_id):
        await state.clear()
        await message.answer("❌ Загрузка только в конечный раздел", reply_markup=admin_main_kb())
        return
    added = await db.bulk_add_products(category_id, lines)
    path = await db.get_category_path(category_id)
    await state.clear()
    await message.answer(
        f"✅ В <b>{path}</b> загружено {added} из {len(lines)} строк",
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


@router.callback_query(F.data == "adm:download_sold")
async def cb_download_sold(callback: CallbackQuery, db: Database) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    if not archive_exists():
        await callback.answer("Архив проданных пуст", show_alert=True)
        return
    path = get_archive_path()
    await callback.message.answer_document(
        FSInputFile(path, filename="sold_channels.txt"),
        caption="📥 Архив проданных каналов",
    )
    clear_archive()
    await callback.message.answer(
        "✅ Архив выгружен и очищен.\nНовые продажи будут записываться с нуля.",
        reply_markup=admin_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:seed")
async def cb_seed_menu(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    encryptor: DataEncryptor,
) -> None:
    if not await db.is_admin(callback.from_user.id):
        return
    status = "✅ Включено" if encryptor.enabled else "❌ Не задано"
    await callback.message.edit_text(
        f"🔐 <b>Шифрование: {status}</b>\n\n"
        f"Отправьте seed-фразу следующим сообщением (мин. 8 символов).\n"
        f"Она шифрует данные каналов в БД.\n\n"
        f"⚠️ При смене seed все товары перешифруются.\n"
        f"Сохраните фразу — без неё данные не восстановить!",
        reply_markup=admin_main_kb(),
    )
    await state.set_state(AdminSeed.waiting_seed)
    await callback.answer()


@router.message(AdminSeed.waiting_seed)
async def admin_set_seed(
    message: Message, state: FSMContext, db: Database, encryptor: DataEncryptor
) -> None:
    if not await db.is_admin(message.from_user.id):
        return
    seed = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
    try:
        count = await encryptor.setup_seed(db, seed)
        db.encryptor = encryptor
        await state.clear()
        await message.answer(
            f"✅ Seed-фраза установлена.\n"
            f"Перешифровано товаров: {count}\n\n"
            f"Все новые загрузки также будут шифроваться.",
            reply_markup=admin_main_kb(),
        )
    except ValueError as e:
        await message.answer(str(e))
    except Exception:
        await message.answer("❌ Ошибка установки seed-фразы", reply_markup=admin_main_kb())
        await state.clear()


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
