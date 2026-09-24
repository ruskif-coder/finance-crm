# -*- coding: utf-8 -*-
"""ЕДИНСТВЕННАЯ точка перевода сделки на другую стадию.

## Зачем отдельный модуль

`our_stage_id` пишут ДВА человеческих пути: диалог движения и массовая правка в реестре.
Гейт, поставленный в одном из них, второй обходит молча — и обход доступен именно админу,
у которого и без того нет проверок прав. Владелец 13.09.2026 назвал это прямо: «через
админ доступ к реестру сделок мы всё равно двигаем сделки в обход правил».

Третьим считалась инлайн-правка стадии в реестре — её НЕ СУЩЕСТВУЕТ: модель `DealPatch`
поле `our_stage_id` никогда не объявляла, Pydantic его отбрасывал. Проверено прогоном
13.09.2026; тогда же из списка правимых полей убрана мёртвая строка.

Замер на тот же день: массовых правок 85, ни одна стадию не трогала; движений диалогом
32. То есть обходом ещё не пользовались — но дверь открыта, и первый, кто в неё войдёт,
отменит требования, не заметив этого. Это ровно та болезнь, которую проект уже проходил:
одно правило в двух местах не падает, оно РАСХОДИТСЯ.

Поэтому здесь и проверка требований, и запись истории, и отражение в Битрикс — в одной
функции, а пути её зовут.

## Обход не запрещён, он ИМЕНОВАН

Мастер может провести сделку мимо требований — это нужно, иначе хвост из 68 сделок без
плана не разобрать. Но обход перестаёт быть невидимым: он требует причины, пишется в
историю движения отдельной пометкой и виден в журнале. Разница между «правило не
сработало» и «человек провёл мимо правила, вот почему» — это разница между догадкой и
записью.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.sales import stage_checks as sc
from app.sales import stage_scope
from app.sales.catalog import Catalog
from app.sales.models import SalesDealStageHistory, SalesStageCheck

# Пометка в истории движения, по которой обход отличается от обычного перехода.
OVERRIDE_MARK = "в обход требований"


@dataclass
class Plan:
    """Что произойдёт при переводе — БЕЗ записи. Считается одинаково для всех путей,
    чтобы диалог показывал ровно то, что потом и случится."""
    target: object
    current: Optional[object] = None
    is_back: bool = False
    needs_pipeline: bool = False
    lines: list = field(default_factory=list)      # весь список требований цели
    blockers: list = field(default_factory=list)   # из них запирающие
    # Цель не применима к услуге сделки (разметка `sales_stage_services`).
    not_applicable: bool = False

    @property
    def allowed(self) -> bool:
        return not self.blockers and not self.not_applicable


def may_move(plan: Plan) -> bool:
    """Можно ли перевести БЕЗ человека: требования выполнены, цель применима к услуге,
    воронка на месте. Один вопрос для всей автоматики (привязка медиаплана, «Завершить
    РК»): до 24.09.2026 она смотрела только на блокеры, а неприменимая цель возвращает
    их пустыми (аудит 23.09.2026, 3.M1).

    Реестр этим вопросом НЕ пользуется намеренно: он пропускает то, что нельзя, — решение
    владельца 24.09.2026, временно, до разбора старых сделок."""
    return plan.allowed and not plan.needs_pipeline


def checks_for(db, stage_id) -> list:
    return (db.query(SalesStageCheck)
            .filter(SalesStageCheck.stage_id == stage_id)
            .order_by(SalesStageCheck.sort_order, SalesStageCheck.id).all())


def next_stage(db, deal, catalog: Optional[Catalog] = None, marks: Optional[dict] = None):
    """Следующая стадия ДЛЯ ЭТОЙ СДЕЛКИ: неприменимые к её услуге проскакиваются.

    Одна точка на всех: карточка, реестр, очередь аккаунта и кнопка «двинуть» обязаны
    называть одну и ту же стадию. Разойдутся — человек увидит «следующая: Бронь», нажмёт
    «двинуть» и попадёт в другую.

    `marks` — разметку стадий по услугам списком страниц передают ОДИН раз: реестр звал
    эту функцию на каждую строку, и каждая строка перечитывала разметку — до 500
    одинаковых запросов на страницу (аудит 23.09.2026, 3.L2)."""
    cat = catalog or Catalog(db)
    return stage_scope.next_for(deal, cat,
                                marks if marks is not None else stage_scope.stage_services(db))


def plan_move(db, deal, target, catalog: Optional[Catalog] = None) -> Plan:
    """Считает последствия перевода: назад ли, нужна ли воронка, что не выполнено.

    Требования берутся у стадии, в которую ВХОДИМ (решение владельца 13.09.2026).
    Следствие, которое надо держать в голове: прыжок сразу в терминал чтит требования
    только цели — то, что прошли мимо, не проверяется вовсе. Поэтому у «Архива успешных
    сделок» свои три записи (услуга, план, период), а не надежда на пройденный путь.
    """
    cat = catalog or Catalog(db)
    cur_id = deal.our_stage_id
    cur_stage = cat.by_id.get(cur_id)
    # Выход ИЗ терминала считается движением назад: сделка объявлена закрытой или
    # сорванной, и вернуть её в работу — решение мастера, а не обычный шаг. Без этого
    # терминал не входит в цепочку, `is_before` всегда False, и воскрешение проходило
    # как рядовой переход.
    is_back = (cur_id is not None and not target.is_terminal
               and (bool(getattr(cur_stage, "is_terminal", False))
                    or cat.is_before(target.id, cur_id)))
    # Стадия, неприменимая к услуге сделки, — не ошибка ввода, а промах разметки: её
    # просто не должно быть в списке. Отвечаем внятно, а не «требований нет».
    marks = stage_scope.stage_services(db)
    if not stage_scope.stage_applies(target.id, deal, marks):
        return Plan(target=target, current=cat.by_id.get(cur_id), is_back=is_back,
                    not_applicable=True)
    needs_pipeline = bool(target.phase and target.phase.is_realization
                          and not target.is_terminal
                          and not deal.realization_pipeline_id)
    lines = sc.evaluate(db, deal, checks_for(db, target.id))
    return Plan(target=target, current=cat.by_id.get(cur_id), is_back=is_back,
                needs_pipeline=needs_pipeline, lines=lines,
                blockers=sc.blockers(lines))


def apply_move(db, deal, target, user, *, reason: str, catalog: Optional[Catalog] = None,
               force: bool = False) -> dict:
    """Переводит сделку. Возвращает {moved, from_stage, to_stage, overridden}.

    НЕ решает, можно ли: это дело вызывающего — у диалога, массовой правки и автоматики
    разные способы сообщить об отказе. Здесь — общая часть: отражение привязки, запись
    истории и пометка обхода.

    Перестановка в ту же стадию историю НЕ пишет: иначе «сколько сделка стоит на стадии»
    обнулялось бы от повторного нажатия, и просрочку можно было бы снять, не сделав
    ничего."""
    from app.routers.sales_dashboard import _notify_move, _reflect_stage_binding

    cat = catalog or Catalog(db)
    cur_id = deal.our_stage_id
    prev = cat.by_id.get(cur_id)
    if cur_id == target.id:
        return {"moved": False, "from_stage": prev, "to_stage": target, "overridden": False}

    deal.our_stage_id = target.id
    _reflect_stage_binding(db, deal, target)
    note = (reason or "").strip() or "без причины"
    if force:
        note = f"{OVERRIDE_MARK}: {note}"
    db.add(SalesDealStageHistory(deal_id=deal.id, from_stage_id=cur_id,
                                 to_stage_id=target.id,
                                 user_id=getattr(user, "id", None), reason=note))
    # Уведомление о СУДЬБЕ сделки («доведена», «сорвалась», «ушла в бронь») шлём ЗДЕСЬ,
    # а не в диалоге. До 13.09.2026 оно жило в `move_deal`, и остальные пути меняли
    # стадию молча: мастер помечал двенадцать сделок сорвавшимися массовой правкой — и
    # ни одного события, хотя ровно эти события объявлены содержанием отказа.
    # Текст берём из `note`: у диалога это комментарий человека, у автоматики — причина
    # перехода. Для срыва причина и есть содержание письма.
    _notify_move(db, deal, prev, target, note, user)
    return {"moved": True, "from_stage": prev, "to_stage": target, "overridden": bool(force)}


def refusal_text(plan: Plan) -> str:
    """Человеческий отказ: перечисляет ЧТО не выполнено, а не «нельзя».

    Каждая строка несёт свою подсказку и, у веерных, имена мешающих — иначе на экране
    окажется «не согласовано» без ответа на вопрос «у кого»."""
    if plan.not_applicable:
        return (f"Стадия «{plan.target.name}» не относится к услуге этой сделки — "
                "выберите другую")
    parts = []
    for ln in plan.blockers:
        bit = ln.title
        if ln.result.detail:
            bit += f" ({ln.result.detail})"
        if ln.result.blockers:
            bit += ": " + ", ".join(map(str, ln.result.blockers[:5]))
            if len(ln.result.blockers) > 5:
                bit += f" и ещё {len(ln.result.blockers) - 5}"
        parts.append(bit)
    return "Нельзя перейти в «%s» — не выполнено: %s" % (plan.target.name, "; ".join(parts))


def is_master(user) -> bool:
    """Кто может двигать назад и проводить мимо требований. Тот же признак, что уже
    гейтил движение назад, — второго понятия «мастер» заводить не надо."""
    role = getattr(user, "role", None)
    return bool(role and (role.key == "admin" or getattr(role, "is_master", False)))
