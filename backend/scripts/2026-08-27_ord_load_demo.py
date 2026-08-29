"""Залить наши договоры на ДЕМО-контур ОРД, чтобы проверять на них выпуск маркеров.

    docker exec finance_backend python -m scripts.2026-08-27_ord_load_demo [--limit N]

ЗАЧЕМ. Демо-кабинет приходит пустым, а креатив нельзя зарегистрировать, не назвав
доходный и изначальный договоры. Идентификаторы, которые у нас есть, выданы БОЕВЫМ
контуром: демо про них не знает (проверено — `/contracts/final?Ids=` отдаёт ноль). Значит
цепочку надо завести в песочнице заново, и это разовая работа, а не часть приложения.

ПОЧЕМУ КОЛОНКИ ПРИ ЭТОМ НЕ ПОРТЯТСЯ. Демовский идентификатор не ложится поверх боевого:
за это отвечает `app/ord/registry.own_contour`, а сам демовский номер живёт в журнале
отправок `ord_submissions`, где и без того есть контур у каждой попытки. Скрипт ничего
не знает про это правило — он просто зовёт обычную регистрацию.

ЗАЩИТА ОТ БОЕВОГО КОНТУРА ЗДЕСЬ ОТДЕЛЬНАЯ. Массовая заливка на прод создала бы в ЕРИР
сотни записей, которые не отозвать, — поэтому скрипт отказывается работать где-либо,
кроме `demo`, даже если разрешение на боевую запись выдано. Одно дело нажать кнопку по
одному договору, другое — прогнать цикл.
"""
import argparse
import sys

from app.database import SessionLocal
from app.models import Contract
from app.ord import client, registry, submit
from app.ord.models import OrdInitialContract, OrdInitialFinalLink


class _Runner:
    """Пользователь для журнала: у разового скрипта нет учётной записи."""
    id = None
    name = 'скрипт заливки на демо'


def _load_clients(db, env, contracts, report):
    """Юрлица плательщиков. Отдельным шагом: регистрация договора их не заводит."""
    seen = set()
    for c in contracts:
        cp = c.counterparty
        if cp is None or not (cp.inn or '').strip() or cp.id in seen:
            continue
        seen.add(cp.id)
        if registry.known_id(db, 'client', registry.client_key(cp.inn), env,
                             cp.ord_client_id, cp.ord_env):
            report['clients_known'] += 1
            continue
        try:
            submit.ensure_client(db, cp.inn, cp.name, _Runner)
            report['clients_added'] += 1
        except Exception as e:                       # noqa: BLE001 — причина в отчёт
            report['failed'].append(f"юрлицо «{cp.name}»: {e}")


def _demo_final_for(db, env, prod_final_id):
    """Демовский номер того доходного, что на проде зовётся `prod_final_id`.

    Связи изначальных договоров записаны БОЕВЫМИ идентификаторами — перевести их на
    демо можно только через нашу строку договора, а она есть не у всех: часть доходных
    в кабинете чужие (у сделки HCLA6E такой нашёлся). Для них связь не переносится, и
    это не ошибка, а отсутствие нашей стороны.
    """
    row = (db.query(Contract)
             .filter(Contract.ord_contract_id == prod_final_id).first())
    if row is None:
        return None
    return registry.known_id(db, 'final_contract', row.id, env,
                             row.ord_contract_id, row.ord_env)


def main(limit=None):
    env = client.env()
    if env != 'demo':
        print(f"Контур {env}, а скрипт только для demo. Массовая заливка в ЕРИР "
              f"необратима — договоры на прод регистрируются по одному, с экрана.")
        return 1

    db = SessionLocal()
    report = {'clients_known': 0, 'clients_added': 0,
              'final_known': 0, 'final_added': 0,
              'initial_known': 0, 'initial_added': 0,
              'initial_no_final': 0, 'failed': []}
    try:
        finals = (db.query(Contract)
                    .filter(Contract.ord_contract_id.isnot(None),
                            Contract.ord_kind == 'final')
                    .order_by(Contract.id).all())
        if limit:
            finals = finals[:limit]
        print(f"доходных к заливке: {len(finals)}")

        _load_clients(db, env, finals, report)
        print(f"юрлица: уже были {report['clients_known']}, "
              f"завели {report['clients_added']}")

        for c in finals:
            if registry.known_id(db, 'final_contract', c.id, env,
                                 c.ord_contract_id, c.ord_env):
                report['final_known'] += 1
                continue
            try:
                submit.register_final_contract(db, c, _Runner)
                report['final_added'] += 1
            except Exception as e:                   # noqa: BLE001
                report['failed'].append(f"доходный {c.contract_number or c.id}: {e}")
        print(f"доходные: уже были {report['final_known']}, "
              f"завели {report['final_added']}")

        initials = (db.query(OrdInitialContract)
                      .filter(OrdInitialContract.ord_id.isnot(None))
                      .order_by(OrdInitialContract.id).all())
        if limit:
            initials = initials[:limit]
        for ini in initials:
            if registry.known_id(db, 'initial_contract', ini.id, env,
                                 ini.ord_id, ini.ord_env):
                report['initial_known'] += 1
                continue
            links = (db.query(OrdInitialFinalLink)
                       .filter(OrdInitialFinalLink.initial_contract_id == ini.id).all())
            demo_final = next((f for f in (_demo_final_for(db, env, l.final_ord_id)
                                           for l in links) if f), None)
            if not demo_final:
                # Изначальный регистрируется только прикреплённым к доходному — так
                # требует API. Нет нашего доходного на демо — нет и изначального.
                report['initial_no_final'] += 1
                continue
            try:
                submit.register_initial_contract(db, ini, demo_final, _Runner)
                report['initial_added'] += 1
            except Exception as e:                   # noqa: BLE001
                report['failed'].append(f"изначальный {ini.number or ini.id}: {e}")
        print(f"изначальные: уже были {report['initial_known']}, "
              f"завели {report['initial_added']}, "
              f"без нашего доходного {report['initial_no_final']}")

        if report['failed']:
            print(f"\nне удалось ({len(report['failed'])}):")
            for line in report['failed'][:40]:
                print("  ·", line)
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None,
                    help='взять первые N — для пробы перед полным прогоном')
    sys.exit(main(ap.parse_args().limit))
