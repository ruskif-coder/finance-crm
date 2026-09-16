# -*- coding: utf-8 -*-
"""Редактор шаблонов писем: оболочка контура и тексты карточек.

Экран `/settings/mail-templates`. Логика правок и настроек взята из хендоффа
`docs/шаблонизатор.zip`, перечень событий и данные — НАШИ (владелец 16.09.2026).

## Что здесь правится, а что нет

    правится   тема, прехедер, заголовок, подзаголовок, подвал — одна оболочка на контур
    правится   заголовок, текст, подпись кнопки карточки — по одному на событие
    НЕ правится тон, набор событий, получатели, пороги повторов — они из реестра

Тон приходит из каталога и здесь только показывается. Разреши мы менять его текстом —
письмо и панель разошлись бы по важности одного и того же события.

## Хранятся ТОЛЬКО ОТКЛОНЕНИЯ

Строки нет — текст берётся из каталога (`registry.EVENTS`, `outward.kinds`). Отсюда
«вернуть правило» = удалить запись, а новое событие приезжает со своим текстом само,
без бэкфилла. Тот же порядок, что у матрицы уведомлений площадки.

Лежит это в `company_settings` — таблице ключ-значение, где уже живут имя отправителя,
подпись и часы рассылки. Отдельной таблицы не заводим: это настройка текста, а не
первичные данные, и схема первичных данных согласуется до кода отдельно.

## Прехедер и подзаголовок — ПРАВИЛО, а не строка

Письмо про одну сверку и письмо про четыре срочных события обещают получателю разное,
поэтому по умолчанию шапка собирается из подстановок и считается из состава письма:

    {срочное}   «Два события требуют действия сегодня» либо «Ничего срочного — только
                подтверждения»; согласование числительного обязательно, иначе письмо
                пишет «2 событий»
    {темы}      перечень тегов карточек письма через запятую
    {всего}     сколько карточек в письме

Как только человек вписал свой текст, поле перестаёт следовать за содержимым — и это
видно на экране, вместе с кнопкой «вернуть правило».

## Подстановки — НАШИ, в одинарных скобках

`{площадка}`, `{период}`, `{сумма}` — тот же синтаксис, что у остальных шаблонов проекта
(`mail/templates.py`). Двойные скобки из хендоффа не берём: два синтаксиса подстановки в
одной системе означают, что половина текстов однажды уедет с фигурными скобками внутри.

**У внешнего контура нет подстановки с кодом сделки.** Это не забывчивость, а правило:
наш код наружу не уходит. Проверка перед сохранением ловит его отдельно.
"""
from __future__ import annotations

import json
from typing import Dict, List

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.mail import preview, render
from app import timez

STAFF, PUB = preview.STAFF, preview.PUB

KEY_SHELL = "mail_shell_{}"          # оболочка контура
KEY_CARDS = "mail_cards_{}"          # отклонения текстов карточек

# Поля оболочки в порядке появления в письме.
SHELL_FIELDS = ("subject", "preheader", "headline", "subtitle", "footer")

SHELL_LABEL = {
    "subject": "Тема письма",
    "preheader": "Прехедер — строка под темой в списке писем",
    "headline": "Заголовок в шапке",
    "subtitle": "Подзаголовок",
    "footer": "Подвал",
}

# Умолчания — ПРАВИЛА. Заменить их фиксированным текстом можно, но тогда письмо перестанет
# отвечать на вопрос «что сегодня важного», а это и есть его работа.
SHELL_DEFAULT = {
    STAFF: {
        "subject": "{всего} · {темы}",
        "preheader": "{срочное} · {темы}",
        "headline": "{имя}, за сутки {всего}",
        "subtitle": "{срочное} Остальное — к сведению.",
        "footer": "Полная очередь всегда в дашборде. Состав и час дайджеста — в настройках уведомлений.",
    },
    PUB: {
        "subject": "{площадка} · {всего}",
        "preheader": "{срочное} · {темы}",
        "headline": "{площадка} · за сутки {всего}",
        "subtitle": "{срочное} Подробности и ответ — в кабинете.",
        "footer": "Что приходит на почту — настраивается в кабинете.",
    },
}

# Поля карточки, которые правятся. `tone`, `tag` и получателей редактор не трогает.
CARD_FIELDS = ("title", "body", "action")

