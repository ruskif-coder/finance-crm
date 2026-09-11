# -*- coding: utf-8 -*-
"""Клиент WCM (Weborama). Свой, а не метод в существующем — и вот почему.

У DSP весь транспорт — JSON-RPC, и подменный транспорт в тестах описывает ВСЁ общение с
ним. Здесь общение другое: form-urlencoded тела, два обязательных заголовка и JWT, который
надо получать отдельным вызовом. Подмешать это к тому клиенту значило бы, что ни один из
двух больше не описывает свой обмен целиком.

Устройство повторяет то, что уже проверено на ОРД и DSP: транспорт подменяемый (тесты без
сети), ошибки — своим типом, а не голым HTTP, идентификаторы вытаскиваются защитно.

ЧЕГО ЗДЕСЬ НЕТ НАМЕРЕННО. Журнала отправок: он в этом проекте — таблица, а схему
согласуют до кода. Место под него оставлено параметром `journal`, и когда таблица
появится, писаться будет ОТСЮДА, а не из вызывающего кода — иначе часть вызовов в журнал
не попадёт, как это уже было с загрузкой архива в DSP (09.09.2026).
"""
import logging
import os
from typing import Any, Callable, Optional

import httpx

from app.weborama import enums

log = logging.getLogger("finance.weborama")

ENV_URL = "WEBORAMA_API_URL"
ENV_EMAIL = "WEBORAMA_EMAIL"
ENV_PASSWORD = "WEBORAMA_PASSWORD"

DEFAULT_URL = "https://api-wcm-ru.weborama.io"

AUTH_PATH = "/advertiser/advertiser_users/jwt_token/json"

# Ключи, под которыми в ответе может лежать идентификатор созданного объекта.
#
# Урок того же дня: у DSP `Campaign.add` отдаёт хеш строкой, а `Creative.add` — объектом
# с ключом `id`, и разбор, ждавший одного `xxhash`, считал успешный вызов неудачей — при
# том что объект в чужой системе уже создан. Здесь заранее смотрим шире и, не найдя id,
# говорим ЧТО пришло, а не «не получилось».
ID_KEYS = ("id", "project_id", "campaign_id", "ad_network_id", "insertion_id")

# ⚠ `format` — это РАСШИРЕНИЕ ПУТИ (`/advertiser/ad_spaces.:format` → `.json`), а НЕ
# параметр запроса. В их доке он записан в таблице «Mandatory Parameters» рядом с
# обычными полями, и это сбивает. Первый же живой вызов 09.09.2026 вернул 500 с
# `Unknown column 'format' in 'where clause'`: они приняли его за фильтр по колонке
# и упали в SQL. Ни в один query-string его класть нельзя.

# Под какими ключами приходит сам JWT. В доке тело ответа не приведено вовсе.
TOKEN_KEYS = ("jwt_token", "token", "jwt", "auth_token", "access_token")


class WcmError(RuntimeError):
    """Ошибка обмена с WCM: отказ, неожиданный формат, сеть."""


class WcmAuthError(WcmError):
    """Отдельно от прочих: только на неё разрешён один автоматический повтор."""


# Сколько тела отказа показывать. 300 символов не хватало: на 406 они возвращают ВЕСЬ
# объект с умолчаниями (`is_visible_in_wam`, `postview_tracking_days`, …), и настоящая
# причина оказывается за обрезом. Та же ошибка, что была с загрузчиком архива в DSP:
# сообщение о неудаче не должно прятать её причину.
REFUSAL_CHARS = 1500

# Ключи, под которыми в их отказе может лежать человеческое объяснение.
_MSG_KEYS = ("message", "error_message", "description", "detail", "reason", "errors")


def _refusal(body: str) -> str:
    """Текст отказа: сначала ищем объяснение, потом уже показываем тело.

    Их 406 отдаёт не сообщение, а echo объекта — тогда полезно то, ЧТО они поняли из
    наших полей, поэтому тело всё равно показываем, просто целиком, а не первые 300.
    """
    import json as _json
    s = (body or "").strip()
    try:
        doc = _json.loads(s)
    except ValueError:
        return s[:REFUSAL_CHARS]
    err = doc.get("error") if isinstance(doc, dict) else None
    for src in (err, doc):
        if isinstance(src, dict):
            for k in _MSG_KEYS:
                v = src.get(k)
                if isinstance(v, str) and v.strip():
                    return f"{v.strip()} | тело: {s[:REFUSAL_CHARS]}"
    return s[:REFUSAL_CHARS]


