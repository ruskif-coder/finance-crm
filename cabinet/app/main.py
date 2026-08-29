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
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import (account_publishers, current_account, find_account, make_token,
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


@app.post("/api/login")
def login(payload: LoginIn):
    """Вход. Одинаковый ответ на «нет такой учётки» и «неверный пароль».

    Проверка пароля прогоняется даже для несуществующего адреса: иначе разница во
    времени ответа отвечает на вопрос «а заведён ли у вас такой человек» — а это
    перечисление учёток внешнего контура.

    Блокировка после серии неудач (30.08.2026) — от ПЕРЕБОРА, тогда как всё выше от
    ПЕРЕЧИСЛЕНИЯ. Для внешнего контура перебор опаснее: туда ходят не наши сотрудники,
    адрес входа известен площадке, и учётка у кабинета обычно одна.
    """
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
    return {"token": make_token(row.id, row.email),
            "name": row.name, "email": row.email,
            "publishers": [{"id": p.publisher_id, "name": p.name, "domain": p.domain}
                           for p in pubs]}


@app.get("/api/me")
def me(acc=Depends(current_account)):
    pubs = account_publishers(acc.id)
    return {"name": acc.name, "email": acc.email,
            "can_approve": bool(getattr(acc, "can_approve", True)),
            "publishers": [{"id": p.publisher_id, "name": p.name, "domain": p.domain}
                           for p in pubs]}


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
            "url_request_text": r.url_request_text,
            "asked_at": r.asked_at,
            "waiting_days": (datetime.now(timezone.utc).date() - r.asked_at.date()).days
                            if r.asked_at else None,
            "files": by_task.get(r.task_id, [])})

    ordered = sorted(groups.values(), key=lambda g: (g["name"] or '').lower())
    return {"publishers": ordered, "total": len(rows)}


@app.get("/api/health")
def health():
    return {"status": "ok"}


class MuteIn(BaseModel):
    kind: str
    muted: bool


@app.get("/api/notify-settings")
def notify_settings(acc=Depends(current_account)):
    """Что площадке приходит и что она отключила.

    Каталог видов берётся у ЯДРА, а не хранится здесь: второй список меток разошёлся бы
    с первым, и разошёлся бы молча — площадка увидела бы переключатель, который ничего
    не выключает. Выключенное читается напрямую из `pub.mute_v1`: это чтение, для него
    ходить в ядро незачем.
    """
    cat = call_core("GET", "/api/cabinet-gw/notify-kinds", None).get("kinds", [])
    db = plain_session()
    try:
        muted = {k for (k,) in db.execute(
            text("SELECT kind FROM pub.mute_v1 WHERE account_id = :a"),
            {"a": acc.id}).all()}
    finally:
        db.close()
    return {"kinds": [{**k, "muted": k["key"] in muted} for k in cat]}


@app.put("/api/notify-settings")
def set_notify_setting(payload: MuteIn, acc=Depends(current_account)):
    """Переключить вид. Пишет ядро — кабинет в базу не пишет по построению.

    `publisher_id` берётся из ПЕРВОЙ площадки учётки: ядру он нужен, чтобы независимо
    проверить, что учётка и площадка связаны. Настройка при этом одна на учётку, а не
    на площадку: человек один, и «по этому сайту пишите, по тому нет» — это про сайты,
    а не про то, что он читает.
    """
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="У учётки нет площадок")
    out = call_core("PUT", f"/api/cabinet-gw/account/{acc.id}/mute",
                    {"publisher_id": pubs[0].publisher_id, "kind": payload.kind,
                     "muted": payload.muted, "author_name": acc.name})
    return out


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
    # Роль внутри кабинета проверяет КАБИНЕТ: ядро о ней не знает и знать не должно —
    # у него своя матрица прав, к этой отношения не имеющая. Технический специалист
    # смотрит баннер, коммерческий отвечает за размещение.
    if not getattr(acc, "can_approve", True):
        raise HTTPException(
            status_code=403,
            detail="У вас доступ только на просмотр — ответ ставит ваш коллега")
    t = my_task(acc, task_id)
    out = call_core("POST", f"/api/cabinet-gw/pair/{task_id}/verdict", {
        "publisher_id": t.publisher_id,
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

    Живёт на РАЗМЕЩЕНИИ (сделка × площадка), а не на креативе: страница одна на всю
    кампанию у этого сайта. Поэтому у второго креатива той же сделки она появится сама.
    """
    t = my_task(acc, task_id)
    return call_core("PUT", f"/api/cabinet-gw/target/{t.target_id}/url", {
        "publisher_id": t.publisher_id,
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
        team = db.execute(text("SELECT * FROM pub.team_v1 ORDER BY role, name")).all()
        done = db.execute(text(
            "SELECT * FROM pub.done_v1 WHERE decided_at > now() - interval '7 days' "
            "ORDER BY decided_at DESC")).all()
        docs = db.execute(text("SELECT * FROM pub.document_v1 ORDER BY uploaded_at DESC")).all()

    def prof(r):
        return {"publisher_id": r.publisher_id, "name": r.name, "domain": r.domain,
                "kind": r.kind, "network": r.network,
                "chat_title": r.chat_title, "chat_url": r.chat_url,
                "chat_url_max": r.chat_url_max,
                "media_kit": r.media_kit_filename,
                "tech_requirements": r.tech_requirements}

    return {
        # Первая площадка — «своя» для шапки. У учётки их может быть несколько: тогда
        # шапка показывает первую, а переключение между ними — задача следующего слоя.
        "profile": prof(profiles[0]) if profiles else None,
        "publishers": [prof(r) for r in profiles],
        # Один человек на роль, а не строка на каждую площадку: витрина отдаёт команду
        # ПО ПЛОЩАДКЕ, и у учётки с сорока одной площадкой один и тот же аккаунт
        # приходил бы сорок один раз. Сводим здесь, а не в SQL: там `DISTINCT` не
        # помогает — строки различаются номером площадки, который экрану не нужен.
        "team": list({(r.name, r.role): {"name": r.name, "role": r.role, "email": r.email}
                      for r in team}.values()),
        "done": [{"task_id": r.task_id, "creative_no": r.creative_no,
                  "creative_title": r.creative_title, "advertiser": r.advertiser,
                  "brand": r.brand, "service": r.service, "verdict": r.verdict,
                  "reason": r.reason, "decided_at": r.decided_at,
                  "decided_by": r.decided_by} for r in done],
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
    pubs = account_publishers(acc.id)
    if not pubs:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")

    data = await file.read()
    try:
        r = httpx.post(
            f"{CORE_API_URL}/api/cabinet-gw/publisher/{pubs[0].publisher_id}/media-kit",
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


@app.post("/api/tasks/{task_id}/rework-file")
async def rework_file(task_id: int, file: UploadFile = File(...),
                      acc=Depends(current_account)):
    """Приложить картинку к доработке. Файл пишет ядро — том смонтирован только туда."""
    t = my_task(acc, task_id)
    if not SERVICE_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Кабинет не настроен на связь с системой")
    data = await file.read()
    try:
        r = httpx.post(f"{CORE_API_URL}/api/cabinet-gw/pair/{t.task_id}/rework-file",
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
