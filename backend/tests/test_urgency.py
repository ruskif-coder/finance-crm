"""Срочность сделки — приоритет правил, каскад SLA и срок оплаты.

Функция чистая, поэтому проверяется прямыми комбинациями дат без базы.
Смысл тестов: зафиксировать ПОРЯДОК правил. Порядок здесь несущий — он определяет,
какую причину и какую кнопку увидит аккаунт, когда горит сразу несколько условий,
и он же гарантирует, что очередь и лента уведомлений не разойдутся.
"""
from datetime import date, timedelta

import pytest

from app.sales.urgency import (DealFacts, Verdict, evaluate, sla_for, payment_due,
                               queue_sort_key, OVERDUE, TODAY, SOON, NORMAL,
                               DEFAULT_TERM_DAYS)

TODAY_D = date(2026, 8, 17)


def facts(**kw) -> DealFacts:
    """Сделка «всё в порядке»: МП есть и завизирован, ДС есть, документы есть, оплачено.
    Тест портит ровно одно поле — так видно, что именно вызвало срочность."""
    # Нейтральная стадия — media_plan: она предзапусковая (правила 1-2 применимы, что
    # тестам и нужно) и при заполненном МП спокойна. booking больше не годится: у него
    # своё правило (подтверждение брони), closing — не предзапусковая вовсе.
    base = dict(stage_key="media_plan", money_layer="планируемые", has_mp=True,
                mp_approved=True, has_ds=True, has_closing_docs=True, is_paid=True)
    base.update(kw)
    return DealFacts(**base)


def d(days: int) -> date:
    return TODAY_D + timedelta(days=days)


# ─────────────────────────── каскад SLA ───────────────────────────

def test_sla_cascade_stage_wins_over_phase():
    assert sla_for(facts(stage_key="closing", stage_sla_days=3, phase_sla_days=5)) == 3


def test_sla_cascade_phase_wins_over_default():
    # closing по умолчанию 5, этап говорит 7
    assert sla_for(facts(stage_key="closing", phase_sla_days=7)) == 7


def test_sla_cascade_falls_to_stage_key_default():
    assert sla_for(facts(stage_key="media_plan")) == 2


def test_sla_zero_is_explicit_not_missing():
    """0 на стадии означает «срока нет» и НЕ должен падать на этап.
    Иначе снятый вручную срок вернулся бы обратно с уровня выше."""
    assert sla_for(facts(stage_key="launch", stage_sla_days=0, phase_sla_days=5)) == 0


def test_sla_unknown_stage_key_has_no_default():
    assert sla_for(facts(stage_key=None)) is None


# ─────────────────────────── срок оплаты ───────────────────────────

def test_payment_due_uses_counterparty_term():
    f = facts(period_to=date(2026, 7, 31), term_days=90)
    assert payment_due(f) == date(2026, 10, 29)


def test_payment_due_defaults_to_60_days():
    f = facts(period_to=date(2026, 7, 31))
    assert payment_due(f) == date(2026, 7, 31) + timedelta(days=DEFAULT_TERM_DAYS)


def test_payment_due_unknown_without_period_end():
    """Нет конца РК — срок неизвестен, а не «сегодня»."""
    assert payment_due(facts(period_to=None)) is None


# ─────────────────── терминальные вне очереди ───────────────────

@pytest.mark.parametrize("kw", [{"is_terminal": True}, {"is_lost": True}])
def test_terminal_and_lost_never_urgent(kw):
    """Даже с грудой нарушений: делать с закрытой сделкой нечего."""
    f = facts(has_mp=False, has_ds=False, is_paid=False,
              period_from=d(1), period_to=d(-100), **kw)
    assert evaluate(f, TODAY_D).urgency == NORMAL


# ─────────────────────── правила по порядку ───────────────────────

def test_rule1_no_mp_before_start():
    v = evaluate(facts(has_mp=False, mp_approved=False, period_from=d(3)), TODAY_D)
    assert v.urgency == OVERDUE
    assert v.cta == "Собрать МП"
    assert "МП не готов" in v.reason
    assert v.due == d(3)


def test_rule1_not_triggered_when_start_far():
    assert evaluate(facts(has_mp=False, mp_approved=False, period_from=d(30)),
                    TODAY_D).urgency == NORMAL


def test_rule2_mp_unapproved_before_start():
    v = evaluate(facts(mp_approved=False, period_from=d(2)), TODAY_D)
    assert (v.urgency, v.cta) == (OVERDUE, "Пингануть")


