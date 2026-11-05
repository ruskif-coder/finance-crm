"""Отчёт «Площадки × РК» (владелец 05.11.2026): проваливающиеся площадки поперёк идущих РК.

Что ловят тесты:
  · темп считается от ПРОГНОЗА к плану, а не от факта к плану — иначе молодая РК всегда «проваливается»;
  · вердикт «системный» требует повторения в нескольких РК, одна плохая РК — «точечно»;
  · строки без плана в вердикт не идут (нет плана — нечего недокручивать);
  · Excel: лист «Сводка» и лист «Разбивка» в колонках примера трафиков.
"""
import io

from app.traffic import platform_report as PR

RK = {"campaign_id": 1, "deal_code": "AAA111", "deal_title": "Сделка", "traffic": "Иванов", "product": "Баннер",
      "date_end": "2026-11-30"}


def _row(pid=10, plan=1000, fact=300, forecast=500, under=500, share=0.1, status="запущен"):
    return {"id": pid, "publisher_id": pid, "domain": f"p{pid}.ru", "publisher": f"P{pid}", "share": share,
            "plan_show": plan, "fact_shows": fact, "forecast": forecast, "under": under, "status": status}


def test_pace_is_forecast_over_plan_not_fact_over_plan():
    c = PR.cell(rk=RK, row=_row(plan=1000, fact=300, forecast=950), in_dsp=True, wr=None, wr_limit=10, days_left=10)
    assert c["pace_pct"] == 95.0 and c["done_pct"] == 30.0
    assert c["tone"] == "ok"


def test_tone_thresholds():
    assert PR.tone(59.9) == "fail" and PR.tone(60) == "under" and PR.tone(89.9) == "under" and PR.tone(90) == "ok"
    assert PR.tone(None) is None


def test_need_per_day_and_wr_mismatch():
    c = PR.cell(rk=RK, row=_row(plan=1000, fact=400, forecast=600), in_dsp=True, wr=360, wr_limit=10, days_left=6)
    assert c["need_per_day"] == 100                      # (1000 − 400) / 6
    assert c["wr_pct"] == 10.0                           # (400 − 360) / 400 — знаменатель наш
    assert c["in_dsp"] == "DSP"


def test_cell_without_plan_is_not_rated():
    c = PR.cell(rk=RK, row=_row(plan=0, fact=0, forecast=0, under=0), in_dsp=False, wr=None, wr_limit=10, days_left=5)
    assert c["tone"] is None and c["in_dsp"] == "вне DSP"


def _cells(paces):
    return [{"tone": PR.tone(p), "pace_pct": p, "under": 100 if p is not None and p < 90 else 0, "wr_level": None}
            for p in paces]


def test_one_bad_campaign_is_spot_not_systemic():
    assert PR.verdict(_cells([40, 100, 98]))["code"] == "spot"


def test_repeated_failure_is_systemic_fail():
    assert PR.verdict(_cells([30, 45, 95]))["code"] == "system_fail"


def test_repeated_undershoot_above_fail_line_is_systemic_under():
    assert PR.verdict(_cells([70, 80, 99]))["code"] == "system_under"


def test_single_campaign_is_never_systemic():
    assert PR.verdict(_cells([10]))["code"] == "spot"


def test_unrated_cells_do_not_dilute_the_verdict():
    assert PR.verdict(_cells([30, 45, None, None, None]))["code"] == "system_fail"
    assert PR.verdict(_cells([None]))["code"] == "no_data"


def test_summary_groups_by_platform_and_puts_systemic_first():
    a = [PR.cell(rk={**RK, "campaign_id": i, "deal_code": f"RK{i}"}, row=_row(pid=1, forecast=f), in_dsp=True,
                 wr=None, wr_limit=10, days_left=5) for i, f in ((1, 300), (2, 400))]
    b = [PR.cell(rk={**RK, "campaign_id": 3, "deal_code": "RK3"}, row=_row(pid=2, forecast=1000, under=0), in_dsp=True,
                 wr=None, wr_limit=10, days_left=5)]
    s = PR.summarize(a + b)
    assert [x["domain"] for x in s] == ["p1.ru", "p2.ru"]
    assert s[0]["rk_count"] == 2 and s[0]["bad_count"] == 2 and s[0]["verdict"]["code"] == "system_fail"
    assert s[0]["under"] == 1000 and s[1]["verdict"]["code"] == "ok"


