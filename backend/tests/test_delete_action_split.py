# -*- coding: utf-8 -*-
"""Право «удаление» отдельно от «правки» (владелец согласовал 07.10.2026).

БЫЛО. Ручки удаления одиннадцати разделов были закрыты правом «правка», а в конструкторе
ролей у этих разделов не было галочки «удаление»: кто мог править запись, мог и удалить её,
а разрешить одно и запретить другое было нечем.

СТАЛО. Действие `delete` заведено у разделов, где удаляется ЗАПИСЬ: статья и группа, договор
(и массовое удаление), медиаплан, годовой план, воронка, услуга/надбавка/формат, комплект креативов,
контакт/документ/площадка-поверхность паблишера, пункт нацеливания. Миграция
`2026-10-07_delete_action_backfill.sql` выдаёт «удаление» всем, у кого есть «правка»: в день
выкладки ни у кого ничего не меняется, дальше владелец снимает галочку у нужных ролей.

ГРАНИЦА (сознательная): «удаление» — это удаление записи. Вложения (файл, письмо о правах,
скриншот), отвязки (`detach_*`), сбросы (`drop_override`, `unsnooze_deal`) и мягкое
отключение услуги остаются правкой: иначе человеку, у которого сняли «удаление», пришлось бы
отнять и ежедневную работу — заменить файл или отвязать контакт.
"""
import pathlib
import types
import uuid

import pytest
from sqlalchemy import text

from app.main import app
from app.models import Role, RolePermission
from app.permissions import SECTIONS
from tests.route_utils import iter_dependencies

MIG = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "2026-10-07_delete_action_backfill.sql"

SPLIT = ("settings_articles", "contracts", "media_plans", "year_plan", "settings_pipelines",
         "settings_services", "creatives", "dir_publishers", "dir_publishers_bulk",
         "dir_publishers_cabinets", "sales_registry")

PUBLISHERS = ("dir_publishers", "dir_publishers_bulk", "dir_publishers_cabinets")

# (модуль, функция) → разделы, под которыми ручка должна требовать `delete`
MOVED = {
    ("articles", "delete_article"): ("settings_articles",),
    ("articles", "delete_article_group"): ("settings_articles",),
    ("contracts", "delete_contract"): ("contracts",),
    ("contracts", "bulk_delete_contracts"): ("contracts",),
    ("media_plans", "delete_media_plan"): ("media_plans",),
    ("year_plan", "delete_plan"): ("year_plan",),
    ("sales_directories", "delete_pipeline"): ("settings_pipelines",),
    ("sales_directories", "delete_service_hard"): ("settings_services",),
    ("sales_directories", "delete_addon"): ("settings_services",),
    ("sales_directories", "delete_format"): ("settings_services",),
    ("sales_directories", "delete_targeting"): ("sales_registry",),
    ("launch_prep", "drop_set"): ("creatives",),
    ("publishers", "delete_contact"): PUBLISHERS,
    ("publishers", "delete_document"): PUBLISHERS,
    ("publishers", "delete_surface"): PUBLISHERS,
}

# Остаются «правкой»: вложение, отвязка, сброс, мягкое отключение
STAY_ON_EDIT = {
    ("account_dashboard", "unsnooze_deal"), ("sales_dashboard", "drop_override"),
    ("sales_dashboard", "delete_deal_file"), ("sales_dashboard", "remove_deal_brief_file"),
    ("contracts", "delete_contract_document"), ("launch_prep", "drop_file"),
    ("launch_prep", "drop_rights_letter"), ("launch_prep", "drop_set_target"),
    ("publishers", "detach_contract"), ("publishers", "detach_counterparty"),
    ("cabinets", "detach_publisher"), ("media_plans", "mp_delete_brief_file"),
    ("sales_directories", "deactivate_service"), ("traffic", "drop_shot"),
}


def _perm_of(module, name):
    """(разделы, действие, вызываемая зависимость) ручки по модулю и имени функции."""
    found = []
    for r in app.routes:
        ep = getattr(r, "endpoint", None)
        if ep is None or ep.__name__ != name or ep.__module__.split(".")[-1] != module:
            continue
        for d in iter_dependencies(r.dependant):
            act = getattr(d.call, "_perm_action", None)
            if act is not None:
                found.append((getattr(d.call, "_perm_sections", ()), act, d.call))
    assert found, f"ручка {module}.{name} не найдена или без проверки прав"
    return found[-1]


def test_every_split_section_offers_the_delete_action():
    acts = {s["key"]: s["actions"] for s in SECTIONS}
    assert [k for k in SPLIT if "delete" not in acts[k]] == []


@pytest.mark.parametrize("module,name", sorted(MOVED))
def test_record_deletion_routes_require_delete(module, name):
    sections, action, _ = _perm_of(module, name)
    assert action == "delete", f"{module}.{name} всё ещё под правом «{action}»"
    assert tuple(sections) == MOVED[(module, name)]


@pytest.mark.parametrize("module,name", sorted(STAY_ON_EDIT))
def test_attachments_unlinks_and_resets_stay_on_edit(module, name):
    _, action, _ = _perm_of(module, name)
    assert action == "edit", f"{module}.{name}: убрать вложение/отвязку/сброс — это правка, а не удаление"


@pytest.fixture
def role(db):
    r = Role(key=f"zz_{uuid.uuid4().hex[:8]}", label="zz тест права удаления")
    db.add(r)
    db.commit()
    yield r
    db.query(RolePermission).filter(RolePermission.role_id == r.id).delete()
    db.query(Role).filter(Role.id == r.id).delete()
    db.commit()


def _user(role):
    return types.SimpleNamespace(role=types.SimpleNamespace(key=role.key), role_id=role.id)


