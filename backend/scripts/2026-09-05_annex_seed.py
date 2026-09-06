# -*- coding: utf-8 -*-
"""Засев генератора приложений: реквизиты подписанта нашего юрлица и типовой шаблон.

Значения не выдуманы — взяты из подписанного документа «Приложение № 68» от 01.06.2026,
который владелец приложил как образец 05.09.2026.

Запуск: docker exec finance_backend python -m scripts.2026-09-05_annex_seed
Идемпотентно: повторный прогон ничего не дублирует и не затирает заполненное руками.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app import models as _core  # noqa: F401
from app.database import SessionLocal
from app.models import Counterparty
from app.sales.models import AnnexTemplate

# Формулировка услуги из образца. Меняются только подстановки — бренд и период;
# остальной текст приложения (стороны, сумма, общие условия, подписи) живёт в шаблоне
# документа, а не здесь: тут только то, что клиент может попросить сформулировать иначе.
BODY = (
    "На условиях настоящего Приложения № {номер} (далее по тексту – «Приложение») и "
    "Договора Исполнитель обязуется оказать услуги по размещению (распространению) "
    "рекламно-информационных материалов бренда: «{бренд}» (далее по тексту – «Услуги») "
    "в период с {период_с} г. по {период_по} г. согласно медиаплану:"
)


def main():
    db = SessionLocal()
    us = db.query(Counterparty).filter(Counterparty.is_own_company.is_(True)).first()
    touched = []
    if us:
        # Только пустые: заполненное руками важнее образца.
        if not us.signer_position:
            us.signer_position = "Генеральный директор"
            touched.append("должность")
        if not us.signer_basis:
            us.signer_basis = "Устава"
            touched.append("основание")
        if not us.signed_place:
            us.signed_place = "г. Москва"
            touched.append("место подписания")

    made = False
    if not db.query(AnnexTemplate).filter(AnnexTemplate.payer_id.is_(None)).first():
        db.add(AnnexTemplate(payer_id=None, name="Типовая формулировка", body=BODY,
                             is_default=True))
        made = True

    db.commit()
    print(f"наше юрлицо: {us.name if us else '—'}, дозаполнено: {', '.join(touched) or 'нечего'}")
    print(f"типовой шаблон: {'заведён' if made else 'уже был'}")
    print(f"всего шаблонов: {db.query(AnnexTemplate).count()}")
    db.close()


if __name__ == "__main__":
    main()
