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

    Сопоставлений ДВА, и оба считаются: по ключу роли и по её рабочей группе. Второе
    появилось 31.08.2026, когда выяснилось, что ключ вида `role_<id>` у каждой установки
    свой: раскладка трафика по ключам стенда на проде не сработала бы.
    """
    from app.models import Role, User

    from app.notify.seed_profiles import STAFF_GROUP_TO_PROFILE

    db = SessionLocal()
    try:
        used = {(k, g) for (k, g) in db.query(Role.key, Role.staff_group)
                .join(User, User.role_id == Role.id)
                .filter(User.is_active == 1).distinct().all()}
    finally:
        db.close()
    missing = sorted(k for k, g in used
                     if k not in ROLE_TO_PROFILE and g not in STAFF_GROUP_TO_PROFILE)
    assert not missing, (
        f'роли есть у живых людей, но не сопоставлены с профилем: {missing}'
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
#
# 31.08.2026 из списка убраны `mp_rework` и `mp_stuck`: правил с такими ключами больше
# нет (удалены 30.08 вместе со стейт-машиной МП, `test_notify.RETIRED_MP_EVENTS`). Список
# с призраками не мера — по нему не видно, сокращается он или нет.
# 31.08.2026 список ОПУСТЕЛ, и это не уборка кода, а событие в данных: владелец сам
# раздал профилю «Аккаунт» подписку на все 26 событий через интерфейс (audit_log,
# `save_notification_profile_subs`, 12:39). Долг, ради которого список заводился, закрыт
# по существу — сканерным правилам назначен адресат.
#
# ВАЖНО ПРО ПРОД: это НАСТРОЙКА, то есть строки в `notification_subscriptions`, а не код
# и не миграция. На боевой базе её нет и она туда не переедет ни с `git pull`, ни с
# накатом миграций. Пока раскладку там не повторят, сканер на проде снова работает в
# пустоту — с той разницей, что теперь об этом известно.
KNOWN_SILENT = set()


def test_the_silent_list_has_no_ghosts():
    """В замороженном списке нет ключей, которых уже нет в коде.

    Призрак в списке безобиден на вид и вреден по сути: список объявлен «только
    сокращающимся», и два снятых ключа читаются как два незакрытых долга. Ровно так
    31.08.2026 он и разошёлся с соседним прибором, который те же ключи числил снятыми.
    """
    scanned = {e.key for e in _events() if getattr(e, 'scan', False)}
    ghosts = KNOWN_SILENT - scanned
    assert not ghosts, f'в KNOWN_SILENT ключи, которых нет среди правил: {sorted(ghosts)}'


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

    31.08.2026 сам прибор переехал с ключей ролей на рабочую группу: ключи `role_120` и
    `role_121` — id ролей ЭТОГО стенда, и на проде их нет (репетиция на боевой базе).
    """
    to_traffic = [e.key for e in _events()
                  if any(r.get('type') == 'staff_group' and r.get('value') == 'traffic'
                         for r in (e.recipients or []))]
    assert to_traffic, 'ни одно событие не адресовано контуру трафика'


def test_no_event_is_addressed_to_a_generated_role_key():
    """Адресат-роль может быть только СИСТЕМНОЙ ролью.

    Ключ вида `role_<id>` — это номер строки в таблице ролей той установки, где роль
    завели. На другой установке та же по смыслу роль получит другой id и другой ключ.
    Событие, адресованное `role_121`, на проде не находит никого — и молчит об этом:
    пустой список получателей ошибкой не считается, `emit` просто выходит.

    Найдено репетицией на боевой базе 31.08.2026: два события контура трафика были
    адресованы `role_120`/`role_121` (id моего стенда), а на проде трафик живёт на
    ролях 12 и 13. Ушли бы в пустоту оба.

    Системные ключи (`admin`, `manager`, `viewer`) заводятся при создании базы и
    одинаковы везде — их можно. Всё остальное адресуется контуром (`staff_group`)
    или резолвером.
    """
    import re

    SYSTEM = {'admin', 'manager', 'viewer'}
    bad = []
    for ev in _events():
        for spec in ev.recipients or []:
            if spec.get('type') != 'role':
                continue
            v = spec.get('value') or ''
            if re.fullmatch(r'role_\d+', v) or v not in SYSTEM:
                bad.append(f'{ev.key} → «{v}»')
    assert not bad, (
        'события адресованы ролью, ключ которой у каждой установки свой '
        '(адресуйте staff_group или резолвером):\n  ' + '\n  '.join(bad))


# ── Единый ярлык сделки в уведомлениях ───────────────────────────────────────

