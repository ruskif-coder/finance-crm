# -*- coding: utf-8 -*-
"""ДС, подписанный вне системы (владелец 02–03.11.2026).

Внешний ДС — рабочий, как наш: занимает номер договора, подписан, к нему привязаны сделки пакета, по нему УПД и 1С.
Документ — файл или ссылка на документ, ранее выгруженный в ЭДО; сумму и услуги указывает аккаунт, сверки с раскладкой нет.

Поломки, которые ловят тесты: ДС «подписан вне системы» без файла и без ссылки; ссылка `javascript:`; номер, занятый
другим ДС договора; внешний ДС выгружается конструктором (DOCX/PDF собрали бы НАШ текст под чужим подписанным
документом); пакет мастер-сделки не идёт дальше после последнего подтверждённого ДС.

Пишут в базу стенда внутри транзакции и откатываются — сервис не коммитит (коммитит ручка).
"""
import os
from datetime import date

import pytest

import app.model_registry  # noqa: F401 — все модели в реестре SQLAlchemy
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import User
from app.sales import annex_external as X
from app.sales.models import SalesAnnex, SalesAnnexItem, SalesService


@pytest.fixture
def ctx():
    db = SessionLocal()
    a = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id.isnot(None), SalesAnnex.no.is_(None))
         .order_by(SalesAnnex.id.desc()).first())
    svc = db.query(SalesService.id).order_by(SalesService.id).first()
    user = db.query(User).join(User.role).filter_by(key="admin").first()
    if a is None or svc is None or user is None:
        db.close()
        pytest.skip("на стенде нет черновика ДС мастер-сделки")
    folder = os.path.join(X.ROOT, X.SUBDIR)
    before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    written = []
    yield db, a, svc[0], user, written
    db.rollback()
    # Уборка — по каталогу, а не по списку: файл, записанный тестом, который упал до `written.append`, иначе остался бы сиротой
    # (так и случилось 03.11.2026).
    for name in (set(os.listdir(folder)) if os.path.isdir(folder) else set()) - before:
        os.remove(os.path.join(folder, name))
    db.close()


def _sign(db, a, svc, user, **kw):
    args = dict(no=987654, number_text=None, doc_date=date(2026, 11, 3), total=120000.0,
                items=[{"service_id": svc, "amount": 120000.0}], edo_link=None, file_name="ДС.pdf", file_bytes=b"%PDF-1.4 x")
    args.update(kw)
    return X.sign_external(db, a, user, **args)


def test_signed_outside_becomes_a_working_confirmed_annex(ctx):
    db, a, svc, user, written = ctx
    out = _sign(db, a, svc, user)
    written.append(out.get("path"))
    assert a.origin == "загружен" and a.status == "подтверждён" and a.no == 987654
    assert a.sign_state == "подписан" and a.date == date(2026, 11, 3) and a.total_amount == 120000.0
    items = db.query(SalesAnnexItem).filter(SalesAnnexItem.annex_id == a.id).all()
    assert [(i.service_id, i.amount) for i in items] == [(svc, 120000.0)]
    assert out["path"] and os.path.exists(os.path.join(X.ROOT, out["path"]))


def test_edo_link_instead_of_a_file(ctx):
    db, a, svc, user, _ = ctx
    _sign(db, a, svc, user, file_name=None, file_bytes=None, edo_link="https://edo.example/doc/1")
    assert a.edo_link == "https://edo.example/doc/1" and a.sign_channel == "ЭДО"


def test_neither_file_nor_link_is_refused(ctx):
    db, a, svc, user, _ = ctx
    with pytest.raises(X.ExternalError) as e:
        _sign(db, a, svc, user, file_name=None, file_bytes=None)
    assert "файл" in e.value.message.lower() and a.origin != "загружен"


def test_unsafe_link_is_refused(ctx):
    db, a, svc, user, _ = ctx
    with pytest.raises((X.ExternalError, HTTPException)):
        _sign(db, a, svc, user, file_name=None, file_bytes=None, edo_link="javascript:alert(1)")


def test_services_and_sum_are_required(ctx):
    db, a, svc, user, _ = ctx
    with pytest.raises(X.ExternalError):
        _sign(db, a, svc, user, items=[])
    with pytest.raises(X.ExternalError):
        _sign(db, a, svc, user, total=0)


def test_number_taken_by_another_annex_is_refused(ctx):
    db, a, svc, user, _ = ctx
    taken = (db.query(SalesAnnex.no).filter(SalesAnnex.contract_id == a.contract_id, SalesAnnex.no.isnot(None),
                                            SalesAnnex.sub_no.is_(None)).first())
    if taken is None:
        pytest.skip("у договора нет подтверждённых ДС")
    with pytest.raises(X.ExternalError) as e:
        _sign(db, a, svc, user, no=taken[0])
    assert "занят" in e.value.message


