# -*- coding: utf-8 -*-
"""Отчёт клиенту по РК (владелец 05.10.2026): суммы блоков сходятся, Weborama в отчёт не
попадает, показы в модели — реальные; ручка закрыта правами и отдаёт Excel."""
import io
from datetime import date

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ad import client_report as CR
from app.database import SessionLocal
from app.main import app
from app.routers.auth import get_current_user


def _camp_with_fact(db):
    row = db.execute(text("""
        SELECT c.id, c.deal_id FROM ad_campaign c
         WHERE EXISTS (SELECT 1 FROM ad_campaign_stat s WHERE s.campaign_id = c.id
                         AND s.source IN ('dsp', 'ms', 'adfox') AND s.shows > 0)
         ORDER BY c.id DESC LIMIT 1""")).first()
    if row is None:
        pytest.skip("на стенде нет РК с боевым фактом")
    return row


def test_blocks_add_up_and_weborama_is_out():
    db = SessionLocal()
    try:
        cid, _ = _camp_with_fact(db)
        rep = CR.build(db, cid)
        own = db.execute(text("""SELECT coalesce(sum(shows), 0) FROM ad_campaign_stat
            WHERE campaign_id = :c AND source IN ('dsp', 'ms', 'adfox')
              AND date BETWEEN :a AND :b"""),
            {"c": cid, "a": rep.head["period_from"], "b": rep.head["period_to"]}).scalar()
        assert rep.totals["shows"] == own, "в отчёте не только наш боевой факт"
        assert sum(r["shows"] for r in rep.by_placement) == rep.totals["shows"]
        assert sum(r["shows"] for r in rep.by_day) == rep.totals["shows"]
        assert sum(v[0] for d in rep.site_days.values() for v in d.values()) == rep.totals["shows"]
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _keep_coefs():
    """Коэффициенты, зафиксированные тестом, убираются: иначе тест занял бы дни стенда
    значениями по умолчанию раньше настроек владельца (05.10.2026)."""
    db = SessionLocal()
    start = db.execute(text("SELECT coalesce(max(id), 0) FROM report_daily_coef")).scalar()
    db.close()
    yield
    db = SessionLocal()
    db.execute(text("DELETE FROM report_daily_coef WHERE id > :s"), {"s": start})
    db.commit()
    db.close()


def test_model_keeps_real_shows():
    db = SessionLocal()
    try:
        cid, _ = _camp_with_fact(db)
        f, m = CR.build(db, cid), CR.build(db, cid, model=True)
        assert m.totals["shows"] == f.totals["shows"]
        assert all(r["uniques"] is not None for r in m.by_placement)
        # Уники и в отчёте факта — модель SIMB ID (DSP их не отдаёт; владелец 24.10.2026)
        assert all(r["uniques"] is not None for r in f.by_placement)
        assert [r["uniques"] for r in f.by_placement] == [r["uniques"] for r in m.by_placement]
        assert all(len(v) == 4 for v in f.pair_days.values())   # показы, клики, уники, охват; без DSP-сырья пар может не быть
    finally:
        db.close()


class _Role:
    def __init__(self, key):
        self.key = key


class _User:
    def __init__(self, key):
        self.id, self.name, self.email = None, "t", "t@t"
        self.role = _Role(key)
        self.role_id = -1                # роли нет — ни одного права
        self.consent_accepted_at = True


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_admin_downloads_excel_without_model_sheets(client):
    """Вкладки «(модель)» из выгрузки убраны (владелец 04.11.2026) — клиенту уходит только факт."""
    db = SessionLocal()
    _, deal_id = _camp_with_fact(db)
    db.close()
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    r = client.get(f"/api/client-report/deal/{deal_id}.xlsx")
    assert r.status_code == 200, r.text[:200]
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Отчёт", "По неделям"]
    # Имя — по какой день отчёт (аккаунты 16.11.2026): последний день данных, не дата выгрузки
    from urllib.parse import quote
    db = SessionLocal()
    cid = db.execute(text("SELECT id FROM ad_campaign WHERE deal_id = :d ORDER BY id DESC LIMIT 1"), {"d": deal_id}).scalar()
    last = CR.last_data_day(db, cid)
    db.close()
    assert quote(f"_по_{last:%d.%m.%Y}.xlsx") in r.headers["content-disposition"]


