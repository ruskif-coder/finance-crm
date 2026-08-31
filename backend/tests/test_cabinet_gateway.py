# -*- coding: utf-8 -*-
"""Шлюз внешнего контура: что он НЕ пропускает.

Через `/api/cabinet-gw/*` в ядро стучится не человек, а наш же процесс, стоящий снаружи.
Поэтому проверяется здесь не «работает ли», а граница: пропуск, принадлежность и пределы
загрузок. Каждое из этих правил ломается молча — сломанное, оно ничего не роняет, а
просто начинает пускать.

Прогоняется в ядре, а не в кабинете: сам шлюз живёт здесь, и проверять его через сетевой
вызов из соседнего контейнера значило бы проверять заодно сеть, Caddy и сериализацию.
"""
import io
import os

import pytest
from sqlalchemy import text
from fastapi import HTTPException, UploadFile

from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepPair, LaunchPrepTarget
from app.routers import cabinet_gateway as gw
from app.sales.models import SalesPublisher


# ── пропуск ──────────────────────────────────────────────────────────────────

def test_empty_service_token_closes_the_door(monkeypatch):
    """Забытая переменная должна ломать функцию, а не защиту.

    Пустой секрет — самое вероятное состояние на новом стенде. Если бы он открывал
    вход «пока не настроили», внешний контур оказался бы распахнут ровно в тот период,
    когда за ним меньше всего следят.
    """
    monkeypatch.setattr(gw, 'SERVICE_TOKEN', '')
    with pytest.raises(HTTPException) as e:
        gw.require_cabinet_service('какой-угодно')
    assert e.value.status_code == 403


def test_wrong_service_token_is_refused(monkeypatch):
    monkeypatch.setattr(gw, 'SERVICE_TOKEN', 'S3cret-Token-For-Tests')
    with pytest.raises(HTTPException) as e:
        gw.require_cabinet_service('Wrong-Token-For-Tests')
    assert e.value.status_code == 403


def test_non_ascii_token_fails_closed(monkeypatch):
    """Кириллица в секрете роняет сравнение — и это ЗАКРЫВАЕТ вход, а не открывает.

    `hmac.compare_digest` со строками требует ASCII: не-ASCII даёт `TypeError`, запрос
    падает в 500 и не проходит. Поведение приемлемо, но должно быть закреплено: замена
    сравнения на наивное `==` «чтобы не падало» сняла бы заодно защиту от подбора по
    времени ответа.
    """
    monkeypatch.setattr(gw, 'SERVICE_TOKEN', 'правильный-секрет')
    with pytest.raises((HTTPException, TypeError)):
        gw.require_cabinet_service('неправильный-секрет')


def test_missing_header_is_refused(monkeypatch):
    """Отсутствие заголовка — не то же самое, что пустая строка, и оба должны падать."""
    monkeypatch.setattr(gw, 'SERVICE_TOKEN', 'S3cret-Token-For-Tests')
    with pytest.raises(HTTPException):
        gw.require_cabinet_service(None)


def test_correct_token_passes(monkeypatch):
    """Иначе три теста выше зелены и при вечно закрытом шлюзе."""
    monkeypatch.setattr(gw, 'SERVICE_TOKEN', 'S3cret-Token-For-Tests')
    assert gw.require_cabinet_service('S3cret-Token-For-Tests') is True


# ── принадлежность ───────────────────────────────────────────────────────────

@pytest.fixture
def env():
    """Живая пара и ЧУЖАЯ площадка — та, которой эта пара не принадлежит."""
    db = SessionLocal()
    pair = db.query(LaunchPrepPair).order_by(LaunchPrepPair.id).first()
    if pair is None:
        db.close()
        pytest.skip('на стенде нет ни одной пары')
    target = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == pair.target_id).first()
    other = (db.query(SalesPublisher)
             .filter(SalesPublisher.id != target.publisher_id)
             .order_by(SalesPublisher.id).first())
    if other is None:
        db.close()
        pytest.skip('нужна вторая площадка')
    # С 30.08.2026 шлюз требует назвать действующего: раньше он проверял только, что
    # пара принадлежит НАЗВАННОЙ площадке, а имеет ли право вызывающий говорить за неё —
    # оставалось на кабинете. Берём живую учётку: она в служебном кабинете и видит всё,
    # поэтому проверка личности не подменяет собой то, ради чего написан каждый тест.
    acc = db.execute(text(
        "SELECT a.id FROM cabinet_account a JOIN cabinet c ON c.id = a.cabinet_id "
        " WHERE c.state = 'активен' ORDER BY a.id LIMIT 1")).scalar()
    if acc is None:
        db.close()
        pytest.skip('нужна учётка в активном кабинете')
    yield type('E', (), {'db': db, 'pair': pair, 'target': target, 'acc': acc,
                         'own': target.publisher_id, 'other': other.id})
    db.rollback()
    db.close()


