# -*- coding: utf-8 -*-
"""Креатив НАЦЕЛИВАНИЯ в DSP: чтобы трафик увидел наш баннер на живом сайте до старта.

НЕ ПУТАТЬ С ПРЕДПРОСМОТРОМ. Это разные функции, обращающиеся к одному и тому же архиву
креатива (владелец 12.09.2026):

  · **предпросмотр** — посмотреть баннер у нас, в песочнице (`launch_prep/sandbox.py`,
    компонент `CreativePreview`, иконка глаза в очереди). Ничего наружу не уходит;
  · **нацеливание** — увидеть тот же баннер НА САЙТЕ ПЛОЩАДКИ, в настоящей выдаче, до
    того как размещение запущено. Для этого баннер обязан существовать в DSP, а браузер
    трафика — быть привязан к нему ссылкой нацеливания (`app/dsp/targeting_link.py`).

Этот модуль отвечает за вторую половину: он заводит в DSP тот самый креатив, на который
потом выпускается ссылка.

ЗАЧЕМ ОТДЕЛЬНЫЙ КРЕАТИВ, А НЕ БОЕВОЙ. Боевой попадает в DSP только после согласования
площадки — раньше нельзя, площадку ещё могут снять, а удалять в DSP нечем (замер
12.09.2026: на стадии «у трафика» хеш есть у 0 креативов из 205). Нацеливание же нужно
ДО согласования, поэтому на отправку трафику заводится второй, отдельный креатив — в
кабинете демоклиента, где такие и живут.

ГДЕ ИМЕННО. Кабинет и кампания заданы настройкой (`Трафики → Каталог → Скрипты сайта`),
а не зашиты: их меняют в кабинете DSP, и смена не должна требовать выкладки. В DSP нет
сущности «клиент» со своим хешем — есть партнёр (кабинет) и его кампании, поэтому
демоклиент это ДРУГОЙ `partner_xxhash`, а не поле.

ЧЕГО В ЭТОМ КРЕАТИВЕ НЕТ НАМЕРЕННО:

  · **счётчиков площадки** — они отправляют данные о показе, а показ нацеливания это
    проверка, а не открутка;
  · **пикселя Weborama** — то есть поля `pixel` у креатива DSP: это одно и то же, тег
    верификатора кладётся именно туда. Его показы попали бы в сверку с верификатором и
    испортили бы её. Пометка «обязателен для ротации» в их доке относится к боевой
    выдаче: **на демо пиксель не нужен** (владелец 12.09.2026);
  · **настоящего ЕРИД** — на отправке трафику маркера ещё нет: он выпускается после
    согласования площадки. Вместо него стоит одна общая заглушка `TEST_ERID` — без
    маркера DSP не запускает креатив, и проверка не состоялась бы вовсе. Подставлять
    ЧУЖОЙ настоящий маркер нельзя ни при каких обстоятельствах.

Скрипт видимости оставлен: его требует сам DSP, и на внешний вид он не влияет.

ИДЕМПОТЕНТНОСТЬ. Повторная отправка комплекта не должна заводить второй такой же креатив.
Защита та же трёхступенчатая, что у боевого заведения: сохранённый хеш → хеш в журнале по
нашему `local_ref` (DSP создал, наш коммит не дошёл) → только тогда `Creative.add`.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dsp import creatives as cr
from app.dsp.client import MsClient, MsError
from app.files_safe import inside_uploads
from app.dsp.targeting_link import ENV_ADMIN_URL
from app.launch_prep.models import LaunchPrepCreativeFile, LaunchPrepCreativeSet

log = logging.getLogger("finance.dsp")

UPLOADS_ROOT = "/app/uploads"

# Приставка к имени: наши креативы лежат в чужом кабинете вперемешку с чужими, и отличить
# их с одного взгляда должно быть можно без нашей базы.
TITLE_PREFIX = "НАЦЕЛИВАНИЕ · "

# Куда ведёт креатив, когда вести некуда. Поле `link` в API обязательное, а посадочной
# страницы на отправке трафику обычно ещё нет — и это НЕ повод не выдать нацеливание.
# Наш сайт честнее выдуманного адреса: по такому баннеру не кликают, а если кликнут,
# будет видно, чей это тест.
FALLBACK_LINK = "https://simb-ad.com"

# МАРКЕР-ЗАГЛУШКА ДЛЯ НАЦЕЛИВАНИЯ (владелец 18.09.2026).
#
# На отправке трафику настоящего ЕРИД ещё нет и быть не может: маркер выпускается после
# согласования площадки. А DSP без маркера креатив не запускает — и проверка,
# ради которой всё затевалось, не состоится вовсе.
#
# Поэтому здесь стоит ОДИН И ТОТ ЖЕ выдуманный маркер на все креативы нацеливания:
#
#   · один на всех — чтобы его нельзя было спутать с настоящим ни глазом, ни поиском:
#     увидев его дважды в разных кампаниях, человек сразу понимает, что это заглушка;
#   · той же длины и формы, что настоящий (9 знаков, буквы и цифры) — иначе DSP
#     отвергнет его форматом, а мы будем искать причину не там;
#   · только в кабинете демоклиента. В боевой креатив он не попадает НИКОГДА: там стоит
#     отдельный заслон `dsp.provision._blocker`, который отказывает при пустом маркере,
#     и подменять его заглушкой нельзя — это была бы реклама без маркировки.
TEST_ERID = "TEST00000"


class TargetingCreativeError(RuntimeError):
    """Креатив нацеливания завести нельзя, и причина называется человеку."""


def _client(partner: str) -> MsClient:
    return MsClient(partner_xxhash=partner)


def _archive(db: Session, s: LaunchPrepCreativeSet) -> LaunchPrepCreativeFile:
    """Архив креатива — тот же самый, что показывает предпросмотр.

    Загрузчик DSP принимает ZIP, и это ограничение ЕГО, а не наше: картинка тем же путём
    не поедет. Сказать об этом надо прямо, иначе кнопка просто «не работает».
    """
    f = (db.query(LaunchPrepCreativeFile)
         .filter(LaunchPrepCreativeFile.set_id == s.id,
                 LaunchPrepCreativeFile.is_archive.is_(True))
         .order_by(LaunchPrepCreativeFile.id).first())
    if not f:
        raise TargetingCreativeError(
            "В комплекте нет HTML5-архива — загрузчик DSP принимает только zip")
    return f


def _landing(db: Session, s: LaunchPrepCreativeSet) -> str:
    """Ссылка перехода у креатива. Поле обязательное в API, но НЕ предмет проверки.

    **Задача модуля — выдать нацеливание, а не проверить готовность размещения**
    (владелец 12.09.2026: «мы не должны проверять вызов на посадочной, наша задача только
    получить нацеливание, остальное работа трафика»). Посадочную запрашивают у площадки
    отдельным ходом, и на отправке трафику её обычно ещё нет; отказывать из-за неё значило
    бы, что кнопка не работает ровно тогда, когда нужна.

    Поэтому здесь нет ни одной ветки отказа: лестница предпочтений, последняя ступень
    которой всегда даёт адрес. Держит это прибор, проверяющий отсутствие `raise`.
    """
    url = db.execute(text("""
        SELECT t.advertiser_url
          FROM launch_prep_pair pr
          JOIN launch_prep_target t ON t.id = pr.target_id
         WHERE pr.set_id = :s AND coalesce(t.advertiser_url, '') <> ''
         ORDER BY pr.id LIMIT 1"""), {"s": s.id}).scalar()
    if not url:
        url = db.execute(text("""
            SELECT t.advertiser_url FROM launch_prep_target t
             WHERE t.deal_id = :d AND coalesce(t.advertiser_url, '') <> ''
             ORDER BY t.id LIMIT 1"""), {"d": s.deal_id}).scalar()
    if not url:
        url = db.execute(text("""
            SELECT a.website FROM sales_deals d
              JOIN sales_advertisers a ON a.id = d.advertiser_id
             WHERE d.id = :d AND coalesce(a.website, '') <> ''"""),
            {"d": s.deal_id}).scalar()
    url = (url or "").strip() or FALLBACK_LINK
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _read(f: LaunchPrepCreativeFile) -> bytes:
    path = inside_uploads(f.path, root=UPLOADS_ROOT)
    if path is None:
        raise TargetingCreativeError(f"некорректный путь файла в базе: {f.path}")
    if not os.path.exists(path):
        raise TargetingCreativeError(f"файл не найден в хранилище: {f.path}")
    with open(path, "rb") as fh:
        return fh.read()


def _html_state(c: MsClient, xxhash: str) -> str:
    """Что с креативом в кабинете: `ok` — код на месте, `empty` — объект без кода,
    `gone` — такого нет.

    Недоступность DSP отдельным исходом НЕ делаем: молчащая связь не должна выглядеть
    как «всё хорошо», поэтому ошибка обмена поднимается наверх и человек видит её текстом.
    """
    try:
        info = c.creative_get_info(xxhash) or {}
    except MsError as e:
        if "not found" in str(e).lower():
            return "gone"
        raise
    data = info.get("data") if isinstance(info, dict) else None
    html = (data or {}).get("html_code") if isinstance(data, dict) else None
    return "ok" if (html or "").strip() else "empty"


def _html_of(db: Session, s: LaunchPrepCreativeSet, c: MsClient, ref: str) -> str:
    """HTML баннера: архив заливается загрузчиком, он же и отдаёт код."""
    f = _archive(db, s)
    up = cr.upload_zip(c, _read(f), filename=(f.original_name or "creative.zip"),
                       local_ref=ref)
    return up["html"]


def ensure(db: Session, s: LaunchPrepCreativeSet, *,
           client: Optional[MsClient] = None) -> str:
    """Хеш креатива нацеливания для комплекта; заводит его, если ещё нет."""
    from app.routers.traffic_catalog import targeting_cabinet, viewability_src

    partner, campaign = targeting_cabinet(db)
    if not partner or not campaign:
        raise TargetingCreativeError(
            "Не задан кабинет или кампания нацеливания: Трафики → Каталог → Скрипты сайта")

    c = client or _client(partner)
    ref = f"tgt{s.id}"

    # КАМПАНИЮ ГОТОВИМ ПО ХОДУ ДЕЛА, а не требуем готовой. Полигон нацеливания живёт
    # ровно столько, сколько нужно проверке, и продлевается в момент получения — так
    # решил владелец 17.09.2026.
    wake_campaign(db, client=c)

    # Уже заведённый креатив ПРОВЕРЯЕМ, а не берём на веру. Причина конкретная: объект
    # создаётся одним вызовом, а HTML вшивается вторым, и между ними связь может
    # оборваться. Тогда в кабинете остаётся креатив БЕЗ КОДА — ссылка на него
    # выпускается, открывается и показывает пустую страницу, по которой человек делает
    # вывод «баннер не загрузился» и идёт искать причину не там (владелец 17.09.2026:
    # «а как убедиться, что баннер загружен?»).
    known = s.ms_targeting_creative_xxhash or c.last_ok_xxhash("Creative.add", "creative", ref)
    if known:
        state = _html_state(c, known)
        if state == "ok":
            return _persist(db, s, known)
        if state == "empty":
            # Объект есть, кода нет — дошиваем его, а не заводим второй: второй в чужом
            # кабинете уже не удалить.
            html = cr.wrap_html(_html_of(db, s, c, ref), erid=TEST_ERID,
                                viewability_src=viewability_src(db))
            c.creative_edit(known, {"data": {"html_code": html}}, local_ref=ref)
            return _persist(db, s, known)
        # state == "gone" — креатив снесли в кабинете руками: заводим заново.
        log.warning("DSP: креатив нацеливания %s не найден в кабинете, завожу заново", known)
        s.ms_targeting_creative_xxhash = None

    f = _archive(db, s)
    link = _landing(db, s)
    try:
        up = cr.upload_zip(c, _read(f), filename=(f.original_name or "creative.zip"),
                           local_ref=ref)
        # Маркер и в ТЕЛЕ креатива, не только в поле: DSP показывает плашку по разметке,
        # и креатив без неё на демо-показе выглядит иначе, чем будет выглядеть боевой.
        html = cr.wrap_html(up["html"], erid=TEST_ERID,
                            viewability_src=viewability_src(db))
        params = cr.build_creative_params(
            title=f"{TITLE_PREFIX}{s.no} · {s.title or s.deal_id}",
            link=link, erid=TEST_ERID, size=up.get("size"))
        xxhash = c.creative_add(campaign, params, local_ref=ref)
        c.creative_edit(xxhash, {"data": {"html_code": html}}, local_ref=ref)
    except (cr.CreativeError, MsError, ValueError) as e:
        raise TargetingCreativeError(str(e))
    log.info("DSP: креатив нацеливания комплекта %s заведён как %s", s.id, xxhash)
    return _persist(db, s, xxhash)


def _persist(db: Session, s: LaunchPrepCreativeSet, xxhash: str) -> str:
    """Хеш коммитится СРАЗУ: объект в чужой системе уже есть, и потерять его нельзя."""
    s.ms_targeting_creative_xxhash = xxhash
    s.ms_targeting_at = datetime.utcnow()
    db.commit()
    return xxhash


# Насколько кампания нацеливания живёт после каждого получения. Двое суток — решение
# владельца 17.09.2026, и это ровно срок жизни самой ссылки нацеливания: кампания,
# пережившая свою ссылку, крутилась бы впустую, а умершая раньше — сорвала бы проверку
# на середине.
LIVE_DAYS = 2


def wake_campaign(db: Session, *, client: Optional[MsClient] = None) -> dict:
    """Продлить срок кампании нацеливания и запустить её — В МОМЕНТ ПОЛУЧЕНИЯ.

    ПОЧЕМУ НЕ ЗАРАНЕЕ И НЕ НАВСЕГДА. Запущенная кампания крутится настоящим людям в
    пределах своих лимитов, и держать полигон открытым месяцами — платить за показы,
    которые никто не смотрит. Поэтому она спит, а просыпается ровно тогда, когда трафик
    нажал «нацелить на себя», и на два дня.

    ПОЧЕМУ НЕ ОТКАЗ. Первая редакция этой проверки (утро 17.09.2026) отказывала: «не
    запущена — покажется ничего». Отказ верен по факту, но перекладывает на человека ход,
    который система делает сама двумя вызовами.

    СРОК ТОЛЬКО ВПЕРЁД. Если кампания уже живёт дольше — не трогаем: укоротить чужой срок
    своей проверкой значит однажды погасить кампанию под чьей-то рукой.

    ЛИМИТЫ ПЕРЕНОСИМ ЦЕЛИКОМ. `Campaign.edit` принимает `limits` объектом, и посылка без
    них обнулила бы показы и бюджет — то есть тихо сняла бы потолок, ради которого они и
    стоят (замер 17.09.2026: показы 200 000, бюджет 1000).
    """
    from app.routers.traffic_catalog import targeting_cabinet

    partner, campaign = targeting_cabinet(db)
    if not (partner and campaign):
        raise TargetingCreativeError(
            "Не задан кабинет или кампания нацеливания: Трафики → Каталог → Скрипты сайта")
    c = client or _client(partner)
    try:
        info = c.campaign_get_info(campaign) or {}
    except MsError as e:
        raise TargetingCreativeError(f"DSP не ответил про кампанию нацеливания: {e}")

    status = (info.get("status") or "").upper()
    # Удалённую и архивную поднять НЕЛЬЗЯ, и делать вид, что можно, — хуже отказа:
    # человек ждал бы показов от того, чего в кабинете уже нет.
    if status in ("DELETED", "ARCHIVE"):
        raise TargetingCreativeError(
            f"Кампания нацеливания «{info.get('title') or campaign}» {STATUS_RU.get(status, status)} "
            f"в кабинете DSP — нужна другая: Трафики → Каталог → Скрипты сайта")

    want_end = (datetime.utcnow() + timedelta(days=LIVE_DAYS)).date()
    end = _moment(info.get("date_end"))
    start = _moment(info.get("date_start"))
    changed = []

    if not end or end.date() < want_end:
        params = {"limits": info.get("limits") or {},
                  "date_end": want_end.isoformat()}
        # Начало двигаем назад, только если оно в будущем: иначе кампания «запущена», а
        # показов нет — и это ровно тот вид поломки, который выглядит как работа.
        if start and start > datetime.utcnow():
            params["date_start"] = datetime.utcnow().date().isoformat()
        elif start:
            params["date_start"] = start.date().isoformat()
        c.campaign_edit(campaign, params, local_ref=campaign)
        changed.append(f"срок до {want_end:%d.%m.%Y}")

    if status != RUNNING:
        c.campaign_set_status(campaign, RUNNING, local_ref=campaign)
        changed.append("запущена")

    if changed:
        log.info("DSP: кампания нацеливания %s — %s", campaign, ", ".join(changed))
    return {"campaign_xxhash": campaign, "changed": changed,
            "date_end": want_end.isoformat()}


# ── состояние кампании нацеливания ───────────────────────────────────────────

# Кампания, в которой лежат креативы нацеливания, — ЧУЖАЯ: её заводят и останавливают
# руками в кабинете DSP, а не мы. Поэтому её состояние не хранится, а спрашивается.
RUNNING = "LAUNCHED"

# Их словарь статусов по-русски. Нужен в текстах отказа: человек читает наше сообщение,
# а видит в кабинете английское слово — поэтому в отказе стоят оба.
STATUS_RU = {"LAUNCHED": "запущена", "STOPPED": "остановлена",
             "DELETED": "удалена", "ARCHIVE": "в архиве"}


def _moment(v):
    """Их дата приходит объектом `{'date': '...', 'timezone': ...}`, а не строкой."""
    if isinstance(v, dict):
        v = v.get("date")
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def campaign_state(db: Session, *, client: Optional[MsClient] = None) -> dict:
    """Карточка кампании нацеливания: имя, статус, сроки — и годна ли она показывать.

    ЗАЧЕМ. До 17.09.2026 в настройке стоял голый хеш, и по нему нельзя было понять
    ничего: ни какая это кампания, ни жива ли она. Кампания при этом была ОСТАНОВЛЕНА и
    закончилась 13.09 — ссылка нацеливания выпускалась, открывалась и не показывала
    ничего. Отказ молчал, потому что спросить было некому.

    Ошибка обмена возвращается полем `error`, а не исключением: это карточка для экрана,
    и недоступность DSP на ней — такая же новость, как остановленная кампания.
    """
    from app.routers.traffic_catalog import targeting_cabinet

    partner, campaign = targeting_cabinet(db)
    out = {"partner_xxhash": partner, "campaign_xxhash": campaign,
           "title": None, "status": None, "date_start": None, "date_end": None,
           "running": False, "asleep": False, "reason": None, "error": None,
           "admin_url": (os.getenv(ENV_ADMIN_URL) or "").strip().rstrip("/") or None}
    if not (partner and campaign):
        out["reason"] = ("Не задан кабинет или кампания нацеливания: "
                         "Трафики → Каталог → Скрипты сайта")
        return out

    c = client or _client(partner)
    try:
        info = c.campaign_get_info(campaign) or {}
    except MsError as e:
        out["error"] = str(e)
        out["reason"] = f"DSP не ответил про кампанию: {e}"
        return out
    if not isinstance(info, dict):
        out["reason"] = "DSP вернул не карточку кампании"
        return out

    out["title"] = info.get("title") or None
    out["status"] = info.get("status") or None
    start, end = _moment(info.get("date_start")), _moment(info.get("date_end"))
    out["date_start"] = start.isoformat() if start else None
    out["date_end"] = end.isoformat() if end else None

    # Два РАЗНЫХ отказа, и различать их обязательно: остановленную запускают одной
    # кнопкой, просроченной надо двигать даты. «Не работает» на оба случая отправляет
    # человека искать причину не там.
    now = datetime.utcnow()
    st = (out["status"] or "").upper()
    if st in ("DELETED", "ARCHIVE"):
        # Единственный настоящий отказ: поднять такую кампанию нечем.
        out["reason"] = (f"Кампания {STATUS_RU.get(st, st)} в кабинете DSP — нужна другая: "
                         f"Трафики → Каталог → Скрипты сайта")
    elif st != RUNNING or (end and end < now):
        # Спит — это НОРМА, а не поломка: полигон просыпается в момент получения
        # нацеливания и живёт двое суток (владелец 17.09.2026). Писать здесь «не
        # работает» значило бы пугать человека штатным состоянием.
        out["asleep"] = True
        out["reason"] = (f"Кампания спит: при получении нацеливания она запустится "
                         f"сама и будет жить {LIVE_DAYS} дня")
    elif start and start > now:
        out["reason"] = (f"Начало {start:%d.%m.%Y} — до этой даты показов не будет")
        out["running"] = True
    else:
        out["running"] = True
        out["reason"] = None
    return out


def ensure_quietly(db: Session, s: LaunchPrepCreativeSet) -> Optional[str]:
    """То же, но без исключения: для отправки трафику.

    Отправка на согласование НЕ должна зависеть от чужой системы. Если DSP недоступен или
    в комплекте нет архива, материал всё равно уходит — креатив нацеливания заведётся
    позже, по нажатию кнопки. Обратное означало бы, что недоступность DSP останавливает
    согласование, а это несоразмерно.
    """
    try:
        return ensure(db, s)
    except (TargetingCreativeError, MsError) as e:
        log.info("Креатив нацеливания для комплекта %s не заведён: %s", s.id, e)
        db.rollback()
        return None


__all__ = ["ensure", "ensure_quietly", "campaign_state", "wake_campaign",
           "TargetingCreativeError", "TITLE_PREFIX", "FALLBACK_LINK", "TEST_ERID",
           "RUNNING", "LIVE_DAYS"]
