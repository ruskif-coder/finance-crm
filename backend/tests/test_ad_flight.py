"""Ядро расчётов дашборда трафика: флайт, прогноз, распределение, пересчёт плана.

Почему приборов здесь много и почему они на датах, а не на «примерно»: на этих числах
стоит весь экран, и ошибка в них не падает, а показывает НЕПРАВИЛЬНУЮ картину — красный
недокрут у РК, которая ещё не стартовала, или зелёный прогноз у той, что провалена.

Хендофф считал флайт номерами дней внутри месяца (`flight: [16, 30]`, опорный день 12).
Здесь всё от настоящих дат — и половина этих тестов существует ровно потому, что перенос
«номер дня → дата» это место, где легко потерять единицу или границу.
"""
from datetime import date

from app.ad.flight import (PLACEMENT_IN_PLAN, PLACEMENT_MANUAL, PLACEMENT_RUNNING,
                           PLACEMENT_STATUSES,
                           culprits, daily_buckets, distribute, flight_of, forecast_of,
                           need_per_day, progress, under_of)

SEP = date(2026, 9, 1)
TODAY = date(2026, 9, 12)


def _fl(d1, d2, today=TODAY):
    return flight_of(date(2026, 9, d1), date(2026, 9, d2), today)


# ── флайт ────────────────────────────────────────────────────────────────────

def test_flight_counts_both_ends():
    """Длина флайта включает ОБА конца: 1–30 сентября это 30 дней, а не 29."""
    fl = _fl(1, 30)
    assert fl.length == 30
    assert fl.done == 12, 'на 12-е отчитано 12 дней, а не 11'
    assert fl.left == 18


def test_flight_in_the_future_has_no_elapsed_days():
    """РК стартует 16-го, сегодня 12-е — отчитано ноль дней.

    Главный случай, ради которого темп считается от флайта, а не от месяца: такая РК
    не должна выглядеть проваленной. Если `done` окажется больше нуля, экран немедленно
    покрасит её красным.
    """
    fl = _fl(16, 30)
    assert fl.done == 0
    assert fl.pace == 0
    assert not fl.is_over


def test_finished_flight_has_no_remainder():
    """Флайт 1–12 на 12-е закончился: остаток 0, «нужно в день» не существует."""
    fl = _fl(1, 12)
    assert fl.done == fl.length == 12
    assert fl.left == 0
    assert fl.is_over
    assert need_per_day(1_000_000, 400_000, fl) is None, (
        'у закончившегося флайта «нужно в день» обязано быть None, а не нулём: ноль '
        'читается как «всё в порядке»'
    )


def test_flight_longer_than_a_month():
    """РК через границу месяца. На номерах дней такой флайт не считался вовсе."""
    fl = flight_of(date(2026, 8, 20), date(2026, 10, 5), TODAY)
    assert fl.length == 47
    assert fl.done == 24
    assert 0 < fl.pace < 1


def test_no_dates_is_unknown_not_zero():
    assert flight_of(None, date(2026, 9, 30), TODAY) is None
    assert flight_of(date(2026, 9, 30), date(2026, 9, 1), TODAY) is None, 'перевёрнутое окно'


# ── прогноз и недокрут ───────────────────────────────────────────────────────

def test_forecast_is_linear_on_the_flight():
    """Половина флайта пройдена, откручена половина плана — прогноз равен плану."""
    fl = _fl(1, 24)                       # 24 дня, отчитано 12
    assert forecast_of(1_000_000, 500_000, fl) == 1_000_000


def test_forecast_needs_an_elapsed_day():
    """Без отчитанных дней прогноза нет — делить не на что."""
    assert forecast_of(1_000_000, 0, _fl(16, 30)) is None


def test_under_never_goes_negative():
    """Перекрут недокрутом не считается."""
    assert under_of(1_000_000, 1_400_000) == 0


def test_progress_keeps_every_key_even_without_data():
    """Ключи есть ВСЕГДА, пустота — это None.

    Пропуск ключа на фронте превращается в `undefined` и рисуется как «undefined»,
    а не как прочерк, — поэтому контракт фиксируется прибором.
    """
    p = progress(None, None, None, None, TODAY)
    assert set(p) == {'days_total', 'days_to_start', 'days_done', 'days_left', 'pace',
                      'flight_over', 'forecast', 'under', 'done_pct', 'speed',
                      'need_per_day'}
    assert all(v is None for v in p.values())


