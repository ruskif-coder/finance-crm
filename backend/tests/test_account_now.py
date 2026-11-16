# -*- coding: utf-8 -*-
"""Блок «Сейчас» «Моих сделок» (v5): шаги «Сборки» и показатели кампании. Чистые функции — без базы; плюс прогон по
живым сделкам стенда на каждой стадии (не падает, форма ответа та, что ждёт экран).

Поломки: «Сборка» зовёт аккаунта, когда креативы уже есть; следующий шаг светится «идёт», пока предыдущий не закрыт;
расхлоп падает на сделке без РК."""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.sales import account_now as AN


def test_assembly_waits_for_creatives_first():
    rows = {r["key"]: r for r in AN.assembly(0, 0, 0, 6, 0, False)}
    assert rows["creatives"]["state"] == "warn" and rows["creatives"]["who"] == "аккаунт"
    assert all(rows[k]["state"] == "wait" for k in ("check", "sites", "erid", "rk"))


def test_assembly_moves_step_by_step():
    rows = {r["key"]: r for r in AN.assembly(2, 2, 3, 6, 0, False)}
    assert (rows["creatives"]["state"], rows["check"]["state"], rows["sites"]["state"]) == ("ok", "ok", "go")
    assert rows["sites"]["text"] == "согласовали 3 из 6" and rows["erid"]["state"] == "wait"
    done = {r["key"]: r for r in AN.assembly(2, 2, 6, 6, 2, True)}
    assert all(done[k]["state"] == "ok" for k in done)


def test_no_pairs_yet_is_not_counted_as_zero_of_zero():
    """Поломка: «согласовали 0 из 0», когда баннер площадкам ещё не уходил (ZQ7QS7)."""
    rows = {r["key"]: r for r in AN.assembly(3, 3, 0, 0, 0, False)}
    assert (rows["sites"]["state"], rows["sites"]["text"]) == ("go", "баннер ещё не ушёл площадкам")


def test_account_contour_assembly_has_no_steps():
    """Контур аккаунта (OLV, Альфарм-Таргет, Polza): по матрице требований шагов сборки нет — запуск во внешней системе (14.11.2026)."""
    assert AN.for_flow(AN.assembly(1, 0, 0, 3, 0, False), True) == []
    assert len(AN.for_flow(AN.assembly(1, 0, 0, 3, 0, False), False)) == 5


def test_external_launch_is_decided_by_the_matrix_in_one_place():
    """Владелец 14.11.2026: что требуется на сборке — по матрице учёта по услугам. Поломка: строка, расхлоп и кнопка решали это
    каждый по-своему (строка — по матрице, расхлоп и «Подтвердить запуск» — по циклу), и включённые в матрице креативы у OLV
    показались бы в строке, но не в расхлопе. Одна функция `account_turn.external_launch` на все три места."""
    from app.sales import account_turn as AT
    from app.sales import queue_state as qs
    assert AT.external_launch("контур аккаунта", {"payer_set", "final_contract"}) is True
    assert AT.external_launch("контур аккаунта", {"payer_set", "creatives_accepted"}) is False, "креативы включены в матрице — сборка есть"
    assert AT.external_launch("полный цикл", set()) is False
    assert AT.external_launch("приоритезация", set()) is False
    row = qs.row_state(qs.Bundle(slot="prep", applies={"payer_set"}, flow="контур аккаунта"))
    assert row["external_launch"] is True
    row = qs.row_state(qs.Bundle(slot="prep", applies={"creatives_accepted"}, flow="контур аккаунта"))
    assert row["external_launch"] is False and row["action"]["label"] == "Креативы"


def test_prio_assembly_follows_placements():
    rows = {r["key"]: r for r in AN.prio_assembly([("черновик", False)] * 5)}
    assert rows["sent"]["state"] == "warn" and rows["approved"]["text"] == "после отправки"
    rows = {r["key"]: r for r in AN.prio_assembly([("у площадки", False)] * 3 + [("согласовано", True), ("идёт", True)])}
    assert (rows["sent"]["state"], rows["approved"]["text"], rows["live"]["text"]) == ("ok", "2 из 5", "1 из 5")


def test_open_documents_are_listed_and_closed_ones_hidden():
    """Поломка: в «Сборке» не видно, что запуск держит незакрытый документ (договор, плательщик), или видно закрытое."""
    lines = [("payer_set", "Плательщик определён", "ok", "", "#head"),
             ("final_contract", "Доходный договор выбран", "not_yet", "не выбран", "#ord"),
             ("ord_initial_contract", "Изначальный договор в цепочке ОРД", "n/a", "самореклама", "#ord"),
             ("creatives_accepted", "Комплект прошёл первичную проверку трафика", "not_yet", "0 из 1", "#creatives")]
    rows = AN.doc_rows(lines)
    assert [(r["key"], r["text"], r["state"], r["link"]) for r in rows] == [("final_contract", "не выбран", "warn", "#ord")]