def test_no_campaign_and_bad_period(client):
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    assert client.get("/api/client-report/deal/999999999.xlsx").status_code == 404
    db = SessionLocal()
    _, deal_id = _camp_with_fact(db)
    db.close()
    r = client.get(f"/api/client-report/deal/{deal_id}.xlsx?date_from=2026-10-05&date_to=2026-10-01")
    assert r.status_code == 400
    assert client.get(f"/api/client-report/deal/{deal_id}.xlsx?date_from=05.10").status_code == 400


def test_role_without_dashboards_is_refused(client):
    app.dependency_overrides[get_current_user] = lambda: _User("no_such_role")
    assert client.get("/api/client-report/deal/1.xlsx").status_code == 403


def test_period_respected():
    db = SessionLocal()
    try:
        cid, _ = _camp_with_fact(db)
        full = CR.build(db, cid)
        d = full.by_day[0]["label"]
        one = CR.build(db, cid, d, d)
        assert [r["label"] for r in one.by_day] == [d]
        assert one.totals["shows"] == full.by_day[0]["shows"]
        assert isinstance(d, date)
    finally:
        db.close()


def test_no_stats_no_report(client):
    """Отчёт — только при статистике хоть за один день (владелец 05.10.2026)."""
    db = SessionLocal()
    row = db.execute(text("""
        SELECT c.deal_id FROM ad_campaign c WHERE NOT EXISTS (
            SELECT 1 FROM ad_campaign_stat s WHERE s.campaign_id = c.id
               AND s.source IN ('dsp', 'ms', 'adfox') AND s.shows > 0) LIMIT 1""")).first()
    db.close()
    if row is None:
        pytest.skip("на стенде нет РК без статистики")
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    assert client.get(f"/api/client-report/deal/{row[0]}.xlsx").status_code == 409
    db = SessionLocal()
    assert CR.deal_report_ready(db, row[0]) is False
    db.close()


# ── ревью 05.10.2026: границы периода ───────────────────────────────────────
D = date


def test_period_without_flight_dates_uses_data():
    """Нет даты старта/конца РК — период и колонки дней от первого до последнего дня данных."""
    p = CR.period_of(start=None, end=None, first=D(2026, 10, 2), last=D(2026, 10, 9),
                     date_from=None, date_to=None)
    assert (p["from"], p["to"], p["days_to"]) == (D(2026, 10, 2), D(2026, 10, 9), D(2026, 10, 9))


def test_days_cover_data_after_flight_end():
    """Докрутка после конца флайта не выпадает из колонок дней."""
    p = CR.period_of(start=D(2026, 10, 1), end=D(2026, 10, 31), first=D(2026, 10, 1),
                     last=D(2026, 11, 2), date_from=None, date_to=None)
    assert p["days_to"] == D(2026, 11, 2) and p["to"] == D(2026, 11, 2)


def test_default_days_run_to_flight_end():
    p = CR.period_of(start=D(2026, 10, 1), end=D(2026, 10, 31), first=D(2026, 10, 1),
                     last=D(2026, 10, 4), date_from=None, date_to=None)
    assert (p["to"], p["days_to"]) == (D(2026, 10, 4), D(2026, 10, 31))


def test_custom_period_is_kept():
    p = CR.period_of(start=D(2026, 10, 1), end=D(2026, 10, 31), first=D(2026, 10, 1),
                     last=D(2026, 10, 20), date_from=D(2026, 10, 5), date_to=D(2026, 10, 11))
    assert (p["from"], p["to"], p["days_to"]) == (D(2026, 10, 5), D(2026, 10, 11), D(2026, 10, 11))


def test_period_after_data_is_refused(client):
    db = SessionLocal()
    _, deal_id = _camp_with_fact(db)
    db.close()
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    r = client.get(f"/api/client-report/deal/{deal_id}.xlsx?date_from=2030-01-01")
    assert r.status_code == 409 and "период" in r.json()["detail"]