def test_progress_separates_pace_from_speed():
    """`pace` — доля (0…1), `speed` — показы в день. Разные единицы, разные имена.

    До 04.09.2026 поле `pace` в ответе означало показы в день. Совпадение имени при
    смене единицы — ровно та ошибка, которую этот прибор и держит.
    """
    p = progress(2_400_000, 1_200_000, date(2026, 9, 1), date(2026, 9, 24), TODAY)
    assert p['pace'] == 0.5, 'ожидаемая доля выполнения на половине флайта'
    assert p['speed'] == 100_000, 'фактический темп в показах за день'
    assert p['days_left'] == 12
    assert p['need_per_day'] == 100_000


# ── распределение по площадкам ───────────────────────────────────────────────

def _p(domain, status, weight, fact=None, pid=None):
    return {'publisher_id': pid, 'domain': domain, 'status': status,
            'weight': weight, 'fact': fact}


def test_pause_keeps_its_share_but_does_not_run():
    """ПАУЗА остаётся в раскладке, ожидание — нет (владелец 04.09.2026).

    «Пауза — приостановка открутки, из суточного плана площадка НЕ исключается»: её доля
    сохраняется за ней. Иначе снятие паузы означало бы новую раскладку, и каждая пауза
    перекраивала бы план всей РК.

    Разведены два разных вопроса: `running` — крутит ли СЕЙЧАС (по нему «крутит N из M»),
    `in_plan` — участвует ли в распределении.
    """
    places = [_p('a.ru', 'запущен', 600), _p('b.ru', 'пауза', 400),
              _p('c.ru', 'у площадки', 500), _p('d.ru', 'ждёт запуска', 500)]
    by = {r['domain']: r for r in distribute(1_000_000, None, _fl(1, 30), places)['rows']}

    assert by['a.ru']['share'] == 0.6 and by['b.ru']['share'] == 0.4
    assert by['b.ru']['in_plan'] is True and by['b.ru']['running'] is False
    assert by['b.ru']['plan_show'] == 400_000, 'у паузы остаётся её план'
    assert by['c.ru']['share'] == 0 and by['d.ru']['share'] == 0, 'ожидание в раскладку не входит'


def test_turning_a_place_off_hands_its_volume_to_the_rest():
    """Отключение («завершена») выводит площадку из раскладки, объём уходит остальным."""
    places = [_p('a.ru', 'запущен', 600), _p('b.ru', 'запущен', 400)]
    before = {r['domain']: r for r in distribute(1_000_000, None, _fl(1, 30), places)['rows']}
    assert before['b.ru']['plan_show'] == 400_000

    places[1]['status'] = 'завершена'
    after = {r['domain']: r for r in distribute(1_000_000, None, _fl(1, 30), places)['rows']}
    assert after['a.ru']['share'] == 1.0 and after['a.ru']['plan_show'] == 1_000_000
    assert after['b.ru']['share'] == 0 and after['b.ru']['in_plan'] is False


def test_place_without_weight_is_flagged_not_hidden():
    """Нет индекса в балансировщике — доля 0, но это ОТДЕЛЬНЫЙ признак.

    «Нет индекса» и «выключена» — разные вещи: первая подключена и ждёт данных, вторую
    выключил человек. Смешать их значит потерять список того, что надо дозаполнить.
    """
    places = [_p('a.ru', 'запущен', 600), _p('b.ru', 'запущен', None)]
    rows = {r['domain']: r for r in distribute(1_000_000, None, _fl(1, 30), places)['rows']}
    assert rows['b.ru']['no_weight'] is True and rows['b.ru']['running'] is True
    assert rows['a.ru']['share'] == 1.0, 'вес выбывшей не размазался — он просто не в сумме'


