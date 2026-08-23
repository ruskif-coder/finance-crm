"""
Разовый бэкфилл реквизитов контрагентов из выгрузки Битрикс24 (COMPANY_*.xlsx).

Матчинг по ИНН (+ по названию для тех, у кого ИНН не заполнен).
Идемпотентный: заполняет ТОЛЬКО пустые поля, никогда не перезатирает заполненные.
Исключение — явный список DIRECTOR_OVERRIDES (сверен по ЕГРЮЛ вручную, см. ниже).

Особенности исходного файла (важно, иначе матчинг ломается):
  - ИНН/КПП/ОГРН/ОКПО выгружены как float ('1673005251.0'). Наивная очистка
    регуляркой \\D даёт лишний ноль в конце и 0 совпадений — приводим к int.
  - ФИО директора в файле КАПСОМ — приводим к Title Case под наш формат.

Запуск (сначала всегда сухой прогон):
    docker exec finance_backend python -m scripts.backfill_counterparty_requisites /tmp/222.xlsx
    docker exec finance_backend python -m scripts.backfill_counterparty_requisites /tmp/222.xlsx --apply
"""
import re
import sys

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Counterparty, CounterpartyBankAccount

# Поля, которые дозаполняем (наше поле -> колонка в выгрузке).
NUM_FIELDS = {
    "kpp": "Реквизит (Россия): КПП",
    "ogrn": "Реквизит (Россия): ОГРН",
    "okpo": "Реквизит (Россия): ОКПО",
}
TXT_FIELDS = {
    # address собирается из компонентов через build_address(), а не из готового поля
    "phone": "Рабочий телефон",
    "email": "Рабочий e-mail",
    "director_name": "Реквизит (Россия): Ген. директор",
    "website": "Корпоративный сайт",
}

# Директора, где наше значение и файл разошлись. Сверено по агрегаторам ЕГРЮЛ
# (rusprofile/checko/РБК/СПАРК) 2026-07-22. Ключ — ИНН контрагента.
# None = оставить наше значение (файл устарел/ошибочен).
DIRECTOR_OVERRIDES = {
    "7736207543": "Савиновский Артем Геннадьевич",   # ЯНДЕКС — у нас была Бунина (устарело)
    "7723828649": "Паршин Евгений Аркадьевич",       # АРТИКС ИС — у нас был Новоселов (устарело)
    "9725041522": None,                              # МАЙ ПЕРФОМАНС — наше верно, в файле ошибка
    "7724890784": "Богданов Антон Олегович",         # ОРМАТЕК — устарели и наше, и файл
}

FORMS = {"ооо", "оао", "зао", "ао", "пао", "ип", "нао", "ано", "лтд", "ltd", "llc", "inc"}

# Готовое поле "Реквизит (Россия): Адрес" в выгрузке склеено криво
# ('Д. Д. 25 ПОМЕЩ. ПОМЕЩ. 516'), поэтому адрес собираем из компонентов.
ADDR_PARTS = {
    "idx": "Реквизит (Россия): Адрес - почтовый индекс",
    "reg": "Реквизит (Россия): Адрес - регион",
    "city": "Реквизит (Россия): Адрес - населенный пункт",
    "street": "Реквизит (Россия): Адрес - улица, номер дома",
    "flat": "Реквизит (Россия): Адрес - квартира, офис, комната, этаж",
}
# Служебные слова адреса — оставляем строчными, как в нашем формате
# ('105082, г. Москва, пер. Переведеновский, д. 13 стр. 18, офис 612').
ADDR_LOWER = {
    "ул", "улица", "пр-кт", "проспект", "пр-д", "проезд", "пер", "переулок", "ш", "шоссе",
    "наб", "набережная", "пл", "площадь", "б-р", "бульвар", "тракт", "линия", "аллея",
    "д", "дом", "двлд", "влд", "стр", "строение", "к", "корп", "корпус", "литера", "литер",
    "пом", "помещ", "помещение", "оф", "офис", "этаж", "эт", "ком", "кв", "антресоль",
    "г", "гор", "город", "пгт", "с", "село", "п", "поселок", "посёлок", "р-н", "район",
    "обл", "область", "респ", "республика", "край", "мкр", "тер", "муниципальный", "округ",
    "г.п", "вн.тер.г",
}


