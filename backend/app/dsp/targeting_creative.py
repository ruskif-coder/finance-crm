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
  · **ЕРИД** — на отправке трафику маркера обычно ещё нет, а подставлять чужой нельзя.

Скрипт видимости оставлен: его требует сам DSP, и на внешний вид он не влияет.

ИДЕМПОТЕНТНОСТЬ. Повторная отправка комплекта не должна заводить второй такой же креатив.
Защита та же трёхступенчатая, что у боевого заведения: сохранённый хеш → хеш в журнале по
нашему `local_ref` (DSP создал, наш коммит не дошёл) → только тогда `Creative.add`.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dsp import creatives as cr
from app.dsp.client import MsClient, MsError
from app.files_safe import inside_uploads
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
FALLBACK_LINK = "https://simbtech.ru"


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
            html = cr.wrap_html(_html_of(db, s, c, ref), viewability_src=viewability_src(db))
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
        html = cr.wrap_html(up["html"], viewability_src=viewability_src(db))
        params = cr.build_creative_params(
            title=f"{TITLE_PREFIX}{s.no} · {s.title or s.deal_id}",
            link=link, size=up.get("size"))
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


__all__ = ["ensure", "ensure_quietly", "TargetingCreativeError", "TITLE_PREFIX",
           "FALLBACK_LINK"]
