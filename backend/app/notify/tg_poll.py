# -*- coding: utf-8 -*-
"""Опрос Телеграма вместо ожидания вебхука.

ЗАЧЕМ. Вебхук — это ВХОДЯЩЕЕ соединение: Телеграм сам стучится к нам. Замер 21.09.2026
на проде показал, что до сервера он не дозванивается:

  · `getWebhookInfo` у обоих ботов — `Connection timed out`, у бота площадок два
    апдейта висят недоставленными (нажатия «Старт»);
  · за семь суток к адресам вебхуков не пришло НИ ОДНОГО запроса от Телеграма
    (проверено по логам бэкенда — логи Caddy для этого не годятся, там нет директивы
    `log`, и в них не видно даже собственных проверочных запросов);
  · при этом наша сторона исправна: сайт снаружи отвечает, маршрут вебхука отдаёт 404
    на неверный секрет, секрет совпадает с зарегистрированным адресом, на хосте нет ни
    ufw, ни fail2ban, политика INPUT — ACCEPT.

ИСХОДЯЩИЕ при этом работают: с прода мы спокойно ходим в `api.telegram.org` (этим и
сняты замеры выше), уведомления и «отправить тест» доходят до людей. Поэтому лекарство —
поменять направление: не ждать, пока постучатся, а спрашивать самим.

ЧТО ЭТО НЕ ЛЕЧИТ. Причина обрыва — сеть между Телеграмом и хостингом, и она остаётся.
Опрос обходит её, а не устраняет; вопрос хостеру всё равно нужен.

СМЕЩЕНИЕ (`offset`) — единственное состояние опроса. Телеграм отдаёт апдейты по одному
разу только если подтвердить прочитанное: следующий запрос с `offset = последний id + 1`
и есть подтверждение. Храним его в `company_settings` — таблице ключ-значение, которая
уже есть; отдельная таблица под одно число была бы лишней.

ЗАПУСК: `python -m app.notify.tg_poll` (крон раз в минуту). Первый перевод контура на
опрос — `python -m app.notify.tg_poll --switch`: он снимает вебхук, иначе Телеграм
отвечает на `getUpdates` отказом 409 «конфликт с setWebhook».
"""
import argparse
import json
import logging
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Callable, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.notify import telegram

log = logging.getLogger("finance.tg_poll")

# Адрес и число попыток — из `telegram.py`: там они уже объявлены для отправки, и вторая
# копия разошлась бы с первой при первой же правке.
API = telegram.API
ATTEMPTS = telegram.ATTEMPTS

# Сколько секунд держать длинный запрос. Меньше минуты намеренно: крон запускает опрос
# раз в минуту, и два одновременных `getUpdates` одного бота Телеграм встречает отказом
# 409 — то есть перехлёст запусков сам себя сломал бы.
LONG_POLL_SECONDS = 20

# Ключ смещения в company_settings. Свой на контур: у ботов разные потоки апдейтов, и
# общий ключ означал бы, что один бот подтверждает прочитанное за другого.
OFFSET_KEY = "tg_poll_offset_{contour}"

# Отметка живости: когда опрос ПОСЛЕДНИЙ РАЗ успешно поговорил с Телеграмом. Пишется
# даже когда сообщений не было — важен сам факт, что канал жив.
#
# Без неё поломка невидима: снятый вебхук означает пустую очередь у Телеграма, и
# проверка экрана состояния (`check_telegram_live`, заведённая 08.09.2026 ровно против
# «токен есть, экран зелёный, бот молчит») показывала бы зелёное при мёртвом кроне.
ALIVE_KEY = "tg_poll_last_ok_{contour}"


def _opener():
    """Открыватель urllib с тем же прокси, что у отправки (см. `telegram.proxy`).

    Строится на каждый вызов, а не один раз на модуль: опрос живёт в кроне, процесс
    короткий, а прокси может смениться правкой `.env` без выкладки кода.
    """
    px = telegram.proxy()
    if not px:
        return urllib.request.build_opener()
    # CONNECT для https ставится самим ProxyHandler — TLS остаётся сквозным до Телеграма,
    # прокси видит только адрес назначения.
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": px, "https": px}))


