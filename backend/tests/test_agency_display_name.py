"""
Имя агентства на экране — короткое, а не длинная историческая форма.

В справочнике у агентства два имени. `name` — то, как запись назвали при заведении:
«OKKAM / оккам», «Media instinct (Медиа инстинкт)», «G4M (group4M) / Груп4М / ГрупМ».
`short_name` — рабочее короткое: «OKKAM», «MI», «G4M».

Дашборды продаж берут короткое, дашборд аккаунта брал длинное — и это выглядело как
«справочники не синхронизировались», хотя и справочник, и Битрикс были в порядке.
Диагностика такой жалобы стоит дороже самой ошибки: сначала проверяются связи с
Битриксом, потом имена компаний, и только потом — что читает конкретный экран.

Поэтому проверка source-level: где бы ни строилась карта id → имя агентства, короткое
имя обязано участвовать. Это ровно тот случай, когда правило дешевле держать
автоматически, чем помнить.
"""
import ast
import io
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _sources():
    for path in sorted(APP.rglob("*.py")):
        yield path, io.open(path, encoding="utf-8").read()


def test_agency_display_name_always_falls_back_to_short_name():
    """Ловит `{a.id: a.name for a in db.query(SalesAgency)}` без short_name.

    Именно в такой форме ошибка и была: словарь-справочник строится одной строкой,
    рядом с правильной версией для рекламодателей, и глазом не отличается.
    """
    bad = []
    for path, src in _sources():
        for m in re.finditer(r'\{\s*(\w+)\.id\s*:\s*(.{0,60}?)\s+for\s+\1\s+in\s+'
                             r'db\.query\(SalesAgency\)', src, re.S):
            value = m.group(2)
            if 'short_name' not in value:
                line = src[:m.start()].count('\n') + 1
                bad.append(f'{path.relative_to(APP)}:{line} → {" ".join(value.split())}')
    assert not bad, (
        'карта имён агентств без short_name — на экране появится длинная форма:\n'
        + '\n'.join('  ' + b for b in bad))


def test_no_bare_agency_name_in_response_dicts():
    """Ключ ответа "agency" не должен собираться из одного только .name.

    Второй путь той же ошибки: не словарь-справочник, а поле прямо в ответе
    эндпоинта — `"agency": agency.name`.
    """
    bad = []
    for path, src in _sources():
        for m in re.finditer(r'"agency"\s*:\s*([^,\n]{0,80})', src):
            value = m.group(1)
            if '.name' not in value:
                continue                      # берётся из готовой карты или иначе
            if 'short_name' in value:
                continue
            line = src[:m.start()].count('\n') + 1
            bad.append(f'{path.relative_to(APP)}:{line} → {" ".join(value.split())}')
    assert not bad, ('поле "agency" собирается из длинного имени:\n'
                     + '\n'.join('  ' + b for b in bad))


def test_the_two_names_really_differ_in_the_directory():
    """Страховка от бессмысленности проверки выше.

    Если бы short_name и name всегда совпадали, тесты были бы зелёными и пустыми.
    Модель обязана иметь оба поля — тогда правило имеет смысл.
    """
    src = io.open(APP / "sales" / "models.py", encoding="utf-8").read()
    tree = ast.parse(src)
    cls = [n for n in ast.walk(tree)
           if isinstance(n, ast.ClassDef) and n.name == 'SalesAgency']
    assert cls, 'модель SalesAgency не найдена'
    fields = {t.id for node in cls[0].body if isinstance(node, ast.Assign)
              for t in node.targets if isinstance(t, ast.Name)}
    assert 'name' in fields and 'short_name' in fields, fields
