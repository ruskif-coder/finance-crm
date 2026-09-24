"""JSON-RPC клиент DSP + журнал отправок в dsp_send_log.

Контур «DSP-коннектор» (этап 2b). Сверено с официальной докой и тестом владельца 02.09.2026
(память dsp-api): `POST {DSP_API_URL}?method=<Method>`, тело JSON-RPC 2.0,
`Authorization: Bearer`. Ответ — `{"jsonrpc":"2.0","result":…,"id":…}`; у `Campaign.add` /
`Creative.add` `result` — это xxhash созданного объекта СТРОКОЙ (16 hex), без обёртки.

Каждый вызов — строка в `dsp_send_log` (аналит. база): метод, наш local_ref, тело запроса
(токен в теле не живёт — он в заголовке, в журнал не попадает), ответ, извлечённый xxhash, ok/error.
Журнал — против дублей (см. campaigns.ensure_campaign) и для аудита, как журнал ОРД.
Сбой записи в журнал НЕ маскирует результат вызова: пишем предупреждение и отдаём ответ.

Транспорт подменяемый (тесты без сети). Секреты только из окружения:
DSP_API_URL, DSP_ACCESS_TOKEN, DSP_PARTNER_XXHASH.
"""
import json
import logging
import os
import re
from typing import Any, Callable, Dict, Optional

import httpx
from sqlalchemy import text

log = logging.getLogger("finance.dsp")

XXHASH_RE = re.compile(r"^[0-9A-Fa-f]{16}$")

PROD, DEMO = "prod", "demo"
CONTOURS = (PROD, DEMO)

CAMPAIGN_STATUSES = ("STOPPED", "LAUNCHED", "DELETED", "ARCHIVE")
TRAFFIC_DISTRIBUTION = ("uniform_basic", "uniform_pro", "accelerated")


class MsError(RuntimeError):
    """Ошибка вызова МС: JSON-RPC error, HTTP-ошибка или неожиданный формат ответа."""


# Под каким ключом приходит идентификатор созданного объекта. Единого правила у API нет,
# и это замерено, а не выведено (09.09.2026, живой кабинет):
#
#   Campaign.add → "AC71A89189EDD994"        — строкой, без обёртки
#   Creative.add → {"id": "6A12AD0CEB6F8AB5"} — ключ `id`, а НЕ `xxhash`
#
# Цена ошибки здесь несимметрична: объект в DSP уже СОЗДАН, а мы, не узнав его хеша,
# считаем вызов неудачным. Креатив остаётся сиротой в чужом кабинете, разметка в него не
# уезжает, и человек видит «шаг не сработал» — ровно это случилось 09.09.2026.
ID_KEYS = ("xxhash", "id", "creative_xxhash", "campaign_xxhash")


def _extract_xxhash(result: Any) -> Optional[str]:
    if isinstance(result, str) and XXHASH_RE.match(result):
        return result.upper()
    if isinstance(result, dict):
        for k in ID_KEYS:
            v = result.get(k)
            if isinstance(v, str) and XXHASH_RE.match(v):
                return v.upper()
    return None