def test_days_are_full_calendar_month_for_short_campaign():
    """Владелец 05.10.2026: РК на 15 дней «поехала» — шаблон рассчитан на полный месяц.
    Колонки дней — весь календарный месяц (горизонтально; вертикаль 24.10 владелец вернул); дни
    вне РК пустые, а не нули. Уники — и на листе факта (модель SIMB ID, 24.10.2026)."""
    from app.ad import client_report_xlsx as X
    head = {"period_from": date(2026, 10, 15), "period_to": date(2026, 10, 18),
            "days_to": date(2026, 10, 29), "last_data": date(2026, 10, 18),
            "date_start": date(2026, 10, 15), "date_end": date(2026, 10, 29),
            "advertiser": "А", "code": "TEST01"}
    tot = {"shows": 40, "clicks": 1, "ctr": 2.5, "plan": None, "done_pct": None}
    pl = [{"label": "site.ru", "shows": 40, "clicks": 1, "uniques": 20}]
    days = [{"label": date(2026, 10, d), "shows": 10, "clicks": 0, "uniques": 5} for d in (15, 16, 17, 18)]
    rep = CR.Report(head=head, totals=tot, by_placement=pl, by_day=days)
    got = X._days_of(rep)
    assert got[0] == date(2026, 10, 1) and got[-1] == date(2026, 10, 31) and len(got) == 31
    wb = openpyxl.load_workbook(io.BytesIO(X.to_xlsx(rep, rep)))
    ws = wb.worksheets[0]
    at = next(c for row in ws.iter_rows() for c in row if c.value == "01.10")
    labels = [ws.cell(at.row, at.column + i).value for i in range(31)]
    assert labels[0] == "01.10" and labels[30] == "31.10", "дни — колонками"
    vals = {labels[i]: ws.cell(at.row + 1, at.column + i).value for i in range(31)}
    uniq = {labels[i]: ws.cell(at.row + 3, at.column + i).value for i in range(31)}
    assert ws.cell(at.row + 3, at.column - 1).value == "Уники"
    assert vals["01.10"] is None and vals["14.10"] is None, "до старта — пусто, не ноль"
    assert vals["15.10"] == 10 and vals["31.10"] is None
    assert uniq["15.10"] == 5 and uniq["19.10"] is None


@pytest.fixture
def grouped():
    """РК с DSP-сырьём по креативам: первому креативу РК временно ставится группа, после — снимается."""
    from app.dsp.db import DspSessionLocal
    if not DspSessionLocal:
        pytest.skip("нет аналитической базы DSP")
    db, ddb = SessionLocal(), DspSessionLocal()
    row = db.execute(text("""
        SELECT c.id, cr.root_set_id FROM ad_campaign c JOIN ad_campaign_creative cr ON cr.campaign_id = c.id
         WHERE cr.root_set_id IS NOT NULL AND cr.ms_creative_xxhash IS NOT NULL
           AND EXISTS (SELECT 1 FROM ad_campaign_stat s WHERE s.campaign_id = c.id AND s.source = 'dsp' AND s.shows > 0)
         ORDER BY c.id DESC LIMIT 1""")).first()
    if row is None:
        db.close(); ddb.close()
        pytest.skip("на стенде нет РК с креативами в DSP")
    cid, set_id = row
    was = db.execute(text("SELECT report_group FROM launch_prep_creative_set WHERE id = :s"), {"s": set_id}).scalar()
    db.execute(text("UPDATE launch_prep_creative_set SET report_group = 'ТЕСТ группа' WHERE id = :s"), {"s": set_id})
    db.commit()
    yield db, ddb, cid, set_id
    db.rollback()
    db.execute(text("UPDATE launch_prep_creative_set SET report_group = :g WHERE id = :s"), {"g": was, "s": set_id})
    db.commit()
    db.close(); ddb.close()


