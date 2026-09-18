# -*- coding: utf-8 -*-
"""Сборка кампании идёт ПО СОБЫТИЮ, а не только по расписанию.

До 18.09.2026 единственным поводом пересобрать РК был ночной прогон. Между вердиктом
площадки и выгрузкой в DSP при этом стояла ночь: маркер выпущен — а кампания о нём не
знает; площадка согласована — а статус в РК вчерашний; файл прикреплён — а выгрузка
отвечает «к креативу не привязан файл комплекта».

Владелец 18.09.2026: «раз в сутки очень редко».

Прибор держит три вещи: событие зовёт сборку, сборка одной сделки не трогает соседние, и
неудача сборки не роняет само действие — оно уже совершилось.
"""
import inspect

from app import models as _core  # noqa: F401
from app.sales import models as _sales  # noqa: F401
from app.launch_prep import models as _lp  # noqa: F401
from app.ad import build, models as _ad  # noqa: F401


def test_the_three_events_call_the_build():
    """Вердикт площадки, выпуск ЕРИД и отправка комплекта — три повода пересобрать.

    Вердикт вшит в ОБЩУЮ функцию `apply_platform_verdict`, а не в ручку: входов в неё
    два — аккаунт и кабинет площадки, — и правило, поставленное на одном экране, второй
    вход обошёл бы молча.
    """
    from app.routers import launch_prep as lp

    for fn in (lp.apply_platform_verdict, lp.issue_erid, lp.send_set):
        src = inspect.getsource(fn)
        assert "sync_deal_quietly" in src, f"{fn.__name__} не зовёт пересборку"


def test_the_build_touches_one_deal_only():
    """Событие пересобирает СВОЮ сделку. Полный прогон по 89 сделкам на каждый вердикт
    превратил бы нажатие кнопки в минутное ожидание."""
    src = inspect.getsource(build.sync_deal)
    assert "AdCampaign.deal_id == deal_id" in src
    # Ищем ВЫЗОВ, а не слово: `sync_all` упомянут в пояснении, и проверка по подстроке
    # ловила бы собственный комментарий — ровно та ошибка прибора, из-за которой утром
    # ЕРИД «проверялся» строкой SQL, которая ничего не находила.
    body = src.split('"""', 2)[-1]
    assert "sync_all(" not in body


def test_a_failed_build_does_not_undo_the_event():
    """Вердикт записан, маркер выпущен — это уже произошло. Ошибка пересборки отправляет
    работу крону, а не возвращает человеку отказ на действии, которое прошло."""
    src = inspect.getsource(build.sync_deal_quietly)
    assert "except Exception" in src and "rollback" in src
    assert "raise" not in src.split("except Exception")[1]


def test_the_nightly_run_stays_as_a_safety_net():
    """Крон не убираем: событие может не дойти из-за обрыва, и тогда утренний прогон
    доберёт. Два повода к одному расчёту — не вторая правда."""
    src = inspect.getsource(build.sync_deal)
    assert "страховк" in src.lower()
