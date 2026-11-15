# -*- coding: utf-8 -*-
"""Аудит 13.11.2026: проверка живости бэкенда (`/`, её зовёт healthcheck контейнера и `deploy.sh release`) не трогала базу.
При упавшей базе контейнер был «healthy», выкладка объявляла успех и не откатывалась. Сломать: вернуть статический ответ."""
import app.model_registry  # noqa: F401
from app import main


def test_root_answers_ok_when_the_database_answers():
    r = main.root()
    assert getattr(r, "status_code", 200) == 200


def test_root_is_503_when_the_database_is_down(monkeypatch):
    def dead():
        raise RuntimeError("база недоступна")
    monkeypatch.setattr(main, "_db_ping", dead)
    r = main.root()
    assert getattr(r, "status_code", 200) == 503