def test_group_report_counts_only_its_creatives(grouped):
    """Отчёт по группе (владелец 24.10.2026): только креативы группы — показы = сумма их пар."""
    db, ddb, cid, set_id = grouped
    full = CR.build(db, cid, dsp_db=ddb)
    g = CR.build(db, cid, dsp_db=ddb, group="ТЕСТ группа")
    assert g.head["group"] == "ТЕСТ группа"
    assert [x["label"] for x in full.groups] == ["Группа «ТЕСТ группа»"]
    blk = full.groups[0]
    assert g.totals["shows"] == sum(r["shows"] for r in blk["by_placement"]) > 0
    assert sum(r["shows"] for r in g.by_day) == g.totals["shows"]
    assert g.totals["shows"] <= full.totals["shows"]
    assert all(c["label"].startswith("Креатив №") for c in g.creatives)
    assert g.totals["plan"] is None, "план РК к группе не относится"


def test_unknown_group_is_refused(client, grouped):
    db, _, cid, _ = grouped
    deal_id = db.execute(text("SELECT deal_id FROM ad_campaign WHERE id = :c"), {"c": cid}).scalar()
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    assert client.get(f"/api/client-report/deal/{deal_id}.xlsx?group=нет такой").status_code == 404
    r = client.get(f"/api/client-report/deal/{deal_id}.xlsx?group=ТЕСТ группа")
    assert r.status_code == 200, r.text[:200]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert any("ТЕСТ группа" in str(c.value) for c in wb["Отчёт"]["A"] + wb["Отчёт"]["B"] + tuple(
        x for row in wb["Отчёт"].iter_rows(max_row=10) for x in row))


def test_weeks_sheet_has_estimated_reach_row():
    """Владелец 16.11.2026: охват не колонкой у площадок, а строкой «Расчётный охват» над неделями; у недели — показы, клики,
    ctr. Охват недели = сумма охватов площадок-дней (4-е число `site_days`), «ИТОГО» — сумма недель. Уронит: снова колонка
    охвата / охват из уников, а не из охвата / «ИТОГО» не сумма недель."""
    from app.ad import client_report_xlsx as X
    # 2026-10-18 — воскресенье: неделя 1 = 15–18.10, неделя 2 = 19–20.10
    head = {"period_from": date(2026, 10, 15), "period_to": date(2026, 10, 20),
            "days_to": date(2026, 10, 20), "last_data": date(2026, 10, 20),
            "date_start": date(2026, 10, 15), "date_end": date(2026, 10, 20),
            "advertiser": "А", "code": "TEST02"}
    sd = {"a.ru": {date(2026, 10, d): [100, 2, 40, 30] for d in (15, 16, 17, 18, 19, 20)},
          "b.ru": {date(2026, 10, 19): [50, 1, 30.4, 20.6]}}
    tot = {"shows": 650, "clicks": 13, "ctr": 2.0, "plan": None, "done_pct": None}
    rep = CR.Report(head=head, totals=tot, by_placement=[], by_day=[], site_days=sd)
    ws = X.render(rep)["По неделям"]
    hdr = next(c for row in ws.iter_rows() for c in row if c.value == "показы")
    subs = [ws.cell(hdr.row, hdr.column + i).value for i in range(9)]
    assert subs == ["показы", "клики", "ctr"] * 3, "колонки охвата у недели нет"
    reach_row = hdr.row - 2
    assert ws.cell(reach_row, 2).value == "Охват"
    c0 = hdr.column
    assert [ws.cell(reach_row, c0 + 3 * k).value for k in range(3)] == [120, 81, 201]   # 4×30; 2×30+20,6; сумма недель
    row_a = next(r for r in range(hdr.row + 1, hdr.row + 5) if ws.cell(r, 2).value == "a.ru")
    assert [ws.cell(row_a, c0 + k).value for k in range(3)] == [400, 8, 0.02]


def test_day_reach_is_uniques_without_repeats_and_overlap():
    """Охват дня пары = уники × (1 − повторы) × (1 − пересечение): 1000 × 0,90 × 0,95 = 855."""
    from app.ad import report_coef as RC
    assert RC.reach(1000, 10, 5) == 855
    assert RC.derive(3700, {"freq": 3.7, "ctr_pct": 0.1, "repeat_pct": 10, "overlap_pct": 5})["reach"] == 855
    assert RC.reach(1000, None, None) == 1000, "дни без чисел охвата (до дозаполнения) — без поправок"

# ── имя файла (владелец 17.11.2026: за выбранные дни — «с … по …») ─────────────────────────────────────────────────

