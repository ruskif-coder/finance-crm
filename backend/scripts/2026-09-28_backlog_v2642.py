"""Бэклог отладки после выкладки v2.6.42 (28.09.2026): ранний выпуск ЕРИД с подтверждением,
кабинеты DSP (боевой / демо), журнал DSP по клиенту кабинета, punycode доменов площадок.

Главное поле — signal_bad: как поломка выглядит СО СТОРОНЫ ПОЛЬЗОВАТЕЛЯ. Повторный
запуск записей не плодит (по title).

Запуск: docker exec finance_backend python -m scripts.2026-09-28_backlog_v2642
"""
import sys
from datetime import date, timedelta

sys.stdout.reconfigure(encoding='utf-8')

from app import models as _core_models  # noqa: F401,E402 — таблица users нужна FK бэклога
from app.backlog_models import BacklogItem  # noqa: E402
from app.database import SessionLocal  # noqa: E402

WATCH = (date.today() + timedelta(days=21)).isoformat()

ITEMS = [
    dict(
        title="DSP: РК снова ушла не в тот кабинет (v2.6.42)",
        area="Трафик",
        context=("Клиент кабинета для РК — поле «Боевой клиент — выгрузка РК» в админке "
                 "трафика, иначе DSP_PARTNER_XXHASH; нацеливание — демоклиент. Защита от "
                 "дублей ищет хеши только своего клиента. РК 45 и 46 отвязаны от демо-кабинета "
                 "скриптом 2026-09-28_dsp_partner_reset."),
        signal_ok="После «D» кампания и креативы видны в кабинете БОЕВОГО клиента DSP.",
        signal_bad=("Кампания после «D» появилась в демо-кабинете; или «D» отвечает, что всё "
                    "заведено, а в боевом кабинете кампании нет; или кнопка ◎ перестала "
                    "показывать баннер на площадке."),
        severity="высокая",
    ),
    dict(
        title="WR/DSP: площадка с кириллическим доменом снова отвергнута (v2.6.42)",
        area="Трафик",
        context="Домены площадок уходят в WR и DSP в punycode (`009.рф` → `009.xn--p1ai`).",
        signal_ok="Вставки WR и креативы DSP для 009.рф и 120на80.рф заводятся без отказа.",
        signal_bad="Отказ WR или DSP с упоминанием домена площадки с кириллицей.",
        severity="средняя",
    ),
    dict(
        title="ЕРИД: ранний выпуск без вопроса или вопрос при взятом пороге (v2.6.42)",
        area="Аккаунты",
        context=("Кнопка «Выпустить ЕРИД» до порога автовыпуска требует отметки «Выпустить до "
                 "согласования площадок»; сервер без неё отвечает 409; в журнале — "
                 "«ЕРИД выпущен до согласования площадок»."),
        signal_ok="Окно спрашивает, только когда площадки ещё не набрали порог.",
        signal_bad=("ЕРИД выпущен без отметки при 0 согласованиях; или отметку требуют, когда "
                    "площадки уже согласовали; или кнопка выпуска не срабатывает вовсе."),
        severity="высокая",
    ),
]


def main():
    db = SessionLocal()
    added = 0
    for item in ITEMS:
        if db.query(BacklogItem).filter(BacklogItem.title == item["title"]).first():
            continue
        db.add(BacklogItem(status="наблюдаем", watch_until=WATCH, **item))
        added += 1
    db.commit()
    print(f"заведено: {added} из {len(ITEMS)}, наблюдаем до {WATCH}")
    db.close()


if __name__ == "__main__":
    main()
