# -*- coding: utf-8 -*-
"""Письмо о правах на изображения: границы, которые ошибаются молча.

Три правила, и каждое ломается так, что видно не сразу:

· письмо НЕ попадает в список файлов комплекта: пустому комплекту оно выдумало бы форму
  креатива, и она уехала бы в ЕРИР (замерено — рядом с материалом форма не меняется);
· список расширений у письма СВОЙ и уже креативного — без zip и html, потому что архив
  у материала разрешён ради песочницы, а песочница заводилась под чужой исполняемый код;
· показанное площадке письмо не подменяется — иначе «при каком письме согласовали»
  становится недоказуемым.
"""
import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepCreativeSet
from app.routers import launch_prep as lp


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.rollback()
    d.close()


def test_letter_extensions_are_narrower_than_creative_ones():
    """Документ нельзя пускать по пути материала.

    У креатива в списке есть `.zip` и `.html` — они едут в песочницу. Письмо туда не
    попадает и попадать не должно: песочница раздаётся БЕЗ авторизации.
    """
    assert ".zip" not in lp.RIGHTS_LETTER_EXTENSIONS
    assert ".html" not in lp.RIGHTS_LETTER_EXTENSIONS
    assert ".svg" not in lp.RIGHTS_LETTER_EXTENSIONS, "внутри SVG бывает скрипт"
    assert lp.RIGHTS_LETTER_EXTENSIONS < lp.ALLOWED_EXTENSIONS | lp.RIGHTS_LETTER_EXTENSIONS
    assert {".pdf", ".doc", ".docx"} <= lp.RIGHTS_LETTER_EXTENSIONS


def test_letter_among_files_would_invent_a_form():
    """Краевой случай, ради которого письмо хранится ОТДЕЛЬНО от файлов комплекта.

    Замер 07.09.2026 поправил моё же обоснование: рядом с материалом письмо форму не
    меняет — архив и видео побеждают расширение документа. Но комплект БЕЗ материала с
    одним письмом внутри объявил бы `Banner`, то есть форму, которой не из чего взяться,
    и она уехала бы в ЕРИР. Прибор держит именно это, а не более широкое утверждение.
    """
    class F:
        def __init__(self, name):
            self.original_name = name

    assert lp._derive_form([F("b.zip"), F("rights.pdf")]) == "BannerHtml5"
    assert lp._derive_form([F("v.mp4"), F("rights.pdf")]) == "Video"
    assert lp._derive_form([]) is None
    assert lp._derive_form([F("rights.pdf")]) == "Banner", (
        "письмо в составе файлов выдумывает форму пустому комплекту — "
        "ровно поэтому оно хранится колонками")


def test_set_carries_letter_columns(db):
    """Колонки на месте и читаются моделью — миграция и модель не разошлись."""
    row = db.query(LaunchPrepCreativeSet).first()
    if row is None:
        pytest.skip("на стенде нет ни одного комплекта")
    for attr in ("rights_letter_path", "rights_letter_name", "rights_letter_type",
                 "rights_letter_size", "rights_letter_at", "rights_letter_by"):
        assert hasattr(row, attr), f"модель не знает {attr}"


def test_letter_is_served_as_attachment_only():
    """Письмо отдаётся ВЛОЖЕНИЕМ всегда.

    У материала есть список типов для показа в браузере (`INLINE_TYPES`); у письма его
    нет и быть не должно — документ незачем отрисовывать на нашем домене.
    """
    import inspect
    src = inspect.getsource(lp.get_rights_letter)
    assert "octet-stream" in src
    assert "INLINE_TYPES" not in src, "письмо не должно попадать в inline-показ"
