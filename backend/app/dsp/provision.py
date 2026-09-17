# -*- coding: utf-8 -*-
"""Выгрузка РК в DSP: кампания → архив креатива → обёртка → креатив в кабинете.

Тот же контур, что у Weborama (`app/weborama/provision.py`), и по тем же причинам:
демо-экран остаётся инструментом разбора, а конвейер ходит сюда. Здесь собраны в одну
цепочку кирпичи, которые до сих пор дёргались руками с демо-экрана — `ensure_campaign`,
`upload_zip`, `wrap_html`, `Creative.add` + `Creative.edit`.

ЧЕТЫРЕ ПРАВИЛА, КАЖДОЕ ОПЛАЧЕНО ЖИВЫМ ВЫЗОВОМ 09.09.2026.

1. **Сначала Weborama, потом DSP.** Пиксель показа вшивается В КРЕАТИВ, и уехавший без
   него баннер придётся заводить заново: дописать счётчик в уже выданную разметку так,
   чтобы показы сошлись задним числом, нечем.
2. **Хеш — единственный признак «уже заведён».** Он лежит в
   `ad_campaign_creative.ms_creative_xxhash` и уже показывается в кабинете трафика;
   второго хранилища того же факта нет намеренно.
3. **Отказ по одному креативу не отменяет остальных.** Девятнадцать площадок в РК —
   обычное дело, и падать целиком из-за одного битого архива значит не завести ничего.
4. **Разметка уходит ВТОРЫМ вызовом.** `add` заводит объект и отдаёт хеш, `html_code`
   кладётся правкой. Пока считалось иначе, «креатив ушёл» означало пустой креатив.
"""
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.ad.build import pixel_setup
from app.ad.flight import PLACEMENT_IN_PLAN, PLACEMENT_READY
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.dsp import creatives as cr
from app.dsp.campaigns import ensure_campaign
from app.dsp.client import MsClient, MsError
from app.files_safe import inside_uploads
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepPair,
                                    LaunchPrepTarget)
from app.sales.models import SalesPublisher
from app.weborama import naming, tags as wtags

log = logging.getLogger("finance.dsp")

UPLOADS_ROOT = "/app/uploads"

# Кого выгружаем: площадка согласована и готова к запуску либо уже крутит — тот же
# порог, что у пикселя Weborama. Раньше — рано, площадку ещё могут снять.
PLACEMENT_OK = (PLACEMENT_READY,) + PLACEMENT_IN_PLAN
# Креатив: согласован конвейером либо уже ведётся трафиком. «У трафика» и «у площадки»
# означают, что вердикта ещё нет, а несогласованный баннер в кабинете — это показ.
CREATIVE_OK = ("согласован", "запущен", "пауза")


class DspProvisionError(RuntimeError):
    """Причина, по которой выгружать нельзя. Текст показывается человеку как есть."""


def _rows(db: Session, camp: AdCampaign) -> list:
    """Кандидаты на выгрузку: креатив + его площадка + файл + посадочная ссылка.

    Пачкой, а не по строке: девятнадцать площадок по три обращения каждая — это
    шестьдесят запросов на одно нажатие.
    """
    pls = {p.id: p for p in db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == camp.id).all()}
    if not pls:
        return []
    crs = (db.query(AdCampaignCreative)
           .filter(AdCampaignCreative.campaign_id == camp.id).all())
    files = {f.id: f for f in db.query(LaunchPrepCreativeFile)
             .filter(LaunchPrepCreativeFile.id.in_(
                 {c.file_id for c in crs if c.file_id} or [0])).all()}
    pairs = {p.id: p for p in db.query(LaunchPrepPair)
             .filter(LaunchPrepPair.id.in_(
                 {c.pair_id for c in crs if c.pair_id} or [0])).all()}
    targets = {t.id: t for t in db.query(LaunchPrepTarget)
               .filter(LaunchPrepTarget.id.in_(
                   {p.target_id for p in pairs.values()} or [0])).all()}
    pubs = {p.id: p for p in db.query(SalesPublisher)
            .filter(SalesPublisher.id.in_({p.publisher_id for p in pls.values()})).all()}

    out = []
    for c in crs:
        p = pls.get(c.placement_id)
        if not p:
            continue
        pair = pairs.get(c.pair_id) if c.pair_id else None
        out.append({"creative": c, "placement": p, "publisher": pubs.get(p.publisher_id),
                    "file": files.get(c.file_id),
                    "target": targets.get(pair.target_id) if pair else None})
    return out