def test_share_sum_below_one_is_visible():
    """Сумма долей меньше единицы — сигнал, что объём стоит на выключенных."""
    places = [_p('a.ru', 'запущен', 600), _p('b.ru', 'завершена', 400)]
    assert distribute(1_000_000, None, _fl(1, 30), places)['share_sum'] == 1.0
    places[0]['status'] = 'у трафика'
    assert distribute(1_000_000, None, _fl(1, 30), places)['share_sum'] == 0.0


def test_place_fact_is_not_invented():
    """Факт площадки берётся из среза; нет среза — None, а не пропорция от факта РК.

    В макете факт площадки нарисован пропорцией — это правдоподобное число, за которым
    не стоит ни одного замера. На экране оно неотличимо от настоящего.
    """
    rows = distribute(1_000_000, 500_000, _fl(1, 30),
                      [_p('a.ru', 'запущен', 600)])['rows']
    assert rows[0]['fact_shows'] is None
    assert rows[0]['under'] is None


# ── динамика и пересчёт плана ────────────────────────────────────────────────

def test_past_buckets_keep_the_original_plan():
    """Прошедшие дни держат исходный план — их не переиграть."""
    fl = _fl(1, 30)
    out = daily_buckets(3_000_000, 900_000, fl, {}, today=TODAY)
    past = [b for b in out['buckets'] if b['days_past'] == b['days']]
    assert past and all(not b['repaced'] for b in past)
    assert past[0]['plan'] == round(3_000_000 / 30)


def test_future_buckets_are_repaced_from_the_shortfall():
    """Будущие дни получают (план − факт) ÷ остаток и помечаются `repaced`."""
    fl = _fl(1, 30)
    out = daily_buckets(3_000_000, 900_000, fl, {}, today=TODAY)
    need = (3_000_000 - 900_000) / 18
    future = [b for b in out['buckets'] if b['days_past'] == 0]
    assert future and all(b['repaced'] for b in future)
    assert future[0]['plan'] == round(need)
    assert out['need_per_day'] == round(need)


def test_interval_is_clipped_to_the_flight():
    """Выбранные даты не могут дать столбцов больше, чем дней в РК."""
    fl = _fl(16, 30)
    out = daily_buckets(1_000_000, None, fl, {}, date_from=date(2026, 9, 1),
                        date_to=date(2026, 10, 31), today=TODAY)
    assert out['buckets'][0]['date_from'] == date(2026, 9, 16)
    assert out['buckets'][-1]['date_to'] == date(2026, 9, 30)
    assert sum(b['days'] for b in out['buckets']) == 15


def test_week_grain_groups_by_seven():
    fl = _fl(1, 30)
    out = daily_buckets(3_000_000, 900_000, fl, {}, grain='week', today=TODAY)
    assert [b['days'] for b in out['buckets']] == [7, 7, 7, 7, 2]


def test_facts_land_in_their_own_bucket():
    fl = _fl(1, 30)
    facts = {date(2026, 9, 3): (120_000, 700), date(2026, 9, 4): (80_000, 300)}
    out = daily_buckets(3_000_000, 200_000, fl, facts, grain='week', today=TODAY)
    assert out['buckets'][0]['shows'] == 200_000
    assert out['buckets'][0]['clicks'] == 1_000


# ── площадки-виновники ───────────────────────────────────────────────────────

def test_culprits_sum_undershoot_across_campaigns():
    """Недокрут одной площадки складывается по всем РК, статус — «частично» при разнобое."""
    rows = [
        {'publisher_id': 1, 'domain': 'dialog.ru', 'status': 'запущен', 'under': 500_000},
        {'publisher_id': 1, 'domain': 'dialog.ru', 'status': 'пауза', 'under': 300_000},
        {'publisher_id': 2, 'domain': 'aptekabv.ru', 'status': 'запущен', 'under': 200_000},
        {'publisher_id': 3, 'domain': 'zdes.ru', 'status': 'запущен', 'under': None},
    ]
    out = culprits(rows)
    assert [c['domain'] for c in out] == ['dialog.ru', 'aptekabv.ru'], 'нулевые не попадают'
    assert out[0]['under'] == 800_000 and out[0]['campaigns'] == 2
    assert out[0]['status'] == 'частично', 'разные статусы в разных РК — не выбираем один'
    assert out[1]['status'] == 'запущен'
    assert round(sum(c['share'] for c in out), 4) == 1.0


