# -*- coding: utf-8 -*-
"""Прибор: порядок наката миграций — по имени файла, и там, где имя врёт, это записано.

РЕШЕНИЕ ВЛАДЕЛЬЦА 23.09.2026. Полный упорядоченный список в README отменён. «Что уже
накатано» знает учёт `schema_migrations` (`deploy.sh migrate-status`), «в каком порядке» —
имя файла (дата впереди, внутри дня алфавит), а README держит только ИСКЛЮЧЕНИЯ: файл обязан
идти после другого, хотя по имени стоит раньше.

ЧТО БЫЛО. Прибор требовал, чтобы каждая миграция была названа в списке. С 12.09 список не
дописывали, к 23.09 он отстал на 27 файлов — а прибор оставался зелёным: тесты идут в
контейнере, где каталог `migrations/` лежал со времени сборки образа. Список, который надо
вести руками, отстаёт; прибор, который сверяет список, ловит только отставание списка.

ЧТО ДЕРЖИМ ТЕПЕРЬ:
  · имя каждого файла — `ГГГГ-ММ-ДД_что.sql`: на этом стоит весь порядок;
  · ссылка «вперёд» — файл упоминает таблицу, представление, функцию или схему, которую
    заводит файл, стоящий по имени ПОЗЖЕ, — обязана быть в блоке исключений. Её находит
    сам прибор, а не память человека: так найдены все шесть исключений за историю, включая
    `cabinet_dashboard` после `cabinet_org`, которое старый список держал неявно;
  · исключения ссылаются на существующие файлы;
  · про `dsp/` написано, что это другая база.

ЧЕГО ПРИБОР НЕ ЛОВИТ: зависимость по смыслу без упоминания имени (например, «сначала
барьер на все представления, потом закрыть public»). Такие дописываются в блок руками —
прибор проверяет только, что файлы существуют.

КАТАЛОГ. Тест читает `migrations/` ИЗ КОНТЕЙНЕРА. Перед прогоном его надо донести целиком
(`docker cp backend/migrations/. finance_backend:/app/migrations`), иначе прибор проверит
каталог со времени сборки образа — именно так прошлый прибор и оставался зелёным.
"""
import pathlib
import re

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"
README = MIGRATIONS / "README.md"

NAME_OK = re.compile(r"^\d{4}-\d{2}-\d{2}_[a-z0-9_]+\.sql$")
EXC_FROM = "### Исключения из порядка по имени"
EXC_TO = "### Как это читать при релизе"
EXC_LINE = re.compile(r"^(\S+\.sql)\s+после\s+(\S+\.sql)\s*$", re.M)

CREATES = (
    re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW)\s+"
               r"(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][\w.]*)", re.I),
    re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([a-z_][\w.]*)", re.I),
    re.compile(r"CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]\w*)", re.I),
)


def _readme() -> str:
    assert README.exists(), "backend/migrations/README.md пропал"
    return README.read_text(encoding="utf-8")


def _exceptions() -> set:
    text = _readme()
    i, j = text.find(EXC_FROM), text.find(EXC_TO)
    assert i >= 0 and j > i, f"в README нет раздела «{EXC_FROM}»"
    blocks = "\n".join(re.findall(r"```\n(.*?)```", text[i:j], re.S))
    return {(a, b) for a, b in EXC_LINE.findall(blocks)}


def _dirs():
    """Главная база и отдельная `dsp/` — у каждой свой порядок."""
    return [MIGRATIONS] + [d for d in MIGRATIONS.iterdir() if d.is_dir()]


def _sql(d):
    return sorted(d.glob("*.sql"))


def _strip(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def forward_refs(files) -> set:
    """{(файл, файл-создатель)} — упоминания объектов, которые заводит файл ПОЗЖЕ по имени."""
    texts = {f.name: _strip(f.read_text(encoding="utf-8")) for f in files}
    creator, own = {}, {}
    for name, t in texts.items():
        own[name] = {m.group(1).lower() for rx in CREATES for m in rx.finditer(t)}
        for obj in own[name]:
            creator.setdefault(obj, name)
    out = set()
    for name, t in texts.items():
        low = t.lower()
        for obj, first in creator.items():
            if first <= name or obj in own[name]:
                continue
            prefix = r"(?<![\w.])" if "." in obj else r"(?<![\w.])(?:public\.)?"
            if re.search(prefix + re.escape(obj) + r"(?!\w)", low):
                out.add((name, first))
    return out


def test_migrations_directory_is_not_empty():
    """Страховка от того, что тест зелёный, потому что ничего не нашёл."""
    assert len(_sql(MIGRATIONS)) > 100


def test_every_file_name_orders_by_date():
    bad = [f"{d.name}/{p.name}" for d in _dirs() for p in _sql(d) if not NAME_OK.match(p.name)]
    assert not bad, ("имя миграции не по образцу ГГГГ-ММ-ДД_что.sql — порядок наката стоит "
                     "на имени:\n  " + "\n  ".join(bad))


def test_every_forward_reference_is_a_written_exception():
    exc = _exceptions()
    missing = sorted(pair for d in _dirs() for pair in forward_refs(_sql(d)) if pair not in exc)
    assert not missing, (
        "по имени эти файлы идут РАНЬШЕ того, что используют. Допишите в README, блок "
        f"«{EXC_FROM[4:]}», строкой `<файл>  после  <файл>` — или переименуйте файл:\n  "
        + "\n  ".join(f"{a}  после  {b}" for a, b in missing))


def test_exceptions_name_existing_files():
    names = {p.name for d in _dirs() for p in _sql(d)}
    ghosts = sorted({n for pair in _exceptions() for n in pair} - names)
    assert not ghosts, "исключения зовут файлы, которых нет:\n  " + "\n  ".join(ghosts)


def test_the_probe_sees_a_forward_reference(tmp_path):
    """Прибор на прибор: ссылка на таблицу из файла, который по имени позже, — ловится,
    а ссылка на свою же или более раннюю — нет."""
    (tmp_path / "2026-01-01_a.sql").write_text("ALTER TABLE later_t ADD COLUMN x int;", "utf-8")
    (tmp_path / "2026-01-01_b.sql").write_text("CREATE TABLE IF NOT EXISTS later_t (id int);", "utf-8")
    (tmp_path / "2026-01-02_c.sql").write_text("SELECT * FROM later_t;", "utf-8")
    assert forward_refs(sorted(tmp_path.glob("*.sql"))) == {("2026-01-01_a.sql", "2026-01-01_b.sql")}


def test_dsp_migrations_are_marked_as_a_separate_database():
    """`dsp/` идёт в ДРУГУЮ базу, и это должно быть написано в README."""
    text = _readme()
    assert "dsp_analytics" in text and "finance_dsp_db" in text, (
        "В README нет указания, что миграции из `dsp/` накатываются в отдельную базу")
