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

    def __init__(self, journal_hash=None, add_hash="NEWHASH000000001",
                 info_html="<div>баннер</div>", campaign_status="LAUNCHED",
                 campaign_end="2999-01-01 00:00:00"):
        self.journal_hash = journal_hash
        self.add_hash = add_hash
        self.info_html = info_html
        self.campaign_status = campaign_status
        self.campaign_end = campaign_end
        self.calls = []

    def campaign_edit(self, xxhash, params, local_ref=None):
        self.calls.append(("campaign_edit", xxhash, params.get("date_end")))
        self.campaign_end = str(params.get("date_end")) + " 00:00:00"
        self.edited_limits = params.get("limits")
        return True

    def campaign_set_status(self, xxhash, status, local_ref=None):
        self.calls.append(("campaign_status", xxhash, status))
        self.campaign_status = status
        return True

    def campaign_get_info(self, xxhash):
        """Карточка кампании, в которой живут креативы нацеливания.

        Кампания ЧУЖАЯ: её останавливают руками в кабинете DSP, и остановленная не
        покажет ничего — поэтому заведение обязано её спрашивать (замер 17.09.2026).
        """
        self.calls.append(("campaign", xxhash))
        return {"title": "ТЕСТ · кампания нацеливания", "xxhash": xxhash,
                "status": self.campaign_status,
                "limits": {"show": {"total": 200000}, "budget": {"total": 1000}},
                "date_start": {"date": "2026-01-01 00:00:00"},
                "date_end": {"date": self.campaign_end}}

    def last_ok_xxhash(self, method, entity_type, local_ref):
        self.calls.append(("journal", method, local_ref))
        return self.journal_hash

    def creative_add(self, campaign_xxhash, params, local_ref=None):
        self.calls.append(("add", campaign_xxhash, params.get("title"), local_ref))
        return self.add_hash

    def creative_edit(self, xxhash, params, local_ref=None):
        self.calls.append(("edit", xxhash, local_ref))
        return True

    def creative_get_info(self, xxhash):
        """Чтение креатива в кабинете. `html` задаётся тестом: `None` — объекта нет,
        пустая строка — объект без кода, текст — полноценный креатив."""
        self.calls.append(("info", xxhash))
        if self.info_html is None:
            from app.dsp.client import MsError
            raise MsError("Creative.getInfo: Creative not found")
        return {"data": {"html_code": self.info_html}}


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


def test_stored_hash_is_verified_but_never_duplicated():
    """Заведён — значит заведён: ВТОРОЙ креатив не создаётся никогда.

    Это главная защита: в DSP нет удаления, лишний креатив останется там навсегда.

    До 17.09.2026 правило было сильнее — «наружу не ходим вообще». Оно защищало от
    дубля, но обещало больше, чем проверяло: объект создаётся одним вызовом, а HTML
    вшивается ВТОРЫМ, и между ними связь может оборваться. Тогда в кабинете остаётся
    креатив БЕЗ КОДА, ссылка на него открывается и показывает пустую страницу — а мы
    рапортовали «заведён». Теперь сохранённый хеш ПЕРЕПРОВЕРЯЕТСЯ чтением, и это
    единственный поход наружу: `Creative.add` в этой ветке по-прежнему не вызывается.
    """
    db = _db()
    s = _set_with(db, ms_targeting_creative_xxhash="ALREADY0000000001")
    c = FakeClient()
    try:
        assert P.ensure(db, s, client=c) == "ALREADY0000000001"
        # Первым идёт вопрос о КАМПАНИИ: остановленная не покажет ничего, и проверять
        # креатив в ней бессмысленно. Дальше — одно чтение креатива. `Creative.add` в
        # этой ветке не вызывается никогда: удалить лишний в чужом кабинете нечем.
        assert c.calls == [("campaign", c.calls[0][1]),
                           ("info", "ALREADY0000000001")], (
            f"лишние вызовы при сохранённом хеше: {c.calls}")
        assert not any(k[0] == "add" for k in c.calls), "создан второй креатив"
    finally:
        _drop(db, s)


def test_an_object_without_html_is_finished_not_duplicated():
    """Креатив есть, кода нет — дошиваем код в него же.

    Завести второй было бы проще и непоправимо: удаления в чужом кабинете нет.
    """
    db = _db()
    s = _set_with(db, ms_targeting_creative_xxhash="EMPTY00000000001")
    c = FakeClient(info_html="")
    try:
        with pytest.raises(P.TargetingCreativeError):
            # архива у времянки нет — важно, что путь пошёл в дошивку, а не в создание
            P.ensure(db, s, client=c)
        assert not any(k[0] == "add" for k in c.calls), (
            "пустой креатив продублирован вместо дошивки")
    finally:
        _drop(db, s)


