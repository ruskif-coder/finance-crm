"""Профиль ответственного под учётной записью.

`sales_reps` — справочник тех, на кого можно записать сделку, кампанию или контакт для
площадки. Он заполнялся разовым переносом из Битрикса и с тех пор не пополнялся ничем:
создание пользователя профиль НЕ заводит, и ни одна ручка приложения в эту таблицу не
пишет.

Измерено 03.09.2026 на стенде: 20 активных учёток против 11 профилей. Без профиля
остались все три трафика и оба менеджера паблишеров — то есть ровно те, кого требовалось
назначать. Наружу это выходило дважды и оба раза непохоже на причину:

  · список кандидатов в трафики (`/launch-prep/traffic-managers`) возвращал ПУСТОТУ,
    а отправка материала упиралась в «не указан ответственный трафик» — тупик без
    выхода с экрана;
  · в «Наших контактах у площадок» показывались только сейлзы и аккаунты, и выбрать
    трафика или менеджера паблишеров было нельзя.

Профиль заводится в момент, когда человека РЕАЛЬНО назначают, а не всем подряд при
создании учётки: справочник ответственных — не список сотрудников, и наполнять его
целиком значило бы предлагать юриста в продавцы.

Кого показывать в выборе — решает РОЛЬ (`Role.staff_group` / отключенная учётка), а не
наличие строки здесь. Иначе выбор ограничен теми, кого уже когда-то выбрали.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Role, User
from app.sales.models import SalesRep


def staff_users(db: Session, group: Optional[str] = None,
                any_role: bool = False) -> List[dict]:
    """Сотрудники для выбора: активные учётки, по рабочей группе роли.

    `group` — 'seller' | 'account' | 'traffic' | 'publishers'. Без него отдаются все с
    проставленной рабочей группой; `any_role=True` снимает и это условие — для списков,
    где уместен любой сотрудник (контакты для площадок: там нужны и юрист, и финансист).

    `rep_id` в ответе может быть None: профиль ещё не заведён, и это нормально —
    он появится при первом назначении (`ensure_rep`).
    """
    q = (db.query(User, Role, SalesRep.id)
         .join(Role, Role.id == User.role_id)
         .outerjoin(SalesRep, SalesRep.user_id == User.id)
         .filter(User.is_active == 1))
    if group:
        q = q.filter(Role.staff_group == group)
    elif not any_role:
        q = q.filter(Role.staff_group.isnot(None))
    items = [{"user_id": u.id, "name": u.name, "email": u.email,
              "group": r.staff_group, "is_master": bool(r.is_master),
              "role_label": r.label, "rep_id": rep_id}
             for u, r, rep_id in q.all()]
    items.sort(key=lambda x: (not x["is_master"], (x["name"] or "").lower()))
    return items


def ensure_rep(db: Session, user_id: int) -> SalesRep:
    """Профиль ответственного для учётки — найти или завести.

    `flush()` обязателен: вызывающий берёт `rep.id` сразу же, а до сброса в сессию его
    нет (та же готча, что с `Operation` — запрос не видит собственной записи).
    Коммитит вызывающий: назначение и заведение профиля — одно действие, и половина
    его в базе не нужна никому.
    """
    user = db.query(User).filter(User.id == user_id, User.is_active == 1).first()
    if not user:
        raise ValueError("Сотрудник не найден или его учётная запись отключена")
    rep = db.query(SalesRep).filter(SalesRep.user_id == user.id).first()
    if rep:
        # Отключённую учётку сюда не пускаем выше, а вот снятый ранее профиль вернуть
        # можно: назначение и есть заявление, что человек снова в работе.
        if not rep.is_active:
            rep.is_active = True
        return rep
    rep = SalesRep(name=user.name or user.email, user_id=user.id, is_active=True)
    db.add(rep)
    db.flush()
    return rep