def test_external_annex_is_never_assembled_by_the_constructor():
    """Выгрузка, пересоздание и правки — только у ДС «система»: у внешнего документ — его файл или ссылка."""
    import inspect

    from app.routers import annexes as R
    for fn in (R.annex_pdf, R.annex_docx, R.rebuild_annex):
        assert "assert_not_external(" in inspect.getsource(fn), fn.__name__


def test_package_zip_takes_the_client_document_not_our_constructor(ctx):
    """Архив пакета («Скачать всё · zip») клал рядом с файлом клиента наш собранный DOCX — наш текст и дату начала РК под
    чужим подписанным документом (прогон цепочки 03.11.2026)."""
    import io
    import zipfile

    from app.master_deal import bundle
    from app.master_deal.models import MasterDeal
    db, a, svc, user, _ = ctx
    _sign(db, a, svc, user)
    names = zipfile.ZipFile(io.BytesIO(bundle.build(db, db.get(MasterDeal, a.master_deal_id))[1])).namelist()
    assert not [n for n in names if n.endswith(".docx")], names
    assert any("ДС.pdf" in n for n in names), names


def test_package_zip_names_the_edo_link(ctx):
    import io
    import zipfile

    from app.master_deal import bundle
    from app.master_deal.models import MasterDeal
    db, a, svc, user, _ = ctx
    _sign(db, a, svc, user, file_name=None, file_bytes=None, edo_link="https://edo.example/doc/7")
    z = zipfile.ZipFile(io.BytesIO(bundle.build(db, db.get(MasterDeal, a.master_deal_id))[1]))
    txt = [n for n in z.namelist() if n.endswith("ссылка ЭДО.txt")]
    assert txt and "https://edo.example/doc/7" in z.read(txt[0]).decode()


# ── Единицы и доп. услуги (владелец 03.11.2026) ─────────────────────────────────────────────────────────────────────

def test_units_follow_the_directories():
    from app.sales import units as U
    assert (U.service_unit("CPM"), U.service_unit(" cpc "), U.service_unit("Фикс"), U.service_unit("Пакет")) == \
        ("показы", "клики", "штуки", "штуки")
    assert (U.addon_unit("разово*"), U.addon_unit("по итогам РК")) == ("штуки", "показы")


def test_lines_keep_volume_unit_and_addons(ctx):
    from app.sales.models import SalesAddonService
    from app.sales import units as U
    db, a, svc, user, _ = ctx
    add = db.query(SalesAddonService).order_by(SalesAddonService.id).first()
    if add is None:
        pytest.skip("справочник доп. услуг пуст")
    _sign(db, a, svc, user, total=150000.0, items=[{"service_id": svc, "amount": 100000.0, "volume": 1222222},
                                                   {"addon_id": add.id, "amount": 50000.0, "volume": 1}])
    rows = db.query(SalesAnnexItem).filter(SalesAnnexItem.annex_id == a.id).order_by(SalesAnnexItem.id).all()
    s_calc = db.get(SalesService, svc).calc_form
    assert [(r.service_id, r.addon_id, r.volume, r.unit) for r in rows] == [
        (svc, None, 1222222.0, U.service_unit(s_calc)), (None, add.id, 1.0, U.addon_unit(add.period))]


def test_a_line_is_either_a_service_or_an_addon(ctx):
    db, a, svc, user, _ = ctx
    with pytest.raises(X.ExternalError):
        _sign(db, a, svc, user, items=[{"service_id": svc, "addon_id": 1, "amount": 10.0}])
    with pytest.raises(X.ExternalError):
        _sign(db, a, svc, user, items=[{"amount": 10.0}])


def test_draft_of_a_package_shows_the_number_it_will_take(ctx):
    """В поле «Номер» черновика ДС пакета стоял счётчик договора («1»), а подтверждение брало номер раскладки (66) — поле
    показывало номер, которого ДС не получит (владелец 03.11.2026). Номер карточки и номер подтверждения — одна функция."""
    from app.routers import annexes as R
    db, a, svc, user, _ = ctx
    got = R.get_annex(a.id, db=db, user=user)
    want = R.master_no(db, a)
    if want is None:
        pytest.skip("у мастер-сделки не задан номер")
    assert got["next_no"] == want and got["master"]["will_be_no"] == want


def test_addons_annex_can_take_its_own_number(ctx):
    """Владелец 05.11.2026: ДС допов пакета, подписанный вне системы, бывает отдельным документом со своим номером (октябрь АПР
    Евразии — № 28 и № 29), а не суффиксом основного (28-01)."""
    from app.master_deal.to_annex import SUB_ADDONS
    db, a, svc, user, _ = ctx
    a.kind, a.sub_no = "addons", SUB_ADDONS
    _sign(db, a, svc, user, no=987655, own_number=True)
    assert a.sub_no is None and a.no == 987655 and a.number.endswith("987655")


def test_addons_annex_keeps_the_suffix_by_default(ctx):
    from app.master_deal.to_annex import SUB_ADDONS
    db, a, svc, user, _ = ctx
    a.kind, a.sub_no = "addons", SUB_ADDONS
    _sign(db, a, svc, user, no=987655)
    assert a.sub_no == SUB_ADDONS and a.number.endswith(f"987655-{SUB_ADDONS}")


