# -*- coding: utf-8 -*-
"""Доп. параметр РК «нужен пиксель Weborama» (владелец 14.09.2026).

До него пиксель требовался БЕЗУСЛОВНО: `dsp/provision._blocker` отказывал строкой «нет
пикселя Weborama», и снять это требование было нечем — РК, которой верификатор не нужен,
в DSP не уезжала вовсе. Параметр делает требование условным, а значит ошибка здесь тихая
в обе стороны: лишний отказ запирает выгрузку, лишний пропуск отправляет в сеть креатив
без счётчика. Поэтому проверяется не наличие колонки, а ПОВЕДЕНИЕ трёх её читателей.
"""
import pytest
from sqlalchemy import text

from app.ad.build import needs_pixel
from app.database import SessionLocal
from app.dsp import provision as dsp_prov
from app.sales import stage_checks as sc
from app.sales import stage_scope
from app.sales.models import SalesDeal


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def pixel_deal(db):
    """Сделка для проб, у которой снимок состояния восстанавливается ПОСЛЕ теста.

    Ручка сохранения делает `commit`, то есть откат фикстуры её записи не уносит — ни
    колонки сделки, ни строку журнала действий. Прогон 14.09.2026 это и показал: три
    записи `deal_weborama_pixel` остались на стенде после зелёных тестов. Тест, который
    оставляет след, врёт о состоянии стенда ровно так же, как тест на старом коде.

    `expire_all` после сырого UPDATE обязателен: ORM держит объект в своей карте, и
    прочитанное им значение осталось бы прежним, а `commit` записал бы стухшее поверх.
    """
    deal = db.query(SalesDeal).first()
    if deal is None:
        pytest.skip("на стенде нет сделок")
    snap = db.execute(text(
        "SELECT weborama_pixel, weborama_pixel_mode, weborama_pixel_tag,"
        " weborama_ext_insertion, weborama_pixel_at FROM sales_deals WHERE id = :d"),
        {"d": deal.id}).first()
    db.expire_all()
    yield deal
    db.rollback()
    db.execute(text(
        "UPDATE sales_deals SET weborama_pixel = :p, weborama_pixel_mode = :m,"
        " weborama_pixel_tag = :t, weborama_ext_insertion = :i, weborama_pixel_at = :a"
        " WHERE id = :d"),
        {"d": deal.id, "p": snap[0], "m": snap[1], "t": snap[2], "i": snap[3], "a": snap[4]})
    db.execute(text("DELETE FROM audit_log WHERE action IN"
                    " ('deal_weborama_pixel', 'deal_verifier_shows')"))
    db.execute(text("DELETE FROM notification_deliveries"
                    " WHERE event_key = 'weborama_pixel_needed'"))
    db.commit()
    db.expire_all()


class _P:
    """Размещение: из всего ряда `_blocker` смотрит на четыре поля.

    Статусы берём КОНСТАНТАМИ модуля, а не строками: список принимаемых статусов —
    его правило, и переписанный от руки он молча разошёлся бы с ним."""
    def __init__(self, pixel=None):
        self.is_direct = False
        self.status = dsp_prov.PLACEMENT_OK[0]
        self.weborama_pixel = pixel


class _C:
    def __init__(self):
        self.status = dsp_prov.CREATIVE_OK[0]


def _row(pixel=None):
    return {"creative": _C(), "placement": _P(pixel), "file": None,
            "target": None, "publisher": None}


# ── Признак на сделке ────────────────────────────────────────────────────────

def test_default_is_off(db):
    """Умолчание — «не заказан» (решение владельца 14.09.2026).

    Проверяется на КОЛОНКЕ, а не на модели: `server_default` и `default` — разные
    механизмы, и строка, вставленная мимо ORM, берёт первый. Этой парой проект уже
    обжигался."""
    val = db.execute(text("SELECT column_default FROM information_schema.columns "
                          "WHERE table_name = 'sales_deals' "
                          "AND column_name = 'weborama_pixel'")).scalar()
    assert val is not None and "false" in val.lower(), (
        f"умолчание колонки — {val!r}, а должно быть false")

    deal = db.query(SalesDeal).first()
    if deal is None:
        pytest.skip("на стенде нет сделок")
    assert needs_pixel(db, deal.id) in (True, False)


