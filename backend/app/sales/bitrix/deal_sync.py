"""Синхронизация одной сделки из Битрикса (через VibeCode).

Читает живой payload сделки, обновляет наши поля и скачивает файлы (МП, договор)
в персистентный том /app/uploads. Идемпотентно: повторный вызов обновляет только
изменившееся, а неопознанные поля НЕ затирает (защита от порчи ручных правок).

Коды полей — в VibeCode-нотации (camelCase), см. «Сверку полей» / DEAL_FIELD_MAP.
"""
import os
import re
import logging
from datetime import datetime, date

import httpx
from sqlalchemy.orm import Session

from app.files_safe import inside_uploads, remove_upload
from app.sales.bitrix.transport import vibecode_get
from app.sales.models import SalesDeal, SalesRep, SalesAdvertiser, SalesBrand, SalesDealFile

logger = logging.getLogger("sales.deal_sync")

UPLOADS_ROOT = "/app/uploads"
FILES_SUBDIR = "deal_files"

# ── коды полей Битрикса ──────────────────────────────────────────
F_AMOUNT_NET = "ufCrm_1690138678699"   # сумма до НДС ("500000|RUB")
F_SALE_MGR = "ufCrm_1761319635"        # employee — продавец (Sale manager)
F_KEY_ACC = "ufCrm_1723638961"         # employee — аккаунт (Key account)
F_ADVERTISER = "ufCrm_1761214459"      # crm/лид — рекламодатель (непоследовательное)
F_BRAND = "ufCrm_64BD76BC5BC45"        # текст — бренд
F_PERIOD_FROM = "ufCrm_1723639172"     # дата — Старт РК
F_MP = "ufCrm_1690138838403"           # file — МП
F_CONTRACT = "ufCrm_1690897647759"     # file — Договор и приложения

# Потолок правдоподобия для суммы с НДС относительно суммы до НДС: ставка 22 % плюс
# запас на округления и старые ставки. Выше — считаем присланное ошибкой заполнения.
_MAX_GROSS_K = 1.31


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(v):
    if not v:
        return None
    return _num(str(v).split("|")[0].strip())


def _parse_date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _first(v):
    """crm/employee/file-поле бывает списком или скаляром."""
    if isinstance(v, list):
        return v[0] if v else None
    return v


# ── резолв связей ────────────────────────────────────────────────
_user_cache = {}


def _resolve_user_name(uid):
    uid = str(uid)
    if uid in _user_cache:
        return _user_cache[uid]
    nm = None
    try:
        r = vibecode_get(f"/users/{uid}", {})
        d = (r.get("data") if isinstance(r, dict) else None) or {}
        nm = ((d.get("name") or "") + " " + (d.get("lastName") or d.get("last_name") or "")).strip() or d.get("title")
    except Exception as e:
        logger.warning("resolve user %s: %s", uid, e)
    _user_cache[uid] = nm
    return nm


def _resolve_rep_id(db, uid):
    """Bitrix user id → наш SalesRep. Сначала по bitrix_user_id, иначе по имени
    (и кэшируем связь в bitrix_user_id для будущих прогонов)."""
    if not uid:
        return None, None
    rep = db.query(SalesRep).filter(SalesRep.bitrix_user_id == str(uid)).first()
    if rep:
        return rep.id, None
    name = _resolve_user_name(uid)
    if not name:
        return None, f"пользователь bx#{uid} не опознан"
    rep = db.query(SalesRep).filter(SalesRep.name == name).first()
    if rep:
        if not rep.bitrix_user_id:
            rep.bitrix_user_id = str(uid)
        return rep.id, None
    return None, f"сейлз «{name}» (bx#{uid}) не найден в справочнике"


