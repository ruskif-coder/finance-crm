# -*- coding: utf-8 -*-
"""Общее для приборов, которые обходят ручки приложения (охрана, права, запись под «просмотром»)."""


def iter_dependencies(dep, seen=None):
    """Все зависимости ручки по дереву, без повторов (FastAPI `Dependant.dependencies`)."""
    seen = seen if seen is not None else set()
    for d in dep.dependencies:
        if id(d) in seen:
            continue
        seen.add(id(d))
        yield d
        yield from iter_dependencies(d, seen)
