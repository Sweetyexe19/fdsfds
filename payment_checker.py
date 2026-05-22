import asyncio
import logging

from aiogram import Bot

from config import PAYMENT_CHECK_INTERVAL
from database import Database
from services.delivery import deliver_order
from services.yookassa_pay import YooKassaPayment

logger = logging.getLogger(__name__)


async def payment_checker_loop(
    bot: Bot, db: Database, yookassa: YooKassaPayment
) -> None:
    while True:
        try:
            cancelled = await db.cancel_expired_orders()
            for order_id in cancelled:
                order = await db.get_order(order_id)
                if order:
                    try:
                        await bot.send_message(
                            order["user_id"],
                            f"⏱ Заказ #{order_id} отменён — истекло время резерва.",
                        )
                    except Exception:
                        pass

            if yookassa.enabled:
                orders = await db.get_pending_orders()
                for order in orders:
                    if order["payment_method"] != "yookassa":
                        continue
                    if order["status"] != "pending":
                        continue
                    ext_id = order.get("external_payment_id")
                    if not ext_id:
                        continue
                    if yookassa.is_paid(ext_id):
                        ok = await deliver_order(bot, db, order["id"], order["user_id"])
                        if ok:
                            logger.info("YooKassa order %s auto-delivered", order["id"])
        except Exception:
            logger.exception("Payment checker error")
        await asyncio.sleep(PAYMENT_CHECK_INTERVAL)