def test_needs_pixel_follows_the_flag(db):
    """Читатель признака ходит в базу, а не кэширует: галочку ставят на карточке, а
    смотрят на неё в двух других контурах."""
    deal = db.query(SalesDeal).first()
    if deal is None:
        pytest.skip("на стенде нет сделок")
    db.execute(text("UPDATE sales_deals SET weborama_pixel = true WHERE id = :d"),
               {"d": deal.id})
    assert needs_pixel(db, deal.id) is True
    db.execute(text("UPDATE sales_deals SET weborama_pixel = false WHERE id = :d"),
               {"d": deal.id})
    assert needs_pixel(db, deal.id) is False


# ── Выгрузка в DSP ───────────────────────────────────────────────────────────

def test_pixel_demanded_only_when_ordered():
    """ГЛАВНЫЙ прибор: заказан — отказ без пикселя; не заказан — отказа нет.

    Если однажды условие снова станет безусловным, покраснеет первая половина; если
    признак начнут игнорировать — вторая."""
    assert dsp_prov._blocker(_row(pixel=None), True) == (
        "нет пикселя Weborama — сначала «ПИКСЕЛЬ WR»")
    assert dsp_prov._blocker(_row(pixel=None), False) != (
        "нет пикселя Weborama — сначала «ПИКСЕЛЬ WR»")


def test_blocker_defaults_to_demanding():
    """Вызов, забывший передать признак, ТРЕБУЕТ пиксель.

    Умолчание выбрано в сторону лишнего отказа: он виден человеку и разбирается за
    минуту, а лишний пропуск уходит в рекламную сеть креативом без счётчика и
    обнаруживается расхождением цифр через недели."""
    assert dsp_prov._blocker(_row(pixel=None)) == (
        "нет пикселя Weborama — сначала «ПИКСЕЛЬ WR»")


# ── Применимость требования стадии ───────────────────────────────────────────

def test_stage_check_applies_only_when_ordered():
    """Требование «пиксель получен» не должно существовать для сделок без заказа.

    Иначе разметка заперла бы вход в «В размещении» всем подряд условием, которое
    большинству сделок нечем выполнить."""
    assert "weborama_pixel" in sc.SCOPE_KEYS
    on = SalesDeal(weborama_pixel=True)
    off = SalesDeal(weborama_pixel=False)
    assert sc.scope_matches({"weborama_pixel": True}, on) is True
    assert sc.scope_matches({"weborama_pixel": True}, off) is False


def test_stage_check_registered():
    assert "weborama_pixel" in sc.REGISTRY
    where, link = sc.PLACES["weborama_pixel"]
    assert where and link, "проверка без адреса «где чинить» — человек пойдёт искать сам"


# ── Блок карточки ────────────────────────────────────────────────────────────

def test_card_block_sits_between_brief_and_creatives():
    """Порядок блоков — не косметика: «зачем крутим» → «что включено» → «чем крутим»."""
    keys = list(stage_scope.BLOCK_KEYS)
    assert "campaign-extra" in keys
    assert keys.index("traffic-brief") < keys.index("campaign-extra") < keys.index("creatives")
    assert stage_scope.BLOCK_LABELS.get("campaign-extra")


def test_card_block_counts_as_filled_when_ordered(db):
    """Заказанный пиксель = «в блоке что-то есть», то есть блок не спрячется разметкой."""
    assert stage_scope._has_content(db, SalesDeal(weborama_pixel=True), "campaign-extra") is True
    assert stage_scope._has_content(db, SalesDeal(weborama_pixel=False), "campaign-extra") is False


# ── Событие трафику ──────────────────────────────────────────────────────────