def test_file_name_for_chosen_days_names_both_ends():
    """Поломка: отчёт за 05–09.11 назван как отчёт со старта по 09.11 — по имени не отличить."""
    from app.routers.client_report import report_filename
    assert report_filename("S3MTU6", None, date(2026, 11, 5), date(2026, 11, 9), chosen_from=True) \
        == "Отчёт_РК_S3MTU6_с_05.11_по_09.11.2026.xlsx"


def test_file_name_for_whole_flight_is_unchanged():
    """Поломка: обычный «XLS» поменял имя — аккаунты ищут файлы по прежнему виду (16.11.2026)."""
    from app.routers.client_report import report_filename
    assert report_filename("S3MTU6", None, date(2026, 11, 1), date(2026, 11, 13), chosen_from=False) \
        == "Отчёт_РК_S3MTU6_по_13.11.2026.xlsx"
    assert report_filename("S3MTU6", "Весна", date(2026, 11, 5), date(2026, 11, 9), chosen_from=True) \
        == "Отчёт_РК_S3MTU6_Весна_с_05.11_по_09.11.2026.xlsx"


def test_reach_row_only_in_whole_rk_table():
    """Владелец 17.11.2026: «охват оставить только на отчёте по всей РК, убрать в разбивке по креативам/группам»; подпись —
    просто «Охват». Уронит: строка охвата снова над таблицами креативов и групп, или в выгрузке по одной группе."""
    from app.ad import client_report_xlsx as X
    head = {"period_from": date(2026, 10, 15), "period_to": date(2026, 10, 20),
            "days_to": date(2026, 10, 20), "last_data": date(2026, 10, 20),
            "date_start": date(2026, 10, 15), "date_end": date(2026, 10, 20), "advertiser": "А", "code": "TEST03"}
    sd = {"a.ru": {date(2026, 10, d): [100, 2, 40, 30] for d in (15, 16, 17)}}
    tot = {"shows": 300, "clicks": 6, "ctr": 2.0, "plan": None, "done_pct": None}
    part = {"by_placement": [], "by_day": [], "site_days": sd}
    parts = dict(groups=[{"label": "Группа «Весна»", **part}], creatives=[{"label": "Креатив 1", **part}])
    rep = CR.Report(head=head, totals=tot, by_placement=[], by_day=[], site_days=sd, **parts)
    ws = X.render(rep)["По неделям"]
    reach_rows = [c.row for row in ws.iter_rows() for c in row if c.value == "Охват"]
    assert len(reach_rows) == 1, "охват должен быть только у таблицы всей РК"
    title = next(c.row for row in ws.iter_rows() for c in row if str(c.value or "").startswith("Показы по неделям"))
    assert reach_rows[0] == title + 1
    rep_g = CR.Report(head={**head, "group": "Весна"}, totals=tot, by_placement=[], by_day=[], site_days=sd, **parts)
    ws_g = X.render(rep_g)["По неделям"]
    assert not [c for row in ws_g.iter_rows() for c in row if c.value == "Охват"], "выгрузка по группе — без охвата"


# ── шапка первого листа по длине месяца (правка владельца 17.11.2026, файл QZ9VNS) ────────────────────────────────

def _head_rep(d_to, d_from=date(2026, 11, 1)):
    head = {"period_from": d_from, "period_to": d_to, "days_to": d_to, "last_data": d_from + (d_to - d_from) // 4,
            "date_start": d_from, "date_end": d_to, "advertiser": "А", "brand": "Б", "agency": "Аг", "code": "TEST04"}
    tot = {"shows": 638874, "clicks": 5526, "ctr": 0.86, "plan": 1515152, "done_pct": 42.2}
    return CR.Report(head=head, totals=tot, by_placement=[], by_day=[])


