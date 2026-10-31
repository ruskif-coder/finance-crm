# -*- coding: utf-8 -*-
"""Очередь дайджеста площадкам: конечное состояние строки и порог давности.

Замер на проде 31.10.2026: 22 строки лежали в `cabinet_digest_queue` третьи сутки,
17 из них в состоянии «вроде ждёт». Отправитель их не брал и взять уже не мог —
29.10.2026 по решению владельца к отбору добавилось условие «писать можно только тому,
кто может войти в кабинет и снять „Письма“ сам» (`HAS_CABINET_ACCESS`), а строки встали
в очередь до этого.

Две поломки из одного корня, и обе тихие:

1. **У строки нет конечного состояния.** `sent_at` остаётся NULL навсегда, поэтому
   «ждёт своего часа» в базе не отличить от «не уйдёт никогда».
2. **Проверка на экране состояния разошлась с отправителем.** Условие добавили в три
   места из четырёх (отправка, дайджест, досылка), а `check_outward_digest` забыли —
   и она показывала `bad` на строки, которых отправитель никогда не возьмёт. Вечно
   красный прибор бесполезен так же, как вечно зелёный: на него перестают смотреть.

Третьего не было вовсе: **порога давности**. У телеграм-досылки он есть с рождения
(48 ч), здесь строка могла уехать пачкой за позапрошлый месяц, если получатель вернёт
доступ.
"""
import inspect

from sqlalchemy import text

from app.database import SessionLocal
from app.notify.outward import digest, send


# ── конечное состояние ───────────────────────────────────────────────────────

def test_queue_row_has_a_terminal_state():
    """Колонка причины закрытия есть в таблице (миграция 2026-10-31).

    Без неё «не уйдёт никогда» пришлось бы изображать через `sent_at`, то есть врать
    «отправлено» — журнал почты при этом остался бы пустым, и разобрать такую строку
    было бы нечем.
    """
    db = SessionLocal()
    try:
        cols = {r[0] for r in db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            " WHERE table_name = 'cabinet_digest_queue'")).all()}
    finally:
        db.close()
    assert 'closed_reason' in cols, 'нет колонки причины — закрыть строку честно нечем'


def test_sender_does_not_pick_up_closed_rows():
    """Закрытая строка не возвращается в отбор дайджеста."""
    src = inspect.getsource(digest._run)
    assert 'closed_reason IS NULL' in src, (
        'отбор дайджеста не исключает закрытые строки — закрытое уедет письмом')


# ── порог давности ───────────────────────────────────────────────────────────

def test_the_queue_has_an_age_cap_at_all():
    """Порог давности объявлен числом, а не «подразумевается»."""
    assert isinstance(getattr(digest, 'MAX_AGE_HOURS', None), int), (
        'у очереди дайджеста нет порога давности — пачка за прошлый месяц уедет как новая')


def test_a_blocked_row_is_not_closed_before_the_cap():
    """Получатель потерял доступ, но строка ещё свежая — НЕ закрываем.

    Доступ возвращается: контакту заводят учётку. Закрыв строку в первый же промах, мы
    потеряли бы пачку, которую через час можно было отдать.
    """
    assert digest.close_reason(age_hours=1, can_receive=False,
                               why_blocked='получатель без учётки кабинета') is None


def test_past_the_cap_the_real_blocker_is_named_not_just_staleness():
    """За порогом причина пишется НАСТОЯЩАЯ, а не «протухло».

    «Протухло» скрыло бы, что получатель вообще не мог её получить, — а именно это и
    нужно знать, чтобы починить данные, а не очередь.
    """
    got = digest.close_reason(age_hours=100, can_receive=False,
                              why_blocked='получатель без учётки кабинета')
    assert got and 'учётки' in got, got


def test_past_the_cap_a_merely_stale_row_is_closed_too():
    """Получатель жив, а пачка просто устарела — закрываем по давности."""
    got = digest.close_reason(age_hours=100, can_receive=True, why_blocked=None)
    assert got and 'протухл' in got.lower(), got


# ── согласие четырёх отборов ─────────────────────────────────────────────────

