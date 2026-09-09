# -*- coding: utf-8 -*-
"""Вкладка «Скрипт» админки трафика: разделение площадок и текст счётчика."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text as sa_text

import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import traffic_catalog as T
from app.sales.models import PUBLISHER_ARCHIVE_STATUS, SalesPublisher


@pytest.fixture
def env():
    db = SessionLocal()
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    if not u:
        db.close()
        pytest.skip('нужна активная учётка')
    keys = (T.SCRIPT_OUR_CODE, T.SCRIPT_NO_CODE, T.SCRIPT_VIEWABILITY)
    was = {k: db.execute(sa_text("SELECT value FROM company_settings WHERE key = :k"),
                         {"k": k}).scalar() for k in keys}
    yield SimpleNamespace(db=db, user=SimpleNamespace(
        id=u.id, name=u.name, role=SimpleNamespace(key='admin', is_master=True)))
    for k, v in was.items():
        db.execute(sa_text("DELETE FROM company_settings WHERE key = :k"), {"k": k})
        if v is not None:
            db.execute(sa_text("INSERT INTO company_settings (key, value) VALUES (:k, :v)"),
                       {"k": k, "v": v})
    db.commit()
    db.close()


def test_archived_publishers_are_not_offered_for_the_script(env):
    """Правило владельца 06.09.2026: архив не показываем. Ставить код там, где мы не
    работаем, незачем, а список из 41 строки вместо 26 делает вкладку бесполезной.

    Замерено: 15 площадок из 41 в статусе «АРХИВ».
    """
    out = T.get_site_script(env.db, env.user)
    shown = ({p["id"] for p in out["with_code"]["publishers"]}
             | {p["id"] for p in out["without_code"]["publishers"]})
    archived = {p.id for p in env.db.query(SalesPublisher)
                .filter(SalesPublisher.status == PUBLISHER_ARCHIVE_STATUS).all()}
    if not archived:
        pytest.skip('на стенде нет архивных площадок')
    assert not (shown & archived), 'архивные площадки попали в выдачу'


def test_split_follows_our_code_and_nothing_else(env):
    """Признак «код стоит» — `sales_publishers.our_code`, тот же, что в карточке
    паблишера. Второй флаг для того же факта разошёлся бы с первым, и стало бы непонятно,
    какой верен."""
    out = T.get_site_script(env.db, env.user)
    assert all(p["our_code"] for p in out["with_code"]["publishers"])
    assert not any(p["our_code"] for p in out["without_code"]["publishers"])
    ids = ([p["id"] for p in out["with_code"]["publishers"]]
           + [p["id"] for p in out["without_code"]["publishers"]])
    assert len(ids) == len(set(ids)), 'площадка не может быть в обеих колонках'


def test_two_columns_have_two_independent_scripts(env):
    """Скрипты разные: на площадках с нашим кодом счётчик уже стоит, и вшивать его второй
    раз значило бы получить двойные замеры. Одна настройка на обе колонки стёрла бы это
    различие — ровно то, ради чего вкладка заводилась."""
    T.set_site_script(T.SiteScriptIn(with_code='<script src="https://a.ru/with.js"></script>',
                                     without_code='<script src="https://a.ru/no.js"></script>'),
                      env.db, env.user)
    assert T.creative_script(env.db, True) == '<script src="https://a.ru/with.js"></script>'
    assert T.creative_script(env.db, False) == '<script src="https://a.ru/no.js"></script>'


def test_empty_column_is_a_legal_value(env):
    """«В эту колонку ничего не вшиваем» — законное состояние, а не недозаполнение.
    Отказ здесь запретил бы половину замысла."""
    T.set_site_script(T.SiteScriptIn(with_code="", without_code=""), env.db, env.user)
    assert T.creative_script(env.db, True) == ""
    assert T.creative_script(env.db, False) == ""


def test_a_bare_url_is_refused(env):
    """Строка без тега попадёт в head креатива текстом и молча ничего не сделает —
    а выяснится это по отсутствию данных, когда РК уже крутится."""
    with pytest.raises(HTTPException) as e:
        T.set_site_script(T.SiteScriptIn(with_code="https://x.ru/a.js"), env.db, env.user)
    assert e.value.status_code == 400


def test_the_wrapper_puts_the_counter_first_inside_head(env):
    """Счётчик должен успеть встать до отрисовки баннера, поэтому он первым в head —
    раньше viewability."""
    from app.dsp import creatives as cr
    out = cr.wrap_html("<html><head></head><body>{RID}</body></html>",
                       extra_script=T.SUGGESTED_SCRIPT,
                       viewability_src="https://example.test/viewability.js")
    assert out.index("qq.js") < out.index("viewability.js")
    assert "{RID}" in out, 'макросы обязаны пережить обёртку'
    # Без скрипта обёртка остаётся прежней — счётчик не выдумывается.
    assert "qq.js" not in cr.wrap_html("<html><head></head><body></body></html>")


def test_viewability_address_is_a_setting_not_a_constant(env):
    """Адрес скрипта видимости вынесен на экран 09.09.2026: в имени хоста узнаётся
    поставщик, а репозиторий уходит на GitHub и история гита не переписывается.

    Пусто — законное состояние: обёртка идёт без скрипта, а демо-экран говорит об этом.
    """
    from app.dsp import creatives as cr
    T.set_site_script(T.SiteScriptIn(viewability="https://example.test/v.js"),
                      env.db, env.user)
    assert T.viewability_src(env.db) == "https://example.test/v.js"
    assert T.get_site_script(env.db, env.user)["viewability"] == "https://example.test/v.js"
    assert "https://example.test/v.js" in cr.wrap_html(
        "<div>x</div>", viewability_src=T.viewability_src(env.db))

    T.set_site_script(T.SiteScriptIn(viewability=""), env.db, env.user)
    assert T.viewability_src(env.db) == ""
    assert "<script src=" not in cr.wrap_html(
        "<div>x</div>", viewability_src=T.viewability_src(env.db))


def test_viewability_wants_an_address_not_a_tag(env):
    """Здесь ждём адрес: тег уехал бы внутрь `src="…"`, обёртка собралась бы, а скрипт не
    подгрузился — и увидели бы мы это по отсутствию данных. Обратная ошибка к соседней
    колонке, где, наоборот, нужен тег."""
    for bad in ('<script src="https://x.ru/v.js"></script>', "http://x.ru/v.js", "x.ru/v.js"):
        with pytest.raises(HTTPException) as e:
            T.set_site_script(T.SiteScriptIn(viewability=bad), env.db, env.user)
        assert e.value.status_code == 400
