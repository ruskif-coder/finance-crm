# -*- coding: utf-8 -*-
"""Признаки договора одни и те же во всех точках ввода (владелец 19.10.2026: «реестр договоров и добавление данных
чтобы были синхронизированы»).

Каждое поле, которое API договора принимает на создание, должно быть в реестре договоров, в «Добавить данные» и в
Excel-выгрузке. Иначе признак вводится в одном месте и молча теряется в другом — так было с «Выставлением» при его появлении.
Исключения названы ниже с причиной. Фронт в контейнере бэкенда отсутствует — тогда тест пропускается, проверка идёт
в репозитории."""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Поле → почему его нет в точке ввода.
NOT_IN_ADD = {
    "inn": "ИНН и имя берутся из контрагента, к которому заводится договор",
    "counterparty_name": "то же",
    "counterparty_id": "передаётся из блока контрагента, не полем формы",
    "services": "устаревшее свободное поле: не показывается нигде, кроме выгрузки",
}
NOT_IN_REGISTRY = {"services": NOT_IN_ADD["services"]}
NOT_IN_EXPORT = {"counterparty_id": "в выгрузке — имя и ИНН контрагента"}


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        pytest.skip("фронта нет рядом (контейнер бэкенда) — проверяется в репозитории")
    return p.read_text(encoding="utf-8")


def _create_fields() -> list:
    src = (ROOT / "backend/app/routers/contracts.py").read_text(encoding="utf-8")
    body = src[src.index("class ContractCreate"):src.index("class ContractBulkUpdate")]
    return re.findall(r"^\s+(\w+): Optional", body, re.M)


def test_every_create_field_is_in_registry_add_page_and_export():
    reg = _read("frontend/pages/directory/contracts.js")
    add = _read("frontend/pages/directory/add.js")
    api = (ROOT / "backend/app/routers/contracts.py").read_text(encoding="utf-8")
    export = api[api.index("_EXPORT_COLS = ["):api.index("_EDITABLE_FIELDS")]
    # «Добавить данные» — поле должно уйти в ЗАПРОСЕ создания, а не просто упоминаться в файле
    post = add[add.index("api.post('/contracts/'"):]
    post = post[:post.index("}, auth())")]
    gaps = []
    for f in _create_fields():
        if f not in NOT_IN_REGISTRY and f not in reg:
            gaps.append(f"реестр договоров: {f}")
        if f not in NOT_IN_ADD and not re.search(rf"\b{f}\s*:", post):
            gaps.append(f"«Добавить данные»: {f}")
        if f not in NOT_IN_EXPORT and f"'{f}'" not in export:
            gaps.append(f"Excel-выгрузка: {f}")
    assert not gaps, "признак договора не во всех точках ввода: " + "; ".join(gaps)


def test_closed_lists_are_one_for_front_and_export():
    """Списки значений — `lib/contractTerms.js` на фронте и копии в выгрузке; расходятся — Excel отвергнет верное значение."""
    terms = _read("frontend/lib/contractTerms.js")
    api = (ROOT / "backend/app/routers/contracts.py").read_text(encoding="utf-8")
    for js, py in (("COOPERATION_FORMATS", "_COOPERATION_FORMATS"), ("PROLONGATION_OPTIONS", "_PROLONGATION_OPTIONS"),
                   ("PAYMENT_TERM_CONDITIONS", "_PAYMENT_TERM_CONDS"), ("ISSUE_CHANNELS", "ISSUE_CHANNELS")):
        a = re.findall(r"'([^']+)'", re.search(rf"export const {js} = \[(.*?)\]", terms, re.S).group(1))
        b = re.findall(r"['\"]([^'\"]+)['\"]", re.search(rf"^{py}\s*=\s*\((.*?)\)|^{py}\s*=\s*\[(.*?)\]", api, re.S | re.M).group(0).split("=", 1)[1])
        assert a == b, f"{js} ≠ {py}: {a} / {b}"
