"""
fill_pm_requisites.py

Заполняет реквизиты контрагента "ООО Программатик Медиа" (находит по ИНН 7725261852
или по точному названию) из файла реквизитов SIMB-AD 2025.docx.

Режимы:
  dry-run (по умолчанию) — только выводит, что будет изменено
  --apply               — записывает в БД

Запуск:
  docker exec finance_backend python app/fill_pm_requisites.py
  docker exec finance_backend python app/fill_pm_requisites.py --apply
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import Counterparty, CounterpartyBankAccount

# ── Данные из реквизитов ──────────────────────────────────────────────────────
REQUISITES = {
    "inn":           "7725261852",
    "kpp":           "770101001",
    "ogrn":          "1157746091722",
    "okpo":          "32451945",
    "address":       "105082, г. Москва, пер. Переведеновский, д. 13 стр. 18, офис 612",
    "phone":         "8 800 500 75 22",
    "email":         "i@programmatic-media.ru",
    "edo_id":        "2BM-7725261852-772501001-201609160223514835082",
    "director_name": "Макаров Денис Сергеевич",
    "website":       "programmatic-media.ru",
}

BANK_ACCOUNTS = [
    {
        "bank_name": 'АО "Альфа-Банк"',
        "rs":        "40702810702860001571",
        "ks":        "30101810200000000593",
        "bik":       "044525593",
    },
    {
        "bank_name": 'АО "ОТП Банк"',
        "rs":        "40702810000520001472",
        "ks":        "30101810000000000311",
        "bik":       "044525311",
    },
]

LOOKUP_INN  = "7725261852"
LOOKUP_NAME = "ООО Программатик Медиа"


def main():
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        # Ищем контрагента по ИНН, потом по названию
        cp = db.query(Counterparty).filter(Counterparty.inn == LOOKUP_INN).first()
        if not cp:
            cp = db.query(Counterparty).filter(Counterparty.name.ilike(f"%Программатик Медиа%")).first()
        if not cp:
            print(f"ОШИБКА: Контрагент с ИНН {LOOKUP_INN} или именем «{LOOKUP_NAME}» не найден.")
            return

        print("=" * 70)
        print(f"Контрагент найден: ID={cp.id}  «{cp.name}»")
        print("=" * 70)

        # Показываем изменения
        for field, new_val in REQUISITES.items():
            old_val = getattr(cp, field, None)
            if old_val != new_val:
                print(f"  {field}: {old_val!r} → {new_val!r}")
            else:
                print(f"  {field}: (без изменений) {new_val!r}")

        existing_banks = db.query(CounterpartyBankAccount).filter(
            CounterpartyBankAccount.counterparty_id == cp.id
        ).all()
        print(f"\n  Банковские счета: {len(existing_banks)} → {len(BANK_ACCOUNTS)}")
        for i, ba in enumerate(BANK_ACCOUNTS):
            print(f"    [{i+1}] {ba['bank_name']}  Р/С {ba['rs']}  БИК {ba['bik']}")

        print()
        if apply_mode:
            for field, new_val in REQUISITES.items():
                setattr(cp, field, new_val)

            # Перезаписываем банковские счета
            db.query(CounterpartyBankAccount).filter(
                CounterpartyBankAccount.counterparty_id == cp.id
            ).delete()
            for i, ba in enumerate(BANK_ACCOUNTS):
                db.add(CounterpartyBankAccount(
                    counterparty_id=cp.id,
                    bank_name=ba["bank_name"],
                    rs=ba["rs"],
                    ks=ba["ks"],
                    bik=ba["bik"],
                    sort_order=i,
                ))

            db.commit()
            print("ПРИМЕНЕНО: реквизиты и банковские счета обновлены.")
        else:
            db.rollback()
            print("DRY RUN — ничего не записано. Добавьте --apply для применения.")
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    main()