def test_own_number_of_addons_is_not_taken_for_the_main_number(ctx):
    """Основной номер пакета — по виду ДС, а не по отсутствию суффикса: иначе основной ДС получил бы номер допов (№ 29)."""
    from app.routers import annexes as R
    db, a, svc, user, _ = ctx
    extra = SalesAnnex(contract_id=a.contract_id, master_deal_id=a.master_deal_id, kind="addons", no=987656, sub_no=None,
                       status="подтверждён", period_from=a.period_from, period_to=a.period_to, date=a.date,
                       total_amount=1.0, template_version_id=a.template_version_id)
    db.add(extra)
    db.flush()
    a.kind = "main"
    assert R.master_no(db, a) != 987656


def test_own_number_of_addons_cannot_take_the_main_annex_future_number(ctx):
    """Ревью 05.11.2026: ДС допов со своим № 28 при неподтверждённом основном (ему раскладка даёт № 28) — основной потом
    не подтвердится (409), а раскладка уже закреплена выпущенным ДС допов. Такой номер — отказ сразу."""
    from app.master_deal.models import MasterDeal
    from app.master_deal.to_annex import SUB_ADDONS
    db, a, svc, user, _ = ctx
    m = db.get(MasterDeal, a.master_deal_id)
    m.start_no = 987600
    main = SalesAnnex(contract_id=a.contract_id, master_deal_id=a.master_deal_id, kind="main", no=None, status="черновик",
                      period_from=a.period_from, period_to=a.period_to, date=a.date, total_amount=1.0,
                      template_version_id=a.template_version_id)
    db.add(main)
    db.flush()
    a.kind, a.sub_no = "addons", SUB_ADDONS
    with pytest.raises(X.ExternalError) as e:
        _sign(db, a, svc, user, no=987601, own_number=True)
    assert "основн" in e.value.message


def test_issued_by_us_can_be_replaced_until_agreed(ctx):
    """Владелец 05.11.2026: выпущенный нами ДС пакета можно переписать внешним (клиент подписал свой документ) — до стадии
    «согласован». Номер — прежний или другой свободный; после «согласован» — отказ."""
    db, a, svc, user, _ = ctx
    a.no, a.number, a.status, a.origin, a.sign_state = 987610, "ДС № 987610", "подтверждён", "система", "выпущен"
    db.flush()
    _sign(db, a, svc, user, no=987610, file_name=None, file_bytes=None, edo_link="https://edo.example/doc/7")
    assert a.origin == "загружен" and a.no == 987610 and a.sign_state == "подписан"

    a.origin, a.sign_state = "система", "согласован"
    db.flush()
    with pytest.raises(X.ExternalError) as e:
        _sign(db, a, svc, user, no=987611, file_name=None, file_bytes=None, edo_link="https://edo.example/doc/8")
    assert "согласован" in e.value.message


def test_rk_dates_default_to_the_media_plan_of_the_package(ctx):
    """Владелец 05.11.2026: у строк внешнего ДС — даты РК. По умолчанию — из строк МП черновика пакета (самая ранняя «с»,
    самая поздняя «по»); без строк — месяц пакета."""
    db, a, svc, user, _ = ctx
    a.rows = [{"date_from": "2026-10-03", "date_to": "2026-10-20"}, {"date_from": "2026-10-10", "date_to": "2026-10-28"}]
    db.flush()
    assert X.rk_dates(a) == (date(2026, 10, 3), date(2026, 10, 28))
    _sign(db, a, svc, user)
    it = db.query(SalesAnnexItem).filter(SalesAnnexItem.annex_id == a.id).one()
    assert (it.period_from, it.period_to) == (date(2026, 10, 3), date(2026, 10, 28))


def test_changing_rk_dates_needs_the_right(ctx):
    """Менять даты РК во внешнем ДС — мастер аккаунт и админ (право «Мастер-сделки · согласование»), владелец 05.11.2026."""
    db, a, svc, user, _ = ctx
    a.rows = [{"date_from": "2026-10-03", "date_to": "2026-10-28"}]
    db.flush()
    own = [{"service_id": svc, "amount": 120000.0, "date_from": "2026-10-05", "date_to": "2026-10-25"}]
    with pytest.raises(X.ExternalError) as e:
        _sign(db, a, svc, user, items=own)
    assert e.value.status == 403
    _sign(db, a, svc, user, items=own, may_change_dates=True)
    it = db.query(SalesAnnexItem).filter(SalesAnnexItem.annex_id == a.id).one()
    assert (it.period_from, it.period_to) == (date(2026, 10, 5), date(2026, 10, 25))
    with pytest.raises(X.ExternalError):
        X._items(db, [{**own[0], "date_from": "2026-10-25", "date_to": "2026-10-05"}], (date(2026, 10, 3), date(2026, 10, 28)), True)
