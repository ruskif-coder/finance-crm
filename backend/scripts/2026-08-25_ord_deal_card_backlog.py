"""Записи в бэклог отладки после выкладки секций карточки сделки и цепочки ОРД (задача 8b).

Под наблюдением: механика сворачивания секций (запоминание состояния в localStorage)
и цепочка ОРД внутри секции «ОРД данные» — сводка в свёрнутом заголовке и сохранение
привязки изначального договора.

Запускается модулем:
    docker exec finance_backend python -m scripts.2026-08-25_ord_deal_card_backlog
"""
# ВАЖНО: app.models импортируется ПЕРВЫМ и только ради побочного эффекта — он
# регистрирует таблицу users в Base.metadata. BacklogItem.created_by/resolved_by
# ссылаются на users.id строкой ("users.id"); без предварительной регистрации
# SQLAlchemy падает NoReferencedTableError при первой же конфигурации мапперов.
import app.models  # noqa: F401
from datetime import date, timedelta

from app.backlog_models import BacklogItem
from app.database import SessionLocal
from app.models import User

# Дата выкладки задачи 8b — 2026-08-25; «через три недели», как требует практика бэклога.
WATCH_UNTIL = date(2026, 8, 25) + timedelta(days=21)  # 2026-09-15

ITEMS = [
    dict(
        title="Секции карточки сделки не запоминают состояние",
        area="Карточка сделки",
        context=(
            "components/deal/Section.js хранит открыто/свёрнуто в localStorage под "
            "ключом deal_sections_open, на пару «сделка × секция». Если запись не "
            "читается или не пишется (приватный режим браузера, повреждённый JSON), "
            "секция молча откатывается к defaultOpen при каждом заходе на карточку."
        ),
        signal_ok=(
            "Открыл карточку, свернул «МП сделки», перезагрузил страницу — секция "
            "осталась свёрнутой."
        ),
        signal_bad=(
            "Открываешь карточку — секции снова свёрнуты/развёрнуты не так, как "
            "оставил"
        ),
        severity="низкая",
    ),
    dict(
        title="Свёрнутая секция ОРД показывает неверную сводку",
        area="Карточка сделки",
        context=(
            "Сводка в заголовке секции «ОРД данные» считается функцией ordSummaryText "
            "([id].js) по последнему ответу AssemblyOrd (payer/final/initial) и "
            "обновляется только когда секцию уже открывали в этой сессии — до первого "
            "открытия заголовок нейтральный «не проверено»."
        ),
        signal_ok=(
            "В заголовке «цепочка сошлась» — внутри все три ступени зелёные; "
            "«выберите изначальный из N» — внутри действительно N кандидатов."
        ),
        signal_bad=(
            "В заголовке «цепочка сошлась», а внутри ступень требует выбора — или "
            "наоборот"
        ),
        severity="средняя",
    ),
    dict(
        title="Привязка изначального договора не сохраняется",
        area="ОРД",
        context=(
            "Кнопка «подтвердить»/«выбрать» на третьей ступени (AssemblyOrd.js) зовёт "
            "PUT /api/ord/deal/{id}/initial и по ответу заново запрашивает сборку "
            "(load()). Если запрос ушёл, но привязка не осела в БД, либо карточка "
            "перерисовалась по старым данным без повторного запроса — расхождение "
            "заметно только после перезагрузки страницы."
        ),
        signal_ok=(
            "Нажал «подтвердить» — ступень позеленела, после F5 остаётся зелёной с "
            "тем же договором."
        ),
        signal_bad=(
            "Нажал «подтвердить», ступень позеленела, после перезагрузки снова "
            "требует выбора"
        ),
        severity="высокая",
    ),
]


def main() -> None:
    db = SessionLocal()
    admin = db.query(User).filter(User.email == 'd.makarov@simb-ad.com').first()
    created = []
    try:
        for spec in ITEMS:
            item = BacklogItem(
                title=spec["title"], area=spec["area"], context=spec["context"],
                signal_ok=spec["signal_ok"], signal_bad=spec["signal_bad"],
                severity=spec["severity"], status="наблюдаем",
                watch_until=WATCH_UNTIL,
                created_by=admin.id if admin else None,
            )
            db.add(item)
            created.append(item)
        db.commit()
    finally:
        for item in created:
            if item.id is not None:
                db.refresh(item)
        for item in created:
            print(f"#{item.id}  {item.title}  (watch_until={item.watch_until})")
        db.close()


if __name__ == '__main__':
    main()