def _resolve_advertiser_id(db, crm_val):
    """ufCrm_1761214459 (crm/лид) → наш SalesAdvertiser по имени. Поле
    непоследовательное — ставим только при уверенном совпадении."""
    ent = _first(crm_val)
    if not ent:
        return None, None
    ent = str(ent).split("_")[-1]  # 'L_2055' -> '2055'
    title = None
    for path in (f"/leads/{ent}", f"/companies/{ent}"):
        try:
            r = vibecode_get(path, {})
            d = (r.get("data") if isinstance(r, dict) else None) or {}
            title = d.get("title") or d.get("name")
            if title:
                break
        except Exception:
            continue
    if not title:
        return None, f"рекламодатель bx#{ent} не резолвится"
    adv = (db.query(SalesAdvertiser)
           .filter((SalesAdvertiser.name == title) | (SalesAdvertiser.short_name == title)).first())
    if adv:
        return adv.id, None
    head = re.split(r"[ (]", title.strip())[0]
    if len(head) >= 3:
        cand = (db.query(SalesAdvertiser)
                .filter((SalesAdvertiser.name.ilike(head + "%")) | (SalesAdvertiser.short_name.ilike(head + "%"))).all())
        if len(cand) == 1:
            return cand[0].id, None
    return None, f"рекламодатель «{title}» не сопоставлен — проверьте вручную"


def _resolve_brand_id(db, text, advertiser_id):
    if not text:
        return None, None
    q = db.query(SalesBrand).filter(SalesBrand.name == text)
    if advertiser_id:
        q = q.filter(SalesBrand.advertiser_id == advertiser_id)
    cand = q.all()
    if len(cand) == 1:
        return cand[0].id, None
    if not cand:
        return None, f"бренд «{text}» не найден в справочнике"
    return None, f"бренд «{text}» неоднозначен ({len(cand)})"


# Куда нам ВООБЩЕ можно ходить за файлами сделки. Адрес приходит из ответа портала, то
# есть из поля, которое заполняется на чужой стороне. Без этого списка испорченное или
# подменённое значение увело бы наш запрос куда угодно — включая адреса внутренней
# docker-сети, куда снаружи не достучаться, а изнутри бэкенда легко (класс SSRF,
# находка F5-05 внешнего аудита 11.09.2026).
#
# Совпадение по СУФФИКСУ домена, а не по подстроке: проверка `"bitrix24.ru" in host`
# пропустила бы `bitrix24.ru.чужой-домен.tld`.
FILE_HOST_SUFFIXES = (".bitrix24.ru", ".bitrix24.tech", ".bitrix24.com")


