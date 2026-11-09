# -*- coding: utf-8 -*-
"""«Документы для бухгалтерии» по хендоффу (05.11.2026): выдача страницы, черновик, разбор XML УПД, «Внести» с серверной
проверкой, возврат со снимком и «пришла повторно», ответ аккаунта, повтор номера, срок закрытия и рабочие часы.

Поломки, которые ловит набор:
- сервер принимает «Внести» без PDF или с XML чужого покупателя (фронту не верим — правила повторяются на сервере);
- XML 1С не разбирается (версии 5.01/5.03, пространство имён) или пропускает DOCTYPE;
- праздник 04.11 считается рабочим — ожидание и срок закрытия врут;
- после возврата и исправления не видно, что поменялось, а «ответ» аккаунта не помечен как новое;
- черновик сохраняет что угодно, а не поля формы; после внесения черновик остаётся.
Живой пакет стенда, транзакция откатывается."""
from datetime import date, datetime, timezone

import pytest

from tests._untouched_kit import untouched_kit
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import status as ST

XML_503 = """<?xml version="1.0" encoding="windows-1251"?>
<Файл ИдФайл="ON_NSCHFDOPPR_1" ВерсФорм="5.03">
 <Документ КНД="1115131" Функция="СЧФДОП">
  <СвСчФакт НомерДок="405" ДатаДок="31.10.2026">
   <СвПрод><ИдСв><СвЮЛУч НаимОрг="Мы" ИННЮЛ="7700000002" КПП="770002001"/></ИдСв></СвПрод>
   <СвПокуп><ИдСв><СвЮЛУч НаимОрг="Они" ИННЮЛ="{inn}" КПП="{kpp}"/></ИдСв></СвПокуп>
  </СвСчФакт>
  <ТаблСчФакт>
   <СведТов НомСтр="1" НаимТов="{svc}" СтТовБезНДС="{net}" СтТовУчНал="{gross}"/>
   <ВсегоОпл СтТовБезНДСВсего="{net}" СтТовУчНалВсего="{gross}"><СумНалВсего><СумНал>{vat}</СумНал></СумНалВсего></ВсегоОпл>
  </ТаблСчФакт>
  <СвПродПер><СвПер><ОснПер РеквНаимДок="Приложение" РеквНомерДок="45"/><ОснПер РеквНаимДок="Договор" РеквНомерДок="{ct}"/></СвПер></СвПродПер>
 </Документ>
</Файл>"""


def _xml(**kw) -> bytes:
    d = {"inn": "7700000001", "kpp": "770001001", "net": "500000.20", "vat": "110000.04", "gross": "610000.24", "ct": "РМ 11-11-25",
         "svc": "Размещение рекламных материалов бренда «Тестовый бренд», в сети SIMB-AD"}
    d.update(kw)
    return XML_503.format(**d).encode("cp1251")


# ── разбор XML ───────────────────────────────────────────────────────────────────────────────────

def test_xml_503_gives_number_date_sums_buyer_and_contract():
    from app.onec_desk import xmlparse as XP
    x = XP.parse(_xml(), "РМ 11-11-25")
    assert (x["number"], x["date"]) == ("405", "31.10.2026")
    assert (x["net"], x["vat"], x["gross"]) == ("500 000,20", "110 000,04", "610 000,24")
    assert x["buyer"] == {"inn": "7700000001", "kpp": "770001001"}
    assert x["contract"] == "РМ 11-11-25", "среди оснований — договор сделки, а не приложение"


def test_xml_501_attributes_are_read_too():
    from app.onec_desk import xmlparse as XP
    raw = _xml().decode("cp1251").replace('НомерДок="405" ДатаДок=', 'НомерСчФ="77" ДатаСчФ=').replace(
        'РеквНаимДок="Договор" РеквНомерДок=', 'НаимОсн="Договор" НомОсн=').encode("cp1251")
    x = XP.parse(raw, None)
    assert x["number"] == "77" and x["contract"] == "РМ 11-11-25"


