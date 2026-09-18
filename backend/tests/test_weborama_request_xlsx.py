# -*- coding: utf-8 -*-
"""Заявка на пиксели Weborama: файл, который уходит человеку в чужую компанию.

Ошибка здесь не падает — она уезжает менеджеру и возвращается неверно заведёнными
вставками через несколько дней. Поэтому проверяется то, что уже расходилось при ручном
заполнении: место данных в листе, форма имён и единицы закупки.
"""
import pytest
from sqlalchemy import text

from app import models as _core  # noqa: F401
from app.sales import models as _sales  # noqa: F401
from app.launch_prep import models as _lp  # noqa: F401
from app.ad import models as _ad  # noqa: F401
from app.weborama import naming, request_xlsx as R


def _db():
    from app.database import SessionLocal
    return SessionLocal()


@pytest.fixture
def fixture():
    """Сделка с брендом + площадка с доменом + пара. Номера тестовые (≥ 9000)."""
    from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair,
                                        LaunchPrepTarget)
    db = _db()
    ids = {}
    deal_id = db.execute(text(
        "SELECT id FROM sales_deals WHERE brand_id IS NOT NULL ORDER BY id LIMIT 1")).scalar()
    pub = db.execute(text(
        "SELECT id, domain FROM sales_publishers "
        " WHERE coalesce(domain, '') <> '' ORDER BY id LIMIT 1")).mappings().first()
    service_id = db.execute(text("SELECT id FROM sales_services ORDER BY id LIMIT 1")).scalar()
    if not (deal_id and pub and service_id):
        db.close()
        pytest.skip("на стенде нет сделки с брендом, площадки с доменом или услуги")
    s = LaunchPrepCreativeSet(deal_id=deal_id, no=9902, title="прибор")
    t = LaunchPrepTarget(deal_id=deal_id, publisher_id=pub["id"], service_id=service_id,
                         surface_kind="WEB", state="согласован")
    db.add_all([s, t])
    db.flush()
    db.add(LaunchPrepPair(set_id=s.id, target_id=t.id))
    db.commit()
    ids = {"set": s.id, "target": t.id, "domain": pub["domain"]}
    yield db, ids
    db.execute(text("DELETE FROM launch_prep_pair WHERE set_id = :s"), {"s": ids["set"]})
    db.execute(text("DELETE FROM launch_prep_creative_set WHERE id = :s"), {"s": ids["set"]})
    db.execute(text("DELETE FROM launch_prep_target WHERE id = :t"), {"t": ids["target"]})
    db.commit()
    db.close()


def test_names_come_from_the_same_place_as_the_api(fixture):
    """Имена строит `naming`, а не вторая реализация рядом.

    Файл и заведение через API обязаны называть одно и то же ОДИНАКОВО: иначе ответ
    менеджера не сойдётся с тем, что у нас уже заведено, и разойдётся это молча —
    вставка просто окажется второй на то же размещение.
    """
    db, ids = fixture
    meta, rows = R.rows_for_set(db, ids["set"])
    assert rows, "строка не собралась"
    r = rows[0]
    assert r["name"] == naming.row_name("Desktop", meta["campaign"], ids["domain"])
    assert r["position"] == naming.position_name(R.ACCOUNT, R.FORMAT, r["name"])


def test_the_position_column_is_longer_than_the_name_column(fixture):
    """Ловушка инструкции: PDF описывает колонку D формулой из колонки E.

    Генератор, написанный по тексту инструкции, положил бы в D значение вида
    `SIMB-AD_banner_Desktop_…` и собрал бы E из него второй раз. Настоящий D короче ровно
    на «аккаунт_формат» — сверено по файлу владельца, а не по PDF.
    """
    db, ids = fixture
    _meta, rows = R.rows_for_set(db, ids["set"])
    r = rows[0]
    assert not r["name"].lower().startswith("simb-ad")
    assert r["position"].startswith("SIMB-AD_banner_")
    assert r["position"].endswith(r["name"])


