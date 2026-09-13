# -*- coding: utf-8 -*-
"""Приборы на креатив нацеливания в DSP. Без сети.

Он заводится в ЧУЖОМ кабинете, где нет удаления: второй такой же креатив
убрать будет нечем. Поэтому половина файла — про то, что повторный вызов ничего не
создаёт, а вторая половина про отказы: у этой кнопки любая тишина выглядит как «не
работает», и причина обязана доезжать до человека словами.
"""
import pytest
from sqlalchemy import text

# Внешние ключи комплекта смотрят в users и sales_deals: без этих модулей в реестре
# моделей SQLAlchemy не соберёт таблицу вовсе, и падает не тест, а импорт.
from app import models as _core_models  # noqa: F401
from app.sales import models as _sales_models  # noqa: F401
from app.dsp import targeting_creative as P

PARTNER = "776845105B3FD2AA"
CAMPAIGN = "6F76E42EF4FD1492"


class FakeClient:
    """Подменный клиент: описывает ВЕСЬ обмен заведения, как у клиентов DSP и WCM."""

    def __init__(self, journal_hash=None, add_hash="NEWHASH000000001"):
        self.journal_hash = journal_hash
        self.add_hash = add_hash
        self.calls = []

    def last_ok_xxhash(self, method, entity_type, local_ref):
        self.calls.append(("journal", method, local_ref))
        return self.journal_hash

    def creative_add(self, campaign_xxhash, params, local_ref=None):
        self.calls.append(("add", campaign_xxhash, params.get("title"), local_ref))
        return self.add_hash

    def creative_edit(self, xxhash, params, local_ref=None):
        self.calls.append(("edit", xxhash, local_ref))
        return True


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def _set_with(db, **kw):
    """Комплект-времянка. Номера ≥ 9000 принадлежат тестам — так уговорено в проекте."""
    from app.launch_prep.models import LaunchPrepCreativeSet
    deal_id = db.execute(text("SELECT id FROM sales_deals ORDER BY id LIMIT 1")).scalar()
    if not deal_id:
        pytest.skip("на стенде нет ни одной сделки")
    s = LaunchPrepCreativeSet(deal_id=deal_id, no=9901, title="прибор", **kw)
    db.add(s)
    db.commit()
    return s


def _drop(db, s):
    db.execute(text("DELETE FROM launch_prep_creative_set WHERE id = :i"), {"i": s.id})
    db.commit()


def test_stored_hash_is_returned_without_going_outside():
    """Заведён — значит заведён. Второй раз наружу не ходим ВООБЩЕ.

    Это главная защита: в DSP нет удаления, и лишний креатив останется там навсегда.
    """
    db = _db()
    s = _set_with(db, ms_targeting_creative_xxhash="ALREADY0000000001")
    c = FakeClient()
    try:
        assert P.ensure(db, s, client=c) == "ALREADY0000000001"
        assert c.calls == [], "при сохранённом хеше не должно быть ни одного вызова"
    finally:
        _drop(db, s)


def test_journal_saves_us_from_a_duplicate():
    """DSP создал, а наш коммит не дошёл — журнал помнит, и повтор не плодит второй."""
    db = _db()
    s = _set_with(db)
    c = FakeClient(journal_hash="FROMJOURNAL00001")
    try:
        assert P.ensure(db, s, client=c) == "FROMJOURNAL00001"
        assert [k[0] for k in c.calls] == ["journal"], "после журнала создавать нечего"
        db.refresh(s)
        assert s.ms_targeting_creative_xxhash == "FROMJOURNAL00001"
        assert s.ms_targeting_at is not None
    finally:
        _drop(db, s)


