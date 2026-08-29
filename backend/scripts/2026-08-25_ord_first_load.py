"""Разовое наполнение зеркала ОРД из трёх выгрузок кабинета (вторая редакция).

Запускается модулем, не файлом:
    docker exec finance_backend python -m scripts.2026-08-25_ord_first_load \\
        /tmp/ord_initial.xlsx /tmp/ord_income.xlsx /tmp/ord_expense.xlsx

Файлы кладутся в контейнер через docker cp — выгрузки содержат имена реальных
контрагентов, в репозиторий им нельзя.
"""
import sys

from app.database import SessionLocal
from app.ord import importer


def main(initial_path: str, final_path: str, outer_path: str) -> None:
    db = SessionLocal()
    stat = importer.upsert(
        db,
        initial=open(initial_path, 'rb').read(),
        final=open(final_path, 'rb').read(),
        outer=open(outer_path, 'rb').read(),
    )
    print('прочитано строк: изначальных', stat['read_initial'],
         '· доходных', stat['read_final'], '· расходных', stat['read_outer'])
    print('контрагентов сопоставлено по ИНН (ord_client_id не пишем — см. I2):', stat['clients'])
    print('договоров помечено (ord_contract_id):', stat['contracts'])
    print('заведено изначальных договоров:', stat['initial'])
    print('заведено связей изначальный-доходный:', stat['links'])
    if stat['warnings']:
        print()
        print('предупреждений:', len(stat['warnings']))
        for w in stat['warnings'][:30]:
            print('   ', w)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
