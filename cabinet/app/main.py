"""Сервис кабинета паблишера: задания на согласование и ответ по ним.

Площадка видит висящие на ней креативы, смотрит баннер в типовых размерах, отвечает
одним из трёх исходов и присылает посадочную страницу, если её у нас попросили.

**Кабинет не пишет в базу.** Ни вердикт, ни ссылку: он зовёт ядро по внутренней сети с
сервисным секретом, и запись делает та же функция, что записывает вердикт со слов
аккаунта. Правила там нетривиальны — неизменяемость, обязательная причина, код пары по
схождению, боковой выход в «отказ площадки», — и вторая их реализация здесь разошлась бы
с первой. Инвариант «у таблицы один писатель» от этого не ослаб, а усилился.

Границы, которые здесь важнее функциональности:

  · ходим под ролью `cabinet` — она не видит `public` вовсе (`app/db.py`);
  · область видимости ставится `set_config(..., is_local => true)` внутри транзакции;
  · свой ключ подписи — токен кабинета не должен подходить к финмодулю;
  · CORS не открывается: фронт кабинета живёт на том же origin через Caddy.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import (account_publishers, current_account, current_account_any,
                      find_account, make_token,
                      verify_password)
from app.db import plain_session, scoped_session

# Документация закрыта так же, как в ядре: во внешнем контуре тем более незачем
# публиковать карту эндпоинтов.
DEBUG = os.getenv("DEBUG", "").lower() == "true"
app = FastAPI(title="Кабинет паблишера",
              docs_url="/docs" if DEBUG else None,
              redoc_url=None, openapi_url="/openapi.json" if DEBUG else None)

SANDBOX_BASE_URL = os.getenv("SANDBOX_BASE_URL", "https://sb.localhost")

# Ядро: кабинет НЕ ПИШЕТ в базу, он зовёт ядро. Правила вердикта нетривиальны
# (неизменяемость, обязательная причина, код пары по схождению, боковой выход в «отказ
# площадки»), и вторая их реализация здесь разошлась бы с первой — в проекте так уже
# случалось со срочностью и с разбором кварталов.
CORE_API_URL = os.getenv("CORE_API_URL", "http://backend:8000").rstrip("/")
SERVICE_TOKEN = os.getenv("CABINET_SERVICE_TOKEN", "")


def call_core(method: str, path: str, body: dict) -> dict:
    """Позвать ядро. Ошибку ядра пересказываем как есть — она написана для человека.

    Обрыв связи и ошибку ядра различаем текстом: «сервис недоступен» и «так нельзя» —
    разные новости, и первая означает «повторите», а вторая «не повторяйте».
    """
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")
    try:
        # `json=None` у httpx означает «без тела» — GET проходит так же, как PUT с телом.
        r = httpx.request(method, f"{CORE_API_URL}{path}", json=body, timeout=15.0,
                          headers={"X-Cabinet-Token": SERVICE_TOKEN})
    except httpx.RequestError:
        raise HTTPException(status_code=503,
                            detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or "Не удалось сохранить"
        except Exception:      # noqa: BLE001 — ядро могло ответить не JSON
            detail = "Не удалось сохранить"
        raise HTTPException(status_code=r.status_code if r.status_code < 500 else 502,
                            detail=detail)
    return r.json()


def my_task(acc, task_id: int):
    """Задание, если оно ЭТОЙ учётки. Иначе 404 — не 403.

    Разница существенная: 403 подтверждает, что такое задание есть, и превращает
    перебор идентификаторов в способ узнать, кто с кем работает.
    """
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    with scoped_session(ids) as db:
        row = db.execute(text(
            "SELECT task_id, publisher_id, target_id FROM pub.task_v1 "
            "WHERE task_id = :t"), {"t": task_id}).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return row


def sandbox_url(token, entry):
    """Адрес предпросмотра. Собирает его тот, кто знает домен песочницы, — бэкенд."""
    if not token or not entry:
        return None
    return f"{SANDBOX_BASE_URL.rstrip('/')}/{token}/{entry.lstrip('/')}"



# Пояс. Своя пара строк, а не `app.timez` из ядра: кабинет — отдельный процесс под
# отдельной ролью БД и `app.*` не импортирует по построению (см. шапку файла). У Москвы
# с 2014 года нет перехода на летнее время, смещение постоянное — поэтому число, а не
# зависимость от базы часовых поясов в образе.
MSK_OFFSET = 3


def _to_msk(dt):
    """Наивная метка из базы (UTC) → московская. Тот же перевод, что в ядре."""
    return dt + timedelta(hours=MSK_OFFSET)


def _msk_today():
    """Сегодня по Москве. Для счёта суток, показываемого площадке."""
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=MSK_OFFSET)).date()


class LoginIn(BaseModel):
    email: str
    password: str


def _lock_minutes(email: str) -> int:
    """Сколько минут осталось до снятия блокировки. Ошибка счётчика вход НЕ открывает.

    Счётчик общий с ядром (`login_attempts`), и кабинет достаёт его через `pub.*`:
    своей таблицы попыток нет намеренно — вторая реализация того же правила однажды
    разошлась бы с первой, и разошлась бы молча.
    """
    db = plain_session()
    try:
        return int(db.execute(text("SELECT pub.login_lock_minutes(:e)"),
                              {"e": email}).scalar() or 0)
    except Exception:
        # Счётчик недоступен — считаем заблокированным. Отказ защиты не должен
        # выглядеть как её отсутствие: это ровно тот случай, ради которого пустой
        # CABINET_SERVICE_TOKEN закрывает вход, а не открывает.
        return 1
    finally:
        db.close()


def _note_login(email: str, ok: bool) -> None:
    """Отметить попытку. Успех обнуляет счётчик, неудача приближает блокировку."""
    db = plain_session()
    try:
        fn = "pub.clear_login_attempts" if ok else "pub.register_failed_login"
        db.execute(text(f"SELECT {fn}(:e)"), {"e": email})
        db.commit()
    except Exception:
        db.rollback()      # учёт попытки не стоит того, чтобы ронять сам вход
    finally:
        db.close()


# ── ограничение попыток входа ПО АДРЕСУ ──────────────────────────────────────
#
# У кабинета был только локаут по почте. Ядру этого сочли мало ещё после пентеста
# 18.07.2026: локаут по одной почте не мешает перебору ОДНОГО пароля по многим учёткам,
# и счётчик по адресу добавили именно поэтому. Внешний контур остался без него — а
# перебор опаснее как раз здесь: адрес входа известен площадке, учёток у кабинета
# немного, и ходят туда не наши сотрудники (F1-03 внешнего аудита 11.09.2026).
#
# Устройство повторяет ядро один в один, включая обе его сегодняшние правки: адрес
# берётся из ПОСЛЕДНЕГО звена `X-Forwarded-For` (левое пишет клиент), а словарь имеет
# потолок и уборку — иначе подделка заголовка растит память процесса без предела.
MAX_LOGIN_PER_IP = 20
LOGIN_IP_WINDOW_SECONDS = 15 * 60
MAX_TRACKED_IPS = 10_000
_ip_attempts: dict = {}
_ip_lock = threading.Lock()


def client_ip(request: Optional[Request]) -> str:
    """Доверенное звено цепочки, а не первое попавшееся.

    `X-Forwarded-For` дополняет каждый прокси на пути: всё, что прислал клиент, слева,
    правее дописывает Caddy — то, что он видел на сокете. Доверять можно только правому.
    Допущение: перед кабинетом ровно один наш прокси, и оно верно по построению —
    порт сервиса слушает только `127.0.0.1`.
    """
    if request is None:
        return "unknown"
    chain = [x.strip() for x in (request.headers.get("x-forwarded-for") or "").split(",")]
    chain = [x for x in chain if x]
    if chain:
        return chain[-1]
    return request.client.host if request.client else "unknown"


def _prune_ip_attempts(now: float) -> None:
    stale = [ip for ip, ts in _ip_attempts.items()
             if not ts or now - ts[-1] >= LOGIN_IP_WINDOW_SECONDS]
    for ip in stale:
        del _ip_attempts[ip]
    if len(_ip_attempts) > MAX_TRACKED_IPS:
        newest = sorted(_ip_attempts.items(), key=lambda kv: kv[1][-1], reverse=True)
        _ip_attempts.clear()
        _ip_attempts.update(dict(newest[:MAX_TRACKED_IPS]))


def _check_ip_rate_limit(ip: str) -> None:
    now = time.time()
    with _ip_lock:
        window = [x for x in _ip_attempts.get(ip, []) if now - x < LOGIN_IP_WINDOW_SECONDS]
        _ip_attempts[ip] = window
        if len(_ip_attempts) > MAX_TRACKED_IPS:
            _prune_ip_attempts(now)
            window = _ip_attempts.setdefault(ip, window)
        if len(window) >= MAX_LOGIN_PER_IP:
            raise HTTPException(
                status_code=429,
                detail="Слишком много попыток входа. Попробуйте позже.")
        window.append(now)


@app.post("/api/login")
def login(payload: LoginIn, request: Request = None):
    """Вход. Одинаковый ответ на «нет такой учётки» и «неверный пароль».

    Проверка пароля прогоняется даже для несуществующего адреса: иначе разница во
    времени ответа отвечает на вопрос «а заведён ли у вас такой человек» — а это
    перечисление учёток внешнего контура.

    Блокировка после серии неудач (30.08.2026) — от ПЕРЕБОРА, тогда как всё выше от
    ПЕРЕЧИСЛЕНИЯ. Для внешнего контура перебор опаснее: туда ходят не наши сотрудники,
    адрес входа известен площадке, и учётка у кабинета обычно одна.
    """
    # Счётчик по адресу — ПЕРВЫМ: он не зависит от того, существует ли учётка, и потому
    # не отвечает на вопрос «а заведён ли у вас такой человек».
    _check_ip_rate_limit(client_ip(request))

    email = (payload.email or "").strip()
    left = _lock_minutes(email)
    if left:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много неудачных попыток входа. Попробуйте через {left} мин.")

    row = find_account(email)
    ok = verify_password(payload.password, row.hashed_password if row else "")
    if not row or not ok or not row.is_active:
        # Счётчик ведётся и для несуществующего адреса — иначе «этот заблокировали, а
        # этот нет» снова отвечает на вопрос о существовании учётки.
        _note_login(email, ok=False)
        raise HTTPException(status_code=401, detail="Неверная почта или пароль")
    _note_login(email, ok=True)

    db = plain_session()
    try:
        # Отметка входа — единственная запись, которую кабинет делает в `public`, и она
        # идёт через функцию ядра. Прямого `UPDATE` у роли нет и не будет.
        db.execute(text("SELECT pub.touch_login(:i)"), {"i": row.id})
        db.commit()
    except Exception:
        db.rollback()          # отметка времени не стоит того, чтобы ронять вход
    finally:
        db.close()

    pubs = account_publishers(row.id)

    return {"token": make_token(row.id, row.email, row.hashed_password),
            "name": row.name, "email": row.email,
            # Первый вход — экран покажет согласие до всего остального (24.09.2026).
            "consent_required": getattr(row, "consent_accepted_at", None) is None,
            "publishers": [{"id": p.publisher_id, "name": p.name, "domain": p.domain}
                           for p in pubs]}


@app.get("/api/me")
def me(acc=Depends(current_account_any)):
    # Открыта и без согласия: экрану надо знать, что показывать. Отдаёт только своё.
    pubs = account_publishers(acc.id)
    return {"name": acc.name, "email": acc.email,
            "consent_required": getattr(acc, "consent_accepted_at", None) is None,
            "can_approve": bool(getattr(acc, "can_approve", True)),
            "publishers": [{"id": p.publisher_id, "name": p.name, "domain": p.domain}
                           for p in pubs]}


@app.post("/api/consent")
def accept_consent(acc=Depends(current_account_any)):
    """Принять согласие на обработку ПДн. Запись — функцией ядра `pub.accept_consent`:
    у роли кабинета нет права менять учётку, и заводить его ради одного поля значило бы
    расширить поверхность внешнего контура. Повторный вызов момент не сдвигает."""
    db = plain_session()
    try:
        at = db.execute(text("SELECT pub.accept_consent(:i)"), {"i": acc.id}).scalar()
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503,
                            detail="Не удалось сохранить согласие — попробуйте ещё раз")
    finally:
        db.close()
    return {"consent_required": False, "accepted_at": at}


@app.get("/api/tasks")
def tasks(acc=Depends(current_account)):
    """Задания на согласование, сгруппированные ПО ПЛОЩАДКЕ.

    Группировка не косметическая: учётка охватывает несколько сайтов, и без неё задания
    разных площадок сливаются в один список, где непонятно, о чьём инвентаре речь.

    Область видимости ставится из связки учётки, а не из запроса: клиент не может
    попросить чужую площадку, потому что он вообще не участвует в выборе.
    """
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        return {"publishers": [], "total": 0}

    with scoped_session(ids) as db:
        rows = db.execute(text("SELECT * FROM pub.task_v1 ORDER BY period_from, task_id")).all()
        files = db.execute(text("SELECT * FROM pub.task_file_v1 ORDER BY file_id")).all()

    by_task = {}
    for f in files:
        by_task.setdefault(f.task_id, []).append({
            "id": f.file_id, "name": f.name, "size": f.size,
            "is_archive": f.is_archive,
            "preview_url": sandbox_url(f.sandbox_token, f.entry_path)})

    groups = {}
    for r in rows:
        g = groups.setdefault(r.publisher_id, {
            "publisher_id": r.publisher_id, "name": r.publisher_name,
            "domain": r.publisher_domain, "tech_requirements": r.tech_requirements,
            "tasks": []})
        g["tasks"].append({
            "task_id": r.task_id,
            "creative_no": r.creative_no, "creative_title": r.creative_title,
            "form": r.form,
            "advertiser": r.advertiser, "brand": r.brand, "service": r.service,
            # Веб или приложение. Карточка печатала это поле с самого начала, но витрина
            # его не отдавала — и строка молча схлопывалась в одну услугу.
            "surface": r.surface_kind,
            "period_from": r.period_from, "period_to": r.period_to,
            "advertiser_url": r.advertiser_url,
            # ТТ площадки — её собственные требования к материалу. Лежат на строке
            # задания, а не только в шапке группы: на них смотрят, отвечая по креативу.
            "tech_requirements": r.tech_requirements,
            # Три ответа на «где ссылка»: есть / ждём от вас / не спрашивали. Правило
            # выведено в ядре (`url_state`), здесь только пересказ фактов — вторая копия
            # в SQL разошлась бы с первой.
            "url_state": ('есть' if r.advertiser_url
                          # Копия `url_state` из ядра (app/routers/launch_prep.py) —
                          # структурная, а не забытая: кабинет отдельный процесс под
                          # отдельной ролью БД и `app.*` не импортирует по построению.
                          # Три ответа менять ОДНОВРЕМЕННО в обоих местах.
                          else 'запрошена' if r.url_requested_at else 'нужна'),
            # Письмо о правах на изображения — приходит вместе с креативом, не
            # отдельным запросом: оно лежит на том же комплекте и появляется у площадки
            # ровно в момент, когда креатив поступил на согласование.
            "rights_letter": ({"name": r.rights_letter_name, "size": r.rights_letter_size}
                              if r.rights_letter_name else None),
            "url_request_text": r.url_request_text,
            "asked_at": r.asked_at,
            # Сутки МОСКОВСКИЕ. Обе даты лежали в UTC, и счёт сходился сам с собой —
            # но граница суток проходила на три часа позже: с полуночи до трёх ночи
            # площадке показывалось на день меньше, чем она ждёт на самом деле. Число
            # выглядело правдой, просто вчерашней.
            "waiting_days": (_msk_today() - _to_msk(r.asked_at).date()).days
                            if r.asked_at else None,
            "files": by_task.get(r.task_id, [])})

    ordered = sorted(groups.values(), key=lambda g: (g["name"] or '').lower())
    return {"publishers": ordered, "total": len(rows)}


@app.get("/api/health")
def health():
    return {"status": "ok"}


class CellIn(BaseModel):
    kind: str
    channel: str                   # 'бот' | 'почта' | 'дайджест'
    enabled: bool


class MailIn(BaseModel):
    # Часа здесь НЕТ: площадка его не выбирает, задаём мы (владелец 15.09.2026). Ручка
    # ядра его принимать умеет — это наш рычаг, а не её.
    enabled: Optional[bool] = None


@app.get("/api/notify-settings")
def notify_settings(acc=Depends(current_account)):
    """Матрица «событие × канал» и настройки почты — всё, что рисует экран.

    ТРИ СПОСОБА ДОСТАВКИ, и два из них — почта: письмом сразу или в утренней пачке
    (правка владельца 15.09.2026). Панели среди них нет: у паблишера панели уведомлений
    не существует, а лента кабинета — журнал наших с ним действий, а не канал.

    Каталог видов берётся у ЯДРА, а не хранится здесь: второй список меток разошёлся бы
    с первым молча — площадка увидела бы переключатель, который ничего не выключает.
    Показываются только ПОСТРОЕННЫЕ виды: выключатель у вида без отправителя — обещание,
    которого мы не держим.
    """
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="У учётки нет площадок")
    cat = call_core("GET", "/api/cabinet-gw/notify-kinds", None).get("kinds", [])
    st = call_core("GET", f"/api/cabinet-gw/account/{acc.id}/notify"
                          f"?publisher_id={pubs[0].publisher_id}", None)
    # Клетки приходят от ядра УЖЕ РАЗРЕШЁННЫМИ — с подставленным умолчанием. Считать
    # умолчание здесь значило бы завести его вторую копию во внешнем контуре, а оно
    # непростое: у бота одно, у двух почтовых колонок противоположные и зависят от
    # расписания вида.
    on = {(c["kind"], c["channel"]): c["enabled"] for c in st["cells"]}
    return {
        "mail": st["mail"], "bot": st["bot"],
        "kinds": [{**k,
                   "бот": on.get((k["key"], "бот"), True),
                   "почта": on.get((k["key"], "почта"), False),
                   "дайджест": on.get((k["key"], "дайджест"), True)}
                  for k in cat],
    }


@app.put("/api/notify-settings")
def set_notify_cell(payload: CellIn, acc=Depends(current_account)):
    """Переключить клетку. Пишет ядро — кабинет в базу не пишет по построению.

    `publisher_id` берётся из ПЕРВОЙ площадки учётки: ядру он нужен, чтобы независимо
    проверить связь учётки с площадкой. Сама настройка одна на учётку, а не на площадку:
    человек один, и «по этому сайту пишите, по тому нет» — это про сайты.
    """
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="У учётки нет площадок")
    call_core("PUT", f"/api/cabinet-gw/account/{acc.id}/notify",
              {"publisher_id": pubs[0].publisher_id, "kind": payload.kind,
               "channel": payload.channel, "enabled": payload.enabled,
               "author_name": acc.name})
    return notify_settings(acc)


@app.delete("/api/notify-settings")
def reset_notify(acc=Depends(current_account)):
    """«Вернуть по умолчанию»: снести отклонения. Час пачки не трогается — кнопка стоит
    под матрицей и обещает вернуть галочки, а не время рассылки."""
    from urllib.parse import quote
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="У учётки нет площадок")
    call_core("DELETE", f"/api/cabinet-gw/account/{acc.id}/notify"
                        f"?publisher_id={pubs[0].publisher_id}"
                        f"&author_name={quote(acc.name or '')}", None)
    return notify_settings(acc)


@app.put("/api/mail-settings")
def set_mail(payload: MailIn, acc=Depends(current_account)):
    """Получать ли почту вообще. Больше отсюда ничего не настраивается.

    ЧТО приходит пачкой, а что срочным письмом, решается в матрице у каждого события.
    Час пачки — 09:00 по времени ПЛОЩАДКИ, константа расписания: площадке он показан,
    но не предложен на выбор, и в базе его нет вовсе.
    """
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="У учётки нет площадок")
    call_core("PUT", f"/api/cabinet-gw/account/{acc.id}/mail",
              {"publisher_id": pubs[0].publisher_id, "enabled": payload.enabled,
               "author_name": acc.name})
    return notify_settings(acc)


@app.get("/api/campaigns")
def campaigns(acc=Depends(current_account)):
    """Актуальные кампании площадки — строка на размещение.

    Блок возвращён в кабинет 15.09.2026 по хендоффу и собирается из НАСТОЯЩИХ данных:
    до сих пор он жил в `lib/demo.js` под флагом `SHOW_MONEY = false`, то есть был
    выключенной выдумкой.

    ФЛАЙТ И ГОД СОБИРАЮТСЯ ЗДЕСЬ, а период компонент выводит из флайта сам. Так написано
    в хендоффе, и причина не косметическая: пока период был отдельным полем, пара
    «период ↔ срок РК» расходилась — декабрьский флайт лежал в сентябрьском периоде.
    Отдай мы готовый период, у экрана снова стало бы два источника одного числа.
    """
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        return {"campaigns": []}
    with scoped_session(ids) as db:
        rows = db.execute(text(
            "SELECT publisher_id, brand, service, surface, date_from, date_to, plan, "
            "       fact, cpm, status, erid, site, reconciled "
            "  FROM pub.campaign_v1")).all()

    out = []
    for r in rows:
        # «01.09 — 30.09» либо прочерк: срок может быть не задан, и выдумывать его нельзя.
        flight = ('%s — %s' % (r.date_from.strftime('%d.%m'), r.date_to.strftime('%d.%m'))
                  if r.date_from and r.date_to else '—')
        out.append({
            # Площадка — чтобы выбор площадки на дашборде сужал и денежные плитки, а не
            # только список заданий (аудит 23.09.2026, 7.L5).
            "publisher_id": r.publisher_id,
            "brand": r.brand, "service": r.service, "site": r.site,
            "surface": r.surface, "flight": flight,
            # Год — от НАЧАЛА флайта: у размещения, переходящего через новый год, период
            # считается по месяцу старта, и год обязан браться оттуда же.
            "year": (r.date_from or r.date_to).year if (r.date_from or r.date_to) else None,
            "plan": int(r.plan or 0), "fact": int(r.fact or 0),
            "cpm": float(r.cpm or 0), "status": r.status, "erid": r.erid or "",
            # Признак, а не отбор: блок дашборда показывает несверенное, экран
            # «Кампании» — всё. Один ответ на два экрана; фильтровать решает тот, кто
            # рисует, а считается признак в одном месте — в витрине.
            "reconciled": bool(r.reconciled),
            # Месяц собирается ЗДЕСЬ, из той же даты, из которой экран выводит период:
            # группировка по месяцам на экране «Кампании» и период в строке обязаны
            # совпадать, а два вычисления одного месяца однажды разошлись бы.
            "period": r.date_from.strftime('%Y-%m') if r.date_from else None,
        })
    return {"campaigns": out}


# ─────────────────────────── Лента событий ───────────────────────────
#
# ПАНЕЛЬ — ТРЕТИЙ КАНАЛ ДОСТАВКИ, и единственный, который нельзя выключить. До 15.09.2026
# его не было вовсе: журнал `cabinet_log` с самого начала объявлен «журналом с двумя
# читателями — админом и самой площадкой», и второй читатель полтора месяца не имел
# способа его прочесть. Поэтому лента не заводит своей таблицы: это тот же журнал, вид с
# внешней стороны.

FEED_LIMIT = 40          # столько влезает в блок, не превращая его в архив


@app.get("/api/feed")
def feed(acc=Depends(current_account)):
    """Что происходило по площадкам этой учётки.

    Подписи событий берутся у ЯДРА — там словарь, и вторая копия подписей разошлась бы с
    первой молча, ровно как каталог рассылки. Тон и сторона лежат в самой строке: они
    заданы событием в момент записи, и правка словаря не должна перекрашивать прошлое.
    """
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        return {"items": []}
    labels = {a["key"]: a["label"]
              for a in call_core("GET", "/api/cabinet-gw/log-actions", None)["actions"]}
    with scoped_session(ids) as db:
        rows = db.execute(text(
            "SELECT id, created_at, action, tone, side, actor_name, subject "
            "  FROM pub.log_v1 ORDER BY created_at DESC, id DESC LIMIT :n"),
            {"n": FEED_LIMIT}).all()
    return {"items": [_feed_item(r, labels) for r in rows]}


def _feed_item(r, labels):
    """Строка ленты для площадки.

    Время — МОСКОВСКОЕ. В `pub.log_v1` оно лежит в UTC, а экран берёт дату срезом
    строки: событие с 00:00 до 03:00 по Москве показывалось вчерашним днём (аудит
    23.09.2026).
    """
    return {
        "id": r.id, "at": _to_msk(r.created_at) if r.created_at else None,
        "tone": r.tone, "side": r.side,
        # Неизвестный ключ показываем КАК ЕСТЬ, а не прячем строку: пропавшее событие
        # выглядит как «ничего не было», и это худшая из двух неправд.
        "label": labels.get(r.action, r.action),
        "actor": r.actor_name, "subject": r.subject,
    }


# ─────────────────────────── Бот ───────────────────────────
#
# Бота человек подключает СЕБЕ САМ — за него это сделать нельзя, чат заводит он. Поэтому
# кнопка доступна каждому, кто вошёл, и с галочкой «получает уведомления» на контакте она
# не связана: та включает ПОЧТУ (владелец 15.09.2026).
#
# Всё состояние спрашивается у ядра одним вызовом: половина ответа живёт не в базе — имя
# бота ядро берёт у самого Телеграма, из него же собирается диплинк с кодом.


def _tg_publisher(acc) -> int:
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="У учётки нет площадок")
    return pubs[0].publisher_id


@app.get("/api/telegram")
def tg_state(acc=Depends(current_account)):
    return call_core("GET", f"/api/cabinet-gw/account/{acc.id}/tg"
                            f"?publisher_id={_tg_publisher(acc)}", None)


@app.post("/api/telegram/link")
def tg_link(acc=Depends(current_account)):
    """Получить код привязки. Повторный вызов выдаёт НОВЫЙ код и сбрасывает старый чат:
    «подключить заново» не должно оставлять получателем чат, откуда человек ушёл."""
    return call_core("POST", f"/api/cabinet-gw/account/{acc.id}/tg/link",
                     {"publisher_id": _tg_publisher(acc)})


@app.delete("/api/telegram")
def tg_unlink(acc=Depends(current_account)):
    from urllib.parse import quote
    return call_core("DELETE", f"/api/cabinet-gw/account/{acc.id}/tg"
                               f"?publisher_id={_tg_publisher(acc)}"
                               f"&author_name={quote(acc.name or '')}", None)


@app.get("/api/reasons")
def reasons(acc=Depends(current_account)):
    """Готовые формулировки причин. Два РАЗНЫХ списка, а не один.

    «Товара нет в наличии» закрывает площадку для кампании, «тяжёлый файл» просит новую
    версию. В общем списке человек выбирал бы из смеси несравнимого.
    """
    with scoped_session([]) as db:
        rows = db.execute(text(
            "SELECT kind, name FROM pub.reason_v1 ORDER BY kind, sort_order, name")).all()
    out = {"на доработку": [], "отказ": []}
    for r in rows:
        out.setdefault(r.kind, []).append(r.name)
    return out


# Пределы — те же, что проверяет ядро (`cabinet_gateway.MEDIA_KIT_MAX`, `REWORK_MAX`,
# `bugs.models.MAX_FILE_BYTES`). Решает ядро; здесь они нужны, чтобы кабинет не читал в
# память то, что ядро всё равно отклонит (аудит 23.09.2026, 1.M2).
MEDIA_KIT_MAX = 30 * 1024 * 1024
ATTACH_MAX = 10 * 1024 * 1024
CHUNK = 1024 * 1024


async def read_capped(file: UploadFile, limit: int) -> bytes:
    """Прочитать файл порциями и отказать 413 на первой порции сверх предела.

    До 23.09.2026 файлы читались целиком одним вызовом, и учётка площадки,
    прислав сотни мегабайт, роняла процесс кабинета по памяти — повторяемо.
    """
    parts, total = [], 0
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413,
                                detail=f"Файл больше {limit // 1024 // 1024} МБ")
        parts.append(chunk)
    return b"".join(parts)


def require_approver(acc) -> None:
    """«Только просмотр» — значит только просмотр (владелец 24.09.2026).

    Роль внутри кабинета проверяет КАБИНЕТ: у ядра своя матрица прав, к этой отношения не
    имеющая (шлюз ядра всё равно перепроверяет — проверка на одной стороне не проверка).
    До 24.09 запрет стоял только на вердикте, а посадочную ссылку, медиакит и файл к
    доработке «только просмотр» менял наравне с ответственным (аудит, 1.L3).
    """
    if not getattr(acc, "can_approve", True):
        raise HTTPException(
            status_code=403,
            detail="У вас доступ только на просмотр — это делает ваш коллега")


class VerdictIn(BaseModel):
    verdict: str                       # ок | на доработку | отказ
    reason: Optional[str] = None


@app.post("/api/tasks/{task_id}/verdict")
def set_verdict(task_id: int, payload: VerdictIn, acc=Depends(current_account)):
    """Ответ площадки. ТРИ исхода, и третий — не разновидность второго.

    Доработка просит новый файл, отказ говорит, что файл ни при чём: площадка выходит из
    кампании, и обратного перехода у неё нет. Поэтому причина обязательна для обоих, а
    списки причин разные.

    Проверок здесь только две — что задание наше и что вердикт из перечня. Всё
    остальное проверяет ядро: неизменяемость, порядок относительно трафика, выдачу кода
    пары. Дублировать их тут значило бы завести вторую версию правил.
    """
    if payload.verdict not in ("ок", "на доработку", "отказ"):
        raise HTTPException(status_code=400, detail="Неизвестный ответ")
    # Технический специалист смотрит баннер, коммерческий отвечает за размещение.
    require_approver(acc)
    t = my_task(acc, task_id)
    out = call_core("POST", f"/api/cabinet-gw/pair/{task_id}/verdict", {
        "publisher_id": t.publisher_id,
        # Номер учётки — не «для журнала»: ядро по нему само проверяет право говорить за
        # эту площадку. До 30.08.2026 такой проверки не было ни в одной из ручек.
        "account_id": acc.id,
        "verdict": payload.verdict,
        "reason": payload.reason,
        # Снимок автора: людей за одной площадкой несколько, и через год «Иванов»
        # перестанет отличаться от другого «Иванова».
        "author_name": acc.name,
        "author_email": acc.email,
    })
    return out


class UrlIn(BaseModel):
    url: str


@app.put("/api/tasks/{task_id}/url")
def set_url(task_id: int, payload: UrlIn, acc=Depends(current_account)):
    """Посадочная страница в ответ на наш запрос.

    Живёт у ЗАДАНИЯ — пары «креатив × площадка» (с 25.09.2026): у разных креативов одной
    площадки в одной РК посадочные бывают разные, поэтому ссылка ложится ровно в этот
    креатив, а не на площадку сделки.
    """
    t = my_task(acc, task_id)          # сначала «есть ли такое задание» — 404 раньше 403
    require_approver(acc)
    return call_core("PUT", f"/api/cabinet-gw/task/{task_id}/url", {
        "publisher_id": t.publisher_id,
        "account_id": acc.id,
        "url": payload.url,
        "author_name": acc.name,
    })


@app.get("/api/dashboard")
def dashboard(acc=Depends(current_account)):
    """Всё, что рисует экран кабинета, ОДНИМ ответом.

    Тем же приёмом, что сборка креативов в ядре: несколько запросов на один экран дают
    мигание и рассинхрон, когда часть уже обновилась, а часть нет.

    Денег здесь нет. Не «пока не показываем», а нет в контракте: `pub.*_v1` их не несёт,
    и прибор со стороны ядра это стережёт. Кампании и суммы на экране — статика на
    фронте (владелец 28.08.2026), и она нарочно живёт отдельным файлом, чтобы её нельзя
    было спутать с настоящими данными.
    """
    ids = [p.publisher_id for p in account_publishers(acc.id)]
    if not ids:
        return {"profile": None, "team": [], "done": [], "documents": [],
                "publishers": []}

    with scoped_session(ids) as db:
        profiles = db.execute(text("SELECT * FROM pub.profile_v1 ORDER BY name")).all()
        # Порядок — из настройки, а не по алфавиту: первым площадка видит того, к кому
        # идти сначала (`cabinet_our_contact.sort_order`).
        team = db.execute(text(
            "SELECT * FROM pub.team_v1 ORDER BY sort_order, name")).all()
        done = db.execute(text(
            "SELECT * FROM pub.done_v1 WHERE decided_at > now() - interval '7 days' "
            "ORDER BY decided_at DESC")).all()
        docs = db.execute(text("SELECT * FROM pub.document_v1 ORDER BY uploaded_at DESC")).all()
        svc = db.execute(text(
            "SELECT * FROM pub.publisher_service_v1 ORDER BY sort_order, service")).all()
        legals = db.execute(text(
            "SELECT * FROM pub.counterparty_v1 ORDER BY name")).all()
        contracts = db.execute(text(
            "SELECT * FROM pub.contract_v1 "
            " ORDER BY is_archived, signed_at DESC NULLS LAST, number")).all()

    by_id = {r.publisher_id: r.name for r in profiles}

    # Поверхности сворачиваются ЗДЕСЬ, а не в представлении: «еФарм WEB · APP» одной
    # строкой — решение экрана, и второе такое решение в SQL разошлось бы с первым.
    folded: dict = {}
    for r in svc:
        folded.setdefault((r.publisher_id, r.service), []).append(r.surface_kind)

    # ── к какому юрлицу относится договор ─────────────────────────────────────
    #
    # У договора с карточкой юрлицо известно (`contracts.counterparty_id`). У 26 из 47
    # карточки нет — они заведены голым номером. Раньше такие висели отдельным списком,
    # и у служебной учётки это были два десятка строк с одинаковым номером: договор
    # заведён на КАЖДОЙ площадке отдельно, а список показывал их без площадки.
    #
    # Правило: договор без карточки относится к юрлицу СВОЕЙ площадки — не к
    # произвольному. Это однозначно, пока у площадки юрлицо одно (замер 30.08.2026:
    # одно у всех 38). Где их ноль или больше одного, договор остаётся неразложенным и
    # попадает в счётчик, а не приписывается наугад.
    def contract(r):
        return {"number": r.number, "signed_at": r.signed_at,
                "valid_until": r.valid_until, "role": r.role,
                "is_archived": bool(r.is_archived), "has_file": bool(r.has_file),
                "publisher_id": r.publisher_id, "counterparty_id": r.counterparty_id}

    def prof(r):
        return {"publisher_id": r.publisher_id, "name": r.name, "domain": r.domain,
                "kind": r.kind, "network": r.network,
                "chat_title": r.chat_title, "chat_url": r.chat_url,
                "chat_url_max": r.chat_url_max,
                "media_kit": r.media_kit_filename,
                "tech_requirements": r.tech_requirements,
                # Доп. каналы связи: запасной чат на случай блокировок основного.
                "messenger_note": r.messenger_note}

    by_pub_legals: dict = {}
    for r in legals:
        by_pub_legals.setdefault(r.publisher_id, []).append(r)

    legal_cards = []
    for r in legals:
        own = [c for c in contracts
               if c.publisher_id == r.publisher_id
               and (c.counterparty_id == r.counterparty_id
                    or (c.counterparty_id is None
                        and len(by_pub_legals.get(r.publisher_id, [])) == 1))]
        legal_cards.append({
            "counterparty_id": r.counterparty_id, "publisher_id": r.publisher_id,
            "publisher": by_id.get(r.publisher_id),
            "name": r.name, "inn": r.inn, "vat_rate": r.vat_rate,
            "contracts": [contract(c) for c in own]})

    unassigned = [c for c in contracts
                  if c.counterparty_id is None
                  and len(by_pub_legals.get(c.publisher_id, [])) != 1]

    return {
        # Первая площадка — «своя» для шапки. У учётки их может быть несколько: тогда
        # шапка показывает первую, а переключение между ними — задача следующего слоя.
        "profile": prof(profiles[0]) if profiles else None,
        "publishers": [prof(r) for r in profiles],
        # Юрлица площадки — по одной плашке на юрлицо, договоры внутри. Разложены ЗДЕСЬ,
        # а не на экране: «к какому юрлицу относится договор» — правило, а не вёрстка, и
        # оно должно быть в одном месте. Договор без карточки юрлица не приписывается
        # никому: он идёт отдельной группой, иначе площадка увидела бы его под чужими
        # реквизитами.
        "legals": legal_cards,
        # Не список, а ЧИСЛО: развесить эти договоры не по чему, и перечислять их
        # площадке нечем помочь — она увидит десяток одинаковых номеров и придёт
        # спрашивать. Число говорит ровно то, что известно: столько-то не разложено.
        "contracts_unassigned": len(unassigned),
        # Услуги, закреплённые за площадками: площадка проверяет, верно ли мы её завели.
        "services": [{"publisher_id": pid, "service": name,
                      "surfaces": sorted(set(surfaces))}
                     for (pid, name), surfaces in folded.items()],
        # Один человек на роль, а не строка на каждую площадку: витрина отдаёт команду
        # ПО ПЛОЩАДКЕ, и у учётки с сорока одной площадкой один и тот же аккаунт
        # приходил бы сорок один раз. Сводим здесь, а не в SQL: там `DISTINCT` не
        # помогает — строки различаются номером площадки, который экрану не нужен.
        "team": list({(r.name, r.role): {"name": r.name, "role": r.role, "email": r.email}
                      for r in team}.values()),
        # Имя площадки подставляется ЗДЕСЬ, а не добавляется в `pub.done_v1`: профили
        # уже загружены тем же запросом выше, и лишняя колонка во внешней витрине — это
        # расширение контракта ради того, что и так под рукой.
        "done": [{"task_id": r.task_id, "creative_no": r.creative_no,
                  "creative_title": r.creative_title, "advertiser": r.advertiser,
                  "brand": r.brand, "service": r.service, "verdict": r.verdict,
                  "reason": r.reason, "decided_at": r.decided_at,
                  "decided_by": r.decided_by,
                  "publisher_id": r.publisher_id,
                  "publisher": by_id.get(r.publisher_id)} for r in done],
        "documents": [{"id": r.id, "type": r.doc_type, "name": r.filename,
                       "note": r.note, "uploaded_at": r.uploaded_at} for r in docs],
    }


@app.post("/api/media-kit")
async def media_kit(file: UploadFile = File(...), acc=Depends(current_account)):
    """Медиакит площадки. Один файл, PDF или PPTX, новый замещает старый.

    Кабинет файл НЕ пишет: том с загрузками смонтирован только в ядро, и давать внешнему
    процессу право писать в общее хранилище значило бы отдать ему ровно то, ради чего он
    вынесен отдельно. Пересылаем в ядро тем же сервисным секретом, что и вердикт.

    Принадлежность площадки проверяется ЗДЕСЬ: только кабинет знает, какие площадки у
    этой учётки. У учётки с несколькими площадками медиакит грузится в первую — выбор
    появится вместе с переключателем площадки в шапке.
    """
    require_approver(acc)
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")

    data = await read_capped(file, MEDIA_KIT_MAX)
    try:
        r = httpx.post(
            f"{CORE_API_URL}/api/cabinet-gw/publisher/{pubs[0].publisher_id}/media-kit",
            params={"account_id": acc.id},
            files={"file": (file.filename, data,
                            file.content_type or "application/octet-stream")},
            headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=60.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503,
                            detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or "Не удалось загрузить"
        except Exception:      # noqa: BLE001 — ядро могло ответить не JSON
            detail = "Не удалось загрузить"
        raise HTTPException(status_code=r.status_code if r.status_code < 500 else 502,
                            detail=detail)
    return r.json()


@app.get("/api/tasks/{task_id}/rights-letter")
def rights_letter(task_id: int, acc=Depends(current_account)):
    """Скачать письмо о правах. Файл отдаёт ЯДРО — том с загрузками смонтирован только
    туда, кабинет видит лишь `pub.*`.

    Через песочницу нельзя: она раздаётся БЕЗ авторизации (иначе баннер не откроется в
    рамке), а документ о правах не должен лежать по угадываемой ссылке.
    """
    t = my_task(acc, task_id)
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")
    try:
        r = httpx.get(f"{CORE_API_URL}/api/cabinet-gw/task/{t.task_id}/rights-letter",
                      params={"account_id": acc.id, "publisher_id": t.publisher_id},
                      headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=60.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503,
                            detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        raise HTTPException(status_code=404, detail="Письмо не найдено")
    return Response(content=r.content,
                    media_type=r.headers.get("content-type", "application/octet-stream"),
                    headers={"Content-Disposition":
                             r.headers.get("content-disposition", "attachment")})


@app.get("/api/tasks/{task_id}/files/{file_id}")
def creative_file(task_id: int, file_id: int, acc=Depends(current_account)):
    """Скачать баннер задания (владелец 25.09.2026). Файл отдаёт ЯДРО и само проверяет,
    что файл от креатива этого задания, — кабинет здесь лишь проверяет, что задание своё.
    """
    t = my_task(acc, task_id)
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")
    try:
        r = httpx.get(f"{CORE_API_URL}/api/cabinet-gw/task/{t.task_id}/file/{file_id}",
                      params={"account_id": acc.id, "publisher_id": t.publisher_id},
                      headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=120.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503,
                            detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        raise HTTPException(status_code=404, detail="Креатив не найден")
    return Response(content=r.content, media_type="application/octet-stream",
                    headers={"Content-Disposition":
                             r.headers.get("content-disposition", "attachment")})


class BugIn(BaseModel):
    comment: str
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    app_version: Optional[str] = None
    viewport: Optional[str] = None


@app.post("/api/bug")
def bug_create(payload: BugIn, acc=Depends(current_account)):
    """Заявка о сбое из кабинета. Кабинет в базу не пишет — просит об этом ядро.

    Площадка попадает в заявку НЕ из запроса, а берётся у учётки: подставить её снаружи
    означало бы разрешить писать от чужого имени.
    """
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=400, detail="За учёткой не закреплена площадка")
    return call_core("POST", f"/api/cabinet-gw/account/{acc.id}/bug",
               {"publisher_id": pubs[0].publisher_id, **payload.dict()})


@app.post("/api/bug/{report_id}/file")
async def bug_file(report_id: int, file: UploadFile = File(...),
                   acc=Depends(current_account)):
    """Снимок к заявке. Файл пишет ядро — том смонтирован только туда."""
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")
    data = await read_capped(file, ATTACH_MAX)
    try:
        r = httpx.post(f"{CORE_API_URL}/api/cabinet-gw/bug/{report_id}/file",
                       params={"account_id": acc.id},
                       files={"file": (file.filename, data,
                                       file.content_type or "application/octet-stream")},
                       headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=60.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503,
                            detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or "Не удалось приложить снимок"
        except Exception:      # noqa: BLE001
            detail = "Не удалось приложить снимок"
        raise HTTPException(status_code=r.status_code if r.status_code < 500 else 502,
                            detail=detail)
    return r.json()


@app.post("/api/bug/{report_id}/sent")
def bug_sent(report_id: int, acc=Depends(current_account)):
    """Заявка дописана — ядро уведомляет владельца."""
    return call_core("POST", f"/api/cabinet-gw/bug/{report_id}/sent?account_id={acc.id}", None)


@app.post("/api/tasks/{task_id}/rework-file")
async def rework_file(task_id: int, file: UploadFile = File(...),
                      acc=Depends(current_account)):
    """Приложить картинку к доработке. Файл пишет ядро — том смонтирован только туда."""
    t = my_task(acc, task_id)          # сначала «есть ли такое задание» — 404 раньше 403
    require_approver(acc)
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")
    data = await read_capped(file, ATTACH_MAX)
    try:
        r = httpx.post(f"{CORE_API_URL}/api/cabinet-gw/pair/{t.task_id}/rework-file",
                       params={"account_id": acc.id},
                       files={"file": (file.filename, data,
                                       file.content_type or "application/octet-stream")},
                       headers={"X-Cabinet-Token": SERVICE_TOKEN}, timeout=60.0)
    except httpx.RequestError:
        raise HTTPException(status_code=503,
                            detail="Система временно недоступна — попробуйте позже")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or "Не удалось приложить файл"
        except Exception:      # noqa: BLE001 — ядро могло ответить не JSON
            detail = "Не удалось приложить файл"
        raise HTTPException(status_code=r.status_code if r.status_code < 500 else 502,
                            detail=detail)
    return r.json()
