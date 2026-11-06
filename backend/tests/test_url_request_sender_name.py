# -*- coding: utf-8 -*-
"""Запрос ссылки площадке (прод 06.11.2026): подстановка «сотрудник» брала `user.full_name`, которого у User нет, — каждая отправка
падала 500 с 23.09. Имя сотрудника — `User.name`, без имени — почта."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.models import User
from app.routers import launch_prep as LP


def _values(monkeypatch, user):
    monkeypatch.setattr(LP, "_deal_brand_name", lambda db, deal: "Бренд")
    monkeypatch.setattr(LP, "deal_period_text", lambda deal: "октябрь 2026")
    return LP._url_request_values(None, SimpleNamespace(), SimpleNamespace(name="Площадка", domain="site.ru"), user, "текст")


def test_sender_is_user_name(monkeypatch):
    assert _values(monkeypatch, User(name="Иван Петров", email="i@example.com"))["сотрудник"] == "Иван Петров"


def test_sender_falls_back_to_email(monkeypatch):
    assert _values(monkeypatch, User(name="", email="i@example.com"))["сотрудник"] == "i@example.com"
