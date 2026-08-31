"""Выпуск маркера: тело креатива и порог.

Запись в ЕРИР необратима, а проверить её без доступа к ОРД можно только двумя способами,
и оба здесь: тело сверяется с ОФИЦИАЛЬНОЙ схемой из фикстуры спеки, а поведение вокруг
отправки — на подменённом транспорте. До настоящего реестра ни один тест не доходит.

Схема `CreateCreativeRequest` при сверке 26.08.2026 поймала три расхождения с разбором по
стороннему клиенту: ККТУ — ровно один код третьего уровня; флаги в `required` есть, а в
описании названы необязательными; статусов двенадцать, а не шесть. Тест ловит первое и
второе; третье живёт в разводке веток отказа.
"""
import io
import json
import os
from datetime import date
from types import SimpleNamespace

import pytest

from app.ord import client as ord_client
from app.ord import submit as ord_submit
from app.ord.payloads import OrdPayloadError, creative
from app.routers.launch_prep import threshold_numbers

SPEC = os.path.join(os.path.dirname(__file__), 'fixtures', 'mediascout_v3_schemas.json')


@pytest.fixture(scope='module')
def schemas():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)['components']['schemas']


def check(schemas, name, body):
    schema = schemas[name]
    props = schema.get('properties', {})
    missing = [f for f in schema.get('required', []) if f not in body]
    assert not missing, f"{name}: не хватает обязательных полей {missing}"
    unknown = [k for k in body if k not in props]
    assert not unknown, f"{name}: полей {unknown} в схеме нет"
    for key, value in body.items():
        allowed = props[key].get('enum')
        if allowed is not None:
            assert value in allowed, f"{name}.{key}: {value!r} не из {allowed}"