def test_rule1_beats_rule2():
    """Нет МП вообще — важнее, чем «не завизирован»: разные кнопки, нужна первая."""
    v = evaluate(facts(has_mp=False, mp_approved=False, period_from=d(2)), TODAY_D)
    assert v.cta == "Собрать МП"


def test_rule1_says_start_passed_not_negative_days():
    """«Старт через -442 дн.» — так выглядит забытая нижняя граница окна."""
    v = evaluate(facts(has_mp=False, mp_approved=False, period_from=d(-10)), TODAY_D)
    assert v.reason == "Старт прошёл 10 дн. назад, МП не готов"


def test_rule1_ignores_long_forgotten_start():
    """Старт год назад, сделка так и висит в проработке — это мусор в данных,
    а не работа на сегодня; вечно занимать очередь он не должен."""
    assert evaluate(facts(has_mp=False, mp_approved=False, period_from=d(-400)),
                    TODAY_D).urgency == NORMAL


@pytest.mark.parametrize("stage_key", ["launch", "closing", "archive"])
def test_rules_1_to_3_silent_after_launch(stage_key):
    """У сделки в эфире или на закрытии спрашивать «собери МП» поздно и незачем:
    там работают правила закрывающих документов и оплаты."""
    v = evaluate(facts(stage_key=stage_key, has_mp=False, mp_approved=False,
                       has_ds=False, period_from=d(2)), TODAY_D)
    assert v.kind not in ("deal_mp_missing", "mp_unapproved", "mp_rework")


def test_rule2_silent_when_approval_unknown():
    """МП приехал файлом из Битрикса: статуса согласования у него нет. None — «не знаю»,
    и считать такой план незавизированным нельзя."""
    assert evaluate(facts(mp_approved=None, period_from=d(2)),
                    TODAY_D).kind != "mp_unapproved"


def test_rework_after_reject_beats_waiting_for_visa():
    """МП отклонён — ответ уже получен, и он отрицательный: ждать нечего, надо
    переделывать. Поэтому раньше правила «не завизирован» и с другой кнопкой."""
    v = evaluate(facts(mp_approved=False, mp_rejected=True, period_from=d(4)), TODAY_D)
    assert (v.urgency, v.cta, v.kind) == (OVERDUE, "Переделать МП", "mp_rework")


def test_rework_yields_to_missing_mp():
    """Плана нет вообще — переделывать нечего."""
    v = evaluate(facts(has_mp=False, mp_rejected=True, period_from=d(3)), TODAY_D)
    assert v.cta == "Собрать МП"


def test_reject_beats_conveyor_check_on_first_stage():
    """План уже показали клиенту и он его забраковал — советовать «посмотрите план»
    бессмысленно. Отказ проверяется раньше непроверенности."""
    v = evaluate(facts(stage_is_first=True, mp_rejected=True, mp_approved=False,
                       period_from=d(30)), TODAY_D)
    assert (v.cta, v.kind) == ("Переделать МП", "mp_rework")


def test_reject_without_dates_still_reported():
    """У сделки может не быть периода вовсе — правило об отказе не должно от этого
    падать (start_phrase() на None бросал бы TypeError)."""
    v = evaluate(facts(stage_is_first=True, mp_rejected=True, mp_approved=False,
                       period_from=None, period_to=None), TODAY_D)
    assert v.reason == "МП отклонён — нужны правки"


def test_conveyor_mp_needs_manual_check():
    """Сделка родилась в конвейере вместе с МП и стоит на первой стадии: отправлять
    клиенту непроверенный автоплан нельзя, дата старта тут не важна."""
    v = evaluate(facts(stage_is_first=True, period_from=d(40)), TODAY_D)
    assert (v.urgency, v.cta, v.kind) == (SOON, "Проверить", "mp_verify")


def test_conveyor_mp_check_is_overdue_near_start():
    v = evaluate(facts(stage_is_first=True, period_from=d(3)), TODAY_D)
    assert v.urgency == OVERDUE


def test_missing_mp_beats_verify():
    """Плана нет вовсе — проверять нечего."""
    v = evaluate(facts(stage_is_first=True, has_mp=False, period_from=d(3)), TODAY_D)
    assert v.cta == "Собрать МП"


def test_booking_confirm_within_15_days():
    v = evaluate(facts(stage_key="booking", period_from=d(12)), TODAY_D)
    assert (v.urgency, v.cta, v.kind) == (SOON, "Подтвердить бронь", "booking_confirm")


