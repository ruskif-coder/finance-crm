# -*- coding: utf-8 -*-
"""Каталог рассылки площадкам: объявлено шестнадцать, отправляется один.

Экран «Кабинеты → Что мы шлём» существует ради одного различия, которое иначе не видно
никому: между «вид объявлен» и «вид отправляется». До 14.09.2026 их не различал никто —
в кабинете все переключатели выглядели одинаково рабочими, хотя четыре из пяти не могли
ничего выключить, потому что отправителя за ними не было.

Приборы здесь стерегут именно это различие, а не состав каталога: состав меняется, а
правило «не обещай того, чего не шлёшь» — нет.
"""
import io
import pytest
from pathlib import Path

from app.notify.outward import kinds as nk


def test_keys_are_unique_and_stable():
    """Ключ записан строкой в `cabinet_account_mute` у живых площадок: дубль означает
    два переключателя на одну строку, а переименование — молча включённое выключенное."""
    keys = [k.key for k in nk.KINDS]
    assert len(keys) == len(set(keys)), f"дубли ключей: {keys}"
    for old in ("новый креатив", "запрос ссылки", "сверка", "продление", "старт близко"):
        assert old in keys, f"ключ {old!r} заведён 29.08.2026 и не может исчезнуть"


def test_exactly_one_kind_cannot_be_muted():
    """Невыключаемый вид ровно один, и это осознанное исключение.

    Второй такой означал бы, что мы решаем за площадку чаще, чем договаривались."""
    locked = [k.key for k in nk.KINDS if not k.can_mute]
    assert locked == ["старт близко"], f"невыключаемых видов стало {locked}"


def test_built_kinds_really_have_a_sender():
    """`built=True` означает, что письмо ДЕЙСТВИТЕЛЬНО кто-то отправляет.

    Признак держится руками, и разойтись с кодом он может молча: поставил галочку «готово»
    заранее — и вид объявлен живым, а площадка ничего не получает. Проверяем встречно: у
    каждого живого вида должен найтись отправитель в коде.
    """
    senders = {
        # ключ вида → чем отправляется
        "запрос ссылки": ("app/routers/launch_prep.py", "KIND_URL_REQUEST"),
        "новый креатив": ("app/routers/traffic.py", '"новый креатив"'),
        "ерид выпущен": ("app/routers/launch_prep.py", '"ерид выпущен"'),
        "старт рк": ("app/routers/traffic_dashboard.py", '"старт рк"'),
    }
    for k in nk.KINDS:
        if not k.built:
            continue
        assert k.key in senders, (
            f"вид «{k.label}» объявлен живым, но отправитель не назван в этом приборе")
        path, marker = senders[k.key]
        src = io.open(Path(__file__).resolve().parents[1] / path, encoding="utf-8").read()
        assert marker in src, f"отправитель вида «{k.label}» пропал из {path}"


def test_unbuilt_kinds_are_the_debt_and_are_counted():
    """Непостроенных сегодня пятнадцать. Число в приборе — не придирка: оно падает, когда
    отправитель появляется, и заставляет снять признак `built` вместе с ним."""
    unbuilt = [k.key for k in nk.KINDS if not k.built]
    assert len(unbuilt) == 12, (
        f"построенных видов стало больше или меньше: не построено {len(unbuilt)}. "
        f"Если отправитель появился — поставьте built=True и поправьте это число")


def test_every_kind_says_who_and_when():
    """Вид без адресата и без правила повтора нельзя ни построить, ни обсудить."""
    bad = [k.key for k in nk.KINDS
           if k.to not in (nk.TO_MANAGER, nk.TO_TECH, nk.TO_MONEY, nk.TO_ALL)
           or not k.trigger or not k.repeat
           or k.schedule not in ("дайджест", "сразу")
           or k.tone not in ("info", "ok", "warn", "bad")]
    assert not bad, f"виды без адресата, повода или правила: {bad}"


def test_cabinet_sees_only_what_can_arrive():
    """Наружу уходят ТОЛЬКО построенные виды.

    Переключатель у вида без отправителя — обещание, которого мы не держим: площадка
    снимает галочку, ничего не меняется, и доверие к экрану кончается на первом же
    «я же выключил, а оно пришло» — или наоборот.
    """
    src = io.open(Path(__file__).resolve().parents[1] / "app" / "routers" /
                  "cabinet_gateway.py", encoding="utf-8").read()
    i = src.index("def cabinet_notify_kinds")
    body = src[i:src.index("class CabinetMuteIn", i)]
    assert "k.built" in body, "шлюз отдаёт площадке виды без отправителя"


def test_enabling_an_unbuilt_kind_is_refused():
    """Включить непостроенный вид нельзя: «включено» означало бы, что мы считаем его
    работающим, и молчание списали бы на площадку."""
    from fastapi import HTTPException
    from app.database import SessionLocal
    from app.models import User
    from app.routers import cabinets

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        if user is None:
            pytest.skip("на стенде нет админской учётки")
        dead = next(k for k in nk.KINDS if not k.built)
        with pytest.raises(HTTPException) as e:
            cabinets.notify_catalog_save(
                cabinets.NotifyToggleIn(key=dead.key, enabled=True), db=db, user=user)
        assert e.value.status_code == 400
        assert "отправитель" in str(e.value.detail)
    finally:
        db.rollback()
        db.close()


# ── Получатели: отметка на контакте ──────────────────────────────────────────

def test_recipients_follow_the_notify_flag_not_the_primary_one(db=None):
    """Адресат берётся по отметке «получает уведомления», а не по «главный».

    Прежнее правило опиралось на чужой флаг: `is_primary` отвечает, к кому идти с
    вопросом, а не кому слать почту. Совпадали они по случайности и разошлись бы на
    первом же «главный, но писать ему не надо».
    """
    from sqlalchemy import text as sa_text
    from app.notify.outward.send import _recipients
    from app.database import SessionLocal

    s = SessionLocal()
    try:
        row = s.execute(sa_text("""
            SELECT publisher_id FROM sales_publisher_contacts
             WHERE notify AND coalesce(email,'') <> '' LIMIT 1""")).first()
        if row is None:
            pytest.skip("на стенде нет контактов с отметкой рассылки")
        pub_id = row[0]
        assert _recipients(s, pub_id), "отмеченный контакт не попал в получатели"

        s.execute(sa_text("UPDATE sales_publisher_contacts SET notify = false "
                          "WHERE publisher_id = :p"), {"p": pub_id})
        assert _recipients(s, pub_id) == [], (
            "без отметки письмо всё равно кому-то уходит — отметка декоративна")
    finally:
        s.rollback()
        s.close()


def test_backfill_left_every_publisher_with_a_recipient():
    """Миграция сохранила поведение: у каждой площадки, где был адресат, он остался.

    Иначе рассылка замолкает МОЛЧА — писем нет, ошибок нет, и понять это можно только
    по отсутствию писем у площадки."""
    from sqlalchemy import text as sa_text
    from app.database import SessionLocal

    s = SessionLocal()
    try:
        orphans = s.execute(sa_text("""
            SELECT count(*) FROM (
                SELECT publisher_id FROM sales_publisher_contacts
                 WHERE coalesce(email,'') <> ''
                 GROUP BY publisher_id
                HAVING count(*) FILTER (WHERE notify) = 0) x""")).scalar()
        assert orphans == 0, (
            f"у {orphans} площадок есть контакт с почтой, но никто не отмечен — "
            f"письма им не уйдут")
    finally:
        s.close()