def test_xml_with_doctype_or_garbage_is_refused():
    from app.onec_desk import service as SV
    from app.onec_desk import xmlparse as XP
    with pytest.raises(SV.DeskError):
        XP.parse(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
    with pytest.raises(SV.DeskError):
        XP.parse(b"<not-an-upd/>")


# ── рабочие часы и срок закрытия ───────────────────────────────────────────────────────────────

def test_holiday_is_not_a_working_day():
    from app.onec_desk import rules as R
    a = datetime(2026, 11, 3, 9, 0, tzinfo=R.MSK)
    b = datetime(2026, 11, 5, 18, 0, tzinfo=R.MSK)
    assert R.work_hours(a, b) == 27
    assert R.work_hours(a, b, {date(2026, 11, 4)}) == 18, "04.11 — праздник"


def test_close_defaults_to_10th_and_closed_month_sets_closed_until():
    from app.database import SessionLocal
    from app.onec_desk import close as CL
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM accounting_close"))
        st = CL.settings(db, datetime(2026, 11, 5, 12, tzinfo=timezone.utc))
        assert st["month"] == "2026-10" and st["close_month_gen"] == "октября"
        assert st["close_at"].startswith("2026-11-10T18:00") and st["closed_until"] is None
        assert "2026-11-04" in st["calendar"]["holidays"]
        CL.save_close(db, "2026-09", datetime(2026, 10, 9, 18, tzinfo=CL.MSK), True, None)
        assert CL.settings(db, datetime(2026, 11, 5, tzinfo=timezone.utc))["closed_until"] == "30.09.2026"
    finally:
        db.rollback()
        db.close()


# ── заявка на живом пакете ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def env(monkeypatch):
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.models import User
    from app.onec_desk import files as OF
    from app.onec_desk import service as SV
    db = SessionLocal()
    k = untouched_kit(db)
    if k is None:
        db.close()
        pytest.skip("на стенде нет комплектов УПД")
    m = db.get(MasterDeal, k.master_deal_id)
    m.status = ST.WAIT_1C
    db.execute(text("UPDATE contracts SET issue_channel = coalesce(issue_channel, 'ЭДО') WHERE id = :c"), {"c": m.contract_id})
    for f in ("onec_state", "onec_at", "onec_invoice_no", "onec_upd_no", "onec_invoice_date", "onec_upd_date", "onec_net",
              "onec_vat", "onec_gross", "onec_by", "onec_draft", "onec_seen_at"):
        setattr(k, f, None)
    db.execute(text("DELETE FROM onec_desk_events WHERE upd_id = :k"), {"k": k.id})
    db.flush()
    sent = []
    monkeypatch.setattr(SV, "_notify", lambda db_, key, m_, **kw: sent.append(key))
    files = {}
    monkeypatch.setattr(OF, "files_of", lambda db_, m_, k_: dict(files))
    user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    try:
        yield db, m, k, user, sent, files
    finally:
        db.rollback()
        db.close()


def _req(db, m, k):
    from app.onec_desk import board as BD
    return BD.request_for(db, m, k)


def _form(req, **kw):
    t = {key: round(sum(float(x[key]) for x in req["lines"]), 2) for key in ("net", "vat", "gross")}
    f = {"invNo": "411", "invDate": "31.10.2026", "updNo": "405", "updDate": "31.10.2026",
         **{key: f"{v:.2f}".replace(".", ",") for key, v in t.items()}, "comment": ""}
    f.update(kw)
    return f


def test_request_has_the_handoff_contract_shape(env):
    db, m, k, *_ = env
    r = _req(db, m, k)
    for key in ("code", "status", "since", "buyer", "contract", "annex", "brand", "period", "basis", "lines", "ds_signed",
                "draft", "seen", "resent", "returned", "done", "thread", "edo"):
        assert key in r, key
    assert r["status"] == "wait" and r["lines"] and {"service", "net", "vat_rate", "vat", "gross"} <= set(r["lines"][0])
    assert r["period"]["to"].endswith("T23:59:00+03:00")


def test_submit_without_pdfs_is_refused_and_with_them_enters(env):
    db, m, k, user, sent, files = env
    from app.onec_desk import service as SV
    db.execute(text("UPDATE contracts SET issue_channel = 'бумага' WHERE id = :c"), {"c": m.contract_id})   # XML не нужен
    req = _req(db, m, k)
    with pytest.raises(SV.DeskError) as e:
        SV.submit(db, m, k, _form(req), req, user)
    assert e.value.status == 409 and "PDF счёта" in e.value.message and "PDF УПД" in e.value.message
    files.update({"invoice": {"id": 1, "filename": "с.pdf"}, "upd": {"id": 2, "filename": "у.pdf"}})
    k.onec_draft = {"invNo": "411"}
    out = SV.submit(db, m, k, _form(req), req, user)
    assert k.onec_state == SV.DONE and k.onec_invoice_no == "411" and k.onec_upd_date == date(2026, 10, 31)
    assert k.onec_draft is None, "после внесения черновик стирается"
    assert "warns" in out


def test_submit_with_sum_diff_needs_comment(env):
    db, m, k, user, _, files = env
    from app.onec_desk import service as SV
    files.update({"invoice": {"id": 1, "filename": "с.pdf"}, "upd": {"id": 2, "filename": "у.pdf"}})
    req = _req(db, m, k)
    bump = {key: f"{round(sum(float(x[key]) for x in req['lines']), 2) + (3 if key != 'net' else 0):.2f}".replace(".", ",")
            for key in ("net", "vat", "gross")}
    with pytest.raises(SV.DeskError) as e:
        SV.submit(db, m, k, _form(req, **bump), req, user)
    assert "комментарий к расхождению" in e.value.message


def test_xml_of_another_buyer_blocks_submit(env, monkeypatch):
    db, m, k, user, _, files = env
    from app.onec_desk import files as OF
    from app.onec_desk import service as SV
    files.update({"invoice": {"id": 1, "filename": "с.pdf"}, "upd": {"id": 2, "filename": "у.pdf"}, "xml": {"id": 3, "filename": "у.xml"}})
    req = _req(db, m, k)
    monkeypatch.setattr(OF, "get", lambda *a: None)
    monkeypatch.setattr(OF, "read", lambda f: _xml(inn=req["buyer"]["inn"], kpp="000000000", ct=req["contract"]["no"]))
    with pytest.raises(SV.DeskError) as e:
        SV.submit(db, m, k, _form(req), req, user)
    assert "XML: покупатель, договор или основание не совпадает" in e.value.message


def test_draft_keeps_only_form_fields(env):
    db, m, k, user, *_ = env
    from app.onec_desk import service as SV
    SV.save_draft(db, m, k, {"invNo": 411, "net": "1 000,00", "evil": "x", "invPdf": {"id": 9}}, user)
    assert k.onec_draft == {"invNo": "411", "net": "1 000,00"}


def test_return_snapshot_then_fixed_shows_changes(env):
    db, m, k, user, sent, _ = env
    from app.onec_desk import board as BD
    from app.onec_desk import service as SV
    req = _req(db, m, k)
    snap = BD.snapshot(req)
    snap["КПП покупателя"] = "000000000"                       # «тогда» КПП был другой
    SV.give_back(db, m, k, "КПП не тот", user, reason="реквизиты покупателя", snap=snap)
    assert sent == ["master_onec_returned"]
    assert _req(db, m, k)["returned"]["reason"] == "реквизиты покупателя: КПП не тот"
    SV.fixed(db, m, k, "поправили", user)
    r = _req(db, m, k)
    assert r["resent"] and any(c["label"] == "КПП покупателя" and c["from"] == "000000000" for c in r["resent"]["changes"])
    assert r["seen"] is False, "исправленное — с меткой, пока бухгалтер не открыл"
    SV.mark_seen(db, k)
    assert _req(db, m, k)["seen"] is True


def test_account_reply_is_unread_until_seen_and_question_notifies(env):
    db, m, k, user, sent, _ = env
    from app.onec_desk import service as SV
    SV.comment(db, k, "Прил. 89 и 90 — не дубль?", user, m=m)
    assert sent == ["master_onec_question"]
    SV.reply(db, m, k, "Нет, разные РК", user)
    r = _req(db, m, k)
    assert r["thread"][0]["from_account"] and r["thread"][0]["unread"] and r["seen"] is False
    SV.mark_seen(db, k)
    assert _req(db, m, k)["seen"] is True


def test_number_seen_in_another_draft_is_reported(env):
    db, m, k, user, *_ = env
    from app.master_deal.models import MasterDealUpd
    from app.onec_desk import service as SV
    other = db.query(MasterDealUpd).filter(MasterDealUpd.id != k.id).order_by(MasterDealUpd.id).first()
    if other is None:
        pytest.skip("нужен второй комплект")
    other.onec_state, other.onec_draft = None, {"invNo": "ТЕСТ-402"}
    db.flush()
    hit = SV.check_number(db, "inv", "ТЕСТ-402", k.id)
    assert hit and hit["status"] == "wait"
    assert SV.check_number(db, "inv", "ТЕСТ-402", other.id) is None, "свою заявку не считаем"


# ── архив ЭДО и номер договора в написании 1С (образец Такском, 05.11.2026) ─────────────────────

def _container(xml: bytes, main: str = "1/ON_NSCHFDOPPR_test.xml") -> bytes:
    import io
    import zipfile
    meta = (f'<?xml version="1.0" encoding="windows-1251"?><ContainerDescription xmlns="http://api-invoice.taxcom.ru/meta">'
            f'<DocFlow><Documents><Document><Files><MainImage Path="{main}"/><ExternalCard Path="1/card.xml"/></Files>'
            f'</Document></Documents></DocFlow></ContainerDescription>').encode("cp1251")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("meta.xml", meta)
        z.writestr("1/card.xml", '<?xml version="1.0"?><Card/>')
        z.writestr(main, xml)
    return buf.getvalue()


def test_edo_zip_container_is_unpacked_by_meta():
    from app.onec_desk import xmlparse as XP
    x = XP.parse(_container(_xml()), "РМ 11-11-25")
    assert x["number"] == "405" and x["gross"] == "610 000,24"


def test_contract_as_1c_writes_it_matches_ours():
    """1С: «Договор РМ 11-11-2025», у нас «РМ 11-11-25» (или «PM» латиницей) — это один договор."""
    from app.onec_desk import xmlparse as XP
    raw = _xml(ct="Договор РМ 11-11-2025")
    assert XP.parse(raw, "РМ 11-11-25")["contract"] == "РМ 11-11-25"
    assert XP.parse(raw, "PM-11-11-25")["contract"] == "PM-11-11-25"
    assert XP.parse(raw, "РМ 11-11-25")["contract_1c"] == "Договор РМ 11-11-2025"
    assert XP.parse(raw, "РМ 11-11-24")["contract"] != "РМ 11-11-24", "другой договор совпасть не должен"


# ── согласованное основание идёт в документ (владелец 05.11.2026) ────────────────────────────────

def test_xml_service_name_is_checked_against_agreed_basis():
    """В УПД 1С наименование услуги = согласованное основание; пробелы и вид кавычек не в счёт, другой текст — не совпало."""
    from app.onec_desk import xmlparse as XP
    agreed = 'Размещение  рекламных материалов бренда "Тестовый бренд", в сети SIMB-AD'
    assert XP.parse(_xml(), "РМ 11-11-25", agreed)["basis"] == agreed
    other = XP.parse(_xml(svc="Услуги по размещению рекламы"), "РМ 11-11-25", agreed)
    assert other["basis"] == "Услуги по размещению рекламы"


def test_request_lines_carry_agreed_basis(env):
    db, m, k, *_ = env
    r = _req(db, m, k)
    if r["basis"]:
        # строка УПД — согласованное основание; у УПД из нескольких строк — своё у каждой (06.11.2026)
        assert all(x["service"] in r["basis"].split("\n") for x in r["lines"]), "в строку УПД идёт согласованное основание"


def test_xml_with_other_service_name_blocks_submit(env, monkeypatch):
    db, m, k, user, _, files = env
    from app.onec_desk import files as OF
    from app.onec_desk import service as SV
    files.update({"invoice": {"id": 1, "filename": "с.pdf"}, "upd": {"id": 2, "filename": "у.pdf"}, "xml": {"id": 3, "filename": "у.xml"}})
    req = _req(db, m, k)
    if not req["basis"]:
        pytest.skip("у комплекта нет основания")
    monkeypatch.setattr(OF, "get", lambda *a: None)
    monkeypatch.setattr(OF, "read", lambda f: _xml(inn=req["buyer"]["inn"], kpp=req["buyer"]["kpp"], ct=req["contract"]["no"],
                                                   svc="Услуги по размещению рекламы"))
    with pytest.raises(SV.DeskError) as e:
        SV.submit(db, m, k, _form(req), req, user)
    assert "основание" in e.value.message


def test_request_shows_issue_channel_of_the_contract(env):
    """Бухгалтеру видно, как выставляем (владелец 06.11.2026): признак договора; бумажный — «бумага», не задан — None."""
    db, m, k, *_ = env
    from sqlalchemy import text as _t
    db.execute(_t("UPDATE contracts SET issue_channel = 'бумага' WHERE id = :c"), {"c": m.contract_id})
    assert _req(db, m, k)["channel"] == "бумага"
    db.execute(_t("UPDATE contracts SET issue_channel = NULL WHERE id = :c"), {"c": m.contract_id})
    assert _req(db, m, k)["channel"] is None


# ── XML обязателен, кроме бумаги; догрузка во внесённое (владелец 09.11.2026) ─────────────────────────

PDFS = {"invoice": {"id": 1, "filename": "с.pdf"}, "upd": {"id": 2, "filename": "у.pdf"}}


@pytest.mark.parametrize("channel", ["ЭДО", None])
def test_submit_without_xml_is_refused_unless_paper(env, channel):
    """Поломка: XML снова «по желанию» — ЭДО-комплект (или с незаданным каналом) вносится без файла для отправки клиенту."""
    db, m, k, user, _, files = env
    from app.onec_desk import service as SV
    db.execute(text("UPDATE contracts SET issue_channel = :ch WHERE id = :c"), {"ch": channel, "c": m.contract_id})
    files.update(PDFS)
    req = _req(db, m, k)
    with pytest.raises(SV.DeskError) as e:
        SV.submit(db, m, k, _form(req), req, user)
    assert "XML УПД" in e.value.message and "PDF" not in e.value.message


def test_paper_submit_needs_both_pdfs_but_no_xml(env):
    db, m, k, user, _, files = env
    from app.onec_desk import service as SV
    db.execute(text("UPDATE contracts SET issue_channel = 'бумага' WHERE id = :c"), {"c": m.contract_id})
    req = _req(db, m, k)
    files.update({"invoice": PDFS["invoice"]})
    with pytest.raises(SV.DeskError) as e:
        SV.submit(db, m, k, _form(req), req, user)
    assert "PDF УПД" in e.value.message and "XML" not in e.value.message
    files.update(PDFS)
    SV.submit(db, m, k, _form(req), req, user)
    assert k.onec_state == SV.DONE


def _entered(db, m, k, user, files):
    from app.onec_desk import service as SV
    db.execute(text("UPDATE contracts SET issue_channel = 'бумага' WHERE id = :c"), {"c": m.contract_id})
    files.update(PDFS)
    req = _req(db, m, k)
    SV.submit(db, m, k, _form(req), req, user)
    db.execute(text("UPDATE contracts SET issue_channel = 'ЭДО' WHERE id = :c"), {"c": m.contract_id})
    return _req(db, m, k)


def test_late_xml_must_match_what_was_entered(env):
    """Догрузка XML во внесённую заявку: файл чужого покупателя или с другим № УПД не принимается — внесённое уже ушло
    в операцию, сверять больше негде."""
    db, m, k, user, _, files = env
    from app.onec_desk import service as SV
    req = _entered(db, m, k, user, files)
    t = {key: f"{round(sum(float(x[key]) for x in req['lines']), 2):.2f}" for key in ("net", "vat", "gross")}
    good = dict(inn=req["buyer"]["inn"], kpp=req["buyer"]["kpp"], ct=req["contract"]["no"], svc=req["basis"] or "x", **t)
    SV.check_late_xml(m, k, _xml(**good), req)
    for bad in ({"kpp": "000000000"}, {"ct": "ЧУЖОЙ 1"}):
        with pytest.raises(SV.DeskError) as e:
            SV.check_late_xml(m, k, _xml(**{**good, **bad}), req)
        assert e.value.status == 409
    k.onec_upd_no = "999"
    with pytest.raises(SV.DeskError) as e:
        SV.check_late_xml(m, k, _xml(**good), req)
    assert "№ УПД" in e.value.message
