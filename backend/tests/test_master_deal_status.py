# -*- coding: utf-8 -*-
"""Статусы мастер-сделки (владелец 19.10.2026): черновик → согласование → ждём 1С → выставление (ЭДО/бумага) → ждём оплату →
архив (скрыт в реестре). Первые два шага ставит система (ДС созданы, ДС подтверждены); дальше двигают руками — у кого есть
редактирование; назад на шаг — мастер и админ («мастер может и админ, а так двигаем руками»)."""
import pytest

from app.master_deal import status as ST


class _M:
    def __init__(self, status, channel="ЭДО"):
        self.status, self.id, self.code, self.updated_at = status, 1, "M-T", None
        self.channel = channel
        self.issued_at_start = False


class _U:
    def __init__(self, admin=False, master=False):
        self.id = 5
        self.role = type("R", (), {"key": "admin" if admin else "role_8", "is_master": master})()


@pytest.fixture(autouse=True)
def _channel(monkeypatch):
    monkeypatch.setattr(ST, "channel_of", lambda db, m: m.channel)
    from types import SimpleNamespace as NS
    from app.master_deal import issue as IS
    # 02.11.2026: условия «ждём оплату» и «архив» — документы пакета; здесь все подписаны, проверяем только право и шаг
    monkeypatch.setattr(IS, "docs", lambda db, m: [NS(sign_state="подписан", sign_channel=m.channel)])
    monkeypatch.setattr(IS, "doc_label", lambda d: "ДС № 1")
    # 05.11.2026: из «ждём 1С» дальше — когда бухгалтер внесла все комплекты; здесь внесены
    monkeypatch.setattr(ST, "_desk_pending", lambda db, m: [])


def test_order_and_values():
    assert ST.STATUSES == ("черновик", "согласование", "ждём закрытия", "ждём 1С", "выставление", "ждём оплату", "ждём сканы",
                           "архив")


@pytest.mark.parametrize("frm,to", [("ждём 1С", "выставление"), ("выставление", "ждём оплату"), ("ждём оплату", "архив")])
def test_forward_by_hand_for_editor(frm, to):
    m = _M(frm)
    ST.move(None, m, to, _U())
    assert m.status == to


@pytest.mark.parametrize("frm,to", [("черновик", "согласование"), ("согласование", "ждём 1С"), ("ждём 1С", "ждём оплату")])
def test_system_steps_and_jumps_are_not_by_hand(frm, to):
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, _M(frm), to, _U(admin=True))
    assert e.value.status == 409


def test_issue_needs_channel_on_contract():
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, _M("ждём 1С", channel=None), "выставление", _U())
    assert "ЭДО или бумага" in e.value.message


def test_issue_by_hand_only_after_accountant_entered_all_kits(monkeypatch):
    """«УПД из 1С получены» руками больше не ставят (05.11.2026): счёт и УПД вносит бухгалтер, пакет уходит сам."""
    monkeypatch.setattr(ST, "_desk_pending", lambda db, m: ["УПД № 2"])
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, _M("ждём 1С"), "выставление", _U(admin=True))
    assert e.value.status == 409 and "УПД № 2" in e.value.message


@pytest.mark.parametrize("u", [_U(), _U(master=True), _U(admin=True)])
def test_back_goes_only_through_revert_with_reason(u):
    """12.11.2026: назад — только «Вернуть стадию» (причина, сброс, уведомление); шаг статусом назад обходил бы всё это."""
    m = _M("ждём оплату")
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, m, "выставление", u)
    assert e.value.status == 409 and "Вернуть стадию" in e.value.message and m.status == "ждём оплату"


def test_back_into_system_steps_goes_through_their_own_buttons():
    """«ждём 1С» → «согласование» — это снять подтверждение ДС, «согласование» → «черновик» — «Вернуть в раскладку»."""
    with pytest.raises(ST.StatusError):
        ST.move(None, _M("ждём 1С"), "согласование", _U(admin=True))


def test_label_shows_channel():
    assert ST.label(None, _M("выставление", "бумага")) == "выставление · бумага"
    assert ST.label(None, _M("ждём оплату")) == "ждём оплату"


def test_actions_for_view():
    a = ST.actions(None, _M("выставление"), _U(master=True))
    assert a["next"] == "ждём оплату" and a["prev"] is None        # назад — «Вернуть стадию» (12.11.2026)
    assert ST.actions(None, _M("черновик"), _U(admin=True))["next"] is None


def test_old_values_are_migrated():
    import pathlib
    f = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "2026-10-19_master_deal_statuses.sql"
    if not f.exists():
        pytest.skip("миграций нет в контейнере — проверяется в репозитории")
    sql = f.read_text(encoding="utf-8")
    for old, new in (("сборка", "черновик"), ("ДС", "согласование"), ("в 1С", "ждём 1С"), ("закрывающие", "выставление"), ("закрыт", "архив")):
        assert f"'{old}'" in sql and f"'{new}'" in sql