# Переключатели карточки. Хранятся так же, как тексты — ОТКЛОНЕНИЕМ: значение по
# умолчанию строки не оставляет, поэтому «вернуть как было» это удаление записи.
CARD_FLAGS = {"show_button": True}


# ── подстановки: значения берём из НАШЕЙ базы ───────────────────────────────

# Примерные ЗНАЧЕНИЯ плашек для предпросмотра. Ключи объявляет каталог видов; здесь
# только то, чем их наполнить на экране. Денежных ключей тут нет и быть не может.
PIN_SAMPLE = {
    "комплект": "№9701",
    "услуга": "еФарм web",
    "ждём ответа с": "12.09",
    "старт": "22.09",
    "ЕРИД": "2SDnje8TgHY",
    "мест без требований": "3",
    "поверхность": "web",
    "план показов": "1 200 000",
    "факт показов": "840 000",
    "отставание": "−12%",
    "последний запрос": "14.09, 03:40",
    "рекламных мест": "5",
    "показов всего": "1 180 000",
    "выполнение плана": "98%",
    "продлеваем до": "31.10",
    "показов у нас": "1 180 000",
    "показов у вас": "1 176 400",
    "расхождение": "0,3%",
    "акт": "№ 214 от 30.09",
    "УПД": "№ 214",
    "ждём с": "05.10",
    "документ": "акт № 214",
    "дата платежа": "07.10",
    "действует до": "31.12.2026",
}

def sample(db: Session, contour: str) -> dict:
    """Живой пример для подстановок: настоящая сделка и настоящая площадка.

    Выдуманные «ООО Ромашка» и «1 000 000 ₽» делают предпросмотр бесполезным: по ним не
    видно ни длины реальных названий, ни того, как ложится настоящий период. Берём
    последнюю сделку с кодом, названием и суммой — и живую площадку с кабинетом.
    """
    out = {"имя": "коллеги", "площадка": "", "домен": "", "бренд": "",
           "период": "", "сумма": "", "дней": "3", "ссылка": ""}

    # Бренд берём СВЯЗЬЮ, а не разбором названия. Разбор по «·» стоял здесь и на живых
    # данных не работал: из 948 сделок прода точку-разделитель содержат 2, вертикальную
    # черту — 48, остальные не содержат ничего, и «бренд» получался равен всему
    # внутреннему заголовку вида «Berlin-Chemie | Лиотон | MI | еФарм WEB | 2026-10».
    # Площадке это ушло бы подстановкой {бренд} — вместе с нашим названием услуги.
    deal = db.execute(sa_text("""
        SELECT d.code, d.title, d.amount, d.period_from, d.period_to, b.name AS brand
          FROM sales_deals d
          LEFT JOIN sales_brands b ON b.id = d.brand_id
         WHERE coalesce(d.code,'') <> '' AND coalesce(d.title,'') <> ''
           AND coalesce(d.amount,0) > 0 AND d.brand_id IS NOT NULL
         ORDER BY d.id DESC LIMIT 1""")).first()
    pub = db.execute(sa_text("""
        SELECT p.name, p.domain FROM sales_publishers p
         WHERE p.status <> 'АРХИВ'
           AND EXISTS (SELECT 1 FROM cabinet_publisher cp WHERE cp.publisher_id = p.id)
         ORDER BY p.id LIMIT 1""")).first()

    if deal:
        out["сумма"] = f"{deal.amount:,.0f} ₽".replace(",", " ")
        out["период"] = _period(deal.period_from, deal.period_to)
        out["бренд"] = deal.brand or ""
        if contour == STAFF:
            # Ярлык сделки «код · имя» — внутренний, тот же порядок, что на карточке.
            out["сделка"] = f"{deal.code} · {deal.title}"
    if pub:
        out["площадка"] = pub.name or ""
        out["домен"] = pub.domain or ""
    out["ссылка"] = render.abs_url("/campaigns" if contour == PUB
                                   else "/accounts/dashboard") or ""
    return out


def _period(a, b) -> str:
    if not a:
        return ""
    months = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль",
              "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
    if b and (a.year, a.month) == (b.year, b.month):
        return f"{months[a.month - 1]} {a.year}"
    return f"{a.strftime('%d.%m')} — {b.strftime('%d.%m.%Y')}" if b else a.strftime("%d.%m.%Y")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Согласование с числом. Одиннадцать — главная ловушка: по последней цифре оно
    было бы «событие»."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