def test_booking_confirm_turns_overdue_close_to_start():
    v = evaluate(facts(stage_key="booking", period_from=d(3)), TODAY_D)
    assert v.urgency == OVERDUE


def test_booking_confirm_silent_when_start_far():
    assert evaluate(facts(stage_key="booking", period_from=d(40)), TODAY_D).kind != "booking_confirm"


def test_missing_mp_beats_booking_confirm():
    """Без плана подтверждать нечего — сначала МП."""
    v = evaluate(facts(stage_key="booking", has_mp=False, period_from=d(4)), TODAY_D)
    assert v.cta == "Собрать МП"


def test_missing_ds_no_longer_urgent():
    """Правило «ДС не подписано» убрано: файлов ДС в системе нет, и оно срабатывало
    на каждой сделке в окне — то есть сообщало «мы не знаем», а не «ДС нет».
    Тест держит это решение: пустой has_ds сам по себе больше не поднимает строку."""
    v = evaluate(facts(has_ds=False, period_from=d(4)), TODAY_D)
    assert v.kind != "ds_unsigned"
    # Ровно normal, а не «скоро»: 4 дня до старта — вне трёхдневного окна дедлайна,
    # и без правила ДС у такой сделки не остаётся ни одной причины гореть.
    assert v.urgency == NORMAL


def test_rule6_closing_docs_missing():
    v = evaluate(facts(stage_key="closing", money_layer="фактические",
                       period_to=d(-10), has_closing_docs=False, is_paid=False),
                 TODAY_D)
    assert (v.urgency, v.cta) == (OVERDUE, "Прикрепить документы")
    assert "10 дн. назад" in v.reason


def test_rule6_has_five_day_grace():
    """Ровно через 5 дней после закрытия периода — ещё не просрочка."""
    assert evaluate(facts(stage_key="closing", money_layer="фактические",
                          period_to=d(-5), has_closing_docs=False),
                    TODAY_D).urgency == NORMAL


def test_rule6_silent_before_document_flow():
    """Сделке на броне или в размещении советовать «принесите УПД» нельзя: период мог
    закрыться, но документооборот по ней ещё не начинался."""
    for key, layer in (("booking", "планируемые"), ("launch", "реализуемые")):
        v = evaluate(facts(stage_key=key, money_layer=layer, period_from=d(-70),
                           period_to=d(-30), has_closing_docs=False), TODAY_D)
        assert v.kind != "act_missing", key


def test_rule7_payment_overdue():
    v = evaluate(facts(period_to=d(-70), is_paid=False, term_days=60), TODAY_D)
    assert (v.urgency, v.cta) == (OVERDUE, "Открыть дебиторку")
    assert "Просрочка оплаты 10 дн." == v.reason


def test_rule6_beats_rule7():
    """Документов нет и оплата просрочена — сначала документы: без них платить не за что."""
    v = evaluate(facts(stage_key="closing", money_layer="фактические",
                       period_to=d(-70), has_closing_docs=False, is_paid=False,
                       term_days=60), TODAY_D)
    assert v.cta == "Прикрепить документы"


def test_rule7_silent_when_paid():
    assert evaluate(facts(period_to=d(-70), is_paid=True), TODAY_D).urgency == NORMAL


def test_rule7_silent_when_payment_unknown():
    """None ≠ «не оплачено». Связи сделки с операцией в схеме нет, факт оплаты на этом
    уровне не читается — и тогда каждая закрытая сделка выглядела бы просроченной."""
    assert evaluate(facts(period_to=d(-70), is_paid=None), TODAY_D).urgency == NORMAL


def test_unknown_payment_does_not_hide_stage_stuck():
    """Следствие предыдущего: правило 7 молчит и НЕ съедает вердикт, поэтому
    зависшая стадия у той же сделки всё равно всплывает."""
    v = evaluate(facts(stage_key="closing", stage_since=d(-20), period_to=d(-70),
                       is_paid=None), TODAY_D)
    assert (v.urgency, v.kind) == (OVERDUE, "stage_stuck")


# ──────────────── связь с реестром событий уведомлений ────────────────

