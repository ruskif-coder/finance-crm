"""Сквозной прогон сборки: одна сделка от черновика до готовности к маркеру.

**Зачем отдельный файл, если каждое правило уже проверено.** Проверено — но по частям и
на подставных объектах. `test_launch_prep_targets.py::test_set_state_is_computed_from_verdict_and_marker`
гоняет лестницу состояний на `SimpleNamespace`, а порог ЕРИД в `test_launch_prep_erid.py` —
на `_FakeDb`. Оба прибора останутся зелёными, если живой прогон перестанет ЭТИ состояния
производить: пропади в `send_set` простановка `sent_at` или заведение строки ожидания —
сравнение значений всё равно сойдётся, потому что значения ему подают руками.

Остальные приборы устроены так же: каждый сам строит нужное состояние и проверяет ОДИН
отказ. Отказ — половина правила. Вторая половина в том, что предыдущий шаг оставил после
себя ровно то, на чём стоит следующий, и её изолированный тест увидеть не может по
устройству.

Здесь цепочка идёт целиком и живыми ручками, а состояние читается тем же
`deal_creatives`, каким его читает экран: прибор видит то же, что человек.

Порядок, который он держит:

    черновик ─первичная «ок»→ готов к отправке ─отправка→ у трафика
      ─вердикт трафика→ отправлен ─вердикт площадки→ код пары, получатель согласован
      ─порог 25 %→ готов к маркеру

Продление входит сюда же: это единственное место, где сборка двигает СТАДИЮ сделки, и до
сих пор оно не было покрыто ничем.
"""
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepReview, LaunchPrepSetTarget,
                                    LaunchPrepTarget)
from app.routers import launch_prep as lp
from app.routers import traffic
from app.sales.models import (SalesDeal, SalesMediaPlan, SalesMediaPlanExtra,
                              SalesMediaPlanRow, SalesStage)

# Стенд общий с ядром модуля: своя копия фикстуры разошлась бы с ним молча. В общий
# `conftest.py` он не вынесен намеренно — имя `env` занято ещё в трёх файлах и означает
# там другое (кабинет, очередь трафика); глобальная фикстура с этим именем вводила бы в
# заблуждение сильнее, чем импорт. `noqa` ниже — на идиому pytest: ruff видит в имени
# параметра переопределение импорта, хотя это запрос фикстуры.
from tests.test_launch_prep_pairs import CODES, _ADMIN, env  # noqa: F401


def _state(db, deal_id, set_id):
    """Состояние комплекта глазами экрана — через ту же ручку чтения."""
    tree = lp.deal_creatives(deal_id, db, _ADMIN)
    return next(s["state"] for s in tree["sets"] if s["id"] == set_id)


def _target_state(db, deal_id, target_id):
    tree = lp.deal_creatives(deal_id, db, _ADMIN)
    return next(t["state"] for t in tree["targets"] if t["id"] == target_id)


def _drop_primary(db, set_id):
    """Убрать первичную проверку, которую фикстура ставит уже пройденной: прогон
    начинается с черновика, иначе первая ступень лестницы остаётся непройденной."""
    db.query(LaunchPrepReview).filter(
        LaunchPrepReview.set_id == set_id,
        LaunchPrepReview.kind == 'первичная_тт').delete(synchronize_session=False)
    db.commit()


# ── сама лестница ────────────────────────────────────────────────────────────
def test_the_chain_runs_in_order(env):  # noqa: F811
    """Одна сделка проходит все ступени, и каждая следующая недоступна до предыдущей."""
    db, cset = env.db, env.cset
    _drop_primary(db, cset.id)

    # ── черновик: отправлять нечего ──
    assert _state(db, env.deal.id, cset.id) == 'черновик'
    with pytest.raises(HTTPException) as e:
        lp.send_set(cset.id, lp.SendIn(), db, _ADMIN)
    assert 'первичная проверка' in e.value.detail.lower()

    # ── первичная проверка ──
    lp.primary_review(cset.id, lp.PrimaryReviewIn(verdict='ок'), db, _ADMIN)
    assert _state(db, env.deal.id, cset.id) == 'готов к отправке'

    # ── отправка: пары есть, мяч у ТРАФИКА ──
    assert lp.send_set(cset.id, lp.SendIn(), db, _ADMIN)["sent"] == 2
    pairs = (db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == cset.id)
             .order_by(LaunchPrepPair.id).all())
    assert len(pairs) == 2
    assert all(p.sent_at is None and p.code is None for p in pairs), (
        "отправка спрашивает трафик: площадке пара ещё не ушла и имени не получила")
    assert _state(db, env.deal.id, cset.id) == 'у трафика'

    # Площадку спросить нельзя — это следующая ступень, а не параллельная.
    with pytest.raises(HTTPException):
        lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='ок'), db, _ADMIN)

    # ── трафик ответил обоим: мяч у площадок ──
    for p in pairs:
        traffic.pair_verdict(p.id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    assert _state(db, env.deal.id, cset.id) == 'отправлен'
    assert db.query(LaunchPrepReview).filter(
        LaunchPrepReview.set_id == cset.id,
        LaunchPrepReview.kind == 'площадка').count() == 2
    db.refresh(pairs[0])
    assert pairs[0].sent_at is not None

    # ── площадка согласовала: код пары и «согласован» у получателя ──
    out = lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='ок'), db, _ADMIN)
    assert out["code"] == f"{env.deal.code}-{CODES[0]}-01"
    db.refresh(pairs[0])
    assert pairs[0].agreed_at is not None
    assert _target_state(db, env.deal.id, pairs[0].target_id) == 'согласован'

    # ── порог: одной из двух хватает (50 % при пороге 25 %) ──
    st = lp.erid_readiness(cset.id, db, _ADMIN)
    assert st["agreed"] == 1 and st["sent"] == 2
    assert st["ready"] is True, "порог 25 % достигнут — по нему и выпускается маркер"
    assert not any(b["code"] == "threshold" for b in st["blockers"])


