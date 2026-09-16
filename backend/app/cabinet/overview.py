# -*- coding: utf-8 -*-
"""Сводка для экрана «Кабинеты паблишеров»: показатели, услуги, лента, контакты.

Всё считается ПАЧКОЙ и отдаётся одним ответом — тем же приёмом, что дерево креативов
сделки: несколько запросов на один экран дают мигание и рассинхрон, когда часть данных
уже обновилась, а часть нет.

Главное решение файла — **«креативов на согласовании» берётся из витрины кабинета**
`pub.task_v1`, а не считается заново. Предикат задания («строка проверки вида
«площадка» без вердикта») живёт в представлении, потому что кабинет ходит в базу
отдельной ролью. Повтори мы его здесь — админский экран и кабинет однажды показали бы
разные числа по одной площадке, и разошлись бы молча. Область выставляется на ВСЕ
площадки: `set_config(..., is_local => true)` умирает вместе с транзакцией, поэтому
чужой видимости это не открывает.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

LOG_PREVIEW = 8          # строк ленты в карточке; остальное — по «Весь лог»
LOG_WINDOW_DAYS = 30     # окно счётчика «7 за 30 дн.» из макета


def creatives_pending(db: Session) -> Dict[int, int]:
    """Сколько заданий висит на каждой площадке. Считает ВИТРИНА, не мы.

    Пустая область у `pub.allowed_publisher_ids()` означает «ничего не видно»
    (защита закрывается, а не открывается), поэтому для сводки её надо выставить явно.
    """
    ids = [str(i) for (i,) in db.execute(text("SELECT id FROM sales_publishers"))]
    if not ids:
        return {}
    db.execute(text("SELECT set_config('app.publisher_ids', :v, true)"),
               {"v": ",".join(ids)})
    return {p: n for p, n in db.execute(text(
        "SELECT publisher_id, count(*) FROM pub.task_v1 GROUP BY publisher_id"))}


def campaigns_live(db: Session) -> Dict[int, int]:
    """Запущенные РК: сделки этой площадки, дошедшие до ступени размещения.

    Ступень, а не период: «сейчас в эфире» — это состояние сделки, и «в текущем месяце»
    из макета отвечало бы на другой вопрос. `stage_key='launch'` покрывает и
    «В размещении», и «Итоговую сверку» — обе означают, что кампания идёт или только что
    закончилась, а не готовится.
    """
    return {p: n for p, n in db.execute(text(
        "SELECT t.publisher_id, count(DISTINCT t.deal_id) "
        "  FROM launch_prep_target t "
        "  JOIN sales_deals d ON d.id = t.deal_id "
        "  JOIN sales_stages s ON s.id = d.our_stage_id "
        " WHERE s.stage_key = 'launch' "
        " GROUP BY t.publisher_id"))}


def recons_open(db: Session) -> Dict[int, int]:
    """Открытые сверки. Открытая — та, по которой площадка ещё не ответила."""
    return {p: n for p, n in db.execute(text(
        "SELECT publisher_id, count(*) FROM publisher_request "
        " WHERE kind = 'сверка' AND verdict IS NULL GROUP BY publisher_id"))}


def services_by_publisher(db: Session) -> Dict[int, List[dict]]:
    """Услуги площадки с поверхностями: «еФарм WEB · APP» одной строкой.

    Поверхности сворачиваются в одну услугу, а не показываются двумя чипами: у площадки
    это одна услуга, продаваемая на двух экранах, и два чипа читались бы как две разные.
    """
    out: Dict[int, Dict[str, List[str]]] = {}
    for pub_id, name, surface in db.execute(text(
            "SELECT ps.publisher_id, sv.name, ps.surface_kind "
            "  FROM sales_publisher_services ps "
            "  JOIN sales_services sv ON sv.id = ps.service_id "
            " WHERE ps.is_active "
            " ORDER BY sv.sort_order, sv.name, ps.surface_kind")):
        out.setdefault(pub_id, {}).setdefault(name, []).append(surface)
    return {pid: [{"name": n, "surfaces": s} for n, s in svc.items()]
            for pid, svc in out.items()}


def contacts_of(db: Session, publisher_ids: List[int],
                cabinet_id: Optional[int] = None) -> List[dict]:
    """Контактные лица кабинета — ВСЕ, а не только те, у кого есть учётка.

    Контакт без учётки существует нормально: это человек для переписки. В колонке он
    ждёт кнопки «Создать учётку», и именно поэтому список один с реестром площадок —
    две истории по одним людям разошлись бы (владелец, 30.08.2026).

    ДВА ИСТОЧНИКА, а не один (15.09.2026, по жалобе владельца «отвязал площадку —
    контакты пропали»). Раньше список выводился ТОЛЬКО из площадок кабинета, и открепление
    площадки убирало с экрана человека, у которого в этом кабинете есть действующая
    учётка: войти он по-прежнему мог, а увидеть его и отключить было негде. Невидимый
    работающий доступ — худший исход из возможных.

    Поэтому берём объединение: контакты площадок кабинета И контакты, чья УЧЁТКА
    заведена в этом кабинете. Второе множество обычно вложено в первое; расходятся они
    ровно в случае открепления, и тогда человек остаётся видимым.
    """
    if not publisher_ids and not cabinet_id:
        return []
    rows = db.execute(text(
        "SELECT c.id, c.publisher_id, c.name, c.email, c.role, c.telegram, "
        "       c.phone, c.note, c.is_primary, c.notify, "
        "       p.name AS publisher_name, "
        "       a.id AS account_id, a.email AS login_email, "
        "       a.is_active, a.can_approve, a.last_login_at, "
        "       (a.hashed_password IS NOT NULL) AS has_password, "
        # Бот человек подключает СЕБЕ САМ — мы за него не можем. Здесь только показываем,
        # подключил ли: без этого «ему не приходит в телеграм» не имеет ответа в системе.
        "       (t.verified_at IS NOT NULL) AS tg_linked, "
        # Площадка контакта могла уехать из кабинета — тогда человек виден, но помечен.
        "       (c.publisher_id = ANY(:ids)) AS publisher_in_cabinet "
        "  FROM sales_publisher_contacts c "
        "  JOIN sales_publishers p ON p.id = c.publisher_id "
        "  LEFT JOIN cabinet_account a ON a.contact_id = c.id "
        "  LEFT JOIN cabinet_account_tg t ON t.account_id = a.id "
        " WHERE c.publisher_id = ANY(:ids) "
        "    OR (:cab IS NOT NULL AND a.cabinet_id = :cab) "
        " ORDER BY p.name, c.is_primary DESC, c.name"),
        {"ids": publisher_ids or [], "cab": cabinet_id})
    return [{"contact_id": r.id, "publisher_id": r.publisher_id,
             "publisher_name": r.publisher_name,
             "name": r.name, "email": r.email, "role": r.role, "telegram": r.telegram,
             "phone": r.phone, "note": r.note,
             # Главное контактное лицо площадки — зелёный квадрат в её карточке. Здесь
             # тот же признак: это одно и то же лицо, а не две пометки.
             "is_primary": bool(r.is_primary), "notify": bool(r.notify),
             # Бот — свойство УЧЁТКИ, а не контакта: подключает его вошедший человек.
             # Без учётки подключать нечем, поэтому там не «нет», а «неприменимо».
             "tg_linked": (bool(r.tg_linked) if r.account_id is not None else None),
             # Человек остался от открепления площадки: доступ живой, площадки в
             # кабинете нет. Экран обязан назвать это, а не показать его как обычного.
             "publisher_detached": not bool(r.publisher_in_cabinet),
             "account_id": r.account_id,
             # Почта входа отдельно от почты контакта: учётка копирует адрес при
             # заведении, дальше они расходятся. Экран обязан показать расхождение, а
             # не выбрать за человека, какой из двух адресов настоящий.
             "login_email": r.login_email,
             "has_account": r.account_id is not None,
             # Уровень есть ТОЛЬКО при учётке: без неё в колонке «Доступ» стоит прочерк,
             # иначе экран обещает права человеку, который не может войти.
             "level": (None if r.account_id is None
                       else ('все' if r.can_approve else 'просмотр')),
             "is_active": bool(r.is_active) if r.account_id is not None else None,
             "has_password": bool(r.has_password) if r.account_id is not None else None,
             "last_login_at": r.last_login_at}
            for r in rows]


def service_accounts_as_contacts(db: Session, cabinet_id: int) -> List[dict]:
    """Учётки СЛУЖЕБНОГО кабинета в том же виде, что контакты площадок.

    Он наш: его люди не контакты площадок, и `contact_id` у них пуст. Но колонка на
    экране одна, и склеивать две разные формы на фронте значило бы держать правило
    «что такое строка контакта» в двух местах. Форма одна — различает их `contact_id`.
    """
    return [{"contact_id": None, "publisher_id": None, "publisher_name": None,
             # Должности у служебной учётки НЕТ: в `cabinet_account` такого поля не
             # существует. Ставим пусто, а не выдумываем — колонка должна показывать
             # отсутствие, а не подставлять правдоподобное.
             "name": r.name, "email": r.email, "role": None, "telegram": None,
             "phone": None, "note": None, "is_primary": False, "notify": False,
             "account_id": r.id, "login_email": r.email, "has_account": True,
             "level": 'все' if r.can_approve else 'просмотр',
             "is_active": bool(r.is_active),
             "has_password": r.hashed_password is not None,
             "last_login_at": r.last_login_at}
            for r in db.execute(text(
                "SELECT id, name, email, can_approve, is_active, hashed_password, "
                "       last_login_at "
                "  FROM cabinet_account WHERE cabinet_id = :c ORDER BY name"),
                {"c": cabinet_id})]


def logs_by_cabinet(db: Session) -> Dict[int, dict]:
    """Лента по кабинетам: последние строки и счётчик за окно.

    Окно считается от `now()`, а не по календарным дням: «7 за 30 дн.» в макете — это
    «за последний месяц», а не «в этом месяце».
    """
    from app.cabinet.journal import BY_KEY

    since = datetime.utcnow() - timedelta(days=LOG_WINDOW_DAYS)
    out: Dict[int, dict] = {}
    for r in db.execute(text(
            "SELECT cabinet_id, actor_name, actor_side, action, tone, subject, created_at "
            "  FROM cabinet_log WHERE created_at >= :since "
            " ORDER BY created_at DESC, id DESC"), {"since": since}):
        box = out.setdefault(r.cabinet_id, {"rows": [], "total": 0})
        box["total"] += 1
        if len(box["rows"]) < LOG_PREVIEW:
            a = BY_KEY.get(r.action)
            box["rows"].append({
                # Подпись берётся из СЛОВАРЯ, а не из базы: переформулировав событие, мы
                # хотим переписать и старые строки — они об одном и том же.
                "label": a.label if a else r.action,
                "action": r.action, "tone": r.tone, "side": r.actor_side,
                "actor": r.actor_name, "subject": r.subject, "at": r.created_at})
    return out


def our_contacts(db: Session) -> List[dict]:
    """Кого из наших видит площадка. Общие на все кабинеты (владелец, 30.08.2026).

    Почта — через `sales_reps.user_id → users.email`. Сотрудник без учётки в системе
    показывается без способа связаться, и это видно в ответе (`email: null`), чтобы
    экран мог его пометить, а не молча показать площадке контакт без почты.

    `user_id` отдаётся рядом с `rep_id`: выбирают учётку (см. `app/sales/reps.py`), а
    хранится профиль ответственного. `is_disabled` — учётку отключили уже ПОСЛЕ того,
    как человека поставили контактом; строка при этом не исчезает (иначе площадка
    молча теряет контакт), но экран обязан её пометить.
    """
    return [{"id": r.id, "role": r.role, "rep_id": r.rep_id, "user_id": r.user_id,
             "name": r.name, "email": r.email, "is_shown": bool(r.is_shown),
             "is_disabled": not bool(r.user_active), "sort_order": r.sort_order}
            for r in db.execute(text(
                "SELECT oc.id, oc.role, oc.rep_id, oc.is_shown, oc.sort_order, "
                "       rp.name, rp.user_id, u.email, u.is_active AS user_active "
                "  FROM cabinet_our_contact oc "
                "  JOIN sales_reps rp ON rp.id = oc.rep_id "
                "  LEFT JOIN users u ON u.id = rp.user_id "
                " ORDER BY oc.sort_order, oc.id"))]


def activity(pub_ids: List[int], pending: Dict[int, int], live: Dict[int, int],
             recons: Dict[int, int], last_login: Optional[datetime]) -> dict:
    """Полоса активности кабинета — сумма по его площадкам."""
    return {"creatives_pending": sum(pending.get(i, 0) for i in pub_ids),
            "campaigns_live": sum(live.get(i, 0) for i in pub_ids),
            "recons_open": sum(recons.get(i, 0) for i in pub_ids),
            "last_login": last_login}
