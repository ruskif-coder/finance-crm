"""Транспорт к API ОРД МедиаСкаут (httpx).

Стиль — тот же, что у транспорта к Битриксу (`app/sales/bitrix/transport.py`): тонкие
функции, ключ из env, гразбор ошибок в одном месте. Второй стиль под второй внешний
сервис заводить незачем.

Спека: `demo.mediascout.ru/swagger/v3/swagger.json` (52 метода) плюс приращения v3.1
(акты и статистика) и v3.2. Копия лежит фикстурой в `backend/tests/fixtures/`, и на ней
проверяются наши тела запросов — до того, как появится доступ.

КОНТУР. Демо и прод — разные хосты, и они выдают РАЗНЫЕ идентификаторы. Демовский,
записанный рядом с боевыми, снаружи неотличим: сдача отчётности сошлётся на запись,
которой в ЕРИР нет. Поэтому `env()` возвращает контур явно, и всё, что мы сохраняем
после ответа, помечается им.

АВТОРИЗАЦИЯ — HTTP Basic. В описании спеки ошибочно сказано «Bearer», авторитетно поле
`securitySchemes.basic.scheme`.
"""
import base64
import os
from typing import Any, Optional

import httpx

HOSTS = {
    'demo': 'https://demo.mediascout.ru',
    'prod': 'https://lk.mediascout.ru',
}
TIMEOUT = 40                          # регистрация договора отвечает не мгновенно


class OrdNotConfigured(RuntimeError):
    """Учётных данных нет. Отдельный класс: это не поломка, а «ещё не подключено»."""


class OrdError(RuntimeError):
    """Отказ ОРД с разобранным текстом. Несёт http-статус и, если был, разбор по полям."""

    def __init__(self, status: int, message: str, fields: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.fields = fields or {}


def env() -> str:
    """Текущий контур: demo (по умолчанию) или prod.

    По умолчанию демо намеренно: забытая переменная должна отправлять в песочницу,
    а не в ЕРИР. Ошибка настройки не обязана быть необратимой.
    """
    value = (os.getenv("ORD_ENV") or "demo").strip().lower()
    return value if value in HOSTS else 'demo'


def base_url() -> str:
    return HOSTS[env()]


def _credentials() -> tuple[str, str]:
    """Учётные данные — ТОЛЬКО из окружения, без файлового запасного пути.

    Файл внутри живого контейнера в этом проекте уже пробовали: ключ Битрикса лежал
    в `/app/vibecode.key`, клался через `docker cp` и терялся при каждой пересборке
    и `up --force-recreate` (см. комментарий в docker-compose.yml). Переменная
    переживает пересоздание, файл — нет, и пропажу замечают не сразу.
    """
    login = (os.getenv("ORD_LOGIN") or "").strip()
    password = (os.getenv("ORD_PASSWORD") or "").strip()
    if not (login and password):
        raise OrdNotConfigured(
            "Доступ к ОРД не настроен: нужны ORD_LOGIN и ORD_PASSWORD в .env, "
            f"и они должны быть перечислены в environment бэкенда. Контур — {env()}.")
    return login, password


def is_configured() -> bool:
    """Есть ли доступ. Экран спрашивает это, чтобы не предлагать кнопку в пустоту."""
    try:
        _credentials()
        return True
    except OrdNotConfigured:
        return False


def _auth_header() -> str:
    login, password = _credentials()
    raw = f"{login}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _explain(response: httpx.Response) -> OrdError:
    """Отказ ОРД — в человеческий текст.

    400 приходит как ValidationProblemDetails: `errors` это словарь «поле → список
    сообщений». Без разбора наружу вылезал бы сырой JSON, а поле, из-за которого
    отказали, — единственное, что нужно человеку, чтобы починить.
    """
    fields: dict = {}
    message = f"ОРД ответил {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        fields = body.get("errors") or {}
        title = body.get("title") or body.get("detail")
        if fields:
            parts = [f"{k}: {'; '.join(v) if isinstance(v, list) else v}"
                     for k, v in fields.items()]
            message = "ОРД отклонил запрос — " + "; ".join(parts)
        elif title:
            message = f"ОРД ответил {response.status_code}: {title}"
    if response.status_code == 401:
        message = "ОРД не принял учётные данные (401). Проверьте ORD_LOGIN/ORD_PASSWORD."
    if response.status_code == 403:
        message = "ОРД отказал в доступе (403) — у учётной записи нет прав на эту операцию."
    return OrdError(response.status_code, message, fields)


def request(method: str, path: str, *, json: Any = None,
            params: Optional[dict] = None) -> tuple[int, Any]:
    """Один запрос к ОРД. Возвращает (http-статус, разобранное тело).

    Ошибки поднимаются как `OrdError` — кроме сетевых, они выходят как есть: обрыв
    связи это НЕ отказ ОРД, и путать их нельзя. Незавершённая попытка в журнале
    отправок остаётся именно после сетевого обрыва, и её нельзя молча считать неудачей:
    запись в ЕРИР могла создаться.
    """
    if not path.startswith("/"):
        path = "/" + path
    response = httpx.request(
        method.upper(), base_url() + path,
        headers={"Authorization": _auth_header(), "Accept": "application/json"},
        json=json, params=params, timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        raise _explain(response)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def get(path: str, params: Optional[dict] = None) -> Any:
    return request("GET", path, params=params)[1]


def post(path: str, body: Any) -> tuple[int, Any]:
    return request("POST", path, json=body)