def test_deal_label_is_code_first_then_name():
    """Код первым, имя вторым — тот же порядок, что у заголовка карточки сделки.

    До 14.09.2026 формат зависел от события: у креативов в заголовке стоял только код,
    у воронки — только имя, у очереди — имя с услугой. Человеку нужно и то и другое: по
    имени он узнаёт сделку, по коду находит её в реестре и называет коллеге. Видел он
    одно из двух, и какое именно — зависело от того, какое правило сработало.
    """
    from app.sales.deal_label import deal_label

    class D:
        id, code, title, product = 42, "7E2JWE", "Эспумизан 09", "еФарм"

    assert deal_label(D()) == "7E2JWE · Эспумизан 09"
    assert deal_label(D(), service=True) == "7E2JWE · Эспумизан 09 · еФарм"


def test_deal_label_survives_missing_parts():
    """Запасные ветки: сделка без имени, без кода, без всего.

    Замер 14.09.2026: код и имя есть у всех 920 сделок, то есть ветки нужны импорту и
    ручной вставке. Пустой ярлык хуже некрасивого — по нему нельзя найти сделку."""
    from app.sales.deal_label import deal_label

    class NoTitle:
        id, code, title, product = 42, "7E2JWE", "", None

    class NoCode:
        id, code, title, product = 42, "", "Эспумизан 09", None

    class Bare:
        id, code, title, product = 42, None, None, None

    assert deal_label(NoTitle()) == "7E2JWE"
    assert deal_label(NoCode()) == "#42 · Эспумизан 09"
    assert deal_label(Bare()) == "#42"
    assert deal_label(Bare(), service=True) == "#42"


def test_every_deal_notification_uses_the_one_label():
    """Храповик: заголовок уведомления не собирается из `deal.code` или `deal.title` руками.

    Иначе формат разойдётся снова — он уже расходился, и заметить это можно было только
    прочитав все двадцать шесть текстов подряд.
    """
    import io
    import re
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    bad = []
    for path in sorted(app_dir.rglob("*.py")):
        src = io.open(path, encoding="utf-8").read()
        for m in re.finditer(r"title=f\"[^\"]*\"", src):
            frag = m.group(0)
            if re.search(r"\{deal\.(code|title)\b", frag):
                bad.append(f"{path.relative_to(app_dir)}: {frag[:70]}")
    assert not bad, ("заголовок уведомления собран мимо deal_label:\n"
                     + "\n".join("  " + b for b in bad))


# ── Модуль собран воедино ────────────────────────────────────────────────────

def test_notifications_live_in_one_module():
    """Уведомления не расползаются обратно по проекту.

    До 14.09.2026 внешний контур жил в `app/cabinet`, доставка была спрятана приватными
    функциями внутри шины, и добавить вид означало править куски в трёх местах. Храповик
    держит сборку: файл с уведомлениями за пределами `app/notify` — это возврат к тому
    состоянию, и он должен быть заметен сразу, а не через полгода.
    """
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    strays = []
    for p in app_dir.rglob("*.py"):
        rel = p.relative_to(app_dir)
        if "notify" not in p.name or "notify" in rel.parts:
            continue
        # Роутеры — HTTP-поверхность, они живут в `app/routers` по устройству проекта и
        # исключены намеренно: `notify_settings.py` — экран настроек, а не логика.
        if rel.parts[0] == "routers":
            continue
        strays.append(str(rel))
    assert not strays, f"уведомления снова снаружи модуля: {strays}"


def test_delivery_is_not_duplicated_by_the_contours():
    """КАК доходит сообщение — знает `channels`, и только он.

    Оба контура зовут почту через один гейт и один сборщик разметки. Второй способ
    доставки в обход канала означал бы два разных письма на одно событие — ровно то, из-за
    чего модуль и собирали.
    """
    import io
    from pathlib import Path

    notify = Path(__file__).resolve().parents[1] / "app" / "notify"
    senders = []
    for p in notify.rglob("*.py"):
        if p.name in ("channels.py",):
            continue
        src = io.open(p, encoding="utf-8").read()
        if "mail.send(" in src:
            senders.append(str(p.relative_to(notify)))
    assert senders == [], (
        f"отправка почтой мимо канала: {senders} — доставка живёт в channels.py")


def test_outward_has_its_own_door():
    """У внешнего контура своя дверь, а не ветка в общей.

    Проверка структурная: `outward` обязан быть подпакетом со своим `__init__`, а не
    файлом рядом. Иначе первый же рефакторинг сольёт его с внутренним, и адресация
    сотрудника окажется в одной функции с адресацией площадки.
    """
    from pathlib import Path

    outward = Path(__file__).resolve().parents[1] / "app" / "notify" / "outward"
    assert (outward / "__init__.py").exists()
    for part in ("kinds.py", "send.py", "schedule.py"):
        assert (outward / part).exists(), f"часть внешнего контура пропала: {part}"
