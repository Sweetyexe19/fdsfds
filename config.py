import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

REVIEWS_URL = os.getenv("REVIEWS_URL", "https://t.me/")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").lstrip("@")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")

CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "")
CRYPTOBOT_TESTNET = os.getenv("CRYPTOBOT_TESTNET", "false").lower() == "true"
CRYPTOBOT_API = (
    "https://testnet-pay.crypt.bot/api"
    if CRYPTOBOT_TESTNET
    else "https://pay.crypt.bot/api"
)

DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/shop.db")
SOLD_EXPORT_DIR = BASE_DIR / os.getenv("SOLD_EXPORT_DIR", "data/sold")

WELCOME_TEXT = os.getenv(
    "WELCOME_TEXT",
    "Добро пожаловать в магазин YouTube-каналов!\n\n"
    "Здесь вы можете приобрести готовые каналы с полным доступом.",
)

DELIVERY_INSTRUCTION = (
    "📋 <b>Инструкция после покупки:</b>\n\n"
    "1. Смените пароль от аккаунта Google\n"
    "2. Смените пароль резервной почты\n"
    "3. Привяжите свой номер телефона\n"
    "4. Удалите старые сессии в настройках Google\n"
    "5. Настройте 2FA через Google Authenticator (ключ указан выше)\n"
    "6. Проверьте доступ к каналу по ссылке\n\n"
    "⚠️ Сохраните все данные в надёжном месте."
)

PAYMENT_CHECK_INTERVAL = 15
RESERVE_MINUTES = 30