def test_one_silent_pair_holds_the_whole_set_at_traffic(env):  # noqa: F811
    """Комплект уходит площадкам ЦЕЛИКОМ. «Частично отправлен» — не состояние.

    Прибор на живом прогоне, а не на подставных строках: правило написано в
    `_set_state`, но исполняется оно только если отправка действительно оставила
    пустую строку ожидания у второй пары.
    """
    db, cset = env.db, env.cset
    lp.send_set(cset.id, lp.SendIn(), db, _ADMIN)
    pairs = (db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == cset.id)
             .order_by(LaunchPrepPair.id).all())

    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    assert _state(db, env.deal.id, cset.id) == 'у трафика', (
        "пока хоть одна пара у трафика, комплект не считается ушедшим площадкам")

    # И вторую площадку спросить всё ещё нельзя — её трафик не смотрел.
    with pytest.raises(HTTPException):
        lp.pair_verdict(pairs[1].id, lp.PairVerdictIn(verdict='ок'), db, _ADMIN)

    traffic.pair_verdict(pairs[1].id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    assert _state(db, env.deal.id, cset.id) == 'отправлен'


# ── продление: единственное место, где сборка двигает стадию сделки ──────────
@pytest.fixture
def prolonged(env):  # noqa: F811
    """Копии сделок, созданные продлением, — со своей уборкой.

    `_purge` из соседнего файла снимает креативы и получателей по номеру комплекта, но
    ни саму сделку, ни скопированный медиаплан он не знает: их заводит только продление.
    """
    made = []
    t0 = datetime.utcnow()
    yield env, made

    db = env.db
    try:
        db.rollback()
    except Exception:
        pass

    # Кроме записанных — все копии этой сделки, заведённые за время теста. Продление
    # КОММИТИТ новую сделку до того, как вернуть её id, поэтому падение между этими
    # двумя точками оставило бы копию, о которой список не знает. Условие узкое (та же
    # исходная сделка и время после начала теста), чтобы не задеть настоящее продление.
    extra = [d.id for d in db.query(SalesDeal).filter(
        SalesDeal.prolonged_from_id == env.deal.id,
        SalesDeal.date_create >= t0).all()]

    # Каждая копия убирается своей транзакцией: сорвавшаяся на одной не должна уносить
    # с собой остальные. Соседний `_purge` подметает детей по номеру комплекта, но не
    # саму сделку — сорванная общая транзакция оставляла бы голую строку.
    failed = []
    for did in dict.fromkeys(list(made) + extra):
        try:
            _drop_deal(db, did)
            db.commit()
        except Exception as err:          # noqa: BLE001 — причина уходит в assert ниже
            db.rollback()
            failed.append((did, str(err)[:120]))
    assert not failed, f"уборка не смогла снять копии: {failed}"


def _drop_deal(db, did):
    """Снять копию сделки со всем, что завело продление и отправка."""
    plans = [p.id for p in db.query(SalesMediaPlan).filter(
        SalesMediaPlan.deal_id == did).all()]
    if plans:
        db.query(SalesMediaPlanRow).filter(
            SalesMediaPlanRow.plan_id.in_(plans)).delete(synchronize_session=False)
        db.query(SalesMediaPlanExtra).filter(
            SalesMediaPlanExtra.plan_id.in_(plans)).delete(synchronize_session=False)
        db.query(SalesMediaPlan).filter(
            SalesMediaPlan.id.in_(plans)).delete(synchronize_session=False)
    sets = [s.id for s in db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.deal_id == did).all()]
    if sets:
        from app.ad.models import AdCampaignCreative   # FK без каскада — раньше комплектов
        db.query(AdCampaignCreative).filter(
            AdCampaignCreative.root_set_id.in_(sets)).delete(synchronize_session=False)
        db.query(LaunchPrepReview).filter(
            LaunchPrepReview.set_id.in_(sets)).delete(synchronize_session=False)
        db.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id.in_(sets)).delete(synchronize_session=False)
        db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id.in_(sets)).delete(synchronize_session=False)
        db.query(LaunchPrepCreativeSet).filter(
            LaunchPrepCreativeSet.id.in_(sets)).delete(synchronize_session=False)
    db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.deal_id == did).delete(synchronize_session=False)
    db.query(SalesDeal).filter(SalesDeal.id == did).delete(synchronize_session=False)