def test_traffic_event_registered():
    """Заказ без уведомления невидим: галочка стоит в карточке сделки, а работу делают
    на дашборде трафика."""
    from app.notify import registry
    ev = registry.get("weborama_pixel_needed")
    assert ev is not None, "событие не зарегистрировано"
    assert ev.direction == "traffic"
    assert not ev.scan, "событие шины, сканеру его искать нечем"


def test_action_has_a_label():
    """Новое действие журнала приходит с подписью — иначе в «Журнале действий» виден
    сырой ключ (правило проекта, отдельный храповик на подписи)."""
    from app.routers.users import ACTION_LABELS
    assert "deal_weborama_pixel" in ACTION_LABELS


# ── Расхождение на карточке: сравнивать сопоставимое ─────────────────────────

def test_campaign_mismatch_compares_only_covered_placements(db):
    """Итог по РК считается по ПОКРЫТЫМ площадкам, а не по всей РК.

    Дефект, найденный замером 14.09.2026 в первой же версии: верификатор покрывал одну
    площадку из девятнадцати, его сумму делили на наш факт по всей кампании — и карточка
    показывала «расхождение 77 %» там, где по измеренной площадке оно было 10 %.
    Арифметически верно, по смыслу ложь: число читается как «четверти показов нет» и
    ведёт разбираться не туда. Прибор держит инвариант: при ОДИНАКОВОМ отставании
    процент не зависит от охвата.
    """
    import app.main            # noqa: F401 — иначе FK моделей не резолвятся
    from app.ad.models import AdCampaign
    from app.models import User
    from app.routers import sales_dashboard as sd

    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    if user is None:
        pytest.skip("на стенде нет админской учётки")
    camp = db.execute(text("""
        SELECT campaign_id FROM ad_campaign_stat GROUP BY campaign_id
         HAVING sum(shows) > 0 ORDER BY sum(shows) DESC LIMIT 1""")).scalar()
    if camp is None:
        pytest.skip("на стенде нет РК с фактом")
    c = db.query(AdCampaign).filter(AdCampaign.id == camp).first()

    base = sd.deal_campaign(str(c.deal_id), db=db, current_user=user)
    rows = [r for r in base["rows"] if r["fact_shows"]]
    if len(rows) < 2:
        pytest.skip("в РК меньше двух площадок с фактом")

    def put(r):
        db.execute(text(
            "INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows,"
            " clicks, source) VALUES (:c, :p, CURRENT_DATE, :s, 0, 'weborama')"),
            {"c": c.id, "p": r["id"], "s": int(r["fact_shows"] * 0.9)})

    put(rows[0])
    one = sd.deal_campaign(str(c.deal_id), db=db, current_user=user)
    assert one["verifier_placements"] == 1
    assert one["mismatch_pct"] == 10.0, (
        "процент посчитан по всей РК, а замерена одна площадка")
    assert one["fact_shows"] == base["fact_shows"], (
        "показы верификатора попали в ФАКТ — то, ради чего заведён stat_sources")

    for r in rows[1:]:
        put(r)
    allp = sd.deal_campaign(str(c.deal_id), db=db, current_user=user)
    assert allp["verifier_placements"] == len(rows)
    assert allp["mismatch_pct"] == one["mismatch_pct"], (
        "при одинаковом отставании процент поехал от охвата")