# ── словарь статусов ─────────────────────────────────────────────────────────

def test_status_vocabulary_is_pinned():
    """Слова сравниваются буквально, и переименование тихо ломает и экран, и раскладку.

    Первые три ставит конвейер согласования, последние три — трафик руками
    (владелец 04.09.2026).
    """
    assert PLACEMENT_STATUSES == ('у трафика', 'у площадки', 'ждёт запуска',
                                  'запущен', 'пауза', 'завершена')
    assert PLACEMENT_MANUAL == ('запущен', 'пауза', 'завершена')
    assert PLACEMENT_RUNNING == ('запущен',), 'крутит — только запущенная'
    assert PLACEMENT_IN_PLAN == ('запущен', 'пауза'), 'пауза из плана не исключается'


# ── статус из конвейера ──────────────────────────────────────────────────────

def test_chain_status_follows_the_ball():
    """Порядок разбора повторяет развёрнутую цепочку: сначала трафик, потом площадка."""
    from app.ad.flight import chain_status
    assert chain_status(None, None, has_pair=False) == 'у трафика', 'ничего не отправляли'
    assert chain_status(None, None, has_pair=True) == 'у трафика'
    assert chain_status('ок', None, has_pair=True) == 'у площадки'
    assert chain_status('ок', 'ок', has_pair=True) == 'ждёт запуска'
    assert chain_status('на переделку', None, has_pair=True) == 'у трафика', (
        'завёрнутый материал возвращается к трафику, а не ждёт площадку'
    )


def test_manual_status_overrides_the_chain():
    """Трафик нажал «запущен» — конвейер больше не двигает строку."""
    from app.ad.flight import effective_status
    assert effective_status('запущен', 'ждёт запуска') == 'запущен'
    assert effective_status('пауза', 'у трафика') == 'пауза'
    assert effective_status('у трафика', 'ждёт запуска') == 'ждёт запуска', (
        'нересурсный статус в базе не должен перекрывать свежий расчёт'
    )


# ── третий этаж: креативы под площадкой ──────────────────────────────────────

def test_placement_volume_splits_evenly_and_the_sum_matches():
    """План площадки делится ПОРОВНУ, остаток — первым по номеру.

    Креативы равнозначны, весов у них нет (владелец 04.09.2026). Остаток обязан
    доставаться кому-то: потерянная единица выглядит безобидно ровно до сверки, где
    не сходится итог площадки.
    """
    from app.ad.flight import split_evenly
    cs = [{'id': 3, 'creative_no': 3, 'status': 'запущен'},
          {'id': 1, 'creative_no': 1, 'status': 'запущен'},
          {'id': 2, 'creative_no': 2, 'status': 'пауза'}]
    out = split_evenly(1000, cs)
    assert [c['creative_no'] for c in out] == [1, 2, 3], 'порядок — по номеру, не по вводу'
    assert [c['plan_show'] for c in out] == [334, 333, 333]
    assert sum(c['plan_show'] for c in out) == 1000
    assert all(c['in_plan'] for c in out)
    assert [c['running'] for c in out] == [True, False, True], 'пауза в плане, но не крутит'


def test_rejected_creative_gets_nothing_and_frees_its_volume():
    """Отклонённый не получает НИЧЕГО (None, не ноль), его объём уходит остальным."""
    from app.ad.flight import split_evenly
    cs = [{'id': 1, 'creative_no': 1, 'status': 'запущен'},
          {'id': 2, 'creative_no': 2, 'status': 'отклонён'}]
    out = {c['creative_no']: c for c in split_evenly(1000, cs)}
    assert out[1]['plan_show'] == 1000
    assert out[2]['plan_show'] is None and out[2]['in_plan'] is False


def test_counts_do_not_derive_launched_from_agreed():
    """«Запущено» — есть в кабинете МС (`ms_creative_xxhash`), а не «согласовано».

    Согласованный креатив может ещё не уехать в DSP. Вывести одно из другого значило бы
    обещать открутку, которой нет.
    """
    from app.ad.flight import creative_counts
    cs = [{'status': 'согласован', 'ms_creative_xxhash': None},
          {'status': 'запущен', 'ms_creative_xxhash': 'AABBCCDD00112233'},
          {'status': 'у площадки'}]
    assert creative_counts(cs) == {'total': 3, 'agreed': 2, 'live': 1}