def test_launch_extras_show_pair_ready_and_pixel():
    """Поломка: «РК заведена» горит, а ни одна площадка не собрана к запуску — и этого не видно."""
    lines = [("one_pair_ready", "Хотя бы одна площадка собрана к запуску", "not_yet", "ни одной", "/traffic/dashboard"),
             ("weborama_pixel", "Пиксель Weborama получен по площадкам", "ok", "3 из 3", "/traffic/dashboard"),
             ("campaign_ready", "РК заведена", "ok", "", "")]
    rows = {r["key"]: r for r in AN.launch_extras(lines)}
    assert set(rows) == {"pair", "pixel"}
    assert (rows["pair"]["state"], rows["pair"]["who"], rows["pixel"]["state"]) == ("go", "трафик", "ok")


def test_assembly_head_names_first_open_item_and_where_to_continue():
    docs = AN.doc_rows([("final_contract", "Доходный договор выбран", "not_yet", "не выбран", "#ord")])
    rows = AN.assembly(1, 1, 1, 3, 0, False)
    assert AN.assembly_head(docs, rows) == {"text": "Доходный договор выбран: не выбран", "href": "#sec-ord"}
    assert AN.assembly_head([], rows) == {"text": "Согласование баннера: согласовали 1 из 3", "href": "#sec-creatives"}
    assert AN.assembly_head([], AN.assembly(0, 0, 0, 3, 0, False))["text"] == "Креативы: не загружены — запуск стоит"
    assert AN.assembly_head([], AN.assembly(2, 2, 3, 3, 2, True)) == {"text": "собрано — можно в размещение", "href": "#sec-creatives"}


def test_diff_cell_reads_like_the_mockup():
    """Поломка: «Расхождение 0 %», когда Weborama ещё не мерила, — ноль выдаётся за сверенное."""
    assert AN.diff_cell(None, 0, 0, "Weborama площадки не мерила") == {"v": "—", "s": "Weborama площадки не мерила", "bad": False}
    assert AN.diff_cell(3.2, 0, 5, "") == {"v": "+3,2 %", "s": "в пределах допустимого", "bad": False}
    assert AN.diff_cell(-14.5, 2, 5, "") == {"v": "−14,5 %", "s": "по 2 из 5 площадок", "bad": True}


def test_assembly_chips_are_ord_creatives_pixel_ds():
    """Сборка в расхлопе — четыре плашки (владелец 13.11.2026). Поломка: ОРД «сошлась» при невыпущенном ЕРИД; пиксель без
    решения выглядит как «не нужен»; черновик ДС — как выпущенный."""
    lines = [("payer_set", "Плательщик", "ok", "", "#head"), ("final_contract", "Доходный договор", "ok", "", "#ord"),
             ("ord_initial_contract", "Изначальный договор", "n/a", "самореклама", "#ord"),
             ("erid_issued", "ЕРИД выпущен", "not_yet", "0 из 3", "#ord")]
    lines = lines + [("creatives_accepted", "Комплект прошёл проверку", "not_yet", "2 из 3", "#creatives")]
    ch = {c["key"]: c for c in AN.assembly_chips(lines, (3, 3, 2, 6), "полный цикл", (False, False), [])}
    assert list(ch) == ["ord", "creatives", "pixel", "ds"]
    assert (ch["ord"]["value"], ch["ord"]["tone"]) == ("2 из 3", "warn")
    assert (ch["creatives"]["value"], ch["creatives"]["tone"]) == ("площадки 2 из 6", "warn")
    assert (ch["pixel"]["value"], ch["pixel"]["tone"]) == ("решение не принято", "warn")
    assert (ch["ds"]["value"], ch["ds"]["tone"]) == ("не выпущен", "off")

    ok = [(k, k, "ok", "", "#ord") for k in ("payer_set", "final_contract", "ord_initial_contract", "erid_issued", "creatives_accepted")]
    ok.append(("weborama_pixel", "Пиксель", "ok", "6 из 6", ""))
    ds = [{"no": 13, "number": "Дополнительное соглашение № 13", "is_draft": False, "sign_state": "подписан"}]
    ch = {c["key"]: c for c in AN.assembly_chips(ok, (3, 3, 6, 6), "полный цикл", (True, True), ds)}
    assert [ch[k]["tone"] for k in ("ord", "creatives", "pixel", "ds")] == ["ok"] * 4
    assert (ch["ord"]["value"], ch["creatives"]["value"], ch["pixel"]["value"], ch["ds"]["value"]) ==         ("цепочка сошлась", "готовы", "получен · 6 из 6", "№ 13 · подписан")
    ch = {c["key"]: c for c in AN.assembly_chips([("creatives_accepted", "Комплект", "not_yet", "комплектов нет", "")], (0, 0, 0, 0), "полный цикл", (False, True),
                                                 [{"no": None, "number": None, "is_draft": True, "sign_state": None}])}
    assert (ch["creatives"]["value"], ch["pixel"]["value"], ch["pixel"]["tone"], ch["ds"]["value"], ch["ds"]["tone"]) ==         ("не загружены", "не нужен", "off", "черновик", "warn")


