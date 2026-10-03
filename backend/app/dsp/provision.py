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

from app.ad.build import creative_plans, pixel_setup
from app.ad.flight import PLACEMENT_IN_PLAN, PLACEMENT_READY
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.dsp import creatives as cr
from app.dsp.campaigns import ensure_campaign
from app.dsp.client import MsClient, MsError
from app.ext_lock import DSP_PROVISION, only_one
from app.ord import readiness
from app.files_safe import inside_uploads
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepPair,
                                    LaunchPrepSetTarget, LaunchPrepTarget)
from app.launch_prep import pub_rules
from app.launch_prep.sandbox import SandboxError, prepare_for_dsp, set_click_href
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
    # Посадочная — у пары «креатив × площадка» (с 25.09.2026), не у площадки сделки:
    # у разных креативов одной площадки она бывает разной. Под ключом "target" строке
    # отдаётся строка состава креатива — из неё берётся только `advertiser_url`.
    members = {(m.set_id, m.target_id): m for m in db.query(LaunchPrepSetTarget)
               .filter(LaunchPrepSetTarget.set_id.in_(
                   {p.set_id for p in pairs.values()} or [0])).all()}
    pubs = {p.id: p for p in db.query(SalesPublisher)
            .filter(SalesPublisher.id.in_({p.publisher_id for p in pls.values()})).all()}
    # Поверхность пары (web/app) — у получателя сделки; по ней берётся правило площадки
    # (ссылки в app, канал размещения — app/launch_prep/pub_rules.py).
    lp_targets = {t.id: t for t in db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id.in_(
        {p.target_id for p in pairs.values()} or [0])).all()}
    rules = pub_rules.rules_for(db, {(t.publisher_id, t.surface_kind) for t in lp_targets.values()})

    out = []
    for c in crs:
        p = pls.get(c.placement_id)
        if not p:
            continue
        pair = pairs.get(c.pair_id) if c.pair_id else None
        lpt = lp_targets.get(pair.target_id) if pair else None
        out.append({"creative": c, "placement": p, "publisher": pubs.get(p.publisher_id),
                    "file": files.get(c.file_id),
                    "target": members.get((pair.set_id, pair.target_id)) if pair else None,
                    "rule": rules.get((lpt.publisher_id, lpt.surface_kind)) if lpt else None})
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
    # Поверхность этого креатива идёт не через нашу DSP (Adfox / вне контура) — у Максавита
    # так web, а app — через DSP (владелец 30.09.2026). Решает канал ПОВЕРХНОСТИ, не
    # признак площадки «наш код».
    if (row.get("rule") or {}).get("channel") in pub_rules.EXTERNAL_CHANNELS:
        return "поверхность площадки во внешней DSP — в нашу DSP не заводится, креатив заводят там"
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
    if not cr.landing_domain(pub_rules.web_url(tgt.advertiser_url)):
        return "посадочная ссылка не похожа на адрес — не из чего взять домен для DSP"
    rule = row.get("rule")
    if (pub_rules.needs_deeplink(rule) and not (getattr(tgt, "deeplink_url", None) or "").strip()
            and not pub_rules.is_app_link(tgt.advertiser_url)):
        return "площадка требует диплинк в коде креатива, а у пары его нет"
    return None


NO_BLOCKS = ("у площадки нет ни одного блока DSP — креатив крутился бы по всей сети, а не "
             "у неё; заведите блоки в реестре площадки")


def _without_blocks(db: Session, camp: AdCampaign, rows: list) -> set:
    """Креативы, которым нечем ограничить показ своей площадкой (аудит 01.10.2026, В-7).
    Таргеты выключены — ограничений не ставим никому, и отказ был бы лишним."""
    from app.dsp import targeting as tg
    if not rows or not tg.enabled(db):
        return set()
    return set(tg.plan_for(db, camp, rows)["summary"]["creatives_without_blocks"])


AD_LABEL_MISSING = ("у сделки не выбран изначальный договор ОРД — ИНН и название "
                    "рекламодателя для рекламной метки взять неоткуда")


