"""Каждая переменная окружения, которую читает код, должна быть осознанно решена.

## Зачем прибор

Одна и та же поломка случилась трижды: код читает `os.getenv("X")`, значение честно
лежит в `.env` на сервере — а до процесса не доходит, потому что `.env` наполняет
docker-compose, а не контейнер. В `environment` сервиса переменной нет.

Так молча отвалились доставка в Телеграм и синк Битрикса (найдено 31.08.2026, записано
предупреждением прямо в `.env.example`), и так же чуть не уехал коннектор DSP
(найдено 06.09.2026 проверкой перед коммитом). Со стороны это выглядит как неверный
токен, а не как отсутствующий проброс — и чинится раздачей токенов заново.

## Почему список, а не сверка с docker-compose.yml

Тесты идут ВНУТРИ контейнера, где `/app` — это `backend/`. Файла `docker-compose.yml`
там нет и быть не должно. Поэтому прибор устроен как реестр прав
(`test_permissions_groups`): множество пинуется здесь строгим равенством, и новая
переменная роняет тест до того, как попадёт на сервер. Уронив — заставляет автора
написать в этот файл, чем она передаётся. Это и есть решение, которое иначе не
принимается вовсе.

**Если тест упал, почти никогда не надо править ожидание молча.** Надо добавить строку
в `environment` сервиса `backend` в `docker-compose.yml`, а сюда — имя и способ.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# Переменная → чем она доходит до процесса.
#
# "compose"    — перечислена в `environment` сервиса backend в docker-compose.yml.
#                Значение приходит из .env (gitignored) через подстановку ${...}.
# "runtime"    — compose подставляет строку целиком, а не ссылку на .env.
# иначе        — НЕ передаётся намеренно, и текст объясняет почему. Такая переменная
#                недоступна процессу: значение из .env до него не дойдёт. Это осознанное
#                решение, а не забытая строка, и разница между ними — вся суть файла.
PASSED_THROUGH = {
    # ── база и подписи ───────────────────────────────────────────────────────
    "DATABASE_URL": "runtime",
    "DSP_DATABASE_URL": "runtime",
    "SECRET_KEY": "compose",
    # ── контур ───────────────────────────────────────────────────────────────
    "DOMAIN": "compose",
    "PDF_SERVICE_URL": "runtime",
    "CABINET_SERVICE_TOKEN": "compose",
    "DEBUG": "НЕ передаётся: true открывает Swagger/ReDoc без аутентификации. "
             "Недоступность переменной на проде держит документацию закрытой даже при "
             "ошибке в .env. Нужен локально — добавляйте строку временно.",
    "LOG_DIR": "НЕ передаётся: дефолт в коде (/app/logs) совпадает с bind-mount, "
               "переопределять нечем и незачем. Проброс тут был бы ВРЕДЕН: `${LOG_DIR:-}` "
               "дал бы пустую строку, getenv вернул бы её вместо своего дефолта, и "
               "os.makedirs('') уронил бы старт.",
    # ── Битрикс24 ────────────────────────────────────────────────────────────
    "VIBECODE_API_KEY": "compose",
    "BITRIX_WEBHOOK_URL": "compose",
    # ── уведомления ──────────────────────────────────────────────────────────
    "TELEGRAM_BOT_TOKEN": "compose",
    "TELEGRAM_BOT_NAME": "compose",
    "TELEGRAM_WEBHOOK_SECRET": "compose",
    # ── ОРД МедиаСкаут ───────────────────────────────────────────────────────
    "ORD_ENV": "compose",
    "ORD_LOGIN": "compose",
    "ORD_PASSWORD": "compose",
    "SANDBOX_BASE_URL": "compose",
    "ORD_ALLOW_PROD_WRITE": "НЕ передаётся НАМЕРЕННО: третий замок на боевую запись в "
                            "ЕРИР, которая необратима. Двух — ORD_ENV=prod и значения 1 "
                            "— сочли мало: включение должно требовать правки compose, то "
                            "есть отдельного осознанного действия. Снимать этот замок "
                            "можно только решением владельца.",
    # ── DSP ─────────────────────────────────────────────────────
    "DSP_API_URL": "compose",
    "DSP_ACCESS_TOKEN": "compose",
    "DSP_PARTNER_XXHASH": "compose",
    "DSP_DEMO_API_URL": "compose",
    "DSP_DEMO_TOKEN": "compose",
    "DSP_DEMO_PARTNER_XXHASH": "compose",
}


def _env_names_in(path: pathlib.Path) -> set:
    """Имена, читаемые из окружения в одном файле.

    Разбирается деревом, а не регулярным выражением: имя бывает не литералом, а
    константой модуля (`ENV_TOKEN = "DSP_DEMO_TOKEN"`, дальше
    `os.getenv(ENV_TOKEN)`). Регулярка такую переменную не видит — а именно она и есть
    самая свежая из трёх поломок.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consts = {
        t.id: n.value.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, str)
        for t in n.targets if isinstance(t, ast.Name)
    }

    def resolve(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        return None

    found = set()
    for n in ast.walk(tree):
        # os.getenv("X") / os.environ.get("X")
        if isinstance(n, ast.Call) and n.args:
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in ("getenv", "get"):
                base = f.value
                is_env = (
                    (isinstance(base, ast.Name) and base.id == "os")
                    or (isinstance(base, ast.Attribute) and base.attr == "environ")
                )
                if is_env and (name := resolve(n.args[0])):
                    found.add(name)
        # os.environ["X"]
        if isinstance(n, ast.Subscript):
            v = n.value
            if isinstance(v, ast.Attribute) and v.attr == "environ":
                if name := resolve(n.slice):
                    found.add(name)
    return found


def test_every_env_var_is_accounted_for():
    """Код не читает ни одной переменной, про которую не решено, как она доедет."""
    used = set()
    for py in APP.rglob("*.py"):
        used |= _env_names_in(py)

    unlisted = used - set(PASSED_THROUGH)
    assert not unlisted, (
        f"код читает переменные, не описанные здесь: {sorted(unlisted)} — "
        "добавьте их в `environment` сервиса backend в docker-compose.yml и впишите "
        "сюда, иначе значение из .env до процесса не дойдёт и функция отвалится молча"
    )

    stale = set(PASSED_THROUGH) - used
    assert not stale, (
        f"переменные описаны, но кодом больше не читаются: {sorted(stale)} — "
        "уберите их из docker-compose.yml и отсюда, чтобы список не врал"
    )


def test_deliberate_omissions_stay_explained():
    """У каждой непереданной переменной есть причина, а не пустая строка.

    Прибор держит не факт, а РЕШЕНИЕ. Пометка "compose" ставится одним словом, а вот
    отказ передавать требует текста: через полгода отличить «решили не передавать» от
    «забыли» иначе нечем — и именно так дыра трижды воспроизводилась.
    """
    for name, how in PASSED_THROUGH.items():
        if how in ("compose", "runtime"):
            continue
        assert how.startswith("НЕ передаётся") and len(how) > 60, (
            f"{name}: причина отказа не написана или слишком коротка — напишите, "
            "почему переменная недоступна процессу, иначе следующий читатель сочтёт "
            "это забытой строкой и «починит»"
        )
