import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import Database
from handlers import setup_routers
from middlewares import DependenciesMiddleware
from payment_checker import payment_checker_loop
from services.yookassa_pay import YooKassaPayment

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("Укажите BOT_TOKEN в .env")
        sys.exit(1)

    db = Database()
    await db.connect()

    yookassa = YooKassaPayment(
        __import__("config").YOOKASSA_SHOP_ID,
        __import__("config").YOOKASSA_SECRET_KEY,
    )

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.message.middleware(DependenciesMiddleware(db, yookassa))
    dp.callback_query.middleware(DependenciesMiddleware(db, yookassa))
    dp.include_router(setup_routers())

    checker_task = asyncio.create_task(payment_checker_loop(bot, db, yookassa))

    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        checker_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