def computed(cards: List[dict]) -> dict:
    """Три подстановки, которые СЧИТАЮТСЯ из состава письма и не набираются текстом."""
    n = len(cards)
    need = sum(1 for c in cards if (c.get("tone") or "info") in ("bad", "warn"))
    if not n:
        urgent = "Письмо пустое."
    elif not need:
        urgent = "Ничего срочного — только подтверждения."
    else:
        word = plural(need, "Одно событие требует", f"{need} события требуют",
                      f"{need} событий требуют")
        urgent = f"{word} действия сегодня."
    topics = []
    for c in cards:
        t = (c.get("tag") or "").strip()
        if t and t not in topics:
            topics.append(t)
    return {
        "срочное": urgent,
        "темы": ", ".join(topics),
        "всего": f"{n} " + plural(n, "событие", "события", "событий"),
    }


def values(db: Session, contour: str, cards: List[dict]) -> dict:
    """Все доступные подстановки: данные плюс посчитанное из состава."""
    v = sample(db, contour)
    v.update(computed(cards))
    return v


def fields_of(contour: str) -> Dict[str, str]:
    """Перечень подстановок для экрана. У внешнего контура СДЕЛКИ НЕТ — наш код наружу
    не уходит, и показывать поле, которое нельзя использовать, значит предлагать ошибку.
    """
    common = {
        "имя": "к кому обращаемся",
        "площадка": "название площадки",
        "домен": "домен площадки",
        "бренд": "бренд рекламодателя",
        "период": "период размещения",
        "дней": "сколько дней осталось",
        "ссылка": "ссылка на экран",
        "срочное": "фраза про срочные события — считается из состава",
        "темы": "перечень тем письма — считается из состава",
        "всего": "сколько событий в письме — считается",
    }
    if contour == STAFF:
        # Только внутри: наш код сделки и наши деньги наружу не уходят. Предлагать
        # площадке подстановку, которую нельзя использовать, значит предлагать ошибку.
        common["сделка"] = "ярлык сделки: код · название"
        common["сумма"] = "сумма сделки"
    return common


# ── хранилище: только отклонения ────────────────────────────────────────────

def _get(db: Session, key: str) -> dict:
    raw = db.execute(sa_text("SELECT value FROM company_settings WHERE key = :k"),
                     {"k": key}).scalar()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        # Испорченное значение не должно ронять экран целиком: тексты вернутся
        # каталожные, и это видно, а падение — нет.
        return {}


