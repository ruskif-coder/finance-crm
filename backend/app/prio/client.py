# -*- coding: utf-8 -*-
"""Клиент API системы приоритезации (pp.simbad.pro; дока владельца «API приоритизация.docx», 19.10.2026).

Bearer-токен — `PRIO_API_TOKEN` в `.env` (кладёт владелец, в код и переписку не переносится); адрес — `PRIO_API_URL`.
Методы: `POST /api/campaigns` (заведение → camp_id + ссылки трекера), `PUT /api/campaigns/:id` (любое подмножество полей),
`GET /api/campaigns` (список/одна РК, фильтры camp_id / toggle_on / date_start+date_end), `GET /api/stats-all-summary`
(разбивка по camp_id; сутки при date_start = date_end; даты МСК). Ответ всегда {"ok": bool, ...}; `ok: false` — ошибка."""
import os
from typing import Any, Optional

import httpx

DEFAULT_URL = "https://pp.simbad.pro"
TIMEOUT = 30


class PrioApiError(RuntimeError):
    pass


class PrioClient:
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        self.token = token if token is not None else os.getenv("PRIO_API_TOKEN")
        self.base = (base_url or os.getenv("PRIO_API_URL") or DEFAULT_URL).rstrip("/")
        if not self.token:
            raise PrioApiError("PRIO_API_TOKEN не задан — токен системы приоритезации кладётся в .env")

    def _call(self, method: str, path: str, *, params: Optional[dict] = None, json: Optional[dict] = None) -> Any:
        from app import external_writes as EW
        if method != "GET" and not EW.allowed():
            raise PrioApiError(f"{method} {path}: {EW.REFUSAL}")
        try:
            r = httpx.request(method, self.base + path, params=params, json=json, timeout=TIMEOUT,
                              headers={"Authorization": f"Bearer {self.token}"})
        except httpx.HTTPError as e:
            raise PrioApiError(f"{method} {path}: сеть — {e}") from e
        try:
            body = r.json()
        except ValueError:
            raise PrioApiError(f"{method} {path}: HTTP {r.status_code}, ответ не JSON: {r.text[:200]}")
        if r.status_code >= 400 or (isinstance(body, dict) and body.get("ok") is False):
            why = body.get("error") if isinstance(body, dict) else None     # тело-список не должно давать AttributeError → 500
            raise PrioApiError(f"{method} {path}: HTTP {r.status_code} — {why or str(body)[:200]}")
        return body

    def create(self, payload: dict) -> dict:
        return self._call("POST", "/api/campaigns", json=payload).get("campaign") or {}

    def update(self, camp_id: int, fields: dict) -> dict:
        return self._call("PUT", f"/api/campaigns/{int(camp_id)}", json=fields)

    def campaigns(self, **filters) -> list:
        params = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in filters.items() if v is not None}
        return self._call("GET", "/api/campaigns", params=params).get("campaigns") or []

    def stats(self, date_start: str, date_end: str) -> Any:
        return self._call("GET", "/api/stats-all-summary", params={"date_start": date_start, "date_end": date_end})