def test_journal_saves_us_from_a_duplicate():
    """DSP создал, а наш коммит не дошёл — журнал помнит, и повтор не плодит второй."""
    db = _db()
    s = _set_with(db)
    c = FakeClient(journal_hash="FROMJOURNAL00001")
    try:
        assert P.ensure(db, s, client=c) == "FROMJOURNAL00001"
        # Журнал подсказал хеш, чтение подтвердило код — создавать нечего.
        assert [k[0] for k in c.calls] == ["campaign", "journal", "info"], (
            f"после журнала должно быть только чтение, а было: {c.calls}")
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


def test_a_sleeping_campaign_is_woken_by_the_request_itself():
    """Спящую кампанию получение нацеливания БУДИТ, а не отвергает.

    Полигон нацеливания не держат открытым месяцами: запущенная кампания крутится
    настоящим людям в пределах лимитов. Поэтому она спит, а просыпается ровно в момент
    нажатия и живёт двое суток (владелец 17.09.2026). Первая редакция проверки в тот же
    день отказывала — отказ был верен по факту, но перекладывал на человека ход, который
    система делает двумя вызовами.
    """
    from datetime import datetime, timedelta
    db = _db()
    try:
        s = _set_with(db)
        c = FakeClient(campaign_status="STOPPED", campaign_end="2026-09-13 00:00:00")
        P.wake_campaign(db, client=c)
        assert [x for x in c.calls if x[0] == "campaign_status"][0][2] == "LAUNCHED"
        end = [x for x in c.calls if x[0] == "campaign_edit"][0][2]
        want = (datetime.utcnow() + timedelta(days=P.LIVE_DAYS)).date().isoformat()
        assert end == want, f"срок должен ехать на {P.LIVE_DAYS} дня вперёд, а не {end}"
    finally:
        _drop(db, s)
        db.close()


def test_waking_carries_the_limits_over():
    """Потолок показов и бюджета переносится ЦЕЛИКОМ.

    `Campaign.edit` принимает `limits` объектом: посылка одних дат обнулила бы показы и
    бюджет, то есть тихо сняла бы потолок, ради которого они и стоят. Тихо — потому что
    кампания при этом продолжает работать, и заметить это можно только по счёту.
    """
    db = _db()
    try:
        s = _set_with(db)
        c = FakeClient(campaign_status="STOPPED", campaign_end="2026-09-13 00:00:00")
        P.wake_campaign(db, client=c)
        assert c.edited_limits == {"show": {"total": 200000}, "budget": {"total": 1000}}
    finally:
        _drop(db, s)
        db.close()


def test_a_live_campaign_is_not_shortened():
    """Срок двигается ТОЛЬКО ВПЕРЁД: укоротить чужую кампанию своей проверкой значит
    однажды погасить её под чьей-то рукой."""
    db = _db()
    try:
        s = _set_with(db)
        c = FakeClient(campaign_end="2999-01-01 00:00:00")
        P.wake_campaign(db, client=c)
        assert not [x for x in c.calls if x[0] == "campaign_edit"]
        assert not [x for x in c.calls if x[0] == "campaign_status"]
    finally:
        _drop(db, s)
        db.close()


def test_a_deleted_campaign_is_the_one_real_refusal():
    """Удалённую и архивную поднять нечем — и делать вид, что можно, хуже отказа: человек
    ждал бы показов от того, чего в кабинете уже нет."""
    db = _db()
    try:
        s = _set_with(db)
        c = FakeClient(campaign_status="DELETED")
        with pytest.raises(P.TargetingCreativeError) as e:
            P.ensure(db, s, client=c)
        assert "удалена" in str(e.value)
        assert not [x for x in c.calls if x[0] == "add"]
    finally:
        _drop(db, s)
        db.close()


def test_the_process_itself_wakes_the_campaign():
    """Пробуждение вшито в ПОЛУЧЕНИЕ нацеливания, а не вынесено в отдельную кнопку.

    Смысл ровно в этом: кампания просыпается от того, что человек попросил нацеливание,
    и ему не нужно знать, что где-то есть спящий полигон. Прибор смотрит на порядок
    вызовов — вопрос о кампании идёт ПЕРВЫМ, до всякой работы с архивом.
    """
    db = _db()
    try:
        s = _set_with(db)
        c = FakeClient(campaign_status="STOPPED", campaign_end="2026-09-13 00:00:00")
        with pytest.raises(P.TargetingCreativeError):
            P.ensure(db, s, client=c)        # архива у времянки нет — дальше не уедет
        assert [x[0] for x in c.calls][:3] == ["campaign", "campaign_edit", "campaign_status"]
    finally:
        _drop(db, s)
        db.close()


