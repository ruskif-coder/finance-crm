"""Превращает ВЫГРУЖЕННЫЙ медиаплан (xlsx) обратно в ШАБЛОН с токенами {{...}}.

Зачем: дизайн шаблона правит аккаунт — но правит он обычно готовую выгрузку
(там видно реальные данные и переносы), а рендеру нужен файл с токенами.
Скрипт берёт такой файл, оставляет всю вёрстку как есть (стили, ширины, объединения,
логотип, примечания) и заменяет ЗНАЧЕНИЯ на токены.

Разметку не угадываем: адреса ячеек заданы явно ниже. Если аккаунт переставит блоки —
правим только карту адресов, код не трогаем.

Запуск:
  docker cp "новый шаблон мп.xlsx" finance_backend:/tmp/src.xlsx
  docker exec finance_backend python /app/app/mp_tokenize_template.py /tmp/src.xlsx /tmp/mp_template.xlsx
  docker cp finance_backend:/tmp/mp_template.xlsx backend/app/templates/mp_template.xlsx
"""
import sys
from openpyxl import load_workbook

# ── Шапка и блоки-одиночки: адрес → токен ────────────────────────────────
SINGLE = {
    "B3": "{{logo}}",              # якорь логотипа (объединено B3:C5)
    "K3": "{{mp_title}}",
    "K5": "{{mp_subtitle}}",
    "B9": "{{title}}",
    # бриф (левая колонка)
    "C11": "{{agency}}", "C12": "{{advertiser}}", "C13": "{{brand}}",
    "C14": "{{period}}", "C15": "{{date_from}}", "C16": "{{date_to}}",
    # таргетинги (средняя колонка)
    "F11": "{{tg_geo}}", "F12": "{{tg_audience}}", "F13": "{{tg_buys}}",
    "F14": "{{tg_interests}}", "F15": "{{tg_behavior}}", "F16": "{{tg_competitors}}",
    # итоги (правый блок) — рендер подставит сюда формулы со ссылками на строки ИТОГО
    "R11": "{{total_net}}", "R13": "{{total_vat}}", "R15": "{{total_gross}}",
}

# ── Строка-образец размещения: колонка → поле r.* ────────────────────────
ROW_COLS = [
    ("B", "place"), ("C", "position"), ("D", "geo"), ("E", "format"), ("F", "device"),
    ("G", "rotation"), ("H", "model"), ("I", "volume"), ("J", "unit_name"), ("K", "period"),
    ("L", "season"), ("M", "unit_price"), ("N", "net_nodisc"), ("O", "disc_pct"),
    ("P", "disc_rub"), ("Q", "net"), ("R", "vat"), ("S", "gross"),
    ("T", "freq"), ("U", "reach"), ("V", "imp"), ("W", "ctr"), ("X", "clicks"),
    ("Y", "cpm"), ("Z", "cpc"), ("AA", "cpu"), ("AB", "cr"), ("AC", "checks"),
    ("AD", "cpo"), ("AE", "price"), ("AF", "revenue"), ("AG", "roi"), ("AH", "sov"),
]
# Строка ИТОГО под размещениями: только суммируемые колонки
TOT_COLS = [("I", "volume"), ("N", "net_nodisc"), ("P", "disc_rub"), ("Q", "net"),
            ("R", "vat"), ("S", "gross"), ("AF", "revenue")]

# ── Доп. услуги ──────────────────────────────────────────────────────────
EXTRA_COLS = [
    ("B", "place"), ("C", "name"), ("I", "volume"), ("J", "unit_name"), ("K", "period"),
    ("L", "season"), ("M", "unit_price"), ("N", "net_nodisc"), ("O", "disc_pct"),
    ("P", "disc_rub"), ("Q", "total"), ("R", "vat"), ("S", "gross"),
]
EXTRA_TOT_COLS = [("N", "net_nodisc"), ("P", "disc_rub"), ("Q", "total"), ("R", "vat"), ("S", "gross")]

# Номера строк в исходной вёрстке
R_SAMPLE, R_TOTAL = 21, 22          # размещение: образец и ИТОГО
E_SAMPLE, E_TOTAL = 26, 27          # доп. услуги: образец и ИТОГО


def tokenize(src, dst):
    wb = load_workbook(src)
    ws = wb["МП"] if "МП" in wb.sheetnames else wb.active

    for addr, token in SINGLE.items():
        ws[addr] = token
    for col, field in ROW_COLS:
        ws[f"{col}{R_SAMPLE}"] = "{{r.%s}}" % field
    for col, field in TOT_COLS:
        ws[f"{col}{R_TOTAL}"] = "{{t.%s}}" % field
    for col, field in EXTRA_COLS:
        ws[f"{col}{E_SAMPLE}"] = "{{e.%s}}" % field
    for col, field in EXTRA_TOT_COLS:
        ws[f"{col}{E_TOTAL}"] = "{{te.%s}}" % field

    # Логотип рендер вставляет сам каждый раз (openpyxl теряет картинки при
    # round-trip) — вшитую в исходник убираем, иначе получим две.
    ws._images = []

    wb.save(dst)
    print(f"шаблон собран: {dst}")
    print(f"  одиночных токенов: {len(SINGLE)}")
    print(f"  размещение: строка {R_SAMPLE} ({len(ROW_COLS)} колонок), ИТОГО {R_TOTAL}")
    print(f"  доп. услуги: строка {E_SAMPLE} ({len(EXTRA_COLS)} колонок), ИТОГО {E_TOTAL}")


if __name__ == "__main__":
    tokenize(sys.argv[1] if len(sys.argv) > 1 else "/tmp/src.xlsx",
             sys.argv[2] if len(sys.argv) > 2 else "/tmp/mp_template.xlsx")