# Предлоги внутри составных топонимов остаются строчными: 'Ростов-на-Дону',
# 'Комсомольск-на-Амуре', 'Франкфурт-на-Майне'.
ADDR_PARTICLES = {"на", "над", "под", "при", "у", "в", "из", "за", "по"}


def _cap_word(tok):
    """Заглавная у каждой части составного слова: 'САНКТ-ПЕТЕРБУРГ' -> 'Санкт-Петербург'.
    Без разбиения по дефису str.capitalize() даёт 'Санкт-петербург'.
    Части-сокращения ('пр-д', 'пр-кт', 'б-р', 'р-н') остаются строчными целиком."""
    parts = tok.split("-")
    if len(parts) > 1 and tok.strip(".,").lower() in ADDR_LOWER:
        return tok.lower()
    return "-".join(
        p.lower() if i and p.strip(".,").lower() in ADDR_PARTICLES else (p.capitalize() if p else p)
        for i, p in enumerate(parts)
    )


def nice_case(s):
    """КАПС из выгрузки -> читаемый вид: служебные слова строчными, остальное с заглавной.
    Токены с цифрами и римские номера помещений ('№II', 'XIV') не трогаем."""
    out = []
    for tok in str(s).split():
        core = tok.strip(".,").lower()
        bare = tok.strip(".,№").upper()
        if any(ch.isdigit() for ch in tok):
            out.append(tok)
        elif bare and set(bare) <= set("IVXLCDM"):
            out.append(tok.upper())          # римская нумерация помещений — только верхний регистр
        elif core in ADDR_LOWER:
            out.append(tok.lower())
        else:
            out.append(_cap_word(tok))
    return " ".join(out)


def build_address(row):
    """Собирает юр. адрес из компонентов. None, если данных нет или они мусорные."""
    parts = {k: txt(row.get(c)) for k, c in ADDR_PARTS.items()}
    street = parts["street"]
    if not street:
        return None

    reg = parts["reg"] or ""
    # 'РЕСПУБЛИКА ТАТАРСТАН (ТАТАРСТАН)' -> 'Республика Татарстан'
    reg = re.sub(r"\s*\([^)]*\)", "", reg).strip()
    # 'Г.МОСКВА' / 'Г.САНКТ-ПЕТЕРБУРГ' -> 'г. Москва'
    reg = re.sub(r"^Г\.\s*", "г. ", reg, flags=re.IGNORECASE)

    city = parts["city"] or ""
    # у городов федерального значения город дублирует регион — не повторяем
    if city and reg and city.split(",")[0].strip().lower() in reg.lower():
        city = ""
    # 'Г.П. ПОСЕЛОК ГОРОДСКОГО ТИПА ВАСИЛЬЕВО, ПГТ ВАСИЛЬЕВО' -> берём последнюю, короткую форму
    if city and "," in city:
        city = city.split(",")[-1].strip()

    chunks = [p for p in (parts["idx"], nice_case(reg) if reg else None,
                          nice_case(city) if city else None,
                          nice_case(street),
                          nice_case(parts["flat"]) if parts["flat"] else None) if p]
    addr = ", ".join(chunks)
    addr = re.sub(r"\s+", " ", addr).strip(" ,")
    # мусор из Битрикса: в поле адреса попадал e-mail; адрес без цифр бесполезен
    if "@" in addr or not re.search(r"\d", addr):
        return None
    return addr or None


def digits(v):
    """Только цифры. Числа из Excel приходят как float — иначе '.0' даёт лишний ноль."""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", str(v)) or None