def test_the_targeting_creative_carries_a_placeholder_marker():
    """У нацеливания стоит ОДНА общая заглушка маркера, а не пусто и не чужой ЕРИД.

    Настоящего маркера на этой стадии нет и быть не может — он выпускается после
    согласования площадки. А DSP без маркера креатив не запускает, и проверка, ради
    которой всё затевалось, не состоится (владелец 18.09.2026).

    Одна и та же строка на все креативы нацеливания — намеренно: увидев её дважды в
    разных кампаниях, человек сразу понимает, что это заглушка, а не чей-то настоящий
    маркер. Длина и форма как у настоящего, иначе DSP отвергнет форматом.
    """
    db = _db()
    try:
        s = _set_with(db)
        assert len(P.TEST_ERID) == 9 and P.TEST_ERID.isalnum()
        c = FakeClient()
        # Заглушка уезжает и в параметры креатива, и в тело разметки.
        src = __import__("inspect").getsource(P.ensure)
        assert "erid=TEST_ERID" in src
        assert src.count("erid=TEST_ERID") >= 2, "маркер нужен и в параметрах, и в html"
        assert c is not None
    finally:
        _drop(db, s)
        db.close()


def test_the_live_contour_never_takes_the_placeholder():
    """В боевой креатив заглушка не попадает НИКОГДА: там отдельный заслон, который
    отказывает при пустом маркере. Подмена означала бы рекламу без маркировки —
    нарушение, и обнаруживается оно не нами."""
    import inspect

    from app.dsp import provision, targeting_creative
    assert "TEST_ERID" not in inspect.getsource(provision)
    assert "нет ЕРИД" in inspect.getsource(provision._blocker)
    assert "TEST_ERID" in inspect.getsource(targeting_creative)


def test_the_fallback_link_is_our_own_site():
    """Посадочная, когда её ещё нет, — наш сайт: по такому баннеру не кликают, а если
    кликнут, видно, чей это тест (владелец 18.09.2026)."""
    assert P.FALLBACK_LINK == "https://simb-ad.com"


# ── аудит 23.09.2026, 4.M7: отправка трафику не будит полигон и не даёт 500 ──

def test_sending_to_traffic_does_not_wake_the_targeting_campaign():
    """Кампания нацеливания просыпается от ПРОСЬБЫ о ссылке, а не от отправки комплекта:
    проснувшаяся крутится настоящим людям двое суток. До правки каждая отправка будила
    её заново."""
    db = _db()
    try:
        s = _set_with(db)
        c = FakeClient(campaign_status="STOPPED", campaign_end="2026-09-13 00:00:00")
        P.ensure_quietly(db, s, client=c)
        woke = [x for x in c.calls if x[0] in ("campaign_edit", "campaign_status")]
        assert not woke, f"отправка трафику разбудила полигон: {woke}"
    finally:
        _drop(db, s)
        db.close()


def test_repeated_send_with_a_known_creative_goes_nowhere():
    db = _db()
    try:
        s = _set_with(db, ms_targeting_creative_xxhash="ALREADY0000000002")
        c = FakeClient()
        assert P.ensure_quietly(db, s, client=c) == "ALREADY0000000002"
        assert c.calls == [], f"повторная отправка ходила в DSP: {c.calls}"
    finally:
        _drop(db, s)
        db.close()


def test_a_broken_archive_is_a_refusal_not_a_500(monkeypatch):
    """Дошивка кода в пустой креатив читает архив; битый архив бросал CreativeError,
    которую тихий вариант не ловил, — и отправка комплекта, уже закоммиченная,
    отвечала 500."""
    from app.dsp import creatives as cr

    def broken(*a, **kw):
        raise cr.CreativeError("в архиве нет index.html")

    monkeypatch.setattr(P, "_html_of", broken)
    db = _db()
    try:
        s = _set_with(db, ms_targeting_creative_xxhash="EMPTY00000000002")
        with pytest.raises(P.TargetingCreativeError):
            P.ensure(db, s, client=FakeClient(info_html=""))
        s.ms_targeting_creative_xxhash = None
        db.commit()
        monkeypatch.setattr(P, "_archive", lambda db, s: broken())
        assert P.ensure_quietly(db, s, client=FakeClient()) is None
    finally:
        _drop(db, s)
        db.close()
