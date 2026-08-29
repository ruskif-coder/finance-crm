"""Наполнение системных профилей подписками — из реестра, а не из SQL.

Запуск: docker exec finance_backend python -m app.notify.seed_profiles

Идемпотентно: уже существующие подписки НЕ перезаписываются (иначе прогон затёр бы
ручные настройки админа). Добавляются только недостающие пары «профиль + событие».

Почему скриптом, а не INSERT'ами в миграции: дефолты обязаны считаться от реестра,
иначе они разъедутся с кодом ровно так же, как в своё время разъехались ACTION_LABELS.
"""
import sys

from app.database import SessionLocal
from app.notify import registry
from app.notify.models import NotificationProfile, NotificationSubscription

# Какие события кладём в какой профиль и с какими каналами.
# Ключ — профиль, значение — {event_key: [каналы]}.
#
# ВАЖНО про каналы на этом этапе: везде только "app". Профиль по умолчанию действует
# на всех пользователей, поэтому любой другой канал здесь означал бы изменение уже
# работающего поведения МП — а обработчиков дайджеста и Telegram ещё нет (фазы 4-5),
# их отправки лежат в журнале статусом queued и человеку не видны. Перевод части
# событий в дайджест — сознательное решение пользователя в интерфейсе, а не побочный
# эффект переезда на реестр.
#
# Кому уходит событие, здесь НЕ задаётся: получатели объявлены в реестре
# (mp_approvers / mp_stakeholders), профиль управляет только каналами.
PLAN = {
    "account":        {k: ["app"] for k in ("mp_submit", "mp_approved", "mp_rejected",
                                            "mp_archived", "mp_recalled")},
    "account_master": {k: ["app"] for k in ("mp_submit", "mp_approved", "mp_rejected",
                                            "mp_archived", "mp_recalled")},
    "sales":          {k: ["app"] for k in ("mp_approved", "mp_rejected", "mp_archived")},
    "fin":            {k: ["app"] for k in ("mp_approved", "mp_rejected")},
    "admin":          {k: ["app"] for k in ("mp_submit", "mp_approved", "mp_rejected",
                                            "mp_archived", "mp_recalled")},

    # Трафик (30.08.2026). Два события и ровно два: пришла работа и кто-то из своих
    # молчит. Всё остальное в реестре — про медиапланы и сделки, к материалу отношения
    # не имеющие; положить их сюда значило бы приучить контур не читать уведомления.
    "traffic":        {k: ["app"] for k in ("traffic_new_work", "traffic_silence")},

    # Менеджер паблишеров. Его роль уже стоит адресатом в `creative_silence` — молчание
    # площадки это его разговор, а не аккаунта. Профиль нужен, чтобы у события были
    # каналы: без подписки оно доходит только до тех, у кого профиль уже есть.
    "publishers":     {k: ["app"] for k in ("creative_silence", "creative_verdict")},
}


# Стартовая раскладка сотрудников по профилям: ключ роли → ключ профиля.
# Это ТОЛЬКО первичное заполнение — дальше профиль назначается человеку вручную и
# от роли не зависит (в том и смысл: роль = что можно видеть, профиль = что касается).
# Пользователей с уже назначенным профилем скрипт не трогает.
ROLE_TO_PROFILE = {
    "role_8": "account",          # Аккаунт
    "role_9": "account_master",   # Мастер аккаунт
    "role_7": "sales",            # Сейлз
    "role_5": "sales",            # Мастер Сейлз — пока тот же набор, дальше разведём
    "manager": "fin",             # Фин Менеджер
    "role_6": "fin",              # Юрист — договоры и закрывающие живут в «Финансах»
    "viewer": "fin",              # Наблюдатель
    "admin": "admin",
    # Заведены 30.08.2026 — до этого три роли не были сопоставлены ни с чем, и скрипт
    # честно писал «пропуск», а люди оставались в профиле по умолчанию.
    "role_120": "traffic",        # Траффик
    "role_121": "traffic",        # Мастер траффик
    "role_10": "publishers",      # Менеджер паблишеров
}


def assign_profiles(dry_run: bool = False) -> int:
    """Разложить активных пользователей по профилям согласно их ролям.

    Нужно потому, что без явного назначения все попадают в профиль по умолчанию —
    и счётчик «Аккаунт · 14 чел.» показывает всю компанию, что неправда.
    """
    from app.models import User, Role

    db = SessionLocal()
    changed = 0
    try:
        profiles = {p.key: p.id for p in db.query(NotificationProfile).all()}
        roles = {r.id: r.key for r in db.query(Role).all()}
        for u in db.query(User).filter(User.is_active == 1,
                                       User.notification_profile_id.is_(None)).all():
            prof_key = ROLE_TO_PROFILE.get(roles.get(u.role_id))
            pid = profiles.get(prof_key) if prof_key else None
            if not pid:
                print(f"  ? {u.email}: роль {roles.get(u.role_id)} не сопоставлена — пропуск")
                continue
            u.notification_profile_id = pid
            changed += 1
            print(f"  → {u.email}: профиль «{prof_key}»")
        if dry_run:
            db.rollback()
            print(f"Сухой прогон: назначений было бы {changed}")
        else:
            db.commit()
            print(f"Готово: назначено профилей {changed}")
        return changed
    finally:
        db.close()


def run(dry_run: bool = False) -> int:
    db = SessionLocal()
    added = 0
    try:
        for prof_key, events in PLAN.items():
            prof = db.query(NotificationProfile).filter(
                NotificationProfile.key == prof_key).first()
            if prof is None:
                print(f"  ! профиль {prof_key} не найден — пропуск")
                continue
            for event_key, channels in events.items():
                ev = registry.get(event_key)
                if ev is None:
                    print(f"  ! событие {event_key} не в реестре — пропуск")
                    continue
                exists = (db.query(NotificationSubscription)
                          .filter(NotificationSubscription.profile_id == prof.id,
                                  NotificationSubscription.event_key == event_key).first())
                if exists:
                    continue
                db.add(NotificationSubscription(
                    profile_id=prof.id, event_key=event_key, is_enabled=True,
                    ch_app="app" in channels, ch_tg="tg" in channels,
                    ch_mail="mail" in channels, ch_digest="digest" in channels,
                    params=dict(ev.params), recipients=list(ev.recipients)))
                added += 1
                print(f"  + {prof_key}: {event_key} → {', '.join(channels) or 'без каналов'}")
        if dry_run:
            db.rollback()
            print(f"Сухой прогон: добавилось бы {added}")
        else:
            db.commit()
            print(f"Готово: добавлено подписок {added}")
        return added
    finally:
        db.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
    assign_profiles(dry_run=dry)