@pytest.mark.parametrize("d_from, d_to, tc", [
    (date(2026, 11, 1), date(2026, 11, 30), "AN"),     # 30 дней — добиты до 31, «ИТОГО» на месте 31-дневного
    (date(2026, 12, 1), date(2026, 12, 31), "AN"),
    (date(2027, 2, 1), date(2027, 2, 28), "AN"),
    (date(2026, 11, 15), date(2026, 12, 10), "BR"),    # два месяца: 61 день — шапка идёт за таблицей
])
def test_header_right_edge_follows_total_column(d_from, d_to, tc):
    """Владелец 17.11.2026 поправил руками: шапка и «Результат за период» кончались на AO, а таблицы — на «ИТОГО», «было
    криво»; и «делай всегда 31 день». Уронит: шапка снова на постоянном AO, блок результата не в последних 4 колонках, или
    короткий месяц снова сдвигает «ИТОГО»."""
    from openpyxl.utils import column_index_from_string as ci, get_column_letter as L
    from app.ad import client_report_xlsx as X
    ws = X.render(_head_rep(d_to, d_from))["Отчёт"]
    t = ci(tc)
    merged = {str(m) for m in ws.merged_cells.ranges}
    assert f"M3:{tc}4" in merged and f"M5:{tc}5" in merged
    assert f"{L(t - 3)}9:{tc}10" in merged and ws.cell(9, t - 3).value == "РЕЗУЛЬТАТ ЗА ПЕРИОД"
    assert f"{L(t - 3)}11:{L(t - 1)}11" in merged and ws.cell(11, t - 3).value == "Показы"
    assert ws.cell(11, t).value == 638874 and ws.cell(14, t).value == 1515152
    assert f"E9:{L(t - 6)}10" in merged and f"E11:{L(t - 5)}16" in merged
    assert not [c for c in ws[11] if c.column > t and c.value not in (None, "")], "справа от «ИТОГО» в шапке ничего нет"
    assert round(ws.column_dimensions[tc].width, 2) == 17.44 and round(ws.column_dimensions[L(t + 1)].width, 2) == 3.11


def test_chart_ends_before_result_block():
    """Положение и ширина графика — ровно из правки владельца 17.11.2026 (файл QZ9VNS v6): колонка D, смещение 818 029,
    ширина 19 061 205 EMU у месяца (31 колонка дней). Уронит: своя формула ширины вместо правки."""
    from app.ad import client_report_xlsx as X
    ws = X.render(_head_rep(date(2026, 11, 30)))["Отчёт"]
    a = ws._charts[0].anchor
    assert (a._from.col, a._from.colOff, a._from.row, a._from.rowOff) == (3, 818029, 10, 54428)
    assert a.ext.width == 19061205
    # ширины колонок — из той же правки: узкие дни 8,33, «ИТОГО» 17,44, поле 3,11
    assert [round(ws.column_dimensions[c].width, 2) for c in ("I", "J", "M", "N", "AM", "AN", "AO")] ==         [8.33, 8.33, 8.33, 8.33, 8.33, 17.44, 3.11]
    wide = X.render(_head_rep(date(2026, 12, 10), date(2026, 11, 15)))["Отчёт"]._charts[0].anchor
    # и в самом файле: по одной записи на колонку, без пересекающихся диапазонов (иначе Excel берёт не ту ширину —
    # «ширина колонок не прописалась», владелец 17.11.2026); все дни I…AM — 8,33, E и F — 13
    import zipfile
    import xml.etree.ElementTree as ET
    raw = zipfile.ZipFile(io.BytesIO(X.to_xlsx(_head_rep(date(2026, 11, 30))))).read("xl/worksheets/sheet1.xml")
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cols = [(int(e.get("min")), int(e.get("max")), float(e.get("width"))) for e in ET.fromstring(raw).iter(ns + "col")]
    covered = [c for a, b, _ in cols for c in range(a, min(b, 60) + 1)]
    assert len(covered) == len(set(covered)), "диапазоны колонок пересекаются"
    width_of = {c: w for a, b, w in cols for c in range(a, min(b, 60) + 1)}
    assert all(abs(width_of[c] - 8.33203125) < 1e-6 for c in range(9, 40))
    assert (width_of[4], width_of[5], width_of[6], width_of[40], width_of[41]) == (14.0, 13.0, 13.0, 17.44140625, 3.109375)
    assert wide.ext.width > 19061205 * 1.5     # два месяца — поле графика вдвое шире, график за ним