def test_all_four_selections_agree_on_who_may_receive():
    """Условие «получатель может войти и отказаться сам» — во ВСЕХ местах, где решается
    судьба письма площадке.

    Их четыре, а не три: отправка, дайджест, досылка и ПРОВЕРКА СОСТОЯНИЯ. В коде
    перечислены три, и четвёртое отстало на двое суток — ровно та поломка 31.10.2026,
    из-за которой экран состояния светился красным на строки, которых отправитель
    никогда не возьмёт.

    Прибор держит их вместе: добавишь условие в отбор — не забудешь про прибор над ним.
    """
    from app.mail import flush
    from app.system import status

    # Ищем ПОДСТАНОВКУ `{HAS_CABINET_ACCESS}` в SQL, а не упоминание имени. Первая
    # редакция прибора искала имя — и не поймала мутанта: условие убрали из запроса,
    # а импорт `from ... import HAS_CABINET_ACCESS` внутри функции остался, и тест
    # прошёл вхолостую. Проверять надо применение, а не наличие.
    used = '{HAS_CABINET_ACCESS}'
    places = {
        'дайджест (outward.digest)': inspect.getsource(digest),
        'досылка (mail.flush)': inspect.getsource(flush),
        'экран состояния (check_outward_digest)': inspect.getsource(status.check_outward_digest),
    }
    missing = [name for name, src in places.items() if used not in src]
    assert not missing, (
        'условие доступа к кабинету не подставлено в запрос: ' + '; '.join(missing)
        + ' — отбор и прибор над ним разойдутся молча')
    # Место определения — там имя без фигурных скобок, и оно должно остаться одним.
    assert "HAS_CABINET_ACCESS = " in inspect.getsource(send), (
        'условие перестало быть одним на все отборы')


def test_status_check_ignores_closed_rows():
    """Закрытая строка не считается «не ушедшей» — иначе прибор красный навсегда."""
    src = inspect.getsource(__import__('app.system.status', fromlist=['x']).check_outward_digest)
    assert 'closed_reason IS NULL' in src, (
        'проверка состояния считает закрытые строки застрявшими')


# ── прибор на телеграм ───────────────────────────────────────────────────────

def test_telegram_delivery_failures_are_watched():
    """Доля неудач телеграма за сутки видна на экране состояния.

    30.10.2026 прокси до Телеграма умер на день: 252 отправки из 268 легли статусом
    `failed`, и это НЕ заметил ни один прибор. Живая проверка «Телеграм: связь» щупает
    связь в момент открытия экрана, а прошедшие сутки не смотрит никто; `failed`
    терминален и досылкой не перечитывается, то есть молчание было полным.
    """
    from app.system import status

    assert hasattr(status, 'check_tg_delivery_failures'), (
        'нет проверки доли неудач телеграма за сутки')
    assert 'check_tg_delivery_failures' in inspect.getsource(status.collect), (
        'проверка написана, но в collect() не включена — на экран не попадёт')


class _FakeDb:
    """Строки очереди старше порога; записи считаются, а не выполняются."""
    def __init__(self, rows):
        self.rows, self.updates, self.commits = rows, 0, 0

    def execute(self, sql, params=None):
        if str(sql).lstrip().upper().startswith("UPDATE"):
            self.updates += 1
            return None
        rows = self.rows
        return type("R", (), {"fetchall": lambda _self: rows})()

    def commit(self):
        self.commits += 1


def _stale_row(i):
    from types import SimpleNamespace
    return SimpleNamespace(id=i, age_hours=digest.MAX_AGE_HOURS + 5, contact_alive=True, notify_on=True,
                           has_access=True, pub_live=True, cab_live=True)


def test_dry_run_counts_but_does_not_close(monkeypatch):
    """Пробный запуск (`--dry-run`) показывает, что ушло бы, и НИЧЕГО не меняет (ревью 31.10.2026).
    Закрытие протухших — запись в базу навсегда: проверка не должна тихо выбрасывать письма."""
    db = _FakeDb([_stale_row(1), _stale_row(2)])
    assert digest._close_stale(db, dry_run=True) == 2
    assert db.updates == 0 and db.commits == 0

    db = _FakeDb([_stale_row(1), _stale_row(2)])
    assert digest._close_stale(db) == 2
    assert db.updates == 2 and db.commits == 1


def test_the_run_passes_its_dry_run_to_closing():
    assert "_close_stale(db, dry_run=dry_run)" in inspect.getsource(digest._run)