def _allowed_file_url(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme != "https":
        return False
    host = (u.hostname or "").lower()
    return any(host == s.lstrip(".") or host.endswith(s) for s in FILE_HOST_SUFFIXES)


# Потолок на размер скачиваемого файла. У контейнера `mem_limit: 512m`, а `r.content`
# буферизует ответ ЦЕЛИКОМ: ответ на гигабайт (или бесконечный поток) убивал процесс —
# и не по злому умыслу, достаточно испорченного поля. В договорах и медиапланах
# 50 МБ с большим запасом; сравните с 20 МБ, которыми ограничена ручная загрузка.
FILE_MAX_BYTES = 50 * 1024 * 1024

# Сколько переадресаций разрешаем. Ноль был бы честнее всего, но портал отдаёт файлы
# через 302 на своё же файловое хранилище, и это законный ход.
FILE_MAX_REDIRECTS = 5


def _fetch_allowed(url: str):
    """Скачать, ПРОВЕРЯЯ адрес на каждом шаге переадресации.

    ЗАЧЕМ. Белый список выше проверял только первый адрес, а запрос шёл с
    `follow_redirects=True`. httpx идёт по переадресации на ЛЮБОЙ хост и любую схему —
    то есть портал (или тот, кто подменил поле) одним ответом `302 Location:
    http://finance_db:5432/...` уводил наш запрос внутрь docker-сети, и тело писалось
    на диск как файл сделки. Проверка давала ложное чувство закрытости: она стояла до
    запроса и после него не повторялась ни разу (найдено 11.09.2026).

    Поэтому переадресации разматываем сами и каждый следующий адрес прогоняем через тот
    же `_allowed_file_url`. Заодно читаем потоком и обрываемся на потолке размера.
    """
    from urllib.parse import urljoin
    seen = 0
    cur = url
    while True:
        if not _allowed_file_url(cur):
            raise ValueError("переадресация увела за пределы Битрикса")
        with httpx.stream("GET", cur, timeout=120, follow_redirects=False) as r:
            if r.status_code in (301, 302, 303, 307, 308):
                seen += 1
                if seen > FILE_MAX_REDIRECTS:
                    raise ValueError("слишком много переадресаций")
                loc = r.headers.get("location")
                if not loc:
                    raise ValueError("переадресация без адреса")
                cur = urljoin(cur, loc)
                continue
            r.raise_for_status()
            body = bytearray()
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > FILE_MAX_BYTES:
                    raise ValueError(
                        f"файл больше {FILE_MAX_BYTES // 1024 // 1024} МБ — не скачиваю")
            return bytes(body), dict(r.headers)


def _download_file(db, deal, field_val, kind):
    """Скачивает файл по urlMachine (со встроенным токеном) в персистентный том."""
    item = _first(field_val)
    if not isinstance(item, dict):
        return None, None
    url = item.get("urlMachine") or item.get("url")
    fid = str(item.get("id") or "")
    if not url:
        return None, f"нет urlMachine у файла ({kind})"
    if not _allowed_file_url(url):
        # Адрес в отчёт НЕ кладём целиком: в нём токен доступа, а отчёт синка виден
        # оператору и попадает в журнал.
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "?") if "//" in url else "?"
        return None, (f"файл {kind}: адрес не из Битрикса ({host}) — не скачиваю")
    existing = (db.query(SalesDealFile)
                .filter(SalesDealFile.deal_id == deal.id, SalesDealFile.kind == kind).first())
    _have = inside_uploads(existing.path) if existing else None
    if existing and existing.bitrix_file_id == fid and _have and os.path.exists(_have):
        return existing, None  # тот же файл уже скачан
    try:
        content, headers = _fetch_allowed(url)
    except Exception as e:
        return None, f"скачивание {kind} не удалось: {repr(e)[:80]}"
    cd = headers.get("content-disposition", "")
    m = re.search(r'filename="([^"]+)"', cd)
    fname = m.group(1) if m else f"{kind}_{fid}"
    subdir = os.path.join(UPLOADS_ROOT, FILES_SUBDIR, str(deal.id))
    os.makedirs(subdir, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", fname)
    abspath = os.path.join(subdir, safe)
    with open(abspath, "wb") as f:
        f.write(content)
    rel = os.path.relpath(abspath, UPLOADS_ROOT)
    if existing:
        # ПРЕЖНИЙ ФАЙЛ СТИРАЕМ (30.08.2026). Строка одна на пару «сделка × вид», а имя
        # файла входит в путь: заменили медиаплан в Битриксе — путь стал другим, строка
        # переписалась, а старый файл остался на диске навсегда. Так набралось 126
        # файлов на 256 МБ против 37 строк — 82% папки.
        # Условие узкое: стираем ТОЛЬКО прежний путь этой же строки и только если он
        # отличается от нового. Совпал — файл уже перезаписан по тому же адресу.
        # Граница — общей проверкой. Местная копия сравнивала СТРОКУ пути, а не
        # разрешённый путь, и потому пропускала `deal_files/../../../etc/passwd`:
        # строка начинается правильно, а `os.remove` уходил в `/etc`. Замерено
        # 11.09.2026. `subdir` сужает границу до папки файлов сделок — этого местная
        # проверка добивалась и почти добилась.
        old = existing.path
        if old and old != rel:
            remove_upload(old, subdir=FILES_SUBDIR)
        existing.bitrix_file_id = fid
        existing.filename = fname
        existing.path = rel
        existing.size = len(content)
        existing.content_type = headers.get("content-type")
        existing.synced_at = datetime.utcnow()
        rec = existing
    else:
        rec = SalesDealFile(deal_id=deal.id, kind=kind, bitrix_file_id=fid, filename=fname,
                            path=rel, size=len(content), content_type=headers.get("content-type"))
        db.add(rec)
    return rec, None


def sync_deal_from_bitrix(db: Session, deal: SalesDeal, download_files: bool = True) -> dict:
    """Живая сделка из Битрикса → наши поля + файлы. Идемпотентно, неопознанное
    НЕ затирает. Возвращает отчёт: changes / files / warnings."""
    if (deal.bitrix_id or "").startswith("local-"):
        raise ValueError("Локальная сделка ещё не в Битриксе")
    r = vibecode_get(f"/deals/{deal.bitrix_id}", {})
    d = (r.get("data") if isinstance(r, dict) else None) or {}
    changes = {}
    issues = []  # [{field, message}] — поля, требующие внимания (для подсветки + попапа)

    # Поля с ручной правкой (override) синхронизация НЕ трогает — иначе «⟳ Обновить
    # из Битрикса» затирает ручной ввод, а override-строка остаётся рассинхронизированной
    # (инвариант из models.py: откат ручной правки — только удалением override).
    from app.sales.models import SalesDealFieldOverride
    override_fields = {o.field_name for o in db.query(SalesDealFieldOverride)
                       .filter(SalesDealFieldOverride.deal_id == deal.id).all()}

    def setf(field, val):
        if val is None or field in override_fields:
            return
        old = getattr(deal, field)
        if old != val:
            changes[field] = {"old": str(old) if old is not None else None, "new": str(val)}
            setattr(deal, field, val)

    def issue(field, w):
        if w:
            issues.append({"field": field, "message": w})

    # Порядок важен: сначала сумма до НДС (наше достоверное поле), затем проверка
    # opportunity об неё. Стандартное opportunity заполняют не всегда и не всегда верно:
    # встречались 0, сумма меньше суммы без НДС и завышение втрое. Такое значение не
    # импортируем вовсе — иначе каждый синк затирал бы корректную цифру, — а поднимаем
    # issue, чтобы расхождение увидели в отчёте сверки.
    setf("amount", _money(d.get(F_AMOUNT_NET)))          # до НДС
    _gross = _num(d.get("amount"))                       # стандартное opportunity — с НДС
    _net = deal.amount
    if _gross is not None and _net:
        if _gross < _net - 1 or _gross > _net * _MAX_GROSS_K:
            issue("amount_with_vat",
                  f"Битрикс прислал сумму с НДС {_gross:,.0f} при сумме до НДС {_net:,.0f} — "
                  f"значение не импортировано".replace(",", " "))
            _gross = None
    setf("amount_with_vat", _gross)
    setf("period_from", _parse_date(d.get(F_PERIOD_FROM)))

    rid, w = _resolve_rep_id(db, _first(d.get(F_SALE_MGR)))
    setf("sales_rep_id", rid)
    issue("sales_rep", w)
    aid, w = _resolve_rep_id(db, _first(d.get(F_KEY_ACC)))
    setf("account_manager_id", aid)
    issue("account_manager", w)
    adv_id, w = _resolve_advertiser_id(db, d.get(F_ADVERTISER))
    setf("advertiser_id", adv_id)
    issue("advertiser", w)
    br_id, w = _resolve_brand_id(db, d.get(F_BRAND), deal.advertiser_id)
    setf("brand_id", br_id)
    issue("brand", w)

    files = []
    if download_files:
        for field, kind in ((F_MP, "mp"), (F_CONTRACT, "contract")):
            val = d.get(field)
            if not val:
                continue
            rec, w = _download_file(db, deal, val, kind)
            if rec:
                files.append({"kind": kind, "filename": rec.filename, "size": rec.size, "id": rec.id})
            issue(kind, w)

    # ── Светофор ──
    # red  — Битрикс расходится с нашими справочниками (что-то не сматчилось);
    # blue — у нас есть ручные правки (данные полнее / не выгружены в Битрикс);
    # green — всё сошлось. red важнее blue.
    has_overrides = bool(override_fields)
    deal.sync_status = "red" if issues else ("blue" if has_overrides else "green")
    deal.sync_checked_at = datetime.utcnow()
    # Отчёт сохраняем в сделке — чтобы клик по светофору показал детали без нового запроса.
    deal.sync_report = {"issues": issues, "changes": list(changes.keys()),
                        "checked_at": deal.sync_checked_at.isoformat()}

    db.commit()
    warnings = [i["message"] for i in issues]
    return {"changes": changes, "files": files, "warnings": warnings, "issues": issues,
            "status": deal.sync_status, "bitrix_id": deal.bitrix_id}
