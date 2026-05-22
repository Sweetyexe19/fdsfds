from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from constants import CRYPTO_LABELS, CRYPTO_NETWORKS
from database import Database
from keyboards.inline import (
    back_main_kb,
    cart_kb,
    catalog_kb,
    category_detail_kb,
    crypto_assets_kb,
    main_menu_kb,
    payment_methods_kb,
    payment_order_kb,
)
from services.delivery import deliver_order, notify_admins_payment_check
from services.yookassa_pay import YooKassaPayment
from states import BuyQuantity

router = Router()


async def show_main(message: Message, db: Database, edit: bool = False) -> None:
    welcome = await db.get_setting("welcome_text")
    reviews = await db.get_setting("reviews_url")
    support = await db.get_setting("support_username")
    kb = main_menu_kb(reviews, support)
    if edit and hasattr(message, "edit_text"):
        await message.edit_text(welcome, reply_markup=kb)
    else:
        await message.answer(welcome, reply_markup=kb)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await show_main(message, db)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db: Database) -> None:
    await show_main(message, db)


@router.callback_query(F.data == "main")
async def cb_main(callback: CallbackQuery, db: Database) -> None:
    await show_main(callback.message, db, edit=True)
    await callback.answer()


@router.callback_query(F.data == "guarantees")
async def cb_guarantees(callback: CallbackQuery, db: Database) -> None:
    text = await db.get_setting("guarantees_text")
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()


@router.callback_query(F.data == "agreement")
async def cb_agreement(callback: CallbackQuery, db: Database) -> None:
    text = await db.get_setting("agreement_text")
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()


@router.callback_query(F.data == "support")
async def cb_support(callback: CallbackQuery, db: Database) -> None:
    support = await db.get_setting("support_username")
    if support:
        await callback.message.edit_text(
            f"Напишите в поддержку: @{support}",
            reply_markup=back_main_kb(),
        )
    else:
        await callback.message.edit_text(
            "Поддержка не настроена. Обратитесь к администратору.",
            reply_markup=back_main_kb(),
        )
    await callback.answer()


async def _show_catalog(
    callback: CallbackQuery,
    db: Database,
    parent_id: int | None,
    title: str,
) -> None:
    categories = await db.get_children(parent_id)
    if not categories:
        await callback.message.edit_text(
            "Раздел пуст. Загляните позже!",
            reply_markup=back_main_kb(),
        )
        return
    ids = [c["id"] for c in categories]
    leaves = {cid: await db.is_leaf(cid) for cid in ids}
    counts = await db.count_available_map(ids)
    await callback.message.edit_text(
        title,
        reply_markup=catalog_kb(categories, counts, leaves, parent_id=parent_id),
    )