def _blocker(row: dict, want_pixel: bool = True,
             ext_tag: Optional[str] = None) -> Optional[str]:
    """Почему этот креатив выгрузить НЕЛЬЗЯ. Пусто — можно.

    Причина возвращается текстом и доезжает до экрана: «не выгрузилось» без причины
    заставляет разбираться заново каждый раз.

    `want_pixel` — заказан ли пиксель верификатора по этой РК. Умолчание True сохраняет
    прежнее поведение для любого вызова, забывшего передать признак: лишний отказ виден
    и разбирается, а лишний пропуск отправил бы в сеть креатив без счётчика молча.

    `ext_tag` — внешний тег, один на всю кампанию. Когда он есть, пиксель у размещения
    не спрашиваем вовсе: вставку заводил клиент, у нас её нет и не будет.
    """
    c, p, f, tgt = row["creative"], row["placement"], row["file"], row["target"]
    pub = row["publisher"]
    if p.is_direct:
        return "площадка крутит сама — в DSP не заводится"
    if p.status not in PLACEMENT_OK:
        return f"площадка в статусе «{p.status}» — рано"
    if c.status not in CREATIVE_OK:
        return f"креатив в статусе «{c.status}» — вердикта ещё нет"
    # БЕЗ МАРКЕРА В СЕТЬ НЕ УХОДИМ. Маркер подставляется и в разметку, и в тело креатива;
    # пустой означал бы рекламу без маркировки — это не «некрасиво», а нарушение, и
    # обнаруживается оно не нами. Отказ виден в плане выгрузки словами, а не молчанием.
    if not (c.erid or "").strip():
        return "нет ЕРИД — маркер не перенесён в креатив кампании"
    if want_pixel and not ext_tag and not p.weborama_pixel:
        return "нет пикселя Weborama — сначала «ПИКСЕЛЬ WR»"
    if not f:
        return "к креативу не привязан файл комплекта"
    if not f.is_archive:
        return "файл креатива не архив — загрузчик DSP принимает zip"
    if not (pub and naming.domain_of(pub.domain or "")):
        return "у площадки не задан домен — в тег пикселя его подставить неоткуда"
    if not (tgt and (tgt.advertiser_url or "").strip()):
        return "нет посадочной ссылки площадки — DSP требует link у креатива"
    return None


def plan(db: Session, camp: AdCampaign) -> dict:
    """Что произойдёт при нажатии. Показывается ДО подтверждения — цифра в вопросе
    «завести N креативов?» и есть то, что отличает осознанное действие от случайного."""
    rows = _rows(db, camp)
    px = pixel_setup(db, camp.deal_id)
    want_pixel, ext_tag = px["needed"], px["tag"]
    done = [r for r in rows if r["creative"].ms_creative_xxhash]
    todo, blocked = [], {}
    for r in rows:
        if r["creative"].ms_creative_xxhash:
            continue
        why = _blocker(r, want_pixel, ext_tag)
        if why:
            blocked[why] = blocked.get(why, 0) + 1
        else:
            todo.append(r)
    return {
        "campaign_ready": bool(camp.ms_campaign_xxhash),
        # Экран обязан сказать, почему шага с пикселем нет: исчезнувшая кнопка без
        # причины читается как поломка, а не как «по этой РК он не заказан».
        "needs_pixel": want_pixel,
        "pixel_mode": px["mode"],
        # Внешний тег заказан, но не загружен — отдельная причина отказа: без неё экран
        # скажет «нет пикселя» и отправит жать «ПИКСЕЛЬ WR», которая тут не поможет.
        "ext_tag_missing": bool(want_pixel and px["mode"] == "external" and not ext_tag),
        "creatives": len(rows),
        "have": len(done),
        "todo": len(todo),
        # Площадки, а не только креативы: владелец считает выгрузку площадками, и вопрос
        # «сколько площадок заведём» задаётся именно так.
        "placements": len({r["placement"].id for r in todo}),
        # Причины отказа с числами — их и показываем в подтверждении.
        "blocked": [{"why": k, "count": v} for k, v in sorted(blocked.items())],
    }


def _read_archive(f: LaunchPrepCreativeFile) -> bytes:
    # Граница хранилища обязательна: содержимое уходит в DSP и там становится боевым
    # креативом. Отправить по испорченному пути чужой файл значит загрузить его в
    # рекламную сеть под нашим именем — отсюда отказ, а не пропуск.
    path = inside_uploads(f.path)
    if path is None:
        raise DspProvisionError(f"некорректный путь файла в базе: {f.path}")
    if not os.path.exists(path):
        raise DspProvisionError(f"файл не найден в хранилище: {f.path}")
    with open(path, "rb") as fh:
        return fh.read()


