import uuid

from yookassa import Configuration, Payment


class YooKassaPayment:
    def __init__(self, shop_id: str, secret_key: str):
        self.enabled = bool(shop_id and secret_key)
        if self.enabled:
            Configuration.account_id = shop_id
            Configuration.secret_key = secret_key

    def create_payment(
        self, amount: float, order_id: int, description: str
    ) -> tuple[str, str] | None:
        if not self.enabled:
            return None
        payment = Payment.create(
            {
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/",
                },
                "capture": True,
                "description": description,
                "metadata": {"order_id": str(order_id)},
            },
            uuid.uuid4(),
        )
        return payment.id, payment.confirmation.confirmation_url

    def is_paid(self, payment_id: str) -> bool:
        if not self.enabled:
            return False
        payment = Payment.find_one(payment_id)
        return payment.status == "succeeded"