def test_missing_settings_name_where_to_set_them():
    db = _db()
    s = _set_with(db)
    saved = db.execute(text(
        "SELECT key, value FROM company_settings "
        "WHERE key IN ('dsp_targeting_partner_xxhash','dsp_targeting_campaign_xxhash')")).all()
    try:
        db.execute(text("UPDATE company_settings SET value='' "
                        "WHERE key LIKE 'dsp_targeting_%'"))
        db.commit()
        with pytest.raises(P.TargetingCreativeError) as e:
            P.ensure(db, s, client=FakeClient())
        assert "Скрипты сайта" in str(e.value)
    finally:
        for k, v in saved:
            db.execute(text("UPDATE company_settings SET value=:v WHERE key=:k"),
                       {"k": k, "v": v})
        db.commit()
        _drop(db, s)


def test_set_without_archive_says_so():
    """Загрузчик DSP принимает zip. Картинка без архива — не поломка, а внятный отказ."""
    db = _db()
    s = _set_with(db)
    try:
        with pytest.raises(P.TargetingCreativeError) as e:
            P.ensure(db, s, client=FakeClient())
        assert "zip" in str(e.value).lower() or "архив" in str(e.value).lower()
    finally:
        _drop(db, s)


def test_landing_never_refuses():
    """Нацеливание выдаём ВСЕГДА: посадочная — работа трафика, а не условие кнопки.

    Владелец 12.09.2026: «мы не должны проверять вызов на посадочной, наша задача только
    получить нацеливание». Поэтому у `_landing` нет ни одной ветки отказа — есть лестница
    предпочтений, последняя ступень которой всегда даёт адрес.
    """
    db = _db()
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d
          JOIN sales_advertisers a ON a.id = d.advertiser_id
         WHERE coalesce(a.website,'') <> '' LIMIT 1""")).scalar()
    if not row:
        pytest.skip("нет сделки с сайтом рекламодателя")
    from app.launch_prep.models import LaunchPrepCreativeSet
    s = LaunchPrepCreativeSet(deal_id=row, no=9902, title="прибор")
    db.add(s)
    db.commit()
    try:
        url = P._landing(db, s)
        assert url.startswith("http"), "ссылка обязана быть абсолютной"
    finally:
        _drop(db, s)


def test_quiet_variant_never_raises():
    """Отправка на согласование не должна зависеть от чужой системы."""
    db = _db()
    s = _set_with(db)          # без архива — ensure упал бы
    try:
        assert P.ensure_quietly(db, s) is None
    finally:
        _drop(db, s)


def test_title_marks_the_creative_as_ours():
    """В чужом кабинете наши креативы должны опознаваться без нашей базы."""
    assert P.TITLE_PREFIX.strip()
    assert "НАЦЕЛИВАНИЕ" in P.TITLE_PREFIX


def test_landing_has_no_refusal_branch_at_all():
    """Проверяем ФОРМУ, а не случай: отказ здесь не должен появиться снова.

    Ветку «нет посадочной — отказ» я уже однажды написал, и она превращала кнопку в
    неработающую именно на отправке трафику. Прибор держит решение владельца.
    """
    import ast
    import inspect
    import textwrap

    # Разбираем ДЕРЕВОМ, а не поиском слова: первая версия этого прибора искала подстроку
    # «raise» и падала на собственной докстроке, где это слово упомянуто. Строковый поиск
    # в коде — почти всегда не то, чем кажется.
    tree = ast.parse(textwrap.dedent(inspect.getsource(P._landing)))
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    assert not raises, "у выбора ссылки перехода не должно быть отказов"
    assert P.FALLBACK_LINK.startswith("https://")


def test_set_without_anything_still_gets_a_link():
    db = _db()
    empty_deal = db.execute(text("""
        SELECT d.id FROM sales_deals d
         WHERE d.advertiser_id IS NULL
            OR d.advertiser_id NOT IN (SELECT id FROM sales_advertisers
                                        WHERE coalesce(website,'') <> '')
         LIMIT 1""")).scalar()
    if not empty_deal:
        pytest.skip("нет сделки без сайта рекламодателя")
    from app.launch_prep.models import LaunchPrepCreativeSet
    s = LaunchPrepCreativeSet(deal_id=empty_deal, no=9903, title="прибор")
    db.add(s); db.commit()
    try:
        assert P._landing(db, s) == P.FALLBACK_LINK
    finally:
        _drop(db, s)
