"""Транспорт к Битрикс24 через платформу VibeCode (httpx-клиент).

Ключ из env VIBECODE_API_KEY либо из файла /app/vibecode.key (кладётся docker cp, как код).
Доступ READWRITE. ГРАБЛЯ пагинации: у Битрикса `meta.hasMore` бывает ВСЕГДА True — стоп
по total/пустой странице (см. _get_paged_with_retry).
"""
import os
import time
import httpx

VIBECODE_BASE = "https://vibecode.bitrix24.tech/v1"
_KEY_FILE = "/app/vibecode.key"


def _api_key() -> str | None:
    key = os.getenv("VIBECODE_API_KEY")
    if key:
        return key.strip()
    try:
        with open(_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def vibecode_get(path: str, params: dict | None = None) -> dict:
    key = _api_key()
    if not key:
        raise RuntimeError("VIBECODE_API_KEY не настроен (нет env и файла /app/vibecode.key)")
    if not path.startswith("/"):
        path = "/" + path
    r = httpx.get(
        VIBECODE_BASE + path,
        headers={"X-Api-Key": key},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _field(row: dict, *names):
    """Битрикс отдаёт поля то camelCase, то UPPER — берём первое непустое."""
    for n in names:
        if row.get(n) not in (None, ""):
            return row[n]
    return None


def vibecode_patch(path: str, body: dict) -> dict:
    key = _api_key()
    if not key:
        raise RuntimeError("VIBECODE_API_KEY не настроен")
    if not path.startswith("/"):
        path = "/" + path
    r = httpx.patch(VIBECODE_BASE + path,
                    headers={"X-Api-Key": key, "Content-Type": "application/json"},
                    json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def vibecode_post(path: str, body: dict) -> dict:
    key = _api_key()
    if not key:
        raise RuntimeError("VIBECODE_API_KEY не настроен")
    if not path.startswith("/"):
        path = "/" + path
    r = httpx.post(VIBECODE_BASE + path,
                   headers={"X-Api-Key": key, "Content-Type": "application/json"},
                   json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def list_deal_ids_for_company(company_id: str) -> list[str]:
    """Все id сделок, указывающих на компанию (для переброса при склейке)."""
    rows = _get_paged_with_retry("/deals", {"filter[companyId]": str(company_id)})
    return [str(r.get("id") or r.get("ID")) for r in rows if (r.get("id") or r.get("ID"))]


def all_deal_company_ids() -> list[str]:
    """companyId всех сделок (лёгкая выборка) — для подсчёта сделок по каждой компании."""
    rows = _get_paged_with_retry("/deals", {"select[]": "companyId"})
    out = []
    for r in rows:
        cid = r.get("companyId") or r.get("COMPANY_ID")
        if cid:
            out.append(str(cid))
    return out


def _get_paged_with_retry(path: str, base_params: dict, retries: int = 3, page_size: int = 500) -> list:
    """Пагинация limit/offset с ретраем на страницу (таймауты/HTTP 000). page_size=500 —
    Битрикс отдаёт до 500 за раз, это резко сокращает число запросов."""
    out: list = []
    offset = 0
    while True:
        params = dict(base_params, limit=page_size, offset=offset)
        last_err = None
        for attempt in range(retries):
            try:
                data = vibecode_get(path, params)
                break
            except Exception as e:  # transient — повторяем с backoff
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        else:
            raise last_err
        rows = data.get("data") or []
        out.extend(rows)
        meta = data.get("meta") or {}
        total = meta.get("total")
        # ВНИМАНИЕ: у Битрикса meta.hasMore бывает ВСЕГДА True (даже за концом).
        # Поэтому основной стоп — по total/пустой странице, hasMore=False лишь дополняет.
        if not rows:
            break
        if total and len(out) >= total:
            break
        if meta.get("hasMore") is False:
            break
        offset += page_size
    return out


def list_bitrix_companies(type_id: str) -> list[dict]:
    """Компании нужного typeId → [{id, title}] (id — строка)."""
    rows = _get_paged_with_retry("/companies", {"filter[typeId]": type_id})
    return [{"id": str(r.get("id") or r.get("ID")),
             "title": r.get("title") or r.get("TITLE") or ""} for r in rows]


def list_bitrix_pipelines() -> list[dict]:
    """Воронки сделок (категории). Категория 0 «Общая» списком не отдаётся — добавляем вручную.
    → [{id:int, name:str}]."""
    rows = _get_paged_with_retry("/deal-categories", {})
    out = [{"id": 0, "name": "Общая"}]
    for r in rows:
        cid = r.get("id")
        if cid is not None:
            out.append({"id": int(cid), "name": r.get("name") or ""})
    return out


def list_bitrix_stages(category_id) -> list[dict]:
    """Стадии воронки. entityId = DEAL_STAGE (кат.0) или DEAL_STAGE_<catId>.
    → [{status_id:str, name:str}]."""
    ent = "DEAL_STAGE" if str(category_id) == "0" else f"DEAL_STAGE_{category_id}"
    rows = _get_paged_with_retry("/statuses", {"filter[entityId]": ent})
    return [{"status_id": r.get("statusId") or r.get("STATUS_ID"), "name": r.get("name") or ""}
            for r in rows if (r.get("statusId") or r.get("STATUS_ID"))]


def list_bitrix_services() -> list[dict]:
    """«Продукты Simb-ad» — элементы смарт-процесса 1050. → [{id:str, title:str}]."""
    rows = _get_paged_with_retry("/items/1050", {})
    return [{"id": str(r.get("id")), "title": r.get("title") or ""} for r in rows if r.get("id")]


def list_bitrix_users(active_only: bool = True) -> list[dict]:
    """Все сотрудники портала (пагинация по 50). → [{id, name, active}]."""
    out: list[dict] = []
    offset = 0
    while True:
        data = vibecode_get("/users", {"limit": 50, "offset": offset})
        rows = data.get("data") or []
        if not rows:
            break
        for u in rows:
            uid = _field(u, "ID", "id")
            if uid is None:
                continue
            active_raw = _field(u, "ACTIVE", "active")
            active = str(active_raw).lower() in ("1", "true", "y", "yes") if active_raw is not None else True
            name = " ".join(
                str(x) for x in (
                    _field(u, "LAST_NAME", "lastName"),
                    _field(u, "NAME", "name"),
                    _field(u, "SECOND_NAME", "secondName"),
                ) if x
            ).strip()
            out.append({
                "id": str(uid),
                "name": name or f"ID {uid}",
                "active": active,
            })
        meta = data.get("meta") or {}
        if not meta.get("hasMore"):
            break
        offset += 50
    if active_only:
        out = [u for u in out if u["active"]]
    out.sort(key=lambda x: x["name"].lower())
    return out