def _call(token: str, method: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params or {}).encode()
    opener = _opener()
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        req = urllib.request.Request(url, data=data)
        try:
            with opener.open(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError:
            # Ответ Телеграма с кодом ошибки повторять нельзя: 409 («стоит вебхук») и
            # 400 от повтора не изменятся, а разбирать их должен вызывающий.
            raise
        except Exception as e:                  # таймаут, обрыв, отказ в соединении
            last = e
            if attempt < ATTEMPTS:
                log.info("tg_poll: %s — попытка %d не прошла (%s), повтор",
                         method, attempt, type(e).__name__)
    raise last


def _offset(db: Session, contour: str) -> int:
    row = db.execute(text("select value from company_settings where key = :k"),
                     {"k": OFFSET_KEY.format(contour=contour)}).first()
    try:
        return int(row[0]) if row and row[0] else 0
    except (TypeError, ValueError):
        # Испорченное значение не должно останавливать приём сообщений: начинаем заново
        # с того, что Телеграм ещё держит (он хранит апдейты сутки).
        log.warning("tg_poll: смещение контура %s нечитаемо — начинаем с нуля", contour)
        return 0


def _set(db: Session, key: str, value: str) -> None:
    db.execute(text("""
        insert into company_settings (key, value) values (:k, :v)
        on conflict (key) do update set value = excluded.value
    """), {"k": key, "v": value})
    db.commit()


def _save_offset(db: Session, contour: str, value: int) -> None:
    _set(db, OFFSET_KEY.format(contour=contour), str(value))


def _mark_alive(db: Session, contour: str) -> None:
    _set(db, ALIVE_KEY.format(contour=contour),
         datetime.utcnow().replace(microsecond=0).isoformat())


def last_ok(db: Session, contour: str) -> Optional[datetime]:
    """Когда опрос последний раз достучался до Телеграма. None — ни разу."""
    row = db.execute(text("select value from company_settings where key = :k"),
                     {"k": ALIVE_KEY.format(contour=contour)}).first()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(row[0])
    except ValueError:
        return None


def drop_webhook(contour: str) -> dict:
    """Снять вебхук у контура. Без этого `getUpdates` отвечает 409.

    `drop_pending_updates` НЕ ставим: висящие апдейты — это сообщения живых людей,
    которые уже нажали «Старт» и ждут ответа. Они и должны приехать первыми.
    """
    token = telegram.bot_token(contour)
    if not token:
        raise RuntimeError(f"не задан {telegram.token_var(contour)}")
    return _call(token, "deleteWebhook")


def poll_once(db: Session, contour: str, handle: Callable[[Session, dict], None]) -> int:
    """Один заход: забрать накопившееся и разобрать. Возвращает число апдейтов.

    Смещение двигается ПОСЛЕ каждого разобранного апдейта, в том числе после сбоя на
    нём. Иначе одно кривое сообщение встаёт поперёк очереди навсегда и хоронит все
    следующие — а сбой на чужом сообщении не должен стоить привязки соседней площадке.
    """
    token = telegram.bot_token(contour)
    if not token:
        log.info("tg_poll: контур %s не настроен (%s пуст) — пропуск",
                 contour, telegram.token_var(contour))
        return 0

    params = {"timeout": LONG_POLL_SECONDS, "allowed_updates": json.dumps(["message"])}
    off = _offset(db, contour)
    if off:
        params["offset"] = off
    try:
        resp = _call(token, "getUpdates", params, timeout=LONG_POLL_SECONDS + 10)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        if e.code == 409:
            log.error("tg_poll: контур %s — 409, вебхук ещё стоит. "
                      "Снимите его: python -m app.notify.tg_poll --switch", contour)
        else:
            log.error("tg_poll: контур %s — HTTP %s %s", contour, e.code, body)
        return 0
    except Exception as e:
        log.error("tg_poll: контур %s — связь с Телеграмом: %s", contour, e)
        return 0

    # Дошли до сюда — значит связь есть, даже если сообщений ноль. Это и есть то, что
    # должен видеть экран состояния.
    _mark_alive(db, contour)

    updates: List[dict] = resp.get("result") or []
    for u in updates:
        uid = u.get("update_id")
        try:
            handle(db, u)
        except Exception:
            db.rollback()
            log.exception("tg_poll: апдейт %s контура %s не разобран", uid, contour)
        if isinstance(uid, int):
            _save_offset(db, contour, uid + 1)
    return len(updates)


def _reply_now(chat_id: str, text_: str, contour: str) -> None:
    try:
        telegram.send_message(chat_id, text_, contour=contour)
    except Exception:
        log.warning("tg_poll: ответ человеку не ушёл", exc_info=True)


def _handle_pub(db: Session, update: dict) -> None:
    """Разбор апдейта бота площадок — ТЕМ ЖЕ кодом, что и вебхук."""
    from app.routers.cabinet_gateway import handle_pub_update
    handle_pub_update(db, update,
                      lambda cid, txt: _reply_now(cid, txt, telegram.PUB))


HANDLERS: Dict[str, Callable[[Session, dict], None]] = {
    telegram.PUB: _handle_pub,
}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Опрос Телеграма (вместо вебхука)")
    ap.add_argument("--contour", default=telegram.PUB,
                    help="pub — бот площадок (по умолчанию)")
    ap.add_argument("--switch", action="store_true",
                    help="снять вебхук перед первым опросом (делается один раз)")
    args = ap.parse_args(argv)

    if args.contour not in HANDLERS:
        print(f"Контур {args.contour} на опрос не переведён. Доступны: "
              f"{', '.join(sorted(HANDLERS))}")
        return 2

    if args.switch:
        try:
            r = drop_webhook(args.contour)
            print(f"Вебхук контура {args.contour} снят: {r.get('description') or r}")
        except Exception as e:
            print(f"Не удалось снять вебхук: {e}")
            return 1

    db = SessionLocal()
    try:
        n = poll_once(db, args.contour, HANDLERS[args.contour])
        print(f"Разобрано апдейтов: {n}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