def test_xlsx_has_summary_and_breakdown_in_the_example_columns():
    from openpyxl import load_workbook
    cells = [PR.cell(rk=RK, row=_row(), in_dsp=True, wr=290, wr_limit=10, days_left=5)]
    wb = load_workbook(io.BytesIO(PR.to_xlsx(PR.summarize(cells), cells, "05.11.2026")))
    assert wb.sheetnames == ["Сводка", "Разбивка"]
    head = [c.value for c in wb["Разбивка"][3]]
    for col in ("Название РК", "Площадка", "Код", "Доля", "План", "Факт", "% плана", "Weborama", "Расхождения WR", "Нужно в день"):
        assert col in head, col
    assert wb["Разбивка"].cell(row=4, column=head.index("Площадка") + 1).value == "p10.ru"


def test_day_goal_is_the_rk_day_plan_rule_applied_to_the_placement():
    # то же правило, что `day_plan.past_goals`: (план − факт до дня) ÷ дни до конца, считая этот
    assert PR.day_goal(1000, 400, 6) == 100
    assert PR.day_goal(1000, 1200, 3) == 0           # перекрут — ноль, не минус
    assert PR.day_goal(1000, 0, 0) is None            # флайт кончился — суточного плана нет


def test_cell_carries_day_plan_and_fact_with_their_own_tone():
    c = PR.cell(rk=RK, row=_row(plan=1000, fact=450, forecast=950), in_dsp=True, wr=None, wr_limit=10, days_left=6,
                day={"before": 400, "on_day": 50, "days": 6})
    assert c["day_plan"] == 100 and c["day_fact"] == 50 and c["day_pct"] == 50.0
    assert c["day_tone"] == "fail" and c["tone"] == "ok"


def test_xlsx_breakdown_has_day_columns():
    from openpyxl import load_workbook
    cells = [PR.cell(rk=RK, row=_row(), in_dsp=True, wr=None, wr_limit=10, days_left=5,
                     day={"before": 200, "on_day": 100, "days": 5})]
    head = [c.value for c in load_workbook(io.BytesIO(PR.to_xlsx(PR.summarize(cells), cells, "05.11.2026")))["Разбивка"][3]]
    for col in ("План дня", "Факт дня", "% плана дня"):
        assert col in head, col


def test_summary_counts_campaigns_below_the_day_plan():
    mk = lambda i, on_day: PR.cell(rk={**RK, "campaign_id": i, "deal_code": f"RK{i}"}, row=_row(pid=1, forecast=1000, under=0),
                                    in_dsp=True, wr=None, wr_limit=10, days_left=5, day={"before": 500, "on_day": on_day, "days": 5})
    s = PR.summarize([mk(1, 20), mk(2, 100), mk(3, 95)])[0]       # план дня 100: 20 % — провал, 100 и 95 — норма
    assert (s["day_bad"], s["day_rated"]) == (1, 3)


def test_summary_has_publisher_code_and_median_day_for_the_design_contract():
    # Контракт хендоффа 05.11.2026 (`sampleData.js`): у площадки код и медиана суток
    mk = lambda i, on_day: PR.cell(rk={**RK, "campaign_id": i}, row={**_row(pid=1), "code": "MIN"}, in_dsp=True, wr=None,
                                    wr_limit=10, days_left=5, day={"before": 500, "on_day": on_day, "days": 5})
    s = PR.summarize([mk(1, 20), mk(2, 100), mk(3, 60)])[0]
    assert s["code"] == "MIN" and s["median_day"] == 60.0


def test_wr_over_threshold_is_any_excess_over_the_deal_limit_not_only_double():
    # Порог сделки 10 %: 15 % — уже «за порогом» (уровень warn), а не только больше 20 % (bad). Как на карточке сделки.
    mk = lambda i, wr: PR.cell(rk={**RK, "campaign_id": i}, row=_row(pid=1, fact=1000), in_dsp=True, wr=wr,
                                wr_limit=10, days_left=5)
    s = PR.summarize([mk(1, 850), mk(2, 850), mk(3, 990)])[0]      # 15 %, 15 %, 1 %
    assert s["wr_bad"] == 2 and s["wr_verdict"] == "системно"