def _dig(data: Any, keys) -> Optional[str]:
    """Найти первое значение по одному из ключей — в объекте или в его единственной
    вложенной ветке (`{"project": {"id": 7}}` встречается у половины подобных API)."""
    if isinstance(data, (str, int)) and str(data).strip():
        return str(data).strip()
    if not isinstance(data, dict):
        return None
    for k in keys:
        v = data.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    for v in data.values():
        if isinstance(v, dict):
            found = _dig(v, keys)
            if found:
                return found
    return None


class WcmClient:
    """Один экземпляр = один аккаунт WCM.

    `account_id` не имеет умолчания из окружения намеренно. Аккаунты Weborama выдаёт
    списком и закрепляет за клиентами: перепутать аккаунт значит записать кампанию одного
    рекламодателя в измерения другого. Такое не должно зависеть от того, что лежит в
    переменной среды в момент вызова.
    """

    def __init__(self, account_id, *, url: Optional[str] = None,
                 email: Optional[str] = None, password: Optional[str] = None,
                 transport: Optional[Callable] = None,
                 journal: Optional[Callable] = None,
                 timeout: float = 30.0):
        if not str(account_id or "").strip():
            raise WcmError("Не задан account_id: у Weborama он адресует весь обмен")
        self.account_id = str(account_id).strip()
        self.url = (url or os.getenv(ENV_URL) or DEFAULT_URL).rstrip("/")
        self.email = email or os.getenv(ENV_EMAIL)
        self.password = password or os.getenv(ENV_PASSWORD)
        self.timeout = timeout
        self._transport = transport      # (method, path, params, data) -> ответ
        self._journal = journal          # место под журнал попыток, см. шапку модуля
        self._token: Optional[str] = None

    # ── авторизация ──────────────────────────────────────────────────────────
    def login(self) -> str:
        """Получить JWT. Пароль в журнал и в логи не попадает никогда."""
        if not self.email or not self.password:
            raise WcmAuthError(
                f"Weborama не настроена: нет {ENV_EMAIL} или {ENV_PASSWORD}. "
                f"Значения кладёт владелец в .env — из переписки они не переносятся")
        raw = self._send("POST", AUTH_PATH, files={"email": (None, self.email),
                                                   "password": (None, self.password)},
                         with_auth=False)
        token = _dig(raw, TOKEN_KEYS)
        if not token:
            raise WcmAuthError(f"В ответе авторизации нет токена: {str(raw)[:200]}")
        self._token = token
        return token

    def _headers(self) -> dict:
        """Два заголовка на КАЖДЫЙ вызов. Забыть второй — работать не в том аккаунте."""
        return {"X-Weborama-JWTUserAuthToken": self._token or "",
                "X-Weborama-Account_id": self.account_id}

    # ── транспорт ────────────────────────────────────────────────────────────
    def _send(self, method: str, path: str, *, params: Optional[dict] = None,
              data: Optional[dict] = None, files: Optional[dict] = None,
              with_auth: bool = True) -> Any:
        if self._transport is not None:
            return self._transport(method, path, params or {}, data or files or {})
        headers = self._headers() if with_auth else {}
        try:
            r = httpx.request(method, self.url + path, params=params, data=data,
                              files=files, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise WcmError(f"Weborama недоступна: {e!r}") from e
        if r.status_code in (401, 403):
            raise WcmAuthError(f"Weborama отказала в доступе ({r.status_code})")
        if r.status_code >= 400:
            raise WcmError(f"Weborama ответила {r.status_code}: {_refusal(r.text)}")
        try:
            return r.json()
        except ValueError:
            return r.text

    def call(self, method: str, path: str, *, params: Optional[dict] = None,
             data: Optional[dict] = None) -> Any:
        """Вызов с автоматическим логином и ОДНИМ повтором — только на отказ в доступе.

        Повторяем именно и только `WcmAuthError`, потому что это единственный случай, про
        который точно известно: запрос НЕ обработан. Повторять по таймауту нельзя —
        создающий вызов мог пройти, и повтор завёл бы второй проект или вторую вставку.
        Та же логика, что у журнала ОРД: неизвестный исход не повторяют молча.
        """
        params = dict(params or {})
        data = dict(data or {})
        # account_id дублируется в теле/параметрах вдобавок к заголовку — так в их доке.
        (data if method.upper() == "POST" and not params else params)["account_id"] = self.account_id

        if not self._token:
            self.login()
        try:
            return self._send(method, path, params=params, data=data)
        except WcmAuthError:
            log.info("Weborama: токен не принят, повторный вход")
            self._token = None
            self.login()
            return self._send(method, path, params=params, data=data)

    # ── структура ────────────────────────────────────────────────────────────
    def create_project(self, label: str) -> str:
        """Проект. У Weborama проекты делят по брендам — их же формулировка."""
        return self._created(self.call("POST", "/advertiser/projects.json",
                                       data={"label": label}), "проект")

    def create_campaign(self, project_id, label: str, landing_url: str,
                        channel_id: int = enums.DEFAULT_CHANNEL) -> str:
        return self._created(self.call(
            "POST", "/advertiser/campaigns.json",
            data={"project_id": project_id, "label": label,
                  "landing_url": landing_url, "channel_id": int(channel_id)}), "кампанию")

    def create_ad_network(self, label: str) -> str:
        """Рекламная сеть — площадка или DSP."""
        return self._created(self.call("POST", "/advertiser/ad_networks.json",
                                       data={"label": label}), "сеть")

    def create_insertion(self, campaign_id, ad_network_id, ad_space_id, label: str,
                         delivery_format_id: int = enums.DEFAULT_DELIVERY_FORMAT) -> str:
        """Вставка (флайт). На ней и живёт тег.

        `ad_space_id` обязателен, а метода его создания в доке НЕТ — только чтение. Пока
        владелец не получил ответ менеджера, откуда он берётся, эта ступень не проверена
        живьём ни разу.
        """
        return self._created(self.call(
            "POST", "/advertiser/insertions/placements/json",
            data={"campaign_id": campaign_id, "ad_network_id": ad_network_id,
                  "ad_space_id": ad_space_id, "label": label,
                  "delivery_format_id": int(delivery_format_id)}), "вставку")

    def insertion_tag(self, insertion_id) -> Any:
        """Тот самый тег. Ответ отдаём как есть: его форма в доке не приведена, а
        пересказывать неизвестное — способ потерять половину."""
        return self.call("GET", f"/advertiser/insertions/{insertion_id}/tags.json")

    def ad_spaces_all(self, page: int = 500, cap: int = 5000) -> list:
        """ВСЕ ad_space аккаунта, страницами.

        Ответ постраничный: `items_per_page` по умолчанию **50**, а всего их 1080 (замер
        09.09.2026). Взять первую страницу и решить, что это весь каталог, — самая дешёвая
        и самая тихая ошибка здесь.
        """
        from app.weborama.matching import _rows, total_result
        out, off = [], 0
        while len(out) < cap:
            payload = self.call("GET", "/advertiser/ad_spaces.json",
                                params={"list_limit": page, "list_offset": off})
            got = _rows(payload)
            out += got
            off += len(got)
            total = total_result(payload)
            if not got or (total is not None and off >= total):
                break
        return out

    def ad_spaces(self) -> Any:
        """Весь список ad_space аккаунта.

        Метода СОЗДАНИЯ ad_space у них нет — это выяснилось 09.09.2026 и обрывало цепочку
        на предпоследнем шаге. Ответ Weborama: пул заводится на их стороне, а нам доступен
        этот список (`/advertiser/ad_spaces.:format`). Значит наша задача не «создать», а
        «выбрать правильный» — см. `matching.match_ad_space`.
        """
        return self.call("GET", "/advertiser/ad_spaces.json", params={"format": "json"})

    def ad_space_insertions(self, ad_space_id) -> Any:
        return self.call("GET", f"/advertiser/ad_spaces/{ad_space_id}/insertions.json")

    def create_conversion_page(self, label: str) -> str:
        return self._created(self.call("POST", "/advertiser/conversion_pages.json",
                                       data={"label": label}), "конверсионный тег")

    # ── отдача ───────────────────────────────────────────────────────────────
    def statistics(self, dimensions, metrics, **opts) -> Any:
        """Статистика верификатора. ВАЖНО помнить при сверке: её цифры не обязаны
        совпадать с нашими от DSP — тот считает отданное, верификатор засчитанное."""
        import json as _json
        params = {"dimensions": _json.dumps(list(dimensions)),
                  "metrics": _json.dumps(list(metrics))}
        for k, v in opts.items():
            params[k] = _json.dumps(v) if isinstance(v, (list, dict)) else v
        return self.call("GET", "/advertiser/statistics.json", params=params)

    def datamining_files(self, month: Optional[str] = None, **opts) -> Any:
        params = {}
        if month:
            params["month"] = month
        params.update(opts)
        return self.call("GET", "/advertiser/datamining_files.json", params=params)

    def datamining_file(self, file_id) -> Any:
        return self.call("GET", f"/advertiser/datamining_files/{file_id}.json")

    # ── общее ────────────────────────────────────────────────────────────────
    def _created(self, result: Any, what: str) -> str:
        wid = _dig(result, ID_KEYS)
        if not wid:
            raise WcmError(f"Weborama не вернула id на «{what}»: {str(result)[:300]}")
        return wid


__all__ = ["WcmClient", "WcmError", "WcmAuthError", "DEFAULT_URL",
           "ENV_URL", "ENV_EMAIL", "ENV_PASSWORD"]