def test_short_month_tail_is_hatched_not_zero():
    """«Всегда 31 день, числа — по реальности; лишние дни заштриховать» (владелец 17.11.2026). Уронит: 31-е ноября с
    датой или нулём вместо пустой заштрихованной колонки."""
    from app.ad import client_report_xlsx as X
    ws = X.render(_head_rep(date(2026, 11, 30)))["Отчёт"]
    hdr = next(c for row in ws.iter_rows(min_row=18) for c in row if c.value == "Дата")
    last = ws.cell(hdr.row, 9 + 30)                                          # 31-я колонка дня — AM
    assert ws.cell(hdr.row, 9 + 29).value == "30.11" and last.value is None
    assert ws.cell(hdr.row, 9 + 31).value == "ИТОГО"
    assert all(ws.cell(hdr.row + k, 9 + 30).fill.fill_type == "lightUp" for k in range(0, 6))
    assert all(ws.cell(hdr.row + k, 9 + 30).value is None for k in range(1, 6))
    # фон таблицы — до одной колонки за «ИТОГО» (AO), дальше чисто (владелец 17.11.2026: «заливка справа на 1 колонку лишняя»)
    assert ws.cell(hdr.row + 1, 9 + 32).fill.fill_type == "solid" and ws.cell(hdr.row + 1, 9 + 33).fill.fill_type is None


def test_total_column_keeps_every_line():
    """Владелец 17.11.2026: «потерял данные в колонке итого» — штриховка встала посреди цикла, и итог писался только у
    «Накопительно». Уронит: снова пустые итоги показов, кликов, уников и CTR."""
    from app.ad import client_report_xlsx as X
    rep = _head_rep(date(2026, 11, 30))
    rep.by_day = [{"label": date(2026, 11, 2), "shows": 1000, "clicks": 10, "uniques": 400},
                  {"label": date(2026, 11, 3), "shows": 3000, "clicks": 20, "uniques": 900}]
    rep.head["last_data"] = date(2026, 11, 3)
    ws = X.render(rep)["Отчёт"]
    hdr = next(c for row in ws.iter_rows(min_row=18) for c in row if c.value == "Дата")
    assert [ws.cell(hdr.row + k, 9 + 31).value for k in range(1, 6)] == [4000, 30, 1300, 0.75, 4000]


def test_every_sheet_opens_at_68_percent():
    """Владелец 17.11.2026: масштаб страницы по умолчанию — 68 % (сначала просил 70). Уронит: 55 % из шаблона на «Отчёте» или 100 % на «По неделям»."""
    from app.ad import client_report_xlsx as X
    wb = X.render(_head_rep(date(2026, 11, 30)), _head_rep(date(2026, 11, 30)))
    assert [(ws.title, ws.sheet_view.zoomScale) for ws in wb.worksheets] ==         [(t, 68) for t in ("Отчёт", "По неделям", "Отчёт (модель)", "По неделям (модель)")]


def test_plot_area_inside_chart_is_owners():
    """Область построения внутри графика — из правки владельца v6 (x 0,0407, w 0,9229; верх и высота прежние). Уронит:
    шаблон графика вернулся к прежней раскладке."""
    import zipfile
    from app.ad import client_report_xlsx as X
    rep = _head_rep(date(2026, 11, 30))
    rep.by_day = [{"label": date(2026, 11, 2), "shows": 1000, "clicks": 10, "uniques": 400}]
    xml = zipfile.ZipFile(io.BytesIO(X.to_xlsx(rep))).read("xl/charts/chart1.xml").decode()
    assert '<c:x val="4.0717604642230079E-2"/>' in xml and '<c:w val="0.92289255966979489"/>' in xml
    assert '<c:y val="7.2268507010202016E-2"/>' in xml and '<c:h val="0.66418693744577195"/>' in xml


def test_left_header_values_on_pure_white():
    """Владелец 17.11.2026 (v7): значения слева в шапке (C11:C16) — на чистом белом, не «белый −5 %». Уронит: снова тон шаблона."""
    from app.ad import client_report_xlsx as X
    ws = X.render(_head_rep(date(2026, 11, 30)))["Отчёт"]
    for r in range(11, 17):
        fg = ws.cell(r, 3).fill.fgColor
        assert ws.cell(r, 3).fill.fill_type == "solid" and fg.theme == 0 and not fg.tint