# ── «Что нужно сейчас» (владелец 19.10.2026: «индикация, что требуется мастер-сделке в данный момент») ──

@pytest.fixture
def _todo(monkeypatch):
    st = {"ready": [], "legal": 0, "drafts": 0}
    monkeypatch.setattr(ST, "_ready", lambda db, m: st["ready"])
    monkeypatch.setattr(ST, "_open_legal", lambda db, m: st["legal"])
    monkeypatch.setattr(ST, "_drafts", lambda db, m: st["drafts"])
    st["desk"] = (None, 2, 2)
    monkeypatch.setattr(ST, "_desk", lambda db, m: st["desk"])
    return st


@pytest.mark.parametrize("why,text,who", [
    (["сверка не завершена у всех сделок"], "дождаться сверки сделок", "аккаунт"),
    (["не задан номер ДС"], "задать стартовый № ДС", "аккаунт"),
    (["сумма не сходится с суммой сделок"], "свести раскладку с суммой сделок", "аккаунт"),
    ([], "создать ДС", "аккаунт"),
])
def test_todo_in_draft(_todo, why, text, who):
    _todo["ready"] = why
    t = ST.todo(None, _M("черновик"))
    assert (t["text"], t["who"]) == (text, who)


def test_todo_agree_legal_first_then_confirm(_todo):
    _todo["legal"], _todo["drafts"] = 1, 2
    assert ST.todo(None, _M("согласование"))["who"] == "юрист"
    _todo["legal"] = 0
    t = ST.todo(None, _M("согласование"))
    assert t["text"] == "подтвердить ДС (2)" and t["who"] == "аккаунт"


def test_todo_later_steps(_todo):
    # 05.11.2026: счёт и УПД вносит бухгалтер в «Документах для 1С»
    assert ST.todo(None, _M("ждём 1С")) == {"text": "ждём счёт и УПД от бухгалтерии", "who": "бухгалтерия", "tone": "info"}
    _todo["desk"] = (None, 1, 3)
    assert ST.todo(None, _M("ждём 1С"))["text"] == "бухгалтерия: внесено 2 из 3"
    _todo["desk"] = ({"upd_no": 2, "text": "КПП не тот"}, 1, 3)
    assert ST.todo(None, _M("ждём 1С")) == {"text": "бухгалтер вернул УПД № 2: КПП не тот", "who": "аккаунт", "tone": "bad"}
    _todo["desk"] = (None, 2, 2)
    t = ST.todo(None, _M("ждём 1С", channel=None))
    assert t["tone"] == "bad" and "ЭДО или бумага" in t["text"]
    assert ST.todo(None, _M("выставление", "бумага"))["text"] == "всё выставлено — ждём оплату"   # подробно — test_master_deal_issue
    assert ST.todo(None, _M("ждём оплату"))["who"] == "финансы"     # 19.10: сканы — своя стадия «ждём сканы»
    assert ST.todo(None, _M("архив")) is None


def test_pack_that_went_by_edo_stays_edo_after_contract_switches_to_paper(monkeypatch):
    """Ушло клиенту по ЭДО — «ждём сканы» не появляется, даже если признак договора потом сменили на бумагу (ревью 21.10.2026).
    С 02.11.2026 канал держит документ (`sign_channel`), а не отметки пакета."""
    from types import SimpleNamespace as NS
    from app.master_deal import issue as IS
    from app.master_deal import status as S
    monkeypatch.setattr(S, "channel_of", lambda db, m: "бумага")
    docs = {"v": [NS(sign_state="выставлен", sign_channel="ЭДО")]}
    monkeypatch.setattr(IS, "docs", lambda db, m: docs["v"])
    assert S.is_paper(None, NS()) is False
    docs["v"] = [NS(sign_state="выпущен", sign_channel=None)]
    assert S.is_paper(None, NS()) is True, "ничего не ушло — решает признак договора"
    docs["v"] = [NS(sign_state="выставлен", sign_channel="ЭДО"), NS(sign_state="подписан у нас", sign_channel="бумага")]
    assert S.is_paper(None, NS()) is True


def test_layout_and_start_no_locked_once_ds_drafts_exist(monkeypatch):
    from types import SimpleNamespace as NS
    import pytest
    from app.master_deal import package as PK
    from app.master_deal import service as MS
    monkeypatch.setattr(PK, "issued_ds", lambda db, m: None)
    m = NS(status="согласование")
    with pytest.raises(MS.MasterError):
        PK.save_settings(None, m, {}, None)
    with pytest.raises(MS.MasterError):
        PK.set_start_no(None, m, 5, None)
