from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database import Database
from services.yookassa_pay import YooKassaPayment


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, db: Database, yookassa: YooKassaPayment):
        self.db = db
        self.yookassa = yookassa

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["yookassa"] = self.yookassa
        return await handler(event, data)