def test_placement_row_carries_its_own_mismatch(db):
    """В расхлопе расхождение считается тем же выражением, что в шапке.

    Иначе итог и строки однажды разойдутся, и правым окажется неизвестно кто."""
    import app.main            # noqa: F401
    from app.ad.models import AdCampaign
    from app.models import User
    from app.routers import sales_dashboard as sd

    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    camp = db.execute(text("""
        SELECT campaign_id FROM ad_campaign_stat GROUP BY campaign_id
         HAVING sum(shows) > 0 ORDER BY sum(shows) DESC LIMIT 1""")).scalar()
    if user is None or camp is None:
        pytest.skip("нет учётки или РК с фактом")
    c = db.query(AdCampaign).filter(AdCampaign.id == camp).first()
    base = sd.deal_campaign(str(c.deal_id), db=db, current_user=user)
    r = next((x for x in base["rows"] if x["fact_shows"]), None)
    if r is None:
        pytest.skip("в РК нет площадок с фактом")
    assert r["mismatch_pct"] is None, "замеров нет, а расхождение посчиталось"

    db.execute(text(
        "INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks,"
        " source) VALUES (:c, :p, CURRENT_DATE, :s, 0, 'weborama')"),
        {"c": c.id, "p": r["id"], "s": int(r["fact_shows"] * 0.75)})
    after = sd.deal_campaign(str(c.deal_id), db=db, current_user=user)
    row = next(x for x in after["rows"] if x["id"] == r["id"])
    assert row["verifier_shows"] == int(r["fact_shows"] * 0.75)
    assert row["mismatch_pct"] == 25.0


# ── Внешний пиксель ──────────────────────────────────────────────────────────

def test_external_tag_is_validated_before_it_reaches_a_creative():
    """Тег приносит человек копированием из чужой таблицы — рядом лежат посадочная,
    тег Adloox и тег клика. Вшить не тот адрес значит отправить в сеть креатив, который
    считает не то, и узнать об этом по расхождению цифр через месяц.
    """
    from app.weborama.naming import check_external_pixel
    good = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?"
            "a.A=im&a.si=9796&a.te=1522&a.he=1&a.wi=1&a.hr=p&a.ra=[RANDOM]")
    assert check_external_pixel("  " + good + "  ") == good

    for bad, why in [
        ("", "пустой"),
        ("http://wcm.weborama-tech.ru/x?a.ra=[RANDOM]", "не https"),
        ("https://example.com/px?a.ra=[RANDOM]", "чужой домен"),
        (good.replace("[RANDOM]", ""), "без кеш-бастера"),
        (good[:40] + " " + good[40:], "склеенные ячейки"),
    ]:
        with pytest.raises(ValueError):
            check_external_pixel(bad)


def test_external_tag_survives_our_builder_and_gets_the_site_domain():
    """Их тег проходит НАШ сборщик без правок и получает домен площадки.

    Это и есть причина, по которой фиксированный тег годится: вставка у них одна на всю
    сеть, но `&a.ycp=https://<домен>` уезжает свой в каждую площадку. Если сборщик
    однажды перестанет дописывать адрес, разбивка по сайтам исчезнет молча.
    """
    from app.weborama.naming import final_tag
    tag = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?"
           "a.A=im&a.si=9796&a.te=1522&a.he=1&a.wi=1&a.hr=p&a.ra=[RANDOM]")
    out = final_tag(tag, "maksavit.ru", kind="dsp")
    assert "[RANDOM]" not in out, "макрос рандомизатора не подставлен"
    assert out.endswith("https://maksavit.ru")


def test_external_tag_replaces_per_placement_pixel_in_the_blocker():
    """С внешним тегом пиксель у размещения не спрашиваем: вставку заводил клиент,
    у нас её нет и не будет. Иначе выгрузка была бы заперта навсегда."""
    tag = "https://wcm.weborama-tech.ru/x?a.ra=[RANDOM]"
    assert dsp_prov._blocker(_row(pixel=None), True, tag) != (
        "нет пикселя Weborama — сначала «ПИКСЕЛЬ WR»")
    assert dsp_prov._blocker(_row(pixel=None), True, None) == (
        "нет пикселя Weborama — сначала «ПИКСЕЛЬ WR»")


def test_manual_source_is_a_verifier_and_never_a_fact():
    """Введённое руками — измерение, а не наш счётчик. В закрытие не идёт никогда."""
    from app.ad.stat_sources import OWN, VERIFIER, fact_sources
    assert "weborama_manual" in VERIFIER
    assert "weborama_manual" not in OWN
    assert "weborama_manual" not in fact_sources()


