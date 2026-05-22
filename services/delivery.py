from aiogram import Bot

from config import DELIVERY_INSTRUCTION
from database.db import Database
from keyboards.inline import admin_payment_kb


async def deliver_order(bot: Bot, db: Database, order_id: int, user_id: int) -> bool:
    products = await db.fulfill_order(order_id)
    if not products:
        return False

    await db.clear_cart(user_id)

    header = f"✅ <b>Заказ #{order_id} оплачен!</b>\n\nВаши каналы:\n\n"
    chunks: list[str] = []
    current = header
    for i, product in enumerate(products, 1):
        block = db.format_product_delivery(product, i) + "\n"
        if len(current) + len(block) > 4000:
            chunks.append(current)
            current = block
        else:
            current += block
    chunks.append(current)
    instruction = await db.get_setting("delivery_instruction_text")
    if not instruction:
        instruction = DELIVERY_INSTRUCTION
    chunks.append(instruction)

    from keyboards.reply import main_reply_kb

    for i, text in enumerate(chunks):
        kwargs = {}
        if i == len(chunks) - 1:
            kwargs["reply_markup"] = main_reply_kb()
        await bot.send_message(user_id, text, **kwargs)

    return True


async def notify_admins_payment_check(
    bot: Bot, admin_ids: list[int], db: Database, order_id: int
) -> None:
    text = (
        "🔔 <b>Проверка оплаты</b>\n\n"
        + await db.format_order_summary(order_id)
        + "\n\nПодтвердите или отмените заказ:"
    )
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                admin_id, text, reply_markup=admin_payment_kb(order_id)
            )
        except Exception:
            pass