def ad_label(db: Session, deal_id) -> Optional[tuple]:
    """(ИНН, название) рекламодателя для рекламной метки — `self_inn` / `self_name` креатива.

    Владелец 28.09.2026: слать всегда — эти данные идут в подсказку рекламной метки рядом
    с ЕРИД. Источник — изначальный договор ОРД сделки: с ним маркер и зарегистрирован в
    ЕРИР, и метка обязана говорить то же, что реестр. Нет договора или в нём пусто — None,
    и креатив не выгружается: без полей боевой кабинет отказывает всем креативам сразу."""
    from app.ord.models import OrdInitialContract
    from app.sales.models import SalesDeal
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if deal is not None and readiness.is_direct(deal):
        # Прямой рекламодатель (02.10.2026): изначальный = доходный, рекламодатель — это
        # плательщик сделки; метка берёт его ИНН и название.
        # Плательщик — тем же разбором, что сборка ОРД и ЕРИД (`resolve_final`): по полю
        # сделки, а если пусто — по метке имени. Иначе экран сборки зелёный, а метки нет.
        from app.ord.matching import resolve_final
        cp = resolve_final(db, deal).payer
        inn = "".join(ch for ch in (getattr(cp, "inn", "") or "") if ch.isdigit())
        name = (getattr(cp, "name", "") or "").strip()
        return (inn, name) if inn and name else None
    if not deal or not getattr(deal, "ord_initial_contract_id", None):
        return None
    ic = (db.query(OrdInitialContract)
          .filter(OrdInitialContract.id == deal.ord_initial_contract_id).first())
    inn = "".join(ch for ch in (getattr(ic, "advertiser_inn", "") or "") if ch.isdigit())
    name = (getattr(ic, "advertiser_name", "") or "").strip()
    return (inn, name) if inn and name else None


def plan(db: Session, camp: AdCampaign) -> dict:
    """Что произойдёт при нажатии. Показывается ДО подтверждения — цифра в вопросе
    «завести N креативов?» и есть то, что отличает осознанное действие от случайного."""
    rows = _rows(db, camp)
    px = pixel_setup(db, camp.deal_id)
    want_pixel, ext_tag = px["needed"], px["tag"]
    label = ad_label(db, camp.deal_id)
    done = [r for r in rows if r["creative"].ms_creative_xxhash]
    nob = _without_blocks(db, camp, rows)
    todo, blocked = [], {}
    for r in rows:
        if r["creative"].ms_creative_xxhash:
            continue
        why = (_blocker(r, want_pixel, ext_tag)
               or (NO_BLOCKS if r["creative"].id in nob else None)
               or (None if label else AD_LABEL_MISSING))
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
        # Что уйдёт в рекламную метку (`self_inn` / `self_name`).
        "ad_label": {"inn": label[0], "name": label[1]} if label else None,
        # Таргетинги — что уйдёт кампании и креативам (app/dsp/targeting.py). Показываются
        # всегда; ставятся, только когда включена настройка `dsp_targeting_enabled`.
        "targeting": _targeting_preview(db, camp, rows),
    }


def _targeting_preview(db: Session, camp: AdCampaign, rows: list) -> dict:
    from app.dsp import targeting as tg
    try:
        p = tg.plan_for(db, camp, rows)
    except Exception as e:  # noqa: BLE001 — сводка не должна ронять окно выгрузки
        log.warning("таргетинг РК %s: сводка не собралась (%s)", camp.id, e)
        return {"enabled": False, "error": str(e)}
    return {"enabled": p["enabled"], **p["summary"]}


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


def pixel_url(row: dict, width, height, ext_tag: Optional[str] = None,
              erid: Optional[str] = None) -> str:
    """Пиксель показа Weborama под ЭТОТ креатив — для поля `pixel` DSP (владелец 01.10.2026:
    только полем, не тегом в HTML). Собирается ТЕМ ЖЕ правилом, что заявка Weborama и
    паспорт (`request_xlsx.build_tag`): макрос DSP, домен, размер, ЕРИД. Внешний тег один
    на кампанию, свой — у каждого размещения; дальше путь общий."""
    from app.weborama.request_xlsx import build_tag
    tag, why = build_tag(ext_tag or row["placement"].weborama_pixel,
                         row["publisher"].domain or "", "dsp", None, erid)
    if not tag:
        raise ValueError(why or "пиксель не собран")
    # Размер — тот, что объявил загрузчик DSP, ВКЛЮЧАЯ 0×0 адаптивного баннера: в теге
    # должно стоять `a.wi=0`, а не заготовка `~WIDTH~` (её DSP не подставит). У заявки и
    # паспорта своё правило для адаптивного (там проверочная ссылка), поэтому размер
    # здесь, а не в `build_tag` (регрессия v2.6.57, найдена пробным прогоном 01.10).
    if width is not None and height is not None:
        tag = wtags.fill_size(tag, width, height)
    return tag


