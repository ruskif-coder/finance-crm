# -*- coding: utf-8 -*-
"""Обвязка уведомлений: событие есть — значит у него есть адресат и канал.

Модуль уведомлений устроен из трёх независимых частей, и каждая по отдельности может
быть в порядке, пока вместе они не работают:

  · РЕЕСТР событий (`app/notify/registry.py`) — кому уходит;
  · ПРОФИЛИ и подписки — по какому каналу;
  · раскладка ролей по профилям — кто вообще в системе рассылки.

Замер 30.08.2026 нашёл разрыв во всех трёх сразу: подписок было НОЛЬ строк (скрипт
раскладки ни разу не прогоняли), три роли не были сопоставлены ни с одним профилем, а
контуру трафика не адресовалось ни одно событие — очередь у него была, а узнать о новой
работе он мог только зайдя и посмотрев.

Ошибки здесь молчаливые по природе: событие исправно порождается, ложится в журнал и
никому не доходит. Ни исключения, ни пустого экрана — просто тишина, неотличимая от
«ничего не случилось».
"""
from app.database import SessionLocal
from app.notify import registry
from app.notify.models import NotificationProfile, NotificationSubscription
from app.notify.seed_profiles import PLAN, ROLE_TO_PROFILE


def _events():
    evs = getattr(registry, 'EVENTS', None) or getattr(registry, '_EVENTS', None) or {}
    return list(evs.values()) if hasattr(evs, 'values') else list(evs)


def test_every_active_role_has_a_profile():
    """Роль без профиля означает человека, получающего чужой набор уведомлений.

    Профиль по умолчанию — «Аккаунт»; трафик, попавший в него, читал бы про медиапланы
    и не читал бы про свою очередь.
    """
    from app.models import Role, User

    db = SessionLocal()
    try:
        used = {k for (k,) in db.query(Role.key).join(User, User.role_id == Role.id)
                .filter(User.is_active == 1).distinct().all()}
    finally:
        db.close()
    missing = used - set(ROLE_TO_PROFILE)
    assert not missing, (
        f'роли есть у живых людей, но не сопоставлены с профилем: {sorted(missing)}'
    )


def test_every_profile_in_the_plan_exists_in_the_database():
    """Опечатка в ключе профиля не падает — скрипт пишет «профиль не найден» и идёт дальше."""
    db = SessionLocal()
    try:
        known = {p.key for p in db.query(NotificationProfile).all()}
    finally:
        db.close()
    assert not (set(PLAN) - known), f'профилей нет в базе: {sorted(set(PLAN) - known)}'
    assert not (set(ROLE_TO_PROFILE.values()) - known), (
        f'роли ссылаются на несуществующие профили: '
        f'{sorted(set(ROLE_TO_PROFILE.values()) - known)}'
    )


def test_every_planned_event_exists_in_the_registry():
    """Событие из раскладки, которого нет в реестре, — подписка в никуда."""
    keys = {e.key for e in _events()}
    planned = {k for evs in PLAN.values() for k in evs}
    assert not (planned - keys), f'нет в реестре: {sorted(planned - keys)}'


# Правила, которые сегодня срабатывают в пустоту. Список ЗАМОРОЖЕН 30.08.2026 и должен
# только сокращаться: он и есть ответ на «190 сработок против двух доставок» — раскладка
# профилей (`PLAN`) покрывала только медиапланы, а все правила, заведённые позже — очередь
# сделок, креативы, бэклог, счета, — не попали ни в один профиль.
#
# Кому какое из них адресовать — решение владельца, а не программиста: адресат
# уведомления это про то, чья это работа, и угадывать здесь дороже, чем спросить.
# Прибор ниже не требует закрыть их сегодня; он требует, чтобы НОВОЕ правило не
# пополнило список молча.
KNOWN_SILENT = {
    'act_missing', 'backlog_overdue', 'booking_confirm', 'creative_erid_failed',
    'deal_mp_missing', 'invoice_overdue', 'mp_draft_stale', 'mp_rework', 'mp_stuck',
    'mp_unapproved', 'mp_verify', 'plan_month_empty', 'stage_stuck', 'stage_unmapped',
}


def test_no_new_rule_joins_the_silent_ones():
    """Новое сканерное правило обязано иметь подписчика.

    Правило без подписки отрабатывает вхолостую: сработка ложится в журнал состояний,
    доставки не порождает, и в сводке прогона выглядит как проделанная работа. Отличить
    «сработало и дошло» от «сработало в пустоту» по выводу сканера нельзя.
    """
    db = SessionLocal()
    try:
        subscribed = {s.event_key for s in db.query(NotificationSubscription).all()}
    finally:
        db.close()
    scanned = {e.key for e in _events() if getattr(e, 'scan', False)}
    new_silent = sorted(scanned - subscribed - KNOWN_SILENT)
    assert not new_silent, (
        f'новые правила без единой подписки: {new_silent}. '
        'Они срабатывают, но не доходят ни до кого.'
    )


def test_the_silent_list_only_shrinks():
    """Замороженный список не должен расти, а разобранное из него — уходить.

    Если правило получило подписку, его имя обязано исчезнуть отсюда: иначе список
    перестаёт быть перечнем долгов и становится украшением.
    """
    db = SessionLocal()
    try:
        subscribed = {s.event_key for s in db.query(NotificationSubscription).all()}
    finally:
        db.close()
    resolved = sorted(KNOWN_SILENT & subscribed)
    assert not resolved, (
        f'этим правилам подписку уже дали — уберите их из KNOWN_SILENT: {resolved}'
    )


def test_traffic_contour_is_addressed_at_all():
    """Контуру трафика адресовано хоть что-то.

    До 30.08.2026 — ни одного события: очередь была, уведомления не было. Прибор
    формулирован широко нарочно, чтобы не ломаться при переименовании конкретного
    события, но падать, если адресация исчезнет целиком.
    """
    to_traffic = [e.key for e in _events()
                  if any(r.get('value') in ('role_120', 'role_121')
                         for r in (e.recipients or []))]
    assert to_traffic, 'ни одно событие не адресовано ролям трафика'
