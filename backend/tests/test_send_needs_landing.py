# -*- coding: utf-8 -*-
"""Без посадочной и без запроса ссылки материал площадке не уходит.

Владелец 18.09.2026. Состояний у ссылки три: «есть», «запрошена», «нужна». Третье значит,
что о ней ещё даже не спрашивали, — и именно оно доводило до тупика: материал уезжал,
площадка согласовывала, выпускался ЕРИД, а вести рекламу было некуда. Обнаруживалось это
на старте, когда чинить поздно и дорого.

Запрошенная ссылка отправку НЕ запирает: ждать её можно параллельно согласованию. Она
запирает согласование — то правило стоит на вердикте и остаётся там.
"""
import inspect


def test_sending_refuses_when_nobody_even_asked():
    """Отказ стоит на ОТПРАВКЕ и называет площадки поимённо.

    «Не хватает ссылки» без списка означает обход двадцати одной строки глазами.
    """
    from app.routers import launch_prep as lp

    src = inspect.getsource(lp.send_set)
    # С 25.09.2026 проверяется посадочная ЭТОГО креатива (строка состава), а не
    # площадки сделки.
    assert 'url_state(own.get((set_id, t.id))) == "нужна"' in src, "проверки состояния ссылки нет"
    assert "silent" in src and '", ".join(sorted(silent))' in src, (
        "в отказе должны быть названы площадки")


def test_a_requested_link_does_not_block_sending():
    """«Запрошена» проходит: иначе работа встанет на время ожидания площадки, а ждать
    её можно параллельно согласованию."""
    from app.routers.launch_prep import url_state

    class T:
        advertiser_url = None
        url_requested_at = "2026-09-18"

    assert url_state(T()) == "запрошена"
    src = inspect.getsource(__import__("app.routers.launch_prep",
                                       fromlist=["x"]).send_set)
    assert '"запрошена"' not in src.split('url_state(own.get(')[1][:200], (
        "запрошенная ссылка не должна запирать отправку")


def test_the_gate_lives_in_the_endpoint_not_on_the_button():
    """Входов в отправку больше одного, и правило, оставленное на кнопке экрана, обошли
    бы соседним путём — так уже было с вердиктом площадки."""
    from app.routers import launch_prep as lp

    assert 'url_state(own.get((set_id, t.id))) == "нужна"' in inspect.getsource(lp.send_set)