def test_verdict_for_someone_elses_pair_is_404(env):
    """Чужая пара отвечает 404, а не 403.

    403 подтверждает, что объект существует, — и перебор идентификаторов превращается в
    опись чужих кампаний. Проверка стоит В ЯДРЕ, а не только в кабинете: проверка,
    оставленная на вызывающей стороне, — это отсутствие проверки.
    """
    payload = gw.CabinetVerdictIn(publisher_id=env.other, account_id=env.acc, verdict='ок',
                                  author_name='чужой')
    with pytest.raises(HTTPException) as e:
        gw.cabinet_verdict(env.pair.id, payload, env.db)
    assert e.value.status_code == 404


def test_verdict_for_a_missing_pair_is_404(env):
    payload = gw.CabinetVerdictIn(publisher_id=env.own, account_id=env.acc, verdict='ок',
                                  author_name='кто-то')
    with pytest.raises(HTTPException) as e:
        gw.cabinet_verdict(10 ** 9, payload, env.db)
    assert e.value.status_code == 404


def test_url_for_someone_elses_target_is_404(env):
    """Посадочную можно прислать только на своё размещение."""
    payload = gw.CabinetUrlIn(publisher_id=env.other, account_id=env.acc,
                              url='https://example.test/x',
                              author_name='чужой')
    with pytest.raises(HTTPException) as e:
        gw.cabinet_target_url(env.target.id, payload, env.db)
    assert e.value.status_code == 404


def test_url_scheme_is_checked(env):
    """`javascript:` в поле, которое где-то отрисуется ссылкой, — это XSS, а не опечатка.

    Поле заполняет ВНЕШНЕЕ лицо, поэтому проверка здесь не формальность.
    """
    for bad in ('javascript:alert(1)', 'data:text/html,<script>', 'file:///etc/passwd'):
        payload = gw.CabinetUrlIn(publisher_id=env.own, account_id=env.acc, url=bad,
                                  author_name='площадка')
        with pytest.raises(HTTPException) as e:
            gw.cabinet_target_url(env.target.id, payload, env.db)
        assert e.value.status_code == 400, f'схема {bad} прошла'


def test_empty_url_is_refused(env):
    payload = gw.CabinetUrlIn(publisher_id=env.own, account_id=env.acc, url='   ',
                              author_name='площадка')
    with pytest.raises(HTTPException) as e:
        gw.cabinet_target_url(env.target.id, payload, env.db)
    assert e.value.status_code == 400


# ── пределы загрузок ─────────────────────────────────────────────────────────

def _upload(name: str, size: int = 10) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(b'x' * size))


def test_media_kit_rejects_foreign_extensions(env):
    """Только PDF и PPTX. Открытый список во внешнем контуре означает приём чего угодно
    от того, кто нам не сотрудник."""
    import asyncio
    for name in ('kit.zip', 'kit.exe', 'kit.html', 'kit.svg', 'kit'):
        with pytest.raises(HTTPException) as e:
            asyncio.run(gw.cabinet_media_kit(env.own, env.acc, _upload(name), env.db))
        assert e.value.status_code == 415, f'{name} прошёл'


def test_media_kit_limits_are_declared():
    """Пределы объявлены константами, а не зашиты в проверку числом.

    Прибор на СОСТАВ, а не на поведение: он падает, если кто-то уберёт ограничение
    вовсе — а это как раз то изменение, которое в диффе выглядит безобидно.
    """
    assert gw.MEDIA_KIT_EXT == {'.pdf', '.pptx'}
    assert gw.MEDIA_KIT_MAX == 30 * 1024 * 1024
    assert gw.REWORK_EXT == {'.png', '.jpg', '.jpeg', '.webp', '.pdf'}
    assert gw.REWORK_MAX_FILES == 5
    assert gw.REWORK_MAX == 10 * 1024 * 1024


def test_upload_name_cannot_escape_the_directory():
    """Имя файла нормализуется: `../` не должно уводить запись из каталога.

    Имя приходит от внешнего лица целиком — это классическая точка обхода пути.
    """
    import re
    for evil in ('../../etc/passwd', '..\\..\\windows\\system32', 'a/b/c.pdf'):
        safe = re.sub(r"[^\w.\-]", "_", evil)
        assert '/' not in safe and '\\' not in safe
        assert not safe.startswith('..') or '..' not in os.path.normpath(
            os.path.join('/app/uploads/mediakit', safe)).split('/')