def test_pixel_setup_reports_mode_and_tag(db):
    """Один вопрос — один ответ: «нужен ли», «какой» и «какой именно тег» спрашивают
    вместе, и разнести их по трём запросам значит однажды получить три разных ответа."""
    from app.ad.build import pixel_setup
    deal = db.query(SalesDeal).first()
    if deal is None:
        pytest.skip("на стенде нет сделок")
    tag = "https://wcm.weborama-tech.ru/x?a.ra=[RANDOM]"
    db.execute(text("UPDATE sales_deals SET weborama_pixel = true,"
                    " weborama_pixel_mode = 'external', weborama_pixel_tag = :t"
                    " WHERE id = :d"), {"d": deal.id, "t": tag})
    db.expire_all()
    got = pixel_setup(db, deal.id)
    assert got == {"needed": True, "mode": "external", "tag": tag}

    # Выключенный признак гасит и режим, и тег: «не заказан» не должен выглядеть как
    # «заказан внешний», иначе выгрузка пойдёт вшивать тег по снятому заказу.
    db.execute(text("UPDATE sales_deals SET weborama_pixel = false WHERE id = :d"),
               {"d": deal.id})
    assert pixel_setup(db, deal.id) == {"needed": False, "mode": "own", "tag": None}


def test_bad_tag_is_rejected_even_when_the_flag_is_already_on(db, pixel_deal):
    """Проверка тела идёт ДО выхода «ничего не изменилось».

    Дефект, найденный замером 14.09.2026: ручка выходила на строке `if was == want`
    раньше, чем разбирала тело. У сделки с уже включённым признаком это означало две
    вещи сразу — заведомо кривой тег принимался молча (ответ 200, ничего не записано),
    а исправить опечатку в уже загруженном теге было нечем вовсе.
    """
    import app.main            # noqa: F401
    from fastapi import HTTPException
    from app.models import User
    from app.routers import sales_dashboard as sd

    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    if user is None:
        pytest.skip("на стенде нет админской учётки")
    deal = pixel_deal
    db.execute(text("UPDATE sales_deals SET weborama_pixel = true,"
                    " weborama_pixel_mode = 'own' WHERE id = :d"), {"d": deal.id})
    db.expire_all()

    with pytest.raises(HTTPException) as e:
        sd.save_deal_campaign_extra(
            deal.id, sd.CampaignExtraIn(weborama_pixel=True, mode="external",
                                        tag="https://example.com/x"),
            db=db, current_user=user)
    assert e.value.status_code == 400
    assert "weborama-tech.ru" in str(e.value.detail)


def test_switching_back_to_own_clears_the_external_tag(db, pixel_deal):
    """external → own стирает тег.

    Оставленный тег однажды вшился бы в креатив по кампании, которая давно считается
    своим пикселем, и расхождение искали бы в цифрах, а не в настройке."""
    import app.main            # noqa: F401
    from app.ad.build import pixel_setup
    from app.models import User
    from app.routers import sales_dashboard as sd

    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    if user is None:
        pytest.skip("на стенде нет админской учётки")
    deal = pixel_deal
    tag = ("https://wcm.weborama-tech.ru/fcgi-bin/dispatch.fcgi?"
           "a.A=im&a.si=9796&a.ra=[RANDOM]")
    db.execute(text("UPDATE sales_deals SET weborama_pixel = false,"
                    " weborama_pixel_mode = 'own', weborama_pixel_tag = NULL"
                    " WHERE id = :d"), {"d": deal.id})
    db.expire_all()
    sd.save_deal_campaign_extra(
        deal.id, sd.CampaignExtraIn(weborama_pixel=True, mode="external", tag=tag),
        db=db, current_user=user)
    assert pixel_setup(db, deal.id)["tag"] == tag

    sd.save_deal_campaign_extra(
        deal.id, sd.CampaignExtraIn(weborama_pixel=True, mode="own"),
        db=db, current_user=user)
    got = pixel_setup(db, deal.id)
    assert got["mode"] == "own" and got["tag"] is None