def _put(db: Session, key: str, data: dict) -> None:
    db.execute(sa_text(
        "INSERT INTO company_settings (key, value) VALUES (:k, :v) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
        {"k": key, "v": json.dumps(data, ensure_ascii=False)})


def shell(db: Session, contour: str) -> dict:
    """Оболочка контура: что задано вручную, что осталось правилом."""
    own = _get(db, KEY_SHELL.format(contour))
    base = SHELL_DEFAULT[contour]
    return {f: {"value": own.get(f, base[f]), "default": base[f],
                "manual": f in own, "label": SHELL_LABEL[f]} for f in SHELL_FIELDS}


def save_shell(db: Session, contour: str, patch: dict) -> None:
    """Сохранить правки оболочки. Значение, совпавшее с правилом, СТРОКИ НЕ ОСТАВЛЯЕТ —
    иначе «вернуть правило» перестало бы отличаться от «вписать то же самое»."""
    own = _get(db, KEY_SHELL.format(contour))
    base = SHELL_DEFAULT[contour]
    for f, v in patch.items():
        if f not in SHELL_FIELDS:
            continue
        if v is None or str(v).strip() == base[f]:
            own.pop(f, None)
        else:
            own[f] = str(v).strip()[:600]
    _put(db, KEY_SHELL.format(contour), own)


def cards(db: Session, contour: str) -> List[dict]:
    """Карточки контура: каталог плюс правки, с пометкой, что именно переопределено."""
    own = _get(db, KEY_CARDS.format(contour))
    out = []
    for c in [x for x in preview.contours() if x["key"] == contour][0]["cards"]:
        patch = own.get(c["key"], {})
        base = {"title": c["label"], "body": c["hint"], "action": c["action"]}
        out.append({**c,
                    **{f: patch.get(f, base[f]) for f in CARD_FIELDS},
                    **{f: bool(patch.get(f, d)) for f, d in CARD_FLAGS.items()},
                    "base": base,
                    "edited": sorted(k for k in patch
                                     if k in CARD_FIELDS or k in CARD_FLAGS)})
    return out


def save_card(db: Session, contour: str, key: str, patch: dict) -> None:
    own = _get(db, KEY_CARDS.format(contour))
    catalog = {c["key"]: c for c in cards(db, contour)}
    if key not in catalog:
        raise KeyError(key)
    base, cur = catalog[key]["base"], own.get(key, {})
    for f, v in patch.items():
        if f in CARD_FLAGS:
            # Значение по умолчанию записи не оставляет: иначе «вернуть как было»
            # перестало бы отличаться от «поставить то же самое».
            if v is None or bool(v) == CARD_FLAGS[f]:
                cur.pop(f, None)
            else:
                cur[f] = bool(v)
            continue
        if f not in CARD_FIELDS:
            continue
        if v is None or str(v).strip() == (base[f] or "").strip():
            cur.pop(f, None)
        else:
            cur[f] = str(v).strip()[:600]
    if cur:
        own[key] = cur
    else:
        own.pop(key, None)
    _put(db, KEY_CARDS.format(contour), own)


# ── сборка письма и проверки ────────────────────────────────────────────────

def compose(db: Session, contour: str, keys: List[str], *, brand: str = "SIMB-AD") -> str:
    """Собрать письмо из оболочки и выбранных карточек — ровно то, что увидит человек.

    Состав здесь ЛОКАЛЬНЫЙ, для проверки вида: настоящий состав определяет рассылка. Но
    рисуется он тем же `render`, что и живое письмо, — иначе редактор показывал бы то,
    чего не бывает.
    """
    chosen = [c for c in cards(db, contour) if c["key"] in keys]
    data = [{
        "title": c["title"], "body": c["body"], "tone": c["tone"], "tag": c["tag"],
        "action": c["action"], "when": "09:30",
        # Кнопки нет — нет и ссылки: рисовальщик письма опирается именно на неё
        # (`render._button`). Подтверждению («ЕРИД выпущен», «оплата отправлена») кнопка
        # не нужна — идти по ней некуда, а синий прямоугольник требует действия.
        "link_abs": (render.abs_url("/campaigns" if contour == PUB else "/accounts/dashboard")
                     if c.get("show_button", True) else None),
        "facts": facts_of(db, contour, c),
        "context": None if contour == STAFF else _context(db, contour),
    } for c in chosen]

    v = values(db, contour, data)
    sh = shell(db, contour)
    text_of = lambda f: subst(sh[f]["value"], v)          # noqa: E731
    return render.composed_html(
        cards_data=data, headline=text_of("headline"), sub=text_of("subtitle"),
        preheader=text_of("preheader"), footer=text_of("footer"),
        brand=brand, when=timez.msk_now(),
        logo_url=render.abs_url(render.LOGO_PATH),
        settings_url=render.abs_url(
            render.SETTINGS_PATH if contour == STAFF else "/settings"))


def _context(db: Session, contour: str) -> str:
    """Строка контекста внешней карточки: площадка · бренд · период. Наших кодов в ней
    нет — правило про то, что наружу уходит только то, что площадка и так знает."""
    v = sample(db, contour)
    return " · ".join(x for x in (v.get("площадка"), v.get("бренд"), v.get("период")) if x)


def facts_of(db: Session, contour: str, card: dict) -> list:
    """Плашки фактов карточки — ОБЪЯВЛЕННЫЕ видом, а не придуманные предпросмотром.

    Ключи берутся из каталога (`kinds.NotifyKind.facts` у площадок), значения — примерные,
    из `PIN_SAMPLE`. Так экран показывает тот же состав плашек, что соберёт отправитель;
    выдуманный набор означал бы, что по предпросмотру правят текст под плашки, которых в
    письме не будет.

    Два правила, оба из разбора письма 16.09.2026:

    · плашка НЕ ПОВТОРЯЕТ строку контекста. У внешнего письма там уже стоят площадка,
      бренд и период — «БРЕНД Хелинорм» под строкой «Maksavit.ru · Хелинорм · сентябрь»
      занимает место, не сказав ничего нового;
    · ДЕНЕГ У ПЛОЩАДКИ НЕТ. Ни суммы, ни ставки: внутри компании это рабочее число,
      снаружи — наша маржа. Отдельно от заслона на отправке (`outward/send.strip_money`),
      потому что предпросмотр идёт мимо неё.
    """
    if contour == PUB:
        from app.notify.outward.kinds import by_key

        kind = by_key(card["key"])
        keys = list(getattr(kind, "facts", ()) or ())
        return [(k, PIN_SAMPLE.get(k, "—")) for k in keys][:4]

    # Внутри компании контекста у карточки нет, и сделка с суммой — ровно те числа,
    # ради которых письмо открывают.
    v = sample(db, contour)
    out = []
    if v.get("сделка"):
        out.append(("сделка", v["сделка"].split(" · ")[0]))
    if v.get("сумма"):
        out.append(("сумма", v["сумма"]))
    if v.get("период"):
        out.append(("период", v["период"]))
    return out[:4]


def subst(textv: str, vals: dict) -> str:
    """Подстановка теми же правилами, что и в шаблонах писем: незаполненное поле
    становится пустотой, а не скобками. Скобки в готовом письме читаются получателем
    как неисправность системы."""
    from app.mail import templates as tpl
    out = tpl.render(textv or "", vals)
    while "  " in out:
        out = out.replace("  ", " ")
    return out.strip()


def checks(db: Session, contour: str, keys: List[str]) -> List[dict]:
    """Четыре правила из хендоффа, посчитанные на текущем содержимом.

    Проверка НЕ запрещает сохранение — она показывает, чем письмо будет плохо. Запрет
    здесь означал бы, что человек не может сохранить черновик и уйти.
    """
    sh = shell(db, contour)
    chosen = [c for c in cards(db, contour) if c["key"] in keys]
    data = [{"tone": c["tone"], "tag": c["tag"]} for c in chosen]
    v = values(db, contour, data)
    subject = subst(sh["subject"]["value"], v)

    out = [{
        "key": "subject",
        "ok": len(subject) <= 60,
        "text": f"Тема не длиннее 60 знаков — сейчас {len(subject)}",
        "hint": "Длинная тема обрежется в списке писем, и человек увидит начало без сути.",
    }, {
        "key": "action",
        "ok": all((c["action"] or "").strip() for c in chosen) if chosen else True,
        "text": "У каждой карточки есть подпись кнопки",
        "hint": "Кнопка без глагола не говорит, что от человека хотят.",
    }, {
        "key": "facts",
        "ok": all(2 <= len(facts_of(db, contour, c)) <= 4 for c in chosen) if chosen else True,
        "text": "Плашек от двух до четырёх",
        "hint": "Одна плашка — факту место в заголовке; пять и больше — карточка "
                "превращается в таблицу.",
    }]
    if contour == PUB:
        # НАШЕГО КОДА НАРУЖУ НЕТ. Правило владельца, и проверка на него стоит отдельно:
        # подстановки «сделка» во внешнем контуре нет вовсе, но текст можно вписать руками.
        def _find(marker):
            found = [SHELL_LABEL[f] for f in SHELL_FIELDS if marker in (sh[f]["value"] or "")]
            found += [c["key"] for c in chosen
                      if any(marker in (c.get(f) or "") for f in CARD_FIELDS)]
            return found

        bad = _find("{сделка}")
        out.append({
            "key": "no_deal_code",
            "ok": not bad,
            "text": "Во внешнем письме нет кода сделки",
            "hint": "Наш внутренний номер площадке бесполезен и показывает о нас больше, "
                    "чем нужно." + (f" Нашлось в: {', '.join(bad)}" if bad else ""),
        })
        # ДЕНЬГИ отдельной проверкой: подстановки «сумма» во внешнем контуре нет, но
        # текст пишет человек, и он может вписать её руками — вместе со скобками.
        money = _find("{сумма}")
        out.append({
            "key": "no_money",
            "ok": not money,
            "text": "Во внешнем письме нет наших сумм",
            "hint": "Наши суммы — это наша маржа и условия с клиентом; площадке они не "
                    "адресованы." + (f" Нашлось в: {', '.join(money)}" if money else ""),
        })
    return out
