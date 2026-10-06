# -*- coding: utf-8 -*-
"""Все ORM-модели одним импортом (06.10.2026).

Внешние ключи между таблицами SQLAlchemy разрешает по ИМЕНИ таблицы при первой записи, и
таблица должна быть зарегистрирована в `Base.metadata` к этому моменту. В приложении это
делает цепочка импортов `app.main` → роутеры → модели. Кроны запускаются отдельным
процессом (`python -m ...`) и этой цепочки не проходят: дайджест площадкам неделю падал на
`mail_log.publisher_id → sales_publishers`, и письма площадкам не уходили с 02.10.

Новый файл с моделями — строка сюда; прибор tests/test_cron_modules_standalone.py
проверяет, что каждый крон разрешает все ключи сам.
"""
import app.ad.models  # noqa: F401
import app.backlog_models  # noqa: F401
import app.bugs.models  # noqa: F401
import app.cabinet.models  # noqa: F401
import app.diadoc_models  # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.mail.models  # noqa: F401
import app.models  # noqa: F401
import app.notify.models  # noqa: F401
import app.ord.models  # noqa: F401
import app.publisher_requests  # noqa: F401
import app.sales.models  # noqa: F401
import app.weborama.models  # noqa: F401