def txt(v):
    if v is None or pd.isna(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip() or None


def title_fio(s):
    """КАПС из выгрузки -> наш Title Case. 'ИВАНОВ ПЁТР' -> 'Иванов Пётр'."""
    s = txt(s)
    return s.title() if s else None


def name_key(s):
    """Ключ сравнения названий: без орг-формы, пунктуации и порядка слов."""
    s = re.sub(r"[^0-9a-zа-яё ]", " ", str(s or "").lower())
    return " ".join(sorted(t for t in s.split() if t and t not in FORMS))


def run(path: str, apply: bool):
    df = pd.read_excel(path)
    df["inn_n"] = df["Реквизит (Россия): ИНН"].apply(digits)
    by_inn = df[df["inn_n"].notna()].drop_duplicates("inn_n", keep="first").set_index("inn_n")

    by_name = {}
    for _, r in df.iterrows():
        for col in ("Название компании",
                    "Реквизит (Россия): Сокращенное наименование организации",
                    "Название компании2"):
            k = name_key(r.get(col))
            if k and k not in by_name:
                by_name[k] = r

    db: Session = SessionLocal()
    stats = {"inn_set": 0, "fields": 0, "banks": 0, "overrides": 0}
    try:
        cps = db.query(Counterparty).all()
        banked = {b.counterparty_id for b in db.query(CounterpartyBankAccount).all()}

        for cp in cps:
            inn = digits(cp.inn)
            row = None

            if inn and inn in by_inn.index:
                row = by_inn.loc[inn]
            elif not inn:
                # ИНН не заполнен — пробуем найти по названию и заодно проставить ИНН
                cand = by_name.get(name_key(cp.name))
                if cand is not None:
                    cand_inn = digits(cand.get("Реквизит (Россия): ИНН"))
                    if cand_inn:
                        print(f"  ИНН  {cp.name}: -> {cand_inn}")
                        if apply:
                            cp.inn = cand_inn
                        stats["inn_set"] += 1
                        inn, row = cand_inn, cand
            if row is None:
                continue

            if not cp.address:
                addr = build_address(row)
                if addr:
                    print(f"  SET  {cp.name} . address = {addr[:80]}")
                    if apply:
                        cp.address = addr
                    stats["fields"] += 1

            for field, col in list(NUM_FIELDS.items()) + list(TXT_FIELDS.items()):
                raw = row.get(col)
                if field in NUM_FIELDS:
                    new = digits(raw)
                elif field == "director_name":
                    new = title_fio(raw)
                else:
                    new = txt(raw)
                if not new:
                    continue
                if getattr(cp, field):       # заполнено — не трогаем
                    continue
                print(f"  SET  {cp.name} . {field} = {str(new)[:60]}")
                if apply:
                    setattr(cp, field, new)
                stats["fields"] += 1

            # Явные правки директора по сверке с ЕГРЮЛ
            if inn in DIRECTOR_OVERRIDES:
                fixed = DIRECTOR_OVERRIDES[inn]
                if fixed and cp.director_name != fixed:
                    print(f"  FIX  {cp.name} . director_name: {cp.director_name} -> {fixed}")
                    if apply:
                        cp.director_name = fixed
                    stats["overrides"] += 1

            # Банковские реквизиты — только если у контрагента их вообще нет
            rs = txt(row.get("Банковский реквизит (Россия): Расчетный счёт"))
            if rs and cp.id not in banked:
                acc = dict(
                    bank_name=txt(row.get("Банковский реквизит (Россия): Наименование банка")),
                    rs=rs,
                    ks=txt(row.get("Банковский реквизит (Россия): Кор. счёт")),
                    bik=digits(row.get("Банковский реквизит (Россия): БИК")),
                )
                print(f"  BANK {cp.name}: {acc['bank_name']} р/с {acc['rs']}")
                if apply:
                    db.add(CounterpartyBankAccount(counterparty_id=cp.id, sort_order=0, **acc))
                stats["banks"] += 1

        if apply:
            db.commit()
            print("\nПРИМЕНЕНО.")
        else:
            db.rollback()
            print("\nСУХОЙ ПРОГОН — ничего не записано. Повтори с --apply.")
        print(f"ИНН проставлено: {stats['inn_set']} | полей: {stats['fields']} | "
              f"правок директора: {stats['overrides']} | банк.реквизитов: {stats['banks']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    run(args[0], apply="--apply" in sys.argv)
