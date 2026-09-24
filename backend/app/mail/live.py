# -*- coding: utf-8 -*-
"""Живые письма читают «Шаблоны писем» (аудит 23.09.2026, 5.M1; владелец 24.09.2026).

До этого правки на экране видели только предпросмотр и «Отправить себе»: отправители
собирали письмо своим кодом. Экран обещал то, чего не делал.

Здесь две точки, через которые проходит всё, что редактор задаёт по письму:

  · `card`   — правка карточки события (заголовок, текст, подпись кнопки, показывать ли
               кнопку) поверх того, что собрал отправитель; подстановки — живыми
               значениями события, тем же `editor.subst`, что в предпросмотре;
  · `digest` — оболочка контура (тема, прехедер, заголовок, подзаголовок, подвал) для
               пачки карточек, тем же `render.composed_html`, что рисует предпросмотр.

Имя отправителя, приставка темы и подпись — не здесь, а в почтовом клиенте: они нужны
КАЖДОМУ письму, включая досылку и «Отправить себе», и единственная точка, через которую
проходят все, — `mail.client.build_message`.

Правок нет — письмо такое же, как было: хранятся только отклонения от каталога.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app import timez
from app.mail import editor, render


TEXT = ("title", "body")      # слова события — применяются там, где известны его данные
LOOK = ("action",)            # вид карточки — применяется при каждой сборке письма


def card(db: Session, contour: str, key: str, base: dict, values: dict,
         fields=TEXT + LOOK) -> dict:
    """Карточка события с правками редактора. `base` — то, что собрал отправитель
    (title, body, action, link_abs, …); возвращается НОВЫЙ словарь.

    `fields` — какие правки применять. Слова (заголовок, текст) применяются ОДИН раз —
    там, где у события есть данные для подстановок (шина событий, прослойка рассылки);
    дальше они едут в журнале доставок готовыми. Подпись кнопки и её показ — при каждой
    сборке письма: досылка и дайджест собирают письмо заново.
    """
    own = editor._get(db, editor.KEY_CARDS.format(contour)).get(key) or {}
    out = dict(base)
    for f in editor.CARD_FIELDS:
        if f in own and f in fields:
            out[f] = editor.subst(own[f], values)
    # Кнопку убрали — убираем и ссылку: рисовальщик письма опирается именно на неё.
    if own.get("show_button") is False:
        out["link_abs"] = None
    return out


def values(db: Session, ctx: Optional[dict], name: Optional[str],
           link: Optional[str] = None) -> dict:
    """Подстановки для письма СОТРУДНИКУ из данных события — те же поля, что показывает
    предпросмотр (`editor.sample`), только настоящие.

    Сделка берётся и у медиаплана: события по медиапланам несут его, а не сделку, и
    `{сделка}` в правке шаблона иначе молча становилась бы пустотой (ревью 24.09.2026).
    """
    from app.sales.deal_label import deal_label
    from app.sales.models import SalesBrand

    out = {"имя": (name or "").strip() or "коллеги",
           "ссылка": render.abs_url(link) or "" if link else ""}
    ctx = ctx or {}
    deal = ctx.get("deal") or getattr(ctx.get("media_plan"), "deal", None)
    if deal is not None:
        out["сделка"] = deal_label(deal)
        amount = getattr(deal, "amount", None)
        out["сумма"] = f"{amount:,.0f} ₽".replace(",", " ") if amount else ""
        out["период"] = editor._period(getattr(deal, "period_from", None),
                                       getattr(deal, "period_to", None))
        if getattr(deal, "brand_id", None):
            row = db.query(SalesBrand.name).filter(SalesBrand.id == deal.brand_id).first()
            out["бренд"] = (row[0] if row else "") or ""
    return out


def digest(db: Session, contour: str, cards: List[dict], values: dict, *, brand: str,
           logo_url: Optional[str], settings_url: Optional[str]) -> Tuple[str, str]:
    """Пачка карточек в оболочке контура → (тема, разметка).

    Подстановки «срочное», «темы», «всего» считаются из СОСТАВА пачки — тем же
    `editor.computed`, что в предпросмотре; остальные приходят живыми значениями.
    """
    v = dict(values)
    v.update(editor.computed(cards))
    sh = editor.shell(db, contour)

    def text_of(f):
        return editor.subst(sh[f]["value"], v)

    html = render.composed_html(
        cards_data=cards, headline=text_of("headline"), sub=text_of("subtitle"),
        preheader=text_of("preheader"), footer=text_of("footer"),
        brand=brand, when=timez.msk_now(), logo_url=logo_url, settings_url=settings_url)
    return text_of("subject"), html


__all__ = ["card", "digest", "values", "TEXT", "LOOK"]
