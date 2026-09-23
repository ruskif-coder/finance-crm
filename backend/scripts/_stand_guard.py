# -*- coding: utf-8 -*-
"""Запрет запуска демо-скриптов вне локального стенда — ОДНА проверка на все.

Демо-скрипты заводят поддельные данные и переписывают настоящие строки: даты, статусы и
веса РК, комплекты креативов. Папка `scripts/` уезжает в образ прода, и до 23.09.2026 у
`2026-09-04_demo_traffic_month` не было никакой проверки — одна команда на проде
сбросила бы статусы всех запущенных размещений (аудит 23.09.2026, 8.H4).

Проверка ЗАКРЫВАЕТСЯ при сомнении: пропускается только явный `DOMAIN=localhost`.
Пустое значение — не «стенд», а «неизвестно где»: в этом проекте трижды бывало, что
переменная есть в `.env`, а до процесса не доходит (готча env-not-reaching-container).

ВТОРОЙ ЗАМОК — ЯВНЫЙ ФЛАГ ЗАПУСКА (ревью 23.09.2026). `docker-compose.yml` подставляет
`DOMAIN: ${DOMAIN:-localhost}`: незаданный домен приходит в контейнер как `localhost`, и
одна проверка домена пропустила бы свежий сервер, где `.env` ещё не заполнен. Поэтому
запуск требует ещё и `STAND=1`, которого нет ни в `.env`, ни в compose, — его пишет
человек в самой команде:

    docker exec -e STAND=1 finance_backend python -m scripts.<демо-скрипт>
"""
import os
import sys


def is_stand() -> bool:
    """Оба признака стенда: явный `DOMAIN=localhost` и флаг запуска `STAND=1`."""
    domain = (os.getenv("DOMAIN") or "").strip().lower()
    return domain == "localhost" and (os.getenv("STAND") or "").strip() == "1"


def require_stand(what: str) -> None:
    if not is_stand():
        domain = (os.getenv("DOMAIN") or "").strip().lower()
        print(f"ОТКАЗ: «{what}» запускается только на локальном стенде: нужны "
              f"DOMAIN=localhost (здесь {domain or 'не задан'}) и флаг запуска STAND=1 — "
              f"docker exec -e STAND=1 finance_backend python -m scripts.<имя>.")
        sys.exit(2)
