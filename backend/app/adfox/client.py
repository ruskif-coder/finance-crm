# -*- coding: utf-8 -*-
"""Клиент API Adfox. Авторизация — OAuth-токен Яндекса с правом adfox:api (`ADFOX_OAUTH_TOKEN`, владелец кладёт в .env сам).

Статистика — API v2 (живой замер 11.11.2026; старые `/api/report/<уровень>` отвечают 404 на всё):
`GET /api/v2/reports/list?level=` — готовые отчёты учётки; `POST /api/v2/reports/<имя>` с телом
`{"level": …, "dateRange": {"from", "to"}}` → `taskId`; `GET /api/v2/reports/<taskId>` до `status=SUCCESS`;
`GET /api/v2/reports/<taskId>/result` → `columns` + `rows`. Настраиваемые отчёты (`POST /api/v2/reports` с metrics) учётке
недоступны — `/metadata` пустой. Документация: yandex.ru/dev/adfox/doc/ru/rest-statistics.

Заведение (позже) — API v1 `https://adfox.yandex.ru/api/v1?object=…&action=…`, ответ XML (список кампаний учётке виден)."""
import os
import time
from typing import List, Optional

import httpx

BASE = "https://adfox.yandex.ru/api/v2/reports"
POLL_EVERY, POLL_MAX = 2.0, 120          # секунды; отчёт за сутки строится за секунды


class AdfoxError(Exception):
    """Отказ API или сети — текст для человека и журнала."""


def configured() -> bool:
    return bool((os.getenv("ADFOX_OAUTH_TOKEN") or "").strip())


class AdfoxClient:
    def __init__(self, token: Optional[str] = None, http: Optional[httpx.Client] = None):
        self.token = (token or os.getenv("ADFOX_OAUTH_TOKEN") or "").strip()
        if not self.token:
            raise AdfoxError("Токен Adfox не задан (ADFOX_OAUTH_TOKEN) — забор через API выключен")
        self.http = http or httpx.Client(timeout=30.0)

    def _call(self, method: str, path: str, **kw) -> dict:
        try:
            r = self.http.request(method, f"{BASE}{path}", headers={"Authorization": f"OAuth {self.token}"}, **kw)
        except httpx.HTTPError as e:
            raise AdfoxError(f"Adfox не ответил: {e.__class__.__name__}")
        if r.status_code in (401, 403):
            raise AdfoxError(f"Adfox отказал в доступе ({r.status_code}): токен неверный или у учётки нет доступа к отчётам")
        try:
            body = r.json()
        except ValueError:
            raise AdfoxError(f"Adfox вернул {r.status_code} не JSON")
        if not isinstance(body, dict):
            raise AdfoxError(f"Adfox вернул {r.status_code} не объект JSON")
        if r.status_code >= 400 or body.get("error"):
            err = body.get("error")
            msg = err.get("message") if isinstance(err, dict) else err
            raise AdfoxError(f"Adfox вернул {r.status_code}: {msg}")
        return body.get("result") or {}

    def reports(self, level: str = "owner") -> List[str]:
        return [x["reportName"] for x in self._call("GET", "/list", params={"level": level}).get("reports", [])]

    def report_v2(self, name: str, level: str, date_from: str, date_to: str, sleep=time.sleep) -> List[dict]:
        """Готовый отчёт целиком строками-словарями по `columns`. Ждёт не дольше POLL_MAX секунд."""
        task = self._call("POST", f"/{name}", json={"level": level, "dateRange": {"from": date_from, "to": date_to}}).get("taskId")
        if not task:
            raise AdfoxError("Adfox не выдал taskId отчёта")
        waited = 0.0
        while True:
            st = self._call("GET", f"/{task}").get("status")
            if st == "SUCCESS":
                break
            if st in ("FAILURE", "EXPIRED"):
                raise AdfoxError(f"Отчёт Adfox не построен: {st}")
            if waited >= POLL_MAX:
                raise AdfoxError("Отчёт Adfox не готов за две минуты")
            sleep(POLL_EVERY)
            waited += POLL_EVERY
        res = self._call("GET", f"/{task}/result")
        cols = [c["name"] for c in res.get("columns", [])]
        return [dict(zip(cols, row)) for row in res.get("rows", [])]
