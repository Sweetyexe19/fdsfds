import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from database.db import Database

PRODUCT_FIELDS = (
    "login",
    "password",
    "backup_email",
    "backup_password",
    "twofa_key",
    "channel_link",
)


class DataEncryptor:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._fernet: Fernet | None = None

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def _token_fernet(self) -> Fernet:
        digest = hashlib.sha256(self.bot_token.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _derive_key(self, seed: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        return base64.urlsafe_b64encode(kdf.derive(seed.encode("utf-8")))

    def _fernet_from_seed(self, seed: str, salt: bytes) -> Fernet:
        return Fernet(self._derive_key(seed, salt))

    def _wrap_key(self, key: bytes) -> str:
        return self._token_fernet().encrypt(key).decode("ascii")

    def _unwrap_key(self, wrapped: str) -> bytes:
        return self._token_fernet().decrypt(wrapped.encode("ascii"))

    async def load_from_db(self, db: Database) -> bool:
        wrapped = await db.get_setting("encryption_key_wrapped")
        if not wrapped:
            self._fernet = None
            return False
        try:
            self._fernet = Fernet(self._unwrap_key(wrapped))
            return True
        except Exception:
            self._fernet = None
            return False

    async def setup_seed(self, db: Database, seed: str) -> int:
        seed = seed.strip()
        if len(seed) < 8:
            raise ValueError("Seed-фраза должна быть не короче 8 символов")

        old_fernet = self._fernet
        salt = os.urandom(16)
        key_bytes = self._derive_key(seed, salt)
        new_fernet = Fernet(key_bytes)

        products = await db.get_all_products_raw()
        for product in products:
            decrypted = self.decrypt_product(product, fernet=old_fernet)
            encrypted = self.encrypt_product(decrypted, fernet=new_fernet)
            await db.update_product_fields(product["id"], encrypted)

        await db.set_setting("encryption_salt", salt.hex())
        await db.set_setting("encryption_key_wrapped", self._wrap_key(key_bytes))
        await db.set_setting("encryption_enabled", "1")
        self._fernet = new_fernet
        return len(products)

    def encrypt(self, value: str, fernet: Fernet | None = None) -> str:
        f = fernet or self._fernet
        if not f or not value:
            return value
        return f.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str, fernet: Fernet | None = None) -> str:
        f = fernet or self._fernet
        if not value:
            return value
        if not f:
            return value
        if not value.startswith("gAAAA"):
            return value
        try:
            return f.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return value

    def encrypt_product(self, product: dict, fernet: Fernet | None = None) -> dict:
        result = dict(product)
        for field in PRODUCT_FIELDS:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]), fernet=fernet)
        return result

    def decrypt_product(self, product: dict, fernet: Fernet | None = None) -> dict:
        result = dict(product)
        for field in PRODUCT_FIELDS:
            if field in result and result[field]:
                result[field] = self.decrypt(str(result[field]), fernet=fernet)
        return result
