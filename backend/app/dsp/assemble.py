# -*- coding: utf-8 -*-
"""Сборка креатива в DSP — ОДНА точка входа (владелец 13.10.2026).

Раньше цепочку «загрузить → обернуть → завести → вшить код» каждый собирал заново: выгрузка РК
(`provision`) и копия нацеливания (`targeting_creative`) держали каждый свою, а у тизера её не было
вовсе. Две копии одной цепочки расходятся на первой же правке (пиксель, диплинк, метка уже расходились).
Теперь все зовут `ensure(client, campaign, spec)`, а различия — в `Spec`.

Что делает `ensure`, одинаково для любого формата:
  1. Уже заведённый креатив ПРОВЕРЯЕТ в кабинете, а не берёт на веру (`state`): `ok` — вернуть хеш,
     `empty` — объект без содержимого, достроить правкой, `gone` — заводить заново. Креатив в чужом
     кабинете по API не удалить, поэтому второй «на всякий случай» недопустим.
  2. Перед созданием — отказ, если прошлый `Creative.add` ушёл без ответа (мог создаться).
  3. Формат HTML: архив → загрузчик → обёртка → `Creative.add` → `Creative.edit(html_code)`.
     Формат TEASER: картинка → загрузчик → `Creative.add` (см. `teaser.py`).

Чего здесь нет намеренно: правил площадки (какую ссылку ставить в `<a href>`, диплинк вторым шагом,
таблица пикселей) — они приходят в `Spec` готовыми функциями от вызывающего; здесь только порядок
вызовов к DSP и защита от дублей.

`cr.*` вызывается через модуль, а не `from … import`: тесты подменяют загрузчик на уровне модуля.
"""
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.dsp import creatives as cr
from app.dsp import teaser

HTML = teaser.HTML
TEASER = teaser.TEASER


@dataclass
class Spec:
    """Что завести. Поля — то, чем креативы отличаются друг от друга; порядок вызовов не меняется."""
    ref: str                                          # метка в журнале обмена (`cr<id>` и т. п.)
    title: str
    link: str
    erid: Optional[str]
    load: Callable[[], Tuple[bytes, str]]             # лениво: (содержимое файла, имя)
    adomain: Optional[str] = None
    known: Optional[str] = None                       # хеш из прошлого прохода
    fmt: str = HTML
    viewability_src: Optional[str] = None
    extra_script: Optional[str] = None
    icon_url: str = ""                                        # иконка тизера (настройка DSP)
    prepare: Optional[Callable[[bytes], bytes]] = None        # правка архива перед отправкой
    pixel: Optional[Callable[[dict], Optional[str]]] = None   # пиксель по ответу загрузчика
    self_inn: Optional[str] = None
    self_name: Optional[str] = None
    total_shows: Optional[int] = None
    before_add: Optional[Callable[[], None]] = None           # отказ ДО создания (нулевая доля)
    on_unknown: Optional[Callable[[], None]] = None           # своё сообщение отказа, если исход прошлого add неизвестен


@dataclass
class Built:
    xxhash: str
    html: Optional[str] = None      # код, вшитый сейчас; None — креатив не трогали или это не HTML


def state(c, fmt: str, xxhash: str) -> str:
    """`ok` / `empty` / `gone` — тем же вопросом для любого формата."""
    return teaser.state(c, xxhash) if fmt == TEASER else cr.html_state(c, xxhash)


def links_for(fmt: str, target) -> Tuple[Optional[str], Optional[str]]:
    """(ссылка клика, конечный адрес) для пары «креатив × площадка» — правило формата одно."""
    if fmt == TEASER:
        return teaser.link_pair(target)
    from app.launch_prep import pub_rules
    web = pub_rules.web_url(target.advertiser_url)
    return cr.landing_link(web), cr.landing_adomain(web)


def ensure(c, campaign: str, spec: Spec) -> Built:
    """Завести креатив в кампании и вернуть его хеш. Ошибки — как у частей (`CreativeError`,
    `MsError`, `ValueError`): вызывающий решает, как показать их человеку."""
    st = state(c, spec.fmt, spec.known) if spec.known else "gone"
    if st == "ok":
        return Built(spec.known)
    # Безусловно (аудит 2.7.0, п. 2.8): прошлый add без ответа — креатив мог создаться, второй в кабинете DSP не удалить.
    # `on_unknown` — сообщение вызывающего; без него — общий отказ.
    if st == "gone" and c.unknown_outcome("Creative.add", "creative", spec.ref):
        if spec.on_unknown:
            spec.on_unknown()
        raise cr.CreativeError("прошлая попытка завести этот креатив осталась без ответа — он мог создаться. "
                               "Сверьтесь с кабинетом DSP, повтор запрещён до сверки")

    data, filename = spec.load()
    if spec.fmt == TEASER:
        return Built(teaser.create(
            c, campaign, ref=spec.ref, known=spec.known, img_state=st, title=spec.title,
            link=spec.link, adomain=spec.adomain, erid=spec.erid, data=data, filename=filename,
            total_shows=spec.total_shows, pixel_of=spec.pixel, before_add=spec.before_add,
            icon_url=spec.icon_url))
    return _html(c, campaign, spec, st, data, filename)


def _html(c, campaign: str, spec: Spec, st: str, data: bytes, filename: str) -> Built:
    if spec.prepare:
        data = spec.prepare(data)
    up = cr.upload_zip(c, data, filename=filename, local_ref=spec.ref)
    html = cr.wrap_html(up["html"], erid=spec.erid, viewability_src=spec.viewability_src,
                        extra_script=spec.extra_script)
    if st == "empty":
        # Объект есть, кода нет (связь оборвалась между add и edit) — дошиваем, второй не заводим.
        c.creative_edit(spec.known, {"data": {"html_code": html}}, local_ref=spec.ref)
        return Built(spec.known, html)
    pix = spec.pixel(up) if spec.pixel else None
    if spec.before_add:
        spec.before_add()
    params = cr.build_creative_params(
        title=spec.title, link=spec.link, pixel=pix, adomain=spec.adomain, erid=spec.erid,
        size=up.get("size"), self_inn=spec.self_inn, self_name=spec.self_name,
        total_shows=spec.total_shows)
    xxhash = c.creative_add(campaign, params, local_ref=spec.ref)
    # Разметка уходит ВТОРЫМ вызовом: `add` заводит объект и отдаёт хеш (оплачено живым вызовом 09.09.2026).
    c.creative_edit(xxhash, {"data": {"html_code": html}}, local_ref=spec.ref)
    return Built(xxhash, html)
