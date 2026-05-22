from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

BTN_BUY = "🛒 Купить канал"
BTN_REVIEWS = "⭐ Отзывы"
BTN_CART = "🧺 Корзина"
BTN_SUPPORT = "💬 Поддержка"
BTN_GUARANTEES = "🛡 Гарантии"
BTN_AGREEMENT = "📜 Соглашение"

MENU_BUTTONS = frozenset(
    {
        BTN_BUY,
        BTN_REVIEWS,
        BTN_CART,
        BTN_SUPPORT,
        BTN_GUARANTEES,
        BTN_AGREEMENT,
    }
)


def main_reply_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_BUY))
    builder.row(KeyboardButton(text=BTN_REVIEWS))
    builder.row(KeyboardButton(text=BTN_CART), KeyboardButton(text=BTN_SUPPORT))
    builder.row(KeyboardButton(text=BTN_GUARANTEES), KeyboardButton(text=BTN_AGREEMENT))
    return builder.as_markup(resize_keyboard=True)