def _set(**kw):
    base = dict(id=7, no=1, kktu_code=None, description=None, form='Banner',
                erid=None, erid_source='наш', ord_creative_id=None, ord_env=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _deal(**kw):
    base = dict(code='HCLA6E', is_self_promo=False, advertiser_url='https://example.test/x',
                period_from=date(2026, 9, 1), period_to=date(2026, 9, 30))
    base.update(kw)
    return SimpleNamespace(**base)


def _brand(**kw):
    base = dict(kktu_code='58.13.12', ad_object_description='описание объекта')
    base.update(kw)
    return SimpleNamespace(**base)


def _files(n=1, archive=False):
    return [SimpleNamespace(original_name=f'300x600_{i}.png', is_archive=archive,
                            content_b64='AAAA') for i in range(n)]


# ── тело креатива ────────────────────────────────────────────────────────────
def test_creative_body_matches_official_schema(schemas):
    body = creative(_set(), _files(), _deal(), _brand(), 'CT-final-1', 'CT-init-1', 'CPM')
    check(schemas, 'CreateCreativeRequest', body)


def test_flags_are_sent_explicitly(schemas):
    """Схема противоречит сама себе: флаги в `required` есть, а описание зовёт их
    необязательными со значением по умолчанию. Полагаться нельзя ни на одно прочтение."""
    body = creative(_set(), _files(), _deal(), _brand(), 'CT-final-1')
    for flag in ('isSelfPromotion', 'isNative', 'isSocial', 'isSocialQuota', 'isCobranding'):
        assert flag in body, f"флаг {flag} обязан уезжать явно"


def test_self_promo_flag_comes_from_the_deal():
    body = creative(_set(), _files(), _deal(is_self_promo=True), _brand(), 'CT-final-1')
    assert body['isSelfPromotion'] is True


def test_kktu_is_taken_from_brand_and_must_be_third_level():
    body = creative(_set(), _files(), _deal(), _brand(), 'CT-final-1')
    assert body['kktuCodes'] == ['58.13.12'], "ровно ОДИН код, а не список"

    with pytest.raises(OrdPayloadError) as e:
        creative(_set(), _files(), _deal(), _brand(kktu_code='58.13'), 'CT-final-1')
    assert 'третьего уровня' in str(e.value)

    with pytest.raises(OrdPayloadError) as e:
        creative(_set(), _files(), _deal(), _brand(kktu_code=None), 'CT-final-1')
    assert 'ККТУ' in str(e.value)


def test_kktu_comes_only_from_the_brand():
    """Код ККТУ берётся у БРЕНДА, даже если у комплекта проставлен свой.

    Переопределение на комплект заморожено 31.08.2026 (владелец): ККТУ описывает
    рекламируемый товар, а не материал, и задаётся один раз на сделку в блоке сборки ОРД.
    Замер в день заморозки: колонка использована 0 раз из 24 комплектов. Прибор смотрит
    именно на «даже если проставлен» — колонка осталась в базе и может быть непустой у
    строк, заведённых раньше.
    """
    body = creative(_set(kktu_code='11.22.33'), _files(), _deal(), _brand(), 'CT-final-1')
    assert body['kktuCodes'] == ['58.13.12'], 'в реестр ушёл код комплекта вместо кода бренда'


def test_description_is_still_overridable():
    """А вот описание объекта рекламирования переопределяется — оно про МАТЕРИАЛ.

    Разница осознанная: у двух баннеров одного бренда описание может отличаться, код
    товара — нет.
    """
    body = creative(_set(description='своё описание'), _files(), _deal(), _brand(), 'CT-final-1')
    assert body['description'] == 'своё описание'


def test_idempotency_key_is_deterministic():
    """Ключ идемпотентности — наш номер комплекта, а не случайное число: без него повтор
    после обрыва связи заводит в ЕРИР второй креатив, который не отозвать."""
    a = creative(_set(id=42), _files(), _deal(), _brand(), 'CT-final-1')
    b = creative(_set(id=42), _files(), _deal(), _brand(), 'CT-final-1')
    assert a['nativeCustomerId'] == b['nativeCustomerId'] == 'set-42'


def test_archive_flag_travels_with_the_file():
    body = creative(_set(form='BannerHtml5'), _files(archive=True), _deal(), _brand(),
                    'CT-final-1')
    assert body['mediaData'][0]['isArchive'] is True


def test_body_without_files_is_refused():
    with pytest.raises(OrdPayloadError) as e:
        creative(_set(), [], _deal(), _brand(), 'CT-final-1')
    assert 'нет ни одного файла' in str(e.value)


def test_body_without_final_contract_is_refused():
    """Креатив нельзя создать, не назвав доходный договор."""
    with pytest.raises(OrdPayloadError) as e:
        creative(_set(), _files(), _deal(), _brand(), None)
    assert 'доходный договор' in str(e.value)


def test_unknown_form_is_refused_not_passed_through():
    with pytest.raises(OrdPayloadError) as e:
        creative(_set(form='Карусель'), _files(), _deal(), _brand(), 'CT-final-1')
    assert 'не из перечня' in str(e.value)


# ── порог ────────────────────────────────────────────────────────────────────
class _FakeQuery:
    def __init__(self, rows): self._rows = rows
    def filter(self, *a, **k): return self
    def all(self): return self._rows


def _pairs(sent, agreed):
    return [SimpleNamespace(agreed_at=(1 if i < agreed else None)) for i in range(sent)]


def test_the_share_no_longer_gates_the_marker():
    """Порог согласовавших снят 31.08.2026 (владелец: «от него отказались»).

    Раньше маркер не выпускался, пока не набрана доля ответивших: четверть от четырёх —
    один, от восьми — двое. Теперь число ответов ни на что не влияет, и прибор держит
    именно это: сколько бы ни молчало, выпуск не заперт.
    """
    for sent, agreed in ((4, 1), (8, 1), (3, 0), (1, 0), (5, 0)):
        st = threshold_numbers(_pairs(sent, agreed))
        assert st["ready"] is True, (sent, agreed)
        assert st["need"] == 0, st


def test_the_counter_still_answers_how_many_replied():
    """Числа остались справкой: «согласовали N из M» показывается на экране.

    Знаменатель — те, КОМУ отправили, а не те, кто ответил. Отказ из него не выпадает:
    строка «1 из 4» описывает состояние опроса, и потеряй она отказавшихся, читалась бы
    как «спросили одного».
    """
    st = threshold_numbers(_pairs(4, 1))
    assert (st["sent"], st["agreed"]) == (4, 1)


def test_no_recipients_means_not_ready():
    st = threshold_numbers([], 0.25)
    assert st["ready"] is False and st["need"] == 0


# ── отказы до сети ───────────────────────────────────────────────────────────
def test_foreign_marker_is_not_registered(monkeypatch):
    """У саморекламы маркер выпускает площадка: наша регистрация за ним не стоит."""
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до сети доходить не должно'))
    with pytest.raises(ord_submit.OrdSubmitRefused) as e:
        ord_submit.register_creative(None, _set(erid_source='площадки'), _files(),
                                     _deal(), _brand(), 'CT-final-1', None, None)
    assert 'выпускает площадка' in str(e.value)


def test_already_marked_set_is_refused(monkeypatch):
    monkeypatch.setattr(ord_client, 'env', lambda: 'demo')
    monkeypatch.setattr(ord_client, 'post',
                        lambda p, b: pytest.fail('до сети доходить не должно'))
    with pytest.raises(ord_submit.OrdSubmitRefused) as e:
        ord_submit.register_creative(None, _set(erid='ERID-1', ord_env='demo'), _files(),
                                     _deal(), _brand(), 'CT-final-1', None, None)
    assert 'уже есть маркер' in str(e.value)


# ── договорная цепочка креатива ──────────────────────────────────────────────
def test_chain_asks_the_same_resolver_as_the_assembly_screen():
    """Креатив обязан уйти под ТОТ доходный договор, который показывает экран.

    Найдено 27.08.2026 на живой сделке: `_ord_chain` читал колонку РУЧНОГО выбора
    (`deal.ord_final_contract_id`), пустую у всех сделок, и уходил в запасную ветку —
    брал доходный из первой попавшейся связи изначального договора. Изначальный бывает
    привязан к нескольким доходным (22 из 126, до трёх у одного), и на HCLA6E запасная
    ветка выдавала ЧУЖОЙ договор, которого у нас в реестре нет вовсе, при зелёной
    лестнице на экране. Креатив ушёл бы в ЕРИР под чужим доходным и не отозвался бы.
    """
    from app.database import SessionLocal
    from app.ord import client as ord_client
    from app.ord import registry
    from app.ord.matching import resolve_final
    from app.routers.launch_prep import _ord_chain
    from app.sales.models import SalesDeal

    db = SessionLocal()
    try:
        env = ord_client.env()
        checked = 0
        for deal in db.query(SalesDeal).filter(
                SalesDeal.ord_initial_contract_id.isnot(None)).limit(30).all():
            chosen = resolve_final(db, deal).contract
            # Сравнивать надо не сырой идентификатор колонки, а идентификатор ЭТОГО
            # договора на ТЕКУЩЕМ контуре: один и тот же договор зовётся на демо и на
            # проде по-разному, и «не совпало» иначе означало бы просто другой контур.
            expected = (registry.known_id(db, 'final_contract', chosen.id, env,
                                          chosen.ord_contract_id, chosen.ord_env)
                        if chosen is not None else None)
            got, _ = _ord_chain(db, deal)
            assert got == expected, (
                f"сделка {deal.code}: экран показывает доходный "
                f"{getattr(chosen, 'contract_number', None)} ({expected}), "
                f"а креатив уйдёт под {got}")
            checked += 1
    finally:
        db.close()
    if not checked:
        pytest.skip("нет сделок с привязанным изначальным договором — сверять нечего")


def test_chain_does_not_fall_back_to_an_arbitrary_link():
    """Структурный пин: запасной ветки «взять первую связь» быть не должно.

    Поведенческий тест выше зависит от того, что в базе есть подходящая сделка. Этот
    не зависит ни от чего: он смотрит на сам код. Возврат `first()` по связям читался
    бы как разумный запасной путь, поэтому запрет записан, а не подразумевается.
    """
    import inspect

    from app.routers import launch_prep

    body = inspect.getsource(launch_prep._ord_chain)
    assert 'OrdInitialFinalLink' not in body, (
        "в выборе доходного договора вернулась ветка по связям изначального — "
        "она берёт произвольную из нескольких")
    assert 'resolve_final' in body, (
        "цепочка перестала спрашивать тот же резолвер, что и экран сборки")


# ── готовность к маркеру: блокеры и маркировка бренда ────────────────────────
def test_blockers_carry_a_code_not_only_a_russian_phrase():
    """Экран решает по КОДУ, какой блокер можно нажать и починить не уходя.

    Разбирать русскую фразу на фронте значило бы привязать поведение кнопки к
    формулировке, которую однажды перепишут, — и кнопка тихо перестала бы появляться.
    """
    from types import SimpleNamespace as NS

    from app.database import SessionLocal
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.routers.launch_prep import erid_readiness

    db = SessionLocal()
    try:
        cset = db.query(LaunchPrepCreativeSet).first()
        if cset is None:
            pytest.skip("в базе нет ни одного комплекта — проверять нечего")
        answer = erid_readiness(cset.id, db=db,
                                current_user=NS(role=NS(key='admin'), id=None, name='тест'))
    finally:
        db.close()

    assert isinstance(answer['blockers'], list)
    for b in answer['blockers']:
        assert set(b) == {'code', 'text'}, f"блокер потерял форму: {b}"
        assert b['code'] in ('threshold', 'chain', 'kktu'), (
            f"неизвестный код блокера {b['code']} — экран не будет знать, что с ним делать")
    assert 'brand' in answer, (
        "маркировка бренда обязана приходить всегда, а не только когда она мешает: "
        "из неё же рисуется справочная строка «что проставлено»")


def test_brand_marking_resolves_the_kktu_name_from_the_mirror():
    """Код без расшифровки — это «12.2.2» и догадка, что это значит.

    Имя категории берётся из зеркала справочника, а не хранится рядом с кодом: оно
    принадлежит классификатору. Нет зеркала — показываем голый код, и это честно.
    """
    from app.database import SessionLocal
    from app.ord.models import OrdKktu
    from app.routers.launch_prep import _brand_marking_out
    from app.sales.models import SalesBrand

    db = SessionLocal()
    try:
        if not db.query(OrdKktu).first():
            pytest.skip("справочник ККТУ не залит")
        brand = (db.query(SalesBrand)
                   .filter(SalesBrand.kktu_code.isnot(None)).first())
        if brand is None:
            pytest.skip("ни у одного бренда нет кода ККТУ")
        out = _brand_marking_out(db, brand)
    finally:
        db.close()

    assert out['kktu_code'] == brand.kktu_code
    assert out['kktu_name'], (
        f"код {brand.kktu_code} не нашёлся в зеркале — на экране останется голый код")

