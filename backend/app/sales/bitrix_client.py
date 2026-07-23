"""
Клиент Битрикс24 через классический REST вебхук портала.

Вебхук уже содержит токен в URL, поэтому отдельная авторизация не нужна:
BITRIX_WEBHOOK_URL хранится в .env и никогда не логируется целиком.

Портал отдаёт списки постранично (обычно по 50) и возвращает смещение
следующей страницы в поле "next". Ошибку он сообщает кодом 200 с полем
"error" в теле — HTTP-статус при этом успешный, поэтому проверяется тело,
а не только raise_for_status.
"""
import hashlib
import json
import os
import httpx

_PAGE_GUARD = 10_000  # предохранитель от бесконечной пагинации при сбое портала


def payload_hash(payload: dict) -> str:
    """Стабильный хеш полезной нагрузки.

    На нём держится append-only слой сырья: новая версия пишется, только когда
    хеш изменился. Порядок ключей на результат не влияет — иначе каждая
    синхронизация плодила бы версии на ровном месте."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BitrixClient:
    def __init__(self, webhook_url: str, client: httpx.Client | None = None, timeout: float = 30.0):
        if not webhook_url:
            raise RuntimeError("BITRIX_WEBHOOK_URL не задан — проверьте .env")
        self.webhook_url = webhook_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    @classmethod
    def from_env(cls) -> "BitrixClient":
        return cls(os.getenv("BITRIX_WEBHOOK_URL", ""))

    def list_entities(self, method: str, params: dict | None = None) -> list[dict]:
        """Забирает все страницы метода-списка. Возвращает плоский список записей."""
        items: list[dict] = []
        start = 0
        params = dict(params or {})

        while True:
            request_params = dict(params)
            request_params["start"] = start

            response = self._client.get(f"{self.webhook_url}/{method}", params=request_params)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                description = data.get("error_description") or data.get("error")
                raise RuntimeError(f"Битрикс24 вернул ошибку по методу {method}: {description}")

            items.extend(data.get("result") or [])

            next_start = data.get("next")
            if next_start is None or len(items) > _PAGE_GUARD:
                return items
            start = int(next_start)
