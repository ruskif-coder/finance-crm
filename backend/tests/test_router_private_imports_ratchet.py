# -*- coding: utf-8 -*-
"""Храповик: внутренние функции роутеров (`_имя`) не импортируются из других модулей (аудит 13.11.2026, владелец 14.11).

Роутер — это HTTP, права и вызов; правило живёт в доменном пакете (`sales`, `ad`, `notify`, `final_recon`, `master_deal`…).
Импорт `_функции` чужого роутера делает файл роутера границей модуля: перенос одной функции ломает 5–10 файлов, и правило
вместо переноса копируют рядом — так и разошлись «срок оплаты» и «план отдан клиенту» в 3–4 местах. Переписать разом —
недели; храповик не даёт числу расти. Сломать: добавить `from app.routers.x import _y` — тест назовёт место. Вынесли правило
в пакет — опустите число."""
import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
CEILING = 60  # 14.11.2026 — замер; только уменьшать


def _hits():
    out = []
    for f in sorted(APP.rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.routers."):
                out += [f"{f.relative_to(APP).as_posix()}:{node.lineno} {node.module}.{a.name}"
                        for a in node.names if a.name.startswith("_")]
    return out


def test_private_router_imports_do_not_grow():
    hits = _hits()
    assert len(hits) <= CEILING, (f"импортов внутренних функций роутеров: {len(hits)} > {CEILING}. Вынесите правило в "
                                  "доменный пакет вместо импорта `_функции` чужого роутера:\n" + "\n".join(hits))
