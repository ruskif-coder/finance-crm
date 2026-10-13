# -*- coding: utf-8 -*-
"""Рекламодатель сделки по изначальному договору ОРД: (ИНН, название) — одним расчётом на всё.

Читают двое: рекламная метка креатива в DSP (`self_inn` / `self_name`, `app/dsp/provision.py`) и шапка
окна «Задачи РК» в кабинете трафика (13.10.2026). Метка в DSP и то, что видит трафик, обязаны говорить то
же, что ЕРИР, — поэтому функция одна, а не две похожие (раньше жила в выгрузке в DSP).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.ord import readiness


def advertiser_label(db: Session, deal_id) -> Optional[tuple]:
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
