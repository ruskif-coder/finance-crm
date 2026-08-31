# -*- coding: utf-8 -*-
"""Контекст события должен нести то, что ищут его получатели.

Событие адресуется резолвером (`account_manager`, `sales_rep_of_deal`, …), резолвер
достаёт объект из `ctx`. Если ключ не тот, резолвер возвращает ПУСТОЙ СПИСОК — адресатов
нет, `emit` молча выходит, строки в журнале отправок не появляется. Ни исключения, ни
предупреждения: событие «сработало», и на этом всё.

Так и было до 31.08.2026. Шесть событий контура креативов и трафика адресованы аккаунту
сделки, а восемь вызовов передавали `ctx={"deal_id": deal.id}` вместо `ctx={"deal": deal}`.
Площадка нажимала в своём кабинете «на доработку» — вердикт ложился в базу, в журнал
кабинета, менял состояние пары, — и аккаунт не узнавал об этом никогда. Нашлось не
приборами: владелец нажал кнопку и спросил, где теперь искать результат.

Прибор читает исходники (`ast`), а не поведение: подобрать данные так, чтобы проявились
все восемь вызовов, дороже и ненадёжнее, чем прочитать сами вызовы.

Держит два правила:

  1. В литеральном `ctx={…}` не бывает ключей, которых не читает ни один резолвер.
     `deal_id` — ровно такой ключ: похож на правильный, не читается никем.
  2. Если у события есть получатель-резолвер, его ключ обязан быть в `ctx` вызова —
     в том числе когда `ctx` не передан вовсе.

Вторая половина правила 2 дописана в тот же день: первая редакция собирала только вызовы
с литеральным `ctx={…}`, и `emit` совсем без контекста проходил мимо прибора. Это та же
ошибка в самой чистой форме — резолверу достаётся пустой словарь.
"""
import ast
import io
import os

from app.notify import registry
from app.notify.recipients import RESOLVER_CTX

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')

# Ключи, которые кто-то действительно читает. Всё остальное в `ctx` — опечатка либо
# остаток от прежней формы вызова.
KNOWN_KEYS = set(RESOLVER_CTX.values())


def _ctx_calls():
    """Вызовы `emit`/`Hit` и их контекст: (файл, строка, имя, ключ события, ключи ctx).

    Ключ события известен только у прямых `emit(db, "…", …)`. У сканера контекст едет в
    `Hit(...)`, и событие там определяется таблицей правил — для таких вызовов проверяем
    только правило 1, оно и ловит `deal_id`.

    `ctx` может отсутствовать: тогда ключей нет — и правило 2 обязано это увидеть.
    Не-литеральный `ctx` (переменная, вызов) пропускается: прочитать его статически
    нельзя, а угадывать хуже, чем молчать.
    """
    out = []
    for base, _dirs, files in os.walk(APP):
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(base, f)
            tree = ast.parse(io.open(path, encoding='utf-8').read(), path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, 'id', None) or getattr(node.func, 'attr', '')
                has_ctx = any(kw.arg == 'ctx' for kw in node.keywords)
                ctx = next((kw.value for kw in node.keywords if kw.arg == 'ctx'), None)
                if has_ctx and not isinstance(ctx, ast.Dict):
                    continue                       # ctx собран в переменной — не прочитать
                if not has_ctx and name not in ('emit', 'Hit'):
                    continue                       # чужой вызов без ctx нас не касается
                keys = {k.value for k in ctx.keys
                        if isinstance(k, ast.Constant)} if has_ctx else set()
                event = None
                if name == 'emit' and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    event = node.args[1].value
                rel = os.path.relpath(path, APP).replace(os.sep, '/')
                out.append((rel, node.lineno, name, event, keys))
    return out


def test_context_keys_are_ones_somebody_reads():
    """Правило 1: чужих ключей в `ctx` не бывает.

    Именно оно ловит `deal_id`: ключ выглядит осмысленно, вызов проходит, резолвер молчит.
    """
    calls = _ctx_calls()
    assert calls, 'ни одного вызова с ctx не найдено — прибор смотрит не туда'
    bad = [f'{rel}:{line} ({name}): {sorted(keys - KNOWN_KEYS)}'
           for rel, line, name, _ev, keys in calls if keys - KNOWN_KEYS]
    assert not bad, (
        'в ctx лежат ключи, которых не читает ни один резолвер '
        f'(известные: {sorted(KNOWN_KEYS)}):\n  ' + '\n  '.join(bad))


def test_every_emit_carries_what_its_recipients_need():
    """Правило 2: чем событие адресуется, то в контексте и лежит."""
    missing = []
    for rel, line, name, event, keys in _ctx_calls():
        if name != 'emit' or not event:
            continue
        ev = registry.get(event)
        assert ev is not None, f'{rel}:{line}: события {event} нет в реестре'
        for spec in ev.recipients:
            if spec.get('type') != 'resolver':
                continue
            need = RESOLVER_CTX.get(spec['value'])
            if need and need not in keys:
                missing.append(f'{rel}:{line}: {event} адресуется «{spec["value"]}», '
                               f'ему нужен ctx["{need}"], а передано '
                               f'{sorted(keys) if keys else "НИЧЕГО"}')
    assert not missing, '\n  '.join([''] + missing)


def test_every_ctx_resolver_is_declared():
    """Резолвер, читающий контекст, обязан быть в `RESOLVER_CTX`.

    Иначе новый резолвер тихо выпадает из-под правила 2: прибор его не знает и молчит.
    """
    import inspect

    from app.notify import recipients

    undeclared = []
    for key, fn in recipients.RESOLVERS.items():
        src = inspect.getsource(fn)
        if 'ctx.get(' in src and key not in RESOLVER_CTX:
            undeclared.append(key)
    assert not undeclared, f'резолверы читают ctx, но не объявлены в RESOLVER_CTX: {undeclared}'
