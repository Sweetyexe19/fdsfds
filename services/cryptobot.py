import aiohttp

from config import CRYPTOBOT_API, CRYPTOBOT_TOKEN


class CryptoBotPayment:
    ASSET_MAP = {
        "USDT": "USDT",
        "USDT_BEP20": "USDT",
        "TON": "TON",
    }

    def __init__(self, token: str = CRYPTOBOT_TOKEN):
        self.token = token
        self.enabled = bool(token)
        self._headers = {"Crypto-Pay-API-Token": token}

    async def _request(
        self, method: str, params: dict | None = None, http_method: str = "GET"
    ) -> dict | None:
        if not self.enabled:
            return None
        url = f"{CRYPTOBOT_API}/{method}"
        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": self._headers}
            if http_method == "POST":
                kwargs["json"] = params or {}
                req = session.post(url, **kwargs)
            else:
                kwargs["params"] = params or {}
                req = session.get(url, **kwargs)
            async with req as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data.get("result")
                return None

    async def create_invoice(
        self, amount_rub: float, asset: str, order_id: int, description: str
    ) -> tuple[int, str] | None:
        crypto_asset = self.ASSET_MAP.get(asset, asset)
        params = {
            "currency_type": "fiat",
            "fiat": "RUB",
            "amount": str(round(amount_rub, 2)),
            "accepted_assets": crypto_asset,
            "description": description,
            "payload": str(order_id),
            "expires_in": 1800,
        }
        result = await self._request("createInvoice", params)
        if not result:
            return None
        return result["invoice_id"], result.get("pay_url", result.get("bot_invoice_url", ""))

    async def is_paid(self, invoice_id: int) -> bool:
        result = await self._request("getInvoices", {"invoice_ids": str(invoice_id)})
        if not result or not result.get("items"):
            return False
        return result["items"][0].get("status") == "paid"
