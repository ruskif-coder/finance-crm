# -*- coding: utf-8 -*-
"""Шаблоны ДС живут в пакете `app/annex_tpl` (правило владельца 13.10.2026: новая логика — в пакет, в старых файлах только вызов).

Три прибора: таблицы шаблонов не трогает никто, кроме пакета; версии не правятся из кода; модели зарегистрированы для кронов.
"""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
# sales/models.py — только колонка `sales_annexes.template_version_id` (внешний ключ на версию), других упоминаний быть не должно.
OWN = ("annex_tpl/", "routers/annex_templates.py", "audit_labels.py", "model_registry.py", "permissions.py", "sales/models.py")


def _files():
    for p in APP.rglob("*.py"):
        yield p, p.relative_to(APP).as_posix()


def test_template_tables_are_touched_only_by_the_package():
    bad = []
    for p, rel in _files():
        if rel.startswith(OWN[0]) or rel in OWN[1:]:
            continue
        src = p.read_text(encoding="utf-8")
        if re.search(r"AnnexTplTemplate|AnnexTplVersion|AnnexTplFormat|annex_tpl_templates|annex_tpl_versions|annex_tpl_formats", src):
            bad.append(rel)
    assert not bad, f"код про шаблоны ДС вне пакета annex_tpl: {bad}"


def test_versions_are_never_updated_or_deleted_in_code():
    """Версии неизменяемы: триггер в базе закрывает UPDATE, а код не должен даже пытаться."""
    pat = re.compile(r"query\(AnnexTplVersion\)[^\n]*\.(update|delete)\(|delete\(AnnexTplVersion\)|update\(AnnexTplVersion\)")
    bad = [rel for p, rel in _files() if pat.search(p.read_text(encoding="utf-8"))]
    assert not bad, f"правка или удаление версий шаблона в коде: {bad}"


def test_models_are_in_the_registry():
    reg = (APP / "model_registry.py").read_text(encoding="utf-8")
    assert "import app.annex_tpl.models" in reg