class MsClient:
    def __init__(self, url: Optional[str] = None, token: Optional[str] = None,
                 partner_xxhash: Optional[str] = None,
                 transport: Optional[Callable[[str, dict], dict]] = None,
                 journal_engine=None, journal: bool = True, timeout: float = 30.0,
                 contour: str = PROD):
        # journal=False — совсем без журнала (чистые тесты); иначе engine подхватится лениво.
        self._journal_on = journal
        # Контур вызова. Он не косметика: защита от дублей ищет прошлый хеш по нашему
        # local_ref, и демо-прогон по той же сделке заставил бы боевое заведение решить,
        # что кампания уже создана. Поиск фильтруется контуром — см. last_ok_xxhash.
        if contour not in CONTOURS:
            raise ValueError(f"неизвестный контур {contour!r}, ожидается один из {CONTOURS}")
        self.contour = contour
        self.url = (url or os.getenv("DSP_API_URL") or "").rstrip("/") + "/"
        self.token = token or os.getenv("DSP_ACCESS_TOKEN")
        self.partner_xxhash = partner_xxhash or os.getenv("DSP_PARTNER_XXHASH")
        self._transport = transport or self._http
        self._journal_engine = journal_engine
        self._timeout = timeout
        self._id = 0

    # ── транспорт ──────────────────────────────────────────────────────────
    def _configured(self) -> bool:
        return bool(self.token) and self.url != "/"

    def _http(self, method: str, body: dict) -> dict:
        if not self._configured():
            raise MsError("DSP_API_URL / DSP_ACCESS_TOKEN не заданы в окружении")
        r = httpx.post(f"{self.url}?method={method}",
                       headers={"Authorization": f"Bearer {self.token}",
                                "Content-Type": "application/json"},
                       json=body, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    # ── журнал ─────────────────────────────────────────────────────────────
    def _engine(self):
        if self._journal_engine is None:
            from app.dsp.db import dsp_engine
            self._journal_engine = dsp_engine()
        return self._journal_engine

    def _journal(self, method, entity_type, local_ref, body, resp, ms_xxhash, ok, error):
        if not self._journal_on:
            return
        try:
            with self._engine().begin() as c:
                c.execute(text(
                    "INSERT INTO dsp_send_log (contour, method, entity_type, local_ref, "
                    "request, response, ms_xxhash, ok, error) VALUES (:ct, :m, :et, :lr, "
                    "CAST(:rq AS jsonb), CAST(:rs AS jsonb), :xx, :ok, :err)"),
                    dict(ct=self.contour, m=method, et=entity_type,
                         lr=(str(local_ref) if local_ref is not None else None),
                         rq=json.dumps(body, ensure_ascii=False),
                         rs=(json.dumps(resp, ensure_ascii=False) if resp is not None else None),
                         xx=ms_xxhash, ok=ok, err=error))
        except Exception as e:  # noqa: BLE001 — журнал не должен ронять вызов
            log.warning("dsp_send_log: не записалось (%s) для %s/%s", e, method, local_ref)

    def journal_raw(self, method, entity_type, local_ref, request, response,
                    ms_xxhash, ok, error) -> None:
        """Записать в журнал вызов, который прошёл МИМО JSON-RPC.

        Такой ровно один — multipart-загрузка архива креатива на выданный URL. Без этой
        записи в журнале был бы разрыв: `getUploadFileUrl` есть, креатив есть, а чем их
        связали — не видно.
        """
        self._journal(method, entity_type, local_ref, request, response, ms_xxhash, ok, error)

    def last_ok_xxhash(self, method: str, entity_type: str, local_ref) -> Optional[str]:
        """Последний удачный хеш по нашему local_ref — защита от повторного add, если
        МС создал объект, а наш коммит не дошёл."""
        if not self._journal_on:
            return None
        try:
            with self._engine().connect() as c:
                return c.execute(text(
                    "SELECT ms_xxhash FROM dsp_send_log WHERE contour=:ct AND method=:m "
                    "AND entity_type=:et AND local_ref=:lr AND ok AND ms_xxhash IS NOT NULL "
                    "ORDER BY ts DESC LIMIT 1"),
                    dict(ct=self.contour, m=method, et=entity_type,
                         lr=str(local_ref))).scalar()
        except Exception as e:  # noqa: BLE001
            log.warning("dsp_send_log: чтение не удалось (%s)", e)
            return None

    # Строка «ушло, исход неизвестен»: без хеша и либо без ответа (таймаут, обрыв), либо
    # с «успехом», в котором хеша не нашлось. Отказ с телом ответа сюда не попадает —
    # он ответ. Считается только то, что позже последней ТОЧКИ СБРОСА: удачного вызова с
    # хешом или отметки человека после сверки с кабинетом (`response.resolved`).
    _UNKNOWN_SQL = (
        "SELECT DISTINCT l.local_ref FROM dsp_send_log l "
        "WHERE l.contour=:ct AND l.method=:m AND l.entity_type=:et "
        "AND l.local_ref = ANY(:refs) AND l.ms_xxhash IS NULL "
        "AND (l.response IS NULL OR l.ok) "
        "AND l.ts > COALESCE((SELECT max(x.ts) FROM dsp_send_log x "
        "WHERE x.contour=l.contour AND x.method=l.method AND x.entity_type=l.entity_type "
        "AND x.local_ref=l.local_ref AND ((x.ok AND x.ms_xxhash IS NOT NULL) "
        "OR x.response->>'resolved' IS NOT NULL)), '-infinity')")

    def _unknown(self, method: str, entity_type: str, refs) -> set:
        with self._engine().connect() as c:
            return {r[0] for r in c.execute(text(self._UNKNOWN_SQL), dict(
                ct=self.contour, m=method, et=entity_type,
                refs=[str(r) for r in refs])).all()}

    def unknown_outcome(self, method: str, entity_type: str, local_ref) -> bool:
        """Был ли вызов, ушедший без ответа, после последней точки сброса.

        DSP мог объект создать, а мы не узнали хеша. Такой вызов не повторяют вслепую
        (аудит 23.09.2026, 4.L5). Журнал недоступен — считаем, что исход неизвестен:
        лишняя осторожность видна отказом, лишняя смелость — дублем в чужом кабинете.
        """
        if not self._journal_on:
            return False
        try:
            return str(local_ref) in self._unknown(method, entity_type, [local_ref])
        except Exception as e:  # noqa: BLE001
            log.warning("dsp_send_log: чтение не удалось (%s)", e)
            return True

    def unknown_refs(self, method: str, entity_type: str, refs) -> set:
        """То же пачкой — для экрана. Журнал недоступен — пусто: экран не падает, а
        запирает повтор всё равно `unknown_outcome` перед самим вызовом."""
        if not self._journal_on or not refs:
            return set()
        try:
            return self._unknown(method, entity_type, refs)
        except Exception as e:  # noqa: BLE001
            log.warning("dsp_send_log: чтение не удалось (%s)", e)
            return set()

    # ── базовый вызов ──────────────────────────────────────────────────────
    def call(self, method: str, params: Dict[str, Any], *, entity_type: Optional[str] = None,
             local_ref=None) -> Any:
        # Не настроено — отказ ДО журнала: запрос никуда не уходил, и строка «без ответа»
        # заперла бы повтор создающего вызова как неизвестный исход.
        if self._transport == self._http and not self._configured():
            raise MsError("DSP_API_URL / DSP_ACCESS_TOKEN не заданы в окружении")
        self._id += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params, "id": self._id}
        resp, result, ok, err = None, None, False, None
        try:
            resp = self._transport(method, body)
            if not isinstance(resp, dict):
                raise MsError(f"{method}: ответ не JSON-объект: {str(resp)[:200]}")
            if resp.get("error"):
                err = json.dumps(resp["error"], ensure_ascii=False)
                raise MsError(f"{method}: {err}")
            result = resp.get("result")
            ok = True
            return result
        except MsError:
            raise
        except Exception as e:
            err = repr(e)
            # 4xx — это ОТВЕТ: DSP отказал, объект не создан. Кладём его в журнал, чтобы
            # строка не читалась как «ушло без ответа» и не запирала повтор зря.
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                resp = {"http_status": e.response.status_code,
                        "body": e.response.text[:500]}
            raise MsError(f"{method}: {err}") from e
        finally:
            self._journal(method, entity_type, local_ref, body, resp,
                          _extract_xxhash(result) if ok else None, ok, err)

    # ── кампании ───────────────────────────────────────────────────────────
    def campaign_add(self, params: dict, local_ref=None) -> str:
        p = {"partner_xxhash": self.partner_xxhash, **params}
        result = self.call("Campaign.add", p, entity_type="campaign", local_ref=local_ref)
        xx = _extract_xxhash(result)
        if not xx:
            raise MsError(f"Campaign.add: в result нет xxhash: {str(result)[:200]}")
        return xx

    def campaign_edit(self, xxhash: str, params: dict, local_ref=None) -> Any:
        return self.call("Campaign.edit", {"xxhash": xxhash, "partner_xxhash": self.partner_xxhash,
                                           **params}, entity_type="campaign", local_ref=local_ref)

    def campaign_get_info(self, xxhash: str) -> Any:
        return self.call("Campaign.getInfo", {"xxhash": xxhash}, entity_type="campaign")

    def campaign_set_status(self, xxhash: str, status: str, local_ref=None) -> Any:
        if status not in CAMPAIGN_STATUSES:
            raise MsError(f"статус кампании бывает {CAMPAIGN_STATUSES}, а не {status!r}")
        return self.call("Campaign.setStatus",
                         {"xxhash": xxhash, "partner_xxhash": self.partner_xxhash, "status": status},
                         entity_type="campaign", local_ref=local_ref)

    def campaign_list_by_partner(self) -> list:
        r = self.call("Campaign.getListByPartner", {"partner_xxhash": self.partner_xxhash},
                      entity_type="campaign", local_ref=self.partner_xxhash)
        return r if isinstance(r, list) else []

    # ── креативы ───────────────────────────────────────────────────────────
    def creative_add(self, campaign_xxhash: str, params: dict, local_ref=None) -> str:
        p = {"campaign_xxhash": campaign_xxhash, "partner_xxhash": self.partner_xxhash, **params}
        result = self.call("Creative.add", p, entity_type="creative", local_ref=local_ref)
        xx = _extract_xxhash(result)
        if not xx:
            raise MsError(f"Creative.add: в result нет xxhash: {str(result)[:200]}")
        return xx

    def creative_get_info(self, xxhash: str) -> Any:
        """Что за креатив лежит в кабинете под этим хешем.

        Метод есть у DSP и отвечает «Creative not found» на несуществующий хеш (проба
        17.09.2026). Нужен он ради одной проверки: `Creative.add` создаёт объект, а HTML
        вшивается ВТОРЫМ вызовом `Creative.edit`. Между ними связь может оборваться — и
        тогда в кабинете остаётся креатив без кода, то есть пустая страница, по которой
        человек «убедился, что баннер загружен».

        `Creative.getListByCampaign` у DSP НЕТ (проверено там же, отвечает «Method not
        found»), поэтому перечислить креативы кампании нельзя — только спросить про
        конкретный.
        """
        return self.call("Creative.getInfo", {"xxhash": xxhash}, entity_type="creative")

    def creative_edit(self, xxhash: str, params: dict, local_ref=None) -> Any:
        # N.B. владельца: description не менять; при uniform_pro без day/hour лимитов
        return self.call("Creative.edit", {"xxhash": xxhash, **params},
                         entity_type="creative", local_ref=local_ref)

    def creative_set_status(self, xxhash: str, status: str, local_ref=None) -> Any:
        return self.call("Creative.setStatus", {"xxhash": xxhash, "status": status},
                         entity_type="creative", local_ref=local_ref)

    # ── таргетинг / загрузка ───────────────────────────────────────────────
    def targeting_get(self, xxhash: str, target_key: str) -> Any:
        return self.call("Targeting.getUserSetting", {"xxhash": xxhash, "target_key": target_key},
                         entity_type="targeting", local_ref=xxhash)

    def targeting_set(self, xxhash: str, target_key: str, items: dict,
                      is_invert_mode: bool = False) -> Any:
        return self.call("Targeting.setUserSetting",
                         {"xxhash": xxhash, "target_key": target_key,
                          "targeting_data": {"is_invert_mode": is_invert_mode, "items": items}},
                         entity_type="targeting", local_ref=xxhash)

    def upload_get_url(self, file_type: str = "zip") -> str:
        r = self.call("Upload.getUploadFileUrl", {"type": file_type}, entity_type="upload")
        if not isinstance(r, str):
            raise MsError(f"Upload.getUploadFileUrl: ожидали URL, получили {str(r)[:200]}")
        return r