def _pixel_tag(row: dict, width, height, ext_tag: Optional[str] = None) -> str:
    """Тег пикселя Weborama под ЭТОТ креатив: макрос рандомизатора DSP, домен площадки,
    размеры из ответа загрузчика. Собирается на лету — хранить производное значит завести
    вторую правду, которая разойдётся с первой."""
    # Внешний тег один на кампанию, свой — у каждого размещения. Дальше путь общий:
    # сборщик подставляет макрос рандомизатора и дописывает `&a.ycp=https://<домен>`,
    # поэтому даже фиксированный тег уезжает в каждую площадку СО СВОИМ адресом.
    url = naming.final_tag(ext_tag or row["placement"].weborama_pixel,
                           row["publisher"].domain or "", kind="dsp")
    url = wtags.fill_size(url, width, height)
    return f'<img src="{url}" width="1" height="1" alt="" style="display:none">'


def provision(db: Session, camp: AdCampaign, user_id=None,
              client: Optional[MsClient] = None) -> dict:
    """Завести всё недостающее в DSP. Идёт по креативам, не падая целиком."""
    from app.routers.traffic_catalog import creative_script, viewability_src

    c = client or MsClient()
    try:
        camp_hash = ensure_campaign(db, camp, c)
    except MsError as e:
        raise DspProvisionError(f"Кампания в DSP не заведена: {e}")

    vsrc = viewability_src(db)
    px = pixel_setup(db, camp.deal_id)
    want_pixel, ext_tag = px["needed"], px["tag"]
    if want_pixel and px["mode"] == "external" and not ext_tag:
        raise DspProvisionError(
            "По РК заказан внешний пиксель Weborama, но тег не загружен — "
            "карточка сделки, блок «Доп. параметры РК»")
    rows = [r for r in _rows(db, camp)
            if not r["creative"].ms_creative_xxhash and not _blocker(r, want_pixel, ext_tag)]
    done, failed = [], []
    for r in rows:
        cre, pub = r["creative"], r["publisher"]
        name = f"{cre.ms_title or cre.id} · {pub.name if pub else '?'}"
        try:
            data = _read_archive(r["file"])
            up = cr.upload_zip(c, data,
                               filename=(r["file"].original_name or "creative.zip"),
                               local_ref=f"cr{cre.id}")
            # Наш счётчик выбирается ПО ПЛОЩАДКЕ — одной точкой на систему.
            script = creative_script(db, bool(pub.our_code)) if pub else ""
            html = cr.wrap_html(up["html"], erid=cre.erid, viewability_src=vsrc,
                                extra_script=script)
            # Пиксель показа — в конец разметки: у баннера от загрузчика собственный
            # `<head>` может быть, а может и не быть, и хвост не зависит ни от того, ни
            # от другого.
            # Пиксель в разметку — только если он по этой РК заказан. Иначе тег
            # верификатора уехал бы в сеть по кампании, которую он не считает.
            if want_pixel:
                html += "\n" + _pixel_tag(r, up.get("width"), up.get("height"), ext_tag)
            params = cr.build_creative_params(
                title=cre.ms_title or name, link=r["target"].advertiser_url,
                erid=cre.erid, size=up.get("size"),
                total_shows=(int(r["placement"].plan_show)
                             if r["placement"].plan_show else None))
            xxhash = c.creative_add(camp_hash, params, local_ref=f"cr{cre.id}")
            c.creative_edit(xxhash, {"data": {"html_code": html}},
                            local_ref=f"cr{cre.id}")
        except (cr.CreativeError, MsError, DspProvisionError, ValueError) as e:
            failed.append({"creative_id": cre.id, "placement_id": r["placement"].id,
                           "name": name, "error": str(e)})
            continue
        # Хеш коммитим СРАЗУ: следующий креатив может упасть, а этот уже заведён, и
        # потерянный хеш означает дубль в чужом кабинете при повторе.
        cre.ms_creative_xxhash = xxhash
        db.commit()
        done.append({"creative_id": cre.id, "placement_id": r["placement"].id,
                     "name": name, "xxhash": xxhash})
    return {"campaign_xxhash": camp_hash, "done": done, "failed": failed}


__all__ = ["plan", "provision", "DspProvisionError", "PLACEMENT_OK", "CREATIVE_OK"]