def test_prolonged_copy_starts_on_the_assembly_stage(prolonged):
    """Копия встаёт на «Готовятся к старту» и не тащит за собой маркер.

    Стадия здесь не украшение: с неё сделка попадает в сборку, и ошибись продление —
    кампания оказалась бы заведённой, но невидимой в работе.
    """
    stand, made = prolonged
    db = stand.db
    out = lp.prolong_deal(stand.deal.id,
                          lp.ProlongIn(period_from='2026-10-01', period_to='2026-10-31'),
                          db, _ADMIN)
    made.append(out["id"])

    new = db.query(SalesDeal).filter(SalesDeal.id == out["id"]).first()
    stage = db.query(SalesStage).filter(SalesStage.stage_key == 'launch_prep').first()
    assert stage is not None, "лестница стадий без ступени сборки — сама по себе поломка"
    assert new.our_stage_id == stage.id
    assert new.prolonged_from_id == stand.deal.id
    assert new.period_from == date(2026, 10, 1)

    copied = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.deal_id == new.id).all()
    assert copied, "продлевать нечего — значит копия пуста и цепочку не проверить"
    assert all(s.origin == 'продление' for s in copied)
    assert all(s.erid is None and s.ord_creative_id is None for s in copied), (
        "маркер выдан на прошлый период: перенесённый, он стал бы вторым размещением "
        "под одним идентификатором")
    assert db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.deal_id == new.id).count() == out["targets"]


def test_prolonged_set_skips_the_traffic_step(prolonged):
    """У продления цепочка короче на ступень: трафик уже смотрел этот материал.

    Отметка идёт источником «продление», а не «авто» — разница между «никто не смотрел»
    и «смотрели в прошлом периоде» должна оставаться видимой.
    """
    stand, made = prolonged
    db = stand.db
    out = lp.prolong_deal(stand.deal.id, lp.ProlongIn(period_from='2026-10-01'), db, _ADMIN)
    made.append(out["id"])

    cset = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.deal_id == out["id"])
            .order_by(LaunchPrepCreativeSet.id).first())
    # Первичная проверка перенесена вместе с материалом — отправка проходит сразу.
    assert _state(db, out["id"], cset.id) == 'готов к отправке'

    lp.send_set(cset.id, lp.SendIn(), db, _ADMIN)
    rows = db.query(LaunchPrepReview).filter(LaunchPrepReview.set_id == cset.id).all()
    tr = [r for r in rows if r.kind == 'трафики']
    pl = [r for r in rows if r.kind == 'площадка']
    assert tr and all(r.verdict == 'ок' and r.source == 'продление' for r in tr)
    assert pl and all(r.verdict is None for r in pl), (
        "площадку спрашиваем заново: согласие давалось на прошлый период")
    assert _state(db, out["id"], cset.id) == 'отправлен', (
        "у продления комплект не задерживается у трафика")


def test_prolonged_plan_is_a_new_calculation(prolonged):
    """Продление — новый период, значит новый расчёт: ставка текущая, сумма с НДС от неё.

    До ревью 23.09.2026 копия плана брала старые суммы с НДС, но не ставку (первое же
    сохранение пересчитало бы их молча), теряла доп. услуги (сумма без НДС их включала —
    таблица с ней не сходилась) и группу версий (`group_id` пустой)."""
    from app import vat
    from app.sales import mp_row
    stand, made = prolonged
    db = stand.db
    src = SalesMediaPlan(deal_id=stand.deal.id, version=1, status="draft",
                         title="прибор продления", vat_rate=20,
                         amount_net=550_000, amount_gross=660_000)
    db.add(src)
    db.flush()
    src.group_id = src.id
    db.add(SalesMediaPlanRow(plan_id=src.id, sort_order=0, position="прибор", model="CPM",
                             inventory="web", volume=1_000_000, unit_price=500, discount=0))
    db.add(SalesMediaPlanExtra(plan_id=src.id, sort_order=0, name="Отчёт верификатора",
                               period="", mode="фикс", price=50_000, total=50_000))
    db.flush()
    try:
        out = lp.prolong_deal(stand.deal.id, lp.ProlongIn(period_from="2026-10-01"), db, _ADMIN)
        made.append(out["id"])
        cp = db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == out["id"]).one()
        rate = vat.current(db)
        assert cp.group_id == cp.id
        assert float(cp.vat_rate) == rate
        assert cp.amount_net == 550_000
        assert cp.amount_gross == mp_row.rub(550_000 * (1 + rate / 100))
        extras = db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == cp.id).all()
        assert [(e.name, e.total) for e in extras] == [("Отчёт верификатора", 50_000)]
        new = db.query(SalesDeal).filter(SalesDeal.id == out["id"]).one()
        if new.amount:
            assert new.amount_with_vat == mp_row.rub(float(new.amount) * (1 + rate / 100))
    finally:
        db.rollback()
        db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == src.id).delete()
        db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == src.id).delete()
        db.query(SalesMediaPlan).filter(SalesMediaPlan.id == src.id).delete()
        db.commit()
