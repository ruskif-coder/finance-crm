# -*- coding: utf-8 -*-
"""Приборы на ссылку нацеливания. Без сети.

Образцы вёрстки сняты с живого генератора 12.09.2026, а не придуманы: вся обвязка стоит
на разборе чужой bootstrap-плашки, и придуманный образец проверял бы мои ожидания.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.dsp.targeting_link import ENV_ADMIN_URL, TargetingLinkError, issue

BASE = "https://admin.example/"

# Живая разметка успеха. Ссылка приходит ТЕКСТОМ внутри плашки, рядом лежит кнопка
# «скопировать» с той же ссылкой в onclick — поэтому берём первую, а не последнюю.
SUCCESS = ('<div class="col-md-12">\r\n<div class="alert alert-success" '
           'style="word-wrap: break-word;">'
           'https://admin.example/share/targeting/?crid=A571B2ACC0BA7E05'
           '&exp=1789402693&checksum=12e875d109e46b62fd4944b04d394e1c18d45bbe</div>\r\n'
           '<button type="button" class="btn btn-secondary mr-2" '
           'onclick="copyToClipboard(\'https://admin.example/share/targeting/'
           '?crid=A571B2ACC0BA7E05&exp=1789402693&checksum=12e875d1\')">копировать</button>')

BAD_CHARS = ('<div class="alert alert-danger">'
             'Идентификатор креатива содержит недопустимые символы</div>')
EMPTY = ('<div class="alert alert-danger">'
         'Идентификатор креатива отсутствует или неизвестен</div>')


def _t(body):
    calls = []

    def transport(url, data):
        calls.append((url, dict(data)))
        return body
    transport.calls = calls
    return transport


def test_link_is_taken_from_the_success_box():
    got = issue("A571B2ACC0BA7E05", url=BASE, transport=_t(SUCCESS))
    assert got.url.startswith("https://admin.example/share/targeting/?crid=A571B2ACC0BA7E05")
    assert "checksum=12e875d109e46b62fd4944b04d394e1c18d45bbe" in got.url


def test_expiry_is_read_from_the_link_itself():
    """Срок не хранится отдельно — он ВНУТРИ ссылки, параметром `exp`."""
    got = issue("A571B2ACC0BA7E05", url=BASE, transport=_t(SUCCESS))
    assert got.expires_at == datetime.fromtimestamp(1789402693, timezone.utc)


def test_expired_link_reports_itself_dead():
    got = issue("A571B2ACC0BA7E05", url=BASE, transport=_t(SUCCESS))
    got.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert not got.alive
    got.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    assert got.alive


def test_it_is_a_plain_form_post_not_a_browser():
    """Один POST с единственным полем — ни сессии, ни токена, ни JavaScript.

    Из этого и следует, что задача решается на сервере без графической оболочки.
    """
    tr = _t(SUCCESS)
    issue("A571B2ACC0BA7E05", url=BASE, transport=tr)
    url, data = tr.calls[0]
    assert data == {"crid": "A571B2ACC0BA7E05"}
    assert url == "https://admin.example/?c=targeting&a=generator"
    assert len(tr.calls) == 1


@pytest.mark.parametrize("body,part", [
    (BAD_CHARS, "недопустимые символы"),
    (EMPTY, "отсутствует или неизвестен"),
])
def test_their_refusal_text_reaches_the_human(body, part):
    """Отказ приходит кодом 200 и отличается только классом плашки.

    Их формулировка точнее нашего пересказа, поэтому показываем как есть.
    """
    with pytest.raises(TargetingLinkError) as e:
        issue("что-то", url=BASE, transport=_t(body))
    assert part in str(e.value)


def test_unparsed_answer_is_not_silence():
    """Переделали вёрстку — снаружи это выглядит как «кнопка не работает».

    Отдельный внятный отказ дешевле, чем разбираться в этом через неделю.
    """
    with pytest.raises(TargetingLinkError) as e:
        issue("A571B2ACC0BA7E05", url=BASE, transport=_t("<html>что-то новое</html>"))
    assert "не разобран" in str(e.value)


def test_empty_crid_does_not_go_outside():
    tr = _t(SUCCESS)
    with pytest.raises(TargetingLinkError):
        issue("", url=BASE, transport=tr)
    assert tr.calls == [], "за пустым идентификатором наружу ходить незачем"


def test_missing_address_names_the_variable(monkeypatch):
    monkeypatch.delenv(ENV_ADMIN_URL, raising=False)
    with pytest.raises(TargetingLinkError) as e:
        issue("A571B2ACC0BA7E05", transport=_t(SUCCESS))
    assert ENV_ADMIN_URL in str(e.value)


def test_no_external_address_is_written_into_the_code():
    """Правило проекта: поставщика DSP не называем нигде — ни в коде, ни в комментарии.

    Проверяем по ФОРМЕ, а не по списку слов: в модуле не должно быть ни одного
    абсолютного внешнего адреса, адрес берётся из окружения. Список запрещённых слов сам
    стал бы местом, где имя записано.
    """
    import pathlib
    import re
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "app" / "dsp" / "targeting_link.py").read_text(encoding="utf-8")
    urls = re.findall(r"https?://[^\s\"')]+", src)
    assert not urls, f"адрес зашит в код вместо окружения: {urls}"
    assert ENV_ADMIN_URL in src
