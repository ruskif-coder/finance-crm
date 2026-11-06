# -*- coding: utf-8 -*-
"""Запрос посадочной — приписка к уведомлению о креативе, а не отдельное письмо (владелец 06.11.2026: «обычное уведомление о
креативе и к нему приписка, что требуется ссылка, а не два отдельных»). Запрос на проде всегда раньше отправки креатива
площадке (33 из 33), поэтому приписка ложится в «новый креатив»; запрос после отправки виден площадке в кабинете."""
import inspect
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.notify import outward
from app.routers import launch_prep as LP
from app.routers import traffic as TR


def _send(monkeypatch, ask):
    got = {}
    monkeypatch.setattr(outward, "notify_publisher", lambda db, kind, pid, **kw: got.update(kind=kind, **kw))
    monkeypatch.setattr(LP, "_deal_brand_name", lambda db, deal: "Бренд")
    monkeypatch.setattr(LP, "deal_period_text", lambda deal: "11.2026")
    monkeypatch.setattr(TR, "url_ask", lambda db, set_id, target: ask)
    TR._tell_publisher(None, SimpleNamespace(id=7), SimpleNamespace(id=3, no=2), SimpleNamespace(id=5, surface_kind="web"),
                       SimpleNamespace(id=9, domain="site.ru", name="Сайт"), SimpleNamespace(product="Услуга"))
    return got


def test_creative_notice_carries_the_url_request(monkeypatch):
    got = _send(monkeypatch, "Пришлите ссылку на карточку товара")
    assert got["kind"] == "новый креатив"
    assert "Нужна посадочная ссылка" in got["body"] and "Пришлите ссылку на карточку товара" in got["body"]
    assert ("посадочная", "нужна ссылка") in got["facts"]


def test_creative_notice_without_request_is_plain(monkeypatch):
    got = _send(monkeypatch, None)
    assert "посадочная" not in got["body"].lower() and all(k != "посадочная" for k, _ in got["facts"])


def test_url_request_sends_no_separate_letter():
    src = inspect.getsource(LP.request_member_url)
    assert "_mail_url_request(" not in src