@router.callback_query(F.data == "buy")
async def cb_buy(callback: CallbackQuery, db: Database) -> None:
    root = await db.get_children(None)
    if not root:
        await callback.message.edit_text(
            "Каталог пуст. Загляните позже!",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return
    await _show_catalog(callback, db, None, "📁 <b>Каталог</b>\n\nВыберите категорию:")
    await callback.answer()


@router.callback_query(F.data.startswith("cat_back:"))
async def cb_cat_back(callback: CallbackQuery, db: Database) -> None:
    ref_id = int(callback.data.split(":")[1])
    cat = await db.get_category(ref_id)
    if not cat:
        await callback.answer("Не найдено", show_alert=True)
        return
    list_parent = cat.get("parent_id")
    if list_parent:
        parent_cat = await db.get_category(list_parent)
        title = f"📁 <b>{parent_cat['name']}</b>\n\nВыберите раздел:"
    else:
        title = "📁 <b>Каталог</b>\n\nВыберите категорию:"
    await _show_catalog(callback, db, list_parent, title)
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(callback: CallbackQuery, db: Database) -> None:
    category_id = int(callback.data.split(":")[1])
    cat = await db.get_category(category_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    if not await db.is_leaf(category_id):
        children = await db.get_children(category_id)
        if not children:
            await callback.answer("Раздел пуст", show_alert=True)
            return
        ids = [c["id"] for c in children]
        leaves = {cid: await db.is_leaf(cid) for cid in ids}
        counts = await db.count_available_map(ids)
        path = await db.get_category_path(category_id)
        await callback.message.edit_text(
            f"📁 <b>{path}</b>\n\nВыберите подраздел:",
            reply_markup=catalog_kb(
                children, counts, leaves, parent_id=category_id
            ),
        )
        await callback.answer()
        return

    count = await db.count_available(category_id)
    path = await db.get_category_path(category_id)
    price = cat.get("price") or 0
    price_line = (
        f"💰 Цена: <b>{price:.0f} ₽</b> за канал\n" if price > 0 else ""
    )
    text = (
        f"📦 <b>{path}</b>\n\n"
        f"{cat['description']}\n\n"
        f"{price_line}"
        f"📊 В наличии: <b>{count}</b> шт."
    )
    await callback.message.edit_text(
        text,
        reply_markup=category_detail_kb(category_id, cat.get("parent_id")),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add:"))
async def cb_add_to_cart(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    category_id = int(callback.data.split(":")[1])
    if not await db.is_leaf(category_id):
        await callback.answer("Выберите конечный раздел с товарами", show_alert=True)
        return
    count = await db.count_available(category_id)
    if count == 0:
        await callback.answer("Нет в наличии", show_alert=True)
        return
    await state.set_state(BuyQuantity.waiting_quantity)
    await state.update_data(category_id=category_id)
    await callback.message.answer(
        f"Введите количество каналов (1–{count}):"
    )
    await callback.answer()


@router.message(BuyQuantity.waiting_quantity)
async def process_quantity(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    category_id = data.get("category_id")
    if not category_id:
        await state.clear()
        return
    try:
        qty = int(message.text.strip())
        if qty < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число больше 0:")
        return

    ok, msg = await db.add_to_cart(message.from_user.id, category_id, qty)
    await state.clear()
    if ok:
        cat = await db.get_category(category_id)
        path = await db.get_category_path(category_id)
        total = qty * (cat.get("price") or 0)
        await message.answer(
            f"✅ {msg}\n\n"
            f"<b>{path}</b> x{qty} = {total:.0f} ₽\n\n"
            f"Перейдите в корзину для оплаты.",
            reply_markup=cart_kb(await db.get_cart(message.from_user.id)),
        )
    else:
        await message.answer(f"❌ {msg}")


@router.callback_query(F.data == "cart")
async def cb_cart(callback: CallbackQuery, db: Database) -> None:
    items = await db.get_cart(callback.from_user.id)
    if not items:
        await callback.message.edit_text(
            "🧺 Корзина пуста",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return
    lines = []
    total = 0.0
    cart_items = []
    for item in items:
        subtotal = item["quantity"] * item["price"]
        total += subtotal
        avail = await db.count_available(item["category_id"])
        path = await db.get_category_path(item["category_id"])
        lines.append(
            f"• <b>{path}</b> x{item['quantity']} = {subtotal:.0f} ₽ "
            f"(доступно: {avail})"
        )
        cart_items.append({**item, "path": path})
    text = "🧺 <b>Корзина</b>\n\n" + "\n".join(lines) + f"\n\n💰 <b>Итого: {total:.0f} ₽</b>"
    await callback.message.edit_text(text, reply_markup=cart_kb(cart_items))
    await callback.answer()


@router.callback_query(F.data.startswith("cart_remove:"))
async def cb_cart_remove(callback: CallbackQuery, db: Database) -> None:
    category_id = int(callback.data.split(":")[1])
    await db.remove_from_cart(callback.from_user.id, category_id)
    await cb_cart(callback, db)


@router.callback_query(F.data == "checkout")
async def cb_checkout(callback: CallbackQuery, db: Database) -> None:
    items = await db.get_cart(callback.from_user.id)
    if not items:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    for item in items:
        avail = await db.count_available(item["category_id"])
        if avail < item["quantity"]:
            await callback.answer(
                f"Недостаточно «{item['name']}». Доступно: {avail}",
                show_alert=True,
            )
            return
    total = await db.cart_total(callback.from_user.id)
    await callback.message.edit_text(
        f"💳 <b>Оплата</b>\n\nСумма: <b>{total:.0f} ₽</b>\n\nВыберите способ оплаты:",
        reply_markup=payment_methods_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:yookassa")
async def cb_pay_yookassa(
    callback: CallbackQuery,
    db: Database,
    yookassa: YooKassaPayment,
) -> None:
    if not yookassa.enabled:
        await callback.answer("ЮKassa не настроена", show_alert=True)
        return
    order_id = await _create_order_from_cart(callback, db, "yookassa")
    if not order_id:
        await callback.answer("Не удалось создать заказ", show_alert=True)
        return
    total = (await db.get_order(order_id))["total"]
    result = yookassa.create_payment(total, order_id, f"Заказ #{order_id}")
    if not result:
        await callback.answer("Ошибка создания платежа", show_alert=True)
        return
    payment_id, url = result
    await db.update_order_payment(order_id, payment_id, url)
    await callback.message.edit_text(
        f"💳 <b>Заказ #{order_id}</b>\n\n"
        f"Сумма: <b>{total:.0f} ₽</b>\n\n"
        f"Оплатите по ссылке — товары выдадутся автоматически.\n"
        f"Или нажмите «Проверить оплату», если уже оплатили.",
        reply_markup=payment_order_kb(order_id, payment_url=url, manual_check=False),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:crypto")
async def cb_pay_crypto(callback: CallbackQuery, db: Database) -> None:
    networks = []
    for key, label, setting_key in CRYPTO_NETWORKS:
        addr = await db.get_setting(setting_key)
        if addr.strip():
            networks.append((key, label))
    if not networks:
        await callback.answer(
            "Крипто-оплата не настроена. Обратитесь к администратору.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        "🪙 Выберите сеть для оплаты:",
        reply_markup=crypto_assets_kb(networks),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("crypto:"))
async def cb_crypto_asset(callback: CallbackQuery, db: Database) -> None:
    asset = callback.data.split(":")[1]
    setting_key = next((s for k, _, s in CRYPTO_NETWORKS if k == asset), None)
    if not setting_key:
        await callback.answer("Сеть не найдена", show_alert=True)
        return
    address = await db.get_setting(setting_key)
    if not address.strip():
        await callback.answer("Адрес не настроен", show_alert=True)
        return

    order_id = await _create_order_from_cart(callback, db, "crypto", asset)
    if not order_id:
        await callback.answer("Не удалось создать заказ", show_alert=True)
        return
    order = await db.get_order(order_id)
    label = CRYPTO_LABELS.get(asset, asset)
    await callback.message.edit_text(
        f"🪙 <b>Заказ #{order_id}</b>\n\n"
        f"Сумма: <b>{order['total']:.0f} ₽</b>\n"
        f"Сеть: <b>{label}</b>\n\n"
        f"1. Нажмите «Перейти к оплате» — получите адрес\n"
        f"2. После перевода нажмите «Проверить оплату»",
        reply_markup=payment_order_kb(order_id, is_crypto=True, manual_check=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_go:"))
async def cb_pay_go_crypto(callback: CallbackQuery, db: Database) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["payment_method"] != "crypto":
        await callback.answer("Неверный тип заказа", show_alert=True)
        return
    asset = order.get("crypto_asset", "")
    setting_key = next((s for k, _, s in CRYPTO_NETWORKS if k == asset), None)
    if not setting_key:
        await callback.answer("Сеть не найдена", show_alert=True)
        return
    address = await db.get_setting(setting_key)
    label = CRYPTO_LABELS.get(asset, asset)
    await callback.answer()
    await callback.message.answer(
        f"🪙 <b>Реквизиты для оплаты</b>\n\n"
        f"Заказ: <b>#{order_id}</b>\n"
        f"Сумма: <b>{order['total']:.0f} ₽</b> (эквивалент в {label})\n"
        f"Сеть: <b>{label}</b>\n\n"
        f"Адрес:\n<code>{address}</code>\n\n"
        f"⚠️ Переводите точную сумму. После оплаты нажмите «Проверить оплату».",
        reply_markup=payment_order_kb(order_id, is_crypto=True, manual_check=True),
    )


@router.callback_query(F.data.startswith("check_yoo:"))
async def cb_check_yookassa(
    callback: CallbackQuery, db: Database, yookassa: YooKassaPayment
) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["payment_method"] != "yookassa":
        await callback.answer("Неверный тип заказа", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("Заказ уже оплачен и выдан", show_alert=True)
        return
    if order["status"] == "cancelled":
        await callback.answer("Оплата отменена", show_alert=True)
        return
    ext_id = order.get("external_payment_id")
    if not ext_id or not yookassa.is_paid(ext_id):
        await callback.answer("Оплата пока не поступила. Попробуйте через минуту.", show_alert=True)
        return
    ok = await deliver_order(callback.bot, db, order_id, order["user_id"])
    if ok:
        await callback.message.edit_text(
            f"✅ <b>Заказ #{order_id} оплачен!</b>\n\nДанные отправлены вам в чат.",
            reply_markup=back_main_kb(),
        )
        await callback.answer("Оплата подтверждена!")
    else:
        await callback.answer("Ошибка выдачи. Обратитесь в поддержку.", show_alert=True)


@router.callback_query(F.data.startswith("check_pay:"))
async def cb_check_payment_crypto(callback: CallbackQuery, db: Database) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["payment_method"] != "crypto":
        await callback.answer("Используйте проверку для вашего способа оплаты", show_alert=True)
        return
    if order["status"] == "paid":
        await callback.answer("Заказ уже оплачен и выдан", show_alert=True)
        return
    if order["status"] == "cancelled":
        await callback.answer("Оплата отменена", show_alert=True)
        return
    if order["status"] == "awaiting_confirmation":
        await callback.answer(
            "Заявка уже на проверке. Ожидайте подтверждения администратора.",
            show_alert=True,
        )
        return

    ok = await db.set_order_awaiting_confirmation(order_id)
    if not ok:
        await callback.answer("Не удалось отправить на проверку", show_alert=True)
        return

    await notify_admins_payment_check(callback.bot, ADMIN_IDS, db, order_id)
    await callback.message.edit_text(
        f"🔍 <b>Заказ #{order_id}</b>\n\n"
        f"Заявка отправлена администратору.\n"
        f"Ожидайте подтверждения — данные придут автоматически.",
        reply_markup=back_main_kb(),
    )
    await callback.answer("Отправлено на проверку")


async def _create_order_from_cart(
    callback: CallbackQuery,
    db: Database,
    method: str,
    crypto_asset: str | None = None,
) -> int | None:
    items = await db.get_cart(callback.from_user.id)
    order_items = [
        {
            "category_id": i["category_id"],
            "quantity": i["quantity"],
            "price": i["price"],
        }
        for i in items
    ]
    total = sum(i["quantity"] * i["price"] for i in items)
    return await db.create_order(
        callback.from_user.id,
        order_items,
        total,
        method,
        crypto_asset=crypto_asset,
    )