def provision(db: Session, camp: AdCampaign, user_id=None,
              client: Optional[MsClient] = None) -> dict:
    """Завести всё недостающее в DSP. Идёт по креативам, не падая целиком.

    Один проход на РК за раз: второй клик получает отказ «уже идёт», а не второй
    комплект объектов в чужом кабинете (аудит 23.09.2026, 4.H2).
    """
    with only_one(DSP_PROVISION, camp.id, DspProvisionError, "Выгрузка в DSP"):
        return _provision(db, camp, client or MsClient())


def _provision(db: Session, camp: AdCampaign, c: MsClient) -> dict:
    from app.dsp.config import creative_script, viewability_src

    px = pixel_setup(db, camp.deal_id)
    want_pixel, ext_tag = px["needed"], px["tag"]
    if want_pixel and px["mode"] == "external" and not ext_tag:
        raise DspProvisionError(
            "По РК заказан внешний пиксель Weborama, но тег не загружен — "
            "карточка сделки, блок «Доп. параметры РК»")
    all_rows = _rows(db, camp)
    nob = _without_blocks(db, camp, all_rows)
    rows = [r for r in all_rows
            if not r["creative"].ms_creative_xxhash and not _blocker(r, want_pixel, ext_tag)
            and r["creative"].id not in nob]
    label = ad_label(db, camp.deal_id)
    if rows and not label:
        # Отказ ДО кампании и загрузок: без метки боевой кабинет откажет каждому креативу,
        # а кампания и архивы остались бы пустыми хвостами (28.09.2026, DLMBGB).
        raise DspProvisionError(AD_LABEL_MISSING[0].upper() + AD_LABEL_MISSING[1:])
    # Нечего заводить — не заводим и кампанию. Иначе в кабинете остаётся пустая
    # STOPPED-кампания, которую по API не удалить (4.L4).
    if not rows and not camp.ms_campaign_xxhash:
        raise DspProvisionError(
            "Нет ни одного креатива, готового к выгрузке, — кампания в DSP не заводится. "
            "Причины — в плане выгрузки")

    try:
        camp_hash = ensure_campaign(db, camp, c)
    except MsError as e:
        raise DspProvisionError(f"Кампания в DSP не заведена: {e}")

    vsrc = viewability_src(db)
    # Лимит креатива — ЕГО доля плана площадки, а не план площадки целиком (27.09.2026).
    plans = creative_plans(db, camp)
    done, failed = [], []
    for r in rows:
        cre, pub = r["creative"], r["publisher"]
        name = f"{cre.ms_title or cre.id} · {pub.name if pub else '?'}"
        ref = f"cr{cre.id}"
        try:
            # Прошлый проход мог завести креатив и оборваться до кода (4.H1). Журнал
            # помнит хеш — тогда смотрим, что лежит в кабинете, а не заводим второй.
            known = c.last_ok_xxhash("Creative.add", "creative", ref)
            # Прошлый add ушёл без ответа — креатив мог создаться, а хеша мы не знаем.
            # Перечислить креативы кампании у DSP нечем, поэтому повтор заперт до сверки
            # (ревью 23.09.2026): второй креатив в кабинете не удалить.
            if not known and c.unknown_outcome("Creative.add", "creative", ref):
                raise DspProvisionError(
                    "прошлая попытка завести этот креатив осталась без ответа — он мог "
                    "создаться. Сверьтесь с кабинетом DSP, повтор запрещён до сверки")
            state = cr.html_state(c, known) if known else "gone"
            if state == "ok":
                xxhash = known
            else:
                data = _read_archive(r["file"])
                # Правило площадки (владелец 29.09.2026): в app-режимах «веб» / «обе» в
                # <a href> встаёт прямая ссылка вместо макроса DSP; url/adomain — веб всегда.
                href = pub_rules.click_href(r.get("rule"), r["target"].advertiser_url,
                                            getattr(r["target"], "deeplink_url", None))
                if href:
                    data, _ = prepare_for_dsp(data)
                    data, _ = set_click_href(data, href)
                up = cr.upload_zip(c, data,
                                   filename=(r["file"].original_name or "creative.zip"),
                                   local_ref=ref)
                # Наш счётчик выбирается ПО ПЛОЩАДКЕ — одной точкой на систему.
                script = creative_script(db, bool(pub.our_code)) if pub else ""
                html = cr.wrap_html(up["html"], erid=cre.erid, viewability_src=vsrc,
                                    extra_script=script)
                # Пиксель показа — полем `pixel`, а не тегом в разметке (владелец
                # 01.10.2026). И только если он по этой РК заказан: иначе тег
                # верификатора уехал бы в сеть по кампании, которую он не считает.
                pix = (pixel_url(r, up.get("width"), up.get("height"), ext_tag, cre.erid)
                       if want_pixel else None)
                if state == "empty":
                    xxhash = known
                else:
                    # Нулевая доля — это «не крутить», а лимит 0 в DSP значит «без лимита»:
                    # креатив ушёл бы откручивать без ограничения. Так бывает, когда соседний
                    # креатив площадки забрал весь её объём заданным (ревью 27.09.2026).
                    if plans.get(cre.id) == 0:
                        raise DspProvisionError(
                            "У креатива нулевой объём на площадке — весь её план отдан другому "
                            "креативу. Уменьшите заданный объём соседа или отключите креатив")
                    params = cr.build_creative_params(
                        title=cre.ms_title or name,
                        # Обычная посадочная: кликовый счётчик Weborama сняли, клики не
                        # считаем (владелец 01.10.2026).
                        # Диплинк SDK в посадочной — в `<a href>` баннера, сюда — его
                        # веб-адрес (`pub_rules.web_url`, владелец 02.10.2026).
                        link=cr.landing_link(pub_rules.web_url(r["target"].advertiser_url)),
                        pixel=pix,
                        # Конечный URL — посадочная креатива целиком (владелец 01.10.2026).
                        adomain=cr.landing_adomain(pub_rules.web_url(r["target"].advertiser_url)),
                        erid=cre.erid, size=up.get("size"),
                        self_inn=label[0], self_name=label[1],
                        total_shows=(int(plans[cre.id]) if plans.get(cre.id) else None))
                    xxhash = c.creative_add(camp_hash, params, local_ref=ref)
                c.creative_edit(xxhash, {"data": {"html_code": html}}, local_ref=ref)
        except (cr.CreativeError, MsError, DspProvisionError, ValueError, SandboxError) as e:
            failed.append({"creative_id": cre.id, "placement_id": r["placement"].id,
                           "name": name, "error": str(e)})
            continue
        # Хеш коммитим СРАЗУ: следующий креатив может упасть, а этот уже заведён, и
        # потерянный хеш означает дубль в чужом кабинете при повторе.
        cre.ms_creative_xxhash = xxhash
        db.commit()
        done.append({"creative_id": cre.id, "placement_id": r["placement"].id,
                     "name": name, "xxhash": xxhash})
    return {"campaign_xxhash": camp_hash, "done": done, "failed": failed,
            "targeting": _apply_targeting(db, camp, c, camp_hash)}