def test_data_start_below_the_legend(fixture):
    """Строки 14–18 — легенда допустимых значений, а не данные. Вписанное туда менеджер
    прочитает как исправление легенды, а не как заявку."""
    from openpyxl import load_workbook
    from io import BytesIO

    db, ids = fixture
    name, blob = R.build(db, ids["set"])
    assert name.endswith(".xlsx")
    ws = load_workbook(BytesIO(blob))["Mediaplan"]
    assert ws["C4"].value == R.ACCOUNT, "Account ID не на месте"
    assert ws[f"D{R.FIRST_ROW}"].value, "первая строка данных пуста"
    assert R.FIRST_ROW == 19
    for n in range(14, 18):
        assert ws[f"D{n}"].value is None, f"строка {n} — легенда, туда писать нельзя"


def test_zero_units_are_left_empty(fixture):
    """Пусто лучше нуля: ноль в «Buying units» менеджер прочитает как «показов не
    планируется», а у нас их просто ещё не посчитали."""
    db, ids = fixture
    _meta, rows = R.rows_for_set(db, ids["set"])
    assert rows[0]["units"] is None or rows[0]["units"] > 0


def test_the_tag_carries_the_site_domain_not_the_placeholder(fixture):
    """В отдаваемом теге вместо `[RANDOM]` стоит макрос, а в хвосте — домен ЭТОЙ площадки.

    Сырой пиксель, как он приходит от Weborama, площадке бесполезен: без подстановки он
    считает показы неверно, а без хвоста с адресом — не различает площадки вовсе.
    Проверяется той же функцией, которой тег собирается при заведении в DSP: две сборки
    одного тега разошлись бы молча, и расхождение всплыло бы через месяц на цифрах.
    """
    raw = "https://sc.weborama-tech.ru/?a.A=im&a.rnd=[RANDOM]"
    dsp = naming.final_tag(raw, "maksavit.ru", "dsp")
    own = naming.final_tag(raw, "maksavit.ru", "adfox")
    assert "[RANDOM]" not in dsp and dsp.endswith("https://maksavit.ru")
    assert "{RND}" in dsp, "у нашего DSP макрос {RND}"
    assert "%system.random%" in own, "в сервере площадки макрос %system.random%"


def test_a_placement_without_a_pixel_keeps_its_row(fixture):
    """Строка без пикселя остаётся в файле с причиной.

    Выброшенная строка хуже пустой клетки: человек пересчитает площадки, не сойдётся с
    медиапланом и решит, что потерял размещение, — вместо того чтобы прочитать, чего не
    хватает.
    """
    db, ids = fixture
    rows = R.pixels_for_set(db, ids["set"])
    assert len(rows) == 1
    assert rows[0]["tag"] is None and rows[0]["why"], "нет ни тега, ни объяснения"


def test_a_placeholder_in_the_middle_is_refused():
    """`[RANDOM]` обязан быть последним — иначе тег собирается МОЛЧА НЕВЕРНО.

    Формула инструкции дописывает адрес в конец строки, то есть предполагает, что после
    плейсхолдера в пикселе ничего нет. Когда есть, выходит `…&a.ycp=&a.x=1https://site.ru`:
    параметр адреса пустой, домен приклеен к чужому значению. Такой тег выглядит рабочим,
    уезжает в креатив и обнаруживается через месяц по расхождению цифр.
    """
    import pytest as _pytest

    good = "https://sc.weborama-tech.ru/?a.A=im&a.rnd=[RANDOM]"
    bad = "https://sc.weborama-tech.ru/?a.A=im&a.rnd=[RANDOM]&a.x=1"
    assert naming.final_tag(good, "maksavit.ru", "dsp").endswith("https://maksavit.ru")
    with _pytest.raises(ValueError) as e:
        naming.final_tag(bad, "maksavit.ru", "dsp")
    assert "не в конце" in str(e.value)


def test_the_campaign_landing_is_our_own_site():
    """Посадочная кампании у Weborama — НАШ сайт, а не адрес одной из площадок.

    Поле у них одно на кампанию и справочное: счёт ведут вставки, каждая со своей
    площадкой. Подставляя туда самую весомую площадку, мы выбирали произвольную — и на
    экране «Посадочная кампании: minicen.ru» рядом со строкой Maksavit читалось как
    перепутанный адрес (владелец 18.09.2026).

    Проверяется и следствие: у поля больше нет состояния «пусто», то есть исчез заслон
    «ни у одной площадки нет ссылки». Свой адрес есть всегда.
    """
    from app.weborama.provision import OWN_LANDING, default_landing

    assert OWN_LANDING.startswith("https://")
    assert default_landing(None, None) == OWN_LANDING