def _give(db, role, section, **flags):
    base = dict(can_view=1, can_create=0, can_edit=0, can_delete=0,
                can_view_operations=0, can_approve=0)
    db.add(RolePermission(role_id=role.id, section=section, **{**base, **flags}))
    db.commit()


def test_edit_alone_no_longer_deletes_but_delete_does(db, role):
    _, _, check = _perm_of("contracts", "delete_contract")
    _give(db, role, "contracts", can_edit=1)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        check(current_user=_user(role), db=db)
    assert e.value.status_code == 403
    db.query(RolePermission).filter(RolePermission.role_id == role.id).update({"can_delete": 1})
    db.commit()
    assert check(current_user=_user(role), db=db) is not None


def test_delete_without_edit_does_not_open_editing(db, role):
    """Галочки независимы: «удаление» не даёт права править."""
    _, _, edit_check = _perm_of("contracts", "delete_contract_document")
    _give(db, role, "contracts", can_delete=1)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        edit_check(current_user=_user(role), db=db)


def test_publisher_deletion_is_open_to_any_of_its_three_sections(db, role):
    _, _, check = _perm_of("publishers", "delete_contact")
    _give(db, role, "dir_publishers_bulk", can_delete=1)
    assert check(current_user=_user(role), db=db) is not None


# ── миграция ──────────────────────────────────────────────────────────────────

def _run_migration(db):
    db.execute(text(MIG.read_text(encoding="utf-8")))


def test_migration_gives_delete_to_everyone_who_could_edit_and_only_once(db, role):
    """В транзакции с откатом: у стенда ничего не остаётся. Сперва сбрасываем «удаление» у
    разделов — так воспроизводится состояние ДО выкладки."""
    secs = ",".join(f"'{s}'" for s in SPLIT)
    try:
        db.execute(text(f"UPDATE role_permissions SET can_delete = 0 WHERE section IN ({secs})"))
        _run_migration(db)
        bad = db.execute(text(f"SELECT count(*) FROM role_permissions WHERE section IN ({secs}) "
                              f"AND can_delete <> can_edit")).scalar()
        assert bad == 0, "после наката «удаление» должно повторять «правку»"
        # владелец снял «удаление» у одной роли — повторный накат не должен вернуть
        # раздел, где правка у двух и более ролей: снимаем «удаление» у одной, у другой оно остаётся —
        # так выглядит «владелец снял галочку у одной роли» (если снять у ВСЕХ в разделе, раздел для
        # признака первого наката выглядит нетронутым — это известная граница, см. шапку миграции)
        row = db.execute(text(f"SELECT id FROM role_permissions WHERE can_edit = 1 AND section IN "
                              f"(SELECT section FROM role_permissions WHERE section IN ({secs}) "
                              f"AND can_edit = 1 GROUP BY section HAVING count(*) >= 2) LIMIT 1")).first()
        if row:
            db.execute(text("UPDATE role_permissions SET can_delete = 0 WHERE id = :i"), {"i": row[0]})
            _run_migration(db)
            back = db.execute(text("SELECT can_delete FROM role_permissions WHERE id = :i"),
                              {"i": row[0]}).scalar()
            assert back == 0, "повторный накат вернул «удаление», снятое владельцем"
    finally:
        db.rollback()


def test_migration_touches_no_other_section(db):
    try:
        secs = ",".join(f"'{s}'" for s in SPLIT)
        before = db.execute(text(f"SELECT section, role_id, can_delete FROM role_permissions "
                                 f"WHERE section NOT IN ({secs}) ORDER BY 1,2")).all()
        db.execute(text(f"UPDATE role_permissions SET can_delete = 0 WHERE section IN ({secs})"))
        _run_migration(db)
        after = db.execute(text(f"SELECT section, role_id, can_delete FROM role_permissions "
                                f"WHERE section NOT IN ({secs}) ORDER BY 1,2")).all()
        assert before == after
    finally:
        db.rollback()


def test_migration_backfills_each_section_on_its_own_not_all_or_nothing(db):
    """Если «удаление» у какой-то роли в ОДНОМ разделе уже есть (сохранили новым конструктором до
    наката, по API), остальные разделы всё равно должны получить бэкфилл, а этот не трогаем."""
    secs = ",".join(f"'{s}'" for s in SPLIT)
    try:
        db.execute(text(f"UPDATE role_permissions SET can_delete = 0 WHERE section IN ({secs})"))
        has_edit = db.execute(text("SELECT section FROM role_permissions WHERE section IN "
                                   f"({secs}) AND can_edit = 1 GROUP BY section ORDER BY 1")).scalars().all()
        assert len(has_edit) >= 2, "на стенде нет двух разделов с правкой — тест нечем проверить"
        early, other = has_edit[0], has_edit[1]
        one = db.execute(text("SELECT id FROM role_permissions WHERE section = :s AND can_edit = 1 LIMIT 1"),
                         {"s": early}).scalar()
        db.execute(text("UPDATE role_permissions SET can_delete = 1 WHERE id = :i"), {"i": one})
        _run_migration(db)
        left = db.execute(text("SELECT count(*) FROM role_permissions WHERE section = :s AND can_edit = 1 "
                               "AND can_delete = 0"), {"s": other}).scalar()
        assert left == 0, "раздел без «удаления» не получил бэкфилл из-за соседнего раздела"
        same = db.execute(text("SELECT count(*) FROM role_permissions WHERE section = :s AND can_edit = 1 "
                               "AND can_delete = 1"), {"s": early}).scalar()
        total = db.execute(text("SELECT count(*) FROM role_permissions WHERE section = :s AND can_edit = 1"),
                           {"s": early}).scalar()
        assert same < total or total == 1, "раздел с уже выданным «удалением» тронут бэкфиллом"
    finally:
        db.rollback()
