from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database import Database
from services.encryption import DataEncryptor
from services.yookassa_pay import YooKassaPayment


class DependenciesMiddleware(BaseMiddleware):
    def __init__(
        self, db: Database, yookassa: YooKassaPayment, encryptor: DataEncryptor
    ):
        self.db = db
        self.yookassa = yookassa
        self.encryptor = encryptor

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["yookassa"] = self.yookassa
        data["encryptor"] = self.encryptor
        return await handler(event, data)