def test_every_kind_is_registered_except_payment():
    """Очередь и лента уведомлений обязаны говорить об одном и том же: каждый kind,
    который умеет вернуть функция, должен иметь событие в реестре. Исключение одно —
    payment_overdue: тема дебиторки принадлежит invoice_overdue (считает по операциям,
    где факт оплаты известен), и второе событие о том же было бы дублем."""
    from app.notify import registry

    kinds = {v.kind for v in [
        evaluate(facts(has_mp=False, mp_approved=False, period_from=d(3)), TODAY_D),
        evaluate(facts(mp_approved=False, period_from=d(2)), TODAY_D),
        evaluate(facts(mp_approved=False, mp_rejected=True, period_from=d(4)), TODAY_D),
        evaluate(facts(stage_key="closing", money_layer="фактические",
                       period_to=d(-10), has_closing_docs=False), TODAY_D),
        evaluate(facts(stage_is_first=True, period_from=d(40)), TODAY_D),
        evaluate(facts(stage_key="booking", period_from=d(12)), TODAY_D),
        evaluate(facts(stage_key="closing", stage_since=d(-11)), TODAY_D),
        evaluate(facts(stage_key=None, money_layer=None), TODAY_D),
    ]}
    assert kinds == {"deal_mp_missing", "mp_verify", "mp_unapproved", "mp_rework", "booking_confirm",
                     "act_missing", "stage_stuck", "stage_unmapped"}
    for k in kinds:
        assert registry.get(k) is not None, f"событие {k} не зарегистрировано"


def test_scanner_covers_all_queue_events():
    """Событие без функции сканера не сработает никогда, поэтому список правил
    и список событий очереди должны совпадать."""
    from app.notify.scanner import RULES, DEAL_QUEUE_EVENTS

    assert set(DEAL_QUEUE_EVENTS) <= set(RULES)


def test_rule5_stage_stuck_over_sla_is_soon():
    v = evaluate(facts(stage_key="closing", stage_since=d(-7)), TODAY_D)
    assert v.urgency == SOON
    assert "норма 5" in v.reason


def test_rule5_double_sla_is_overdue():
    assert evaluate(facts(stage_key="closing", stage_since=d(-11)),
                    TODAY_D).urgency == OVERDUE


def test_rule5_zero_sla_never_fires():
    """«В размещении» стоит месяцами и это нормально."""
    assert evaluate(facts(stage_key="launch", stage_sla_days=0, stage_since=d(-90)),
                    TODAY_D).urgency == NORMAL


def test_rule8_unmapped_layer_is_today():
    v = evaluate(facts(stage_key=None, money_layer=None), TODAY_D)
    assert (v.urgency, v.cta) == (TODAY, "Разобрать")


def test_unmapped_stage_wins_over_document_rules():
    """У несопоставленной стадии неизвестно даже, где сделка стоит, поэтому любой
    совет может быть неверным: сначала разобрать. Проверяем и предзапусковые правила,
    и закрывающие — «нет стадии» бьёт и те, и другие."""
    v6 = evaluate(facts(stage_key=None, money_layer=None, period_to=d(-30),
                        has_closing_docs=False), TODAY_D)
    assert (v6.cta, v6.kind) == ("Разобрать", "stage_unmapped")
    v = evaluate(facts(stage_key=None, money_layer=None, has_mp=False,
                       mp_approved=False, period_from=d(2)), TODAY_D)
    assert (v.cta, v.kind) == ("Разобрать", "stage_unmapped")


def test_deadline_today():
    assert evaluate(facts(period_from=d(0), period_to=d(30)), TODAY_D).urgency == TODAY


def test_deadline_soon_within_three_days():
    """Старт через 3 дня, но всё готово — просто «скоро», без просрочки."""
    assert evaluate(facts(period_from=d(3), period_to=d(30)), TODAY_D).urgency == SOON


def test_all_clear_is_normal():
    assert evaluate(facts(period_from=d(30), period_to=d(60)), TODAY_D).urgency == NORMAL


# ─────────────────────── сортировка очереди ───────────────────────

def test_queue_sort_urgency_then_due():
    rows = [
        Verdict(SOON, due=d(1)),
        Verdict(OVERDUE, due=d(5)),
        Verdict(OVERDUE, due=d(2)),
        Verdict(NORMAL),
        Verdict(TODAY, due=d(0)),
    ]
    order = [(v.urgency, v.due) for v in sorted(rows, key=queue_sort_key)]
    assert order == [(OVERDUE, d(2)), (OVERDUE, d(5)), (TODAY, d(0)),
                     (SOON, d(1)), (NORMAL, None)]


def test_rows_without_due_go_last_in_group():
    rows = [Verdict(OVERDUE), Verdict(OVERDUE, due=d(9))]
    assert [v.due for v in sorted(rows, key=queue_sort_key)] == [d(9), None]