def test_own_run_shows_plan_and_period_without_dsp():
    """Сделки, которые аккаунт запускает сам (OLV, Polza): РК в нашей DSP нет. Поломка: расхлоп пишет «статистики нет» и
    больше ничего — не видно ни плана, ни сколько осталось, ни что факт вносит аккаунт."""
    r = AN.own_run(500000, 225000.0, date(2026, 11, 1), date(2026, 11, 30), date(2026, 11, 13))
    assert (r["plan"], r["plan_sum"], r["day"], r["days"], r["left"], r["over"]) == (500000, 225000.0, 13, 30, 17, False)
    assert r["elapsed_pct"] == 43.3
    done = AN.own_run(None, None, date(2026, 10, 1), date(2026, 10, 31), date(2026, 11, 13))
    assert (done["day"], done["left"], done["over"], done["elapsed_pct"]) == (31, 0, True, 100.0)


def test_assembly_chips_follow_the_requirements_matrix():
    """OLV и Альфарм-Таргет (контур аккаунта): креативы, согласование и ЕРИД по матрице требований — только у полного цикла, пиксель —
    только где заказан. Поломка (14.11.2026): у OLV «площадки 0 из 3» и «пиксель: решение не принято», хотя ничего не требуется."""
    lines = [("payer_set", "Плательщик", "ok", "", "#head"), ("final_contract", "Доходный договор", "ok", "", "#ord")]
    ch = AN.assembly_chips(lines, (1, 0, 0, 3), "контур аккаунта", (False, False), [])
    assert [c["key"] for c in ch] == ["ord"]
    assert AN.assembly_head([], []) == {"text": "сборка не требуется — запуск кнопкой «Запустить» в карточке", "href": "#sec-head"}


@pytest.mark.parametrize("stage", ["МП Отправлено", "Бронь", "Готовятся к старту", "В размещении", "Итоговая сверка"])
def test_now_on_a_live_deal_of_each_stage(stage):
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    try:
        from app.final_recon import flow as F
        ids = db.execute(text("""SELECT d.id FROM sales_deals d JOIN sales_stages s ON s.id = d.our_stage_id
                                  WHERE s.name = :n ORDER BY d.id DESC LIMIT 100"""), {"n": stage}).scalars().all()
        # Сборка из пяти шагов — у полного цикла; у контура аккаунта её нет по решению 14.11.2026, а «последней» на стенде
        # бывает демо-сделка OLV/Polza — тогда тест краснел от данных, а не от кода.
        did = next((i for i in ids if F.of_deal(db, db.get(SalesDeal, i)) == F.FULL), ids[0] if ids else None)             if stage == "Готовятся к старту" else (ids[0] if ids else None)
        if did is None:
            pytest.skip(f"на стенде нет сделки на «{stage}»")
        out = AN.now(db, db.get(SalesDeal, did), date(2026, 11, 13))
        assert out["steps"] and 0 <= out["at"] < len(out["steps"])
        if stage == "Готовятся к старту":
            keys = [r["key"] for r in out["assembly"]]
            assert [k for k in keys if k in ("creatives", "check", "sites", "erid", "rk")] == ["creatives", "check", "sites", "erid", "rk"]
            assert set(keys) <= {"creatives", "check", "sites", "erid", "pixel", "rk", "pair"}
            assert out["head"]["text"] and out["head"]["href"] and isinstance(out["docs"], list)
        if stage == "Итоговая сверка":
            assert "recon" not in out   # сверку показывает блок карточки, свой расчёт не нужен
    finally:
        db.rollback()
        db.close()


def test_prio_head_is_not_done_while_sites_have_not_agreed():
    """16.11.2026: запрос ушёл всем, никто не согласовал — шапка сборки звала это «собрано — можно в размещение»
    (пункты «ждут» пропускались). Первый незакрытый пункт любого состояния, кроме «ok»."""
    rows = AN.prio_assembly([("у площадки", False)] * 5)
    assert AN.assembly_head([], rows) == {"text": "Согласование: 0 из 5", "href": "#sec-prio"}