def test_placement_state_is_the_best_of_its_creatives():
    """Статус площадки — самый продвинутый из её креативов, а не последний по времени.

    До 04.09.2026 бралась ПОСЛЕДНЯЯ пара. С несколькими креативами это означало бы, что
    свежая переделка одного баннера откатывает в «у трафика» площадку, которая уже
    крутит другой.
    """
    from app.ad.flight import best_chain_status
    assert best_chain_status(['у трафика', 'ждёт запуска', 'у площадки']) == 'ждёт запуска'
    assert best_chain_status(['у трафика', 'у площадки']) == 'у площадки'
    assert best_chain_status([]) == 'у трафика', 'креативов нет — материал не отправляли'


def test_placement_cannot_start_without_an_agreed_creative():
    """«Площадка запущена только при хоть одном согласованном креативе»."""
    from app.ad.flight import can_start_placement
    assert can_start_placement(['согласован']) is True
    assert can_start_placement(['запущен', 'у трафика']) is True
    assert can_start_placement(['у трафика', 'у площадки']) is False
    assert can_start_placement([]) is False, 'без креативов запускать нечего'


# ── статус РК: вычисляемый с ручными оверрайдами ─────────────────────────────

def test_campaign_status_is_derived_from_what_is_under_it():
    """«Запущена» — ФАКТ работы, а не намерение: хоть одна площадка крутит.

    До 04.09.2026 статус был просто хранимым полем: синк ставил «ожидает сборки» и больше
    не трогал, то есть РК оставалась в нём навсегда, а «запущена» на экране означало лишь
    то, что кто-то написал это руками.
    """
    from app.ad.flight import campaign_chain_status
    assert campaign_chain_status(True, 5, 2, True) == 'запущена'
    assert campaign_chain_status(True, 5, 0, True) == 'готова', 'всё есть, но никто не крутит'
    assert campaign_chain_status(True, 5, 0, False) == 'ожидает сборки', 'нет согласованных'
    assert campaign_chain_status(False, 5, 0, True) == 'ожидает сборки', 'нет плана'
    assert campaign_chain_status(True, 0, 0, True) == 'ожидает сборки', 'нет площадок'


def test_manual_campaign_status_wins_over_the_calculation():
    """Пауза и стоп — решения человека, и расчёт их не отменяет.

    Иначе поставленную на паузу РК возвращало бы в «запущена» первой же площадкой,
    которая продолжает крутить, — то есть пауза не работала бы вовсе.
    """
    from app.ad.flight import CAMPAIGN_MANUAL, effective_campaign_status
    assert effective_campaign_status('пауза', 'запущена') == 'пауза'
    assert effective_campaign_status('остановлена', 'запущена') == 'остановлена'
    assert effective_campaign_status('окончена', 'готова') == 'окончена'
    # «Запущена» в поле — это снятый оверрайд: дальше решает расчёт.
    assert effective_campaign_status('запущена', 'готова') == 'готова'
    assert effective_campaign_status('ожидает сборки', 'запущена') == 'запущена'
    assert 'запущена' not in CAMPAIGN_MANUAL


def test_countdown_to_start_replaces_days_left_before_the_flight():
    """У нестартовавшей РК осмысленно «до старта N дн», а не «осталось N дней».

    «Осталось 30» у кампании, которая начнётся послезавтра, читается как «идёт и вот-вот
    кончится». Число то же — длина флайта, — а смысл противоположный.
    """
    p = progress(1000, None, date(2026, 9, 16), date(2026, 10, 15), TODAY)   # TODAY = 12.09
    assert p['days_done'] == 0
    assert p['days_to_start'] == 4
    assert p['days_left'] == 30, 'осталось = вся длина флайта — потому и не годится в подпись'
    p2 = progress(1000, 300, date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert p2['days_to_start'] is None, 'РК уже идёт — обратного отсчёта нет'