def _apply_targeting(db: Session, camp: AdCampaign, c: MsClient, camp_hash: str):
    """Таргеты кампании и блоки заведённых креативов — если включено. Ставятся каждый
    проход целиком: вызов идемпотентен, а креатив, заведённый в прошлый раз, иначе
    остался бы без блоков."""
    from app.dsp import targeting as tg
    if not tg.enabled(db):
        return {"skipped": "таргетинги не отправляются — выключатель dsp_targeting_enabled"}
    # Таргеты — ПОСЛЕ необратимого: кампания и креативы уже заведены, хеши записаны. Сбой
    # здесь — строка отчёта, а не 500 вместо него (аудит 01.10.2026, С-2): иначе человек не
    # видит, что заведено, и жмёт снова.
    try:
        rows = _rows(db, camp)
        plan = tg.plan_for(db, camp, rows)
        hashes = {r["creative"].id: r["creative"].ms_creative_xxhash for r in rows
                  if r["creative"].ms_creative_xxhash}
        return tg.apply(c, plan, camp_hash, hashes)
    except Exception as e:  # noqa: BLE001 — отчёт после заведения не должен падать
        # Откат: после SQL-ошибки сессия сломана, и запись в журнал действий следом снова
        # дала бы 500. Хеши креативов уже закоммичены выше — откат их не трогает.
        db.rollback()
        log.warning("таргетинг РК %s не поставлен: %s", camp.id, e, exc_info=True)
        return {"error": f"таргеты не поставлены: {e}"}


__all__ = ["plan", "provision", "DspProvisionError", "PLACEMENT_OK", "CREATIVE_OK"]
