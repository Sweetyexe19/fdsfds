from aiogram import Router

from handlers.admin import router as admin_router
from handlers.user import router as user_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(admin_router)
    root.include_router(user_router)
    return root
