from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import sys

wb = Workbook()

C_HEADER_BG  = "2F5597"
C_HEADER_FG  = "FFFFFF"
C_MATCH      = "E2EFDA"
C_NEW        = "FFF2CC"
C_SKIP       = "F2F2F2"
C_CONFLICT   = "FCE4D6"
C_DELETED    = "D9D9D9"
C_BACKFILL   = "DDEBF7"

thin = Side(style="thin", color="AAAAAA")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

def h_font(bold=True, color=C_HEADER_FG, size=10):
    return Font(name="Arial", bold=bold, color=color, size=size)
def h_fill(color):
    return PatternFill("solid", start_color=color, fgColor=color)
def center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)
def left_w():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)

def style_header(cell, bg=C_HEADER_BG):
    cell.font = h_font()
    cell.fill = h_fill(bg)
    cell.alignment = center()
    cell.border = border

def set_col_widths(ws, widths):
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

# ──────────────────────────────────────────────────────
# SHEET 1 — Сравнение
# ──────────────────────────────────────────────────────
ws1 = wb.active
ws1.title = "Сравнение"
ws1.row_dimensions[1].height = 40

headers1 = [
    "Статус", "CSV Название", "CSV Номер договора", "CSV Дата", "CSV Дата оконч.",
    "deferralDays", "НДС", "docType", "ownLegalRole", "Тип КА", "deletedAt",
    "БД id", "БД Контрагент", "БД Номер", "БД term_days", "БД end_date_text", "Комментарий"
]
for col, h in enumerate(headers1, 1):
    cell = ws1.cell(row=1, column=col, value=h)
    style_header(cell)

status_bg = {
    "СОВПАДЕНИЕ": C_MATCH, "НОВЫЙ": C_NEW, "КОНФЛИКТ": C_CONFLICT,
    "УДАЛЁН": C_DELETED, "ТЕСТ": C_SKIP, "ДУБ CSV": C_SKIP,
}

rows1 = [
    ("СОВПАДЕНИЕ","ДД Инсайт Люди","PM-24-12-2024","2024-12-24","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",51,"ИНСАЙТ ЛЮДИ ООО","PM-24-12-2024",None,"31.12.2025","Точное совпадение"),
    ("СОВПАДЕНИЕ","ДД Нектарин","№ УК-ПМ-1103","2024-03-11","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",36,"НЕКТАРИН УК ООО","УК-ПМ-1103",None,"31.12.2024","Совпадение (убран '№ ')"),
    ("СОВПАДЕНИЕ","ДД Сайтсинг","PM-01-08-23","2023-08-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",22,"САЙТСИНГ ООО","PM-01-08-23",None,"31.12.2023","Точное совпадение"),
    ("СОВПАДЕНИЕ","ДД ЭмДжиКом","РМ 01-12-2023","2022-12-01","31.12.2026",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",11,"ЭМДЖИКОМ ООО","РМ 01-12-2023",None,"31.12.2023 года","end_date устарел → обновить на 2026"),
    ("СОВПАДЕНИЕ","ДД Уайт Бокс Медиа","РМ 30-11-2023","2023-11-30","31.12.2025",30,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",21,"УАЙТ БОКС МЕДИА ООО","РМ 30-11-2023",None,None,"Совпадение; deferral=30 (не 60!)"),
    ("ДУБ CSV","ООО «Уайт Бокс Медиа»","РМ 30-11-2023","2023-11-30","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",21,"УАЙТ БОКС МЕДИА ООО","РМ 30-11-2023",None,None,"Дубликат в CSV (другой UUID, тот же номер) — пропускаем"),
    ("СОВПАДЕНИЕ","МегаБайт","РМ-30-08-24","2024-08-30","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",30,"МЕГАБАЙТ ООО","РМ-30-08-24",None,None,"Точное совпадение"),
    ("СОВПАДЕНИЕ","Безен Хелскеа РУС","PM-31-01-25","2025-01-30","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","ADVERTISER","",55,"БЕЗЕН ХЕЛСКЕА РУС ООО","РМ-31-01-25",None,None,"Совпадение (PM↔РМ формат)"),
    ("СОВПАДЕНИЕ","ДД Кванза Медиа Баинг","222035","2024-08-08","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",46,"КВАНЗА МЕДИА БАИНГ ООО","№222035",None,"31.12.2025","Совпадение (убран '№'); end_date уже совпадает"),
    ("СОВПАДЕНИЕ","ДД Роре Медиа","РМ-01-04-24","2024-04-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",31,"РОРЕ МЕДИА ООО","РМ-01-04-24",None,None,"Точное совпадение"),
    ("СОВПАДЕНИЕ","ДД Т-Банк","РМ-09-01-25","2025-01-09","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","ADVERTISER","",54,"ТБАНК АО","РМ-09-01-25",None,None,"Совпадение"),
    ("СОВПАДЕНИЕ","ДД Муви 360","РМ-10-09-25","2025-09-10","31.12.2025",60,"ДА","SERVICE_AGREEMENT","CUSTOMER","AD_AGENCY","",57,"МУВИ 360 ООО","РМ -10-09-25",None,"31.12.2025","Совпадение (лишний пробел в БД); роль CUSTOMER"),
    ("СОВПАДЕНИЕ","ДД Изи-Нэт","PM-05-12-2023","2023-12-05","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",27,"ИЗИ-НЭТ ООО","РМ 05-12-2023",None,"до полного исполнения...","Совпадение (PM→РМ); end_date — бизнес-условие, не трогаем"),
    ("СОВПАДЕНИЕ","ДД Адлабс","РМ -03-06-2024","2024-06-03","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",32,"АДЛАБС.РУ ООО","РМ -03-06-2024",None,None,"Точное совпадение"),
    ("СОВПАДЕНИЕ","ООО «С-МАРКЕТИНГ»","№ РМ-27-12-2023","2023-12-27","31.12.2026",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",17,"С-МАРКЕТИНГ","РМ-27-12-2023",None,"27.12.2024","Совпадение; end_date обновить до 2026"),
    ("СОВПАДЕНИЕ","ДД Колтач Солюшнс","№ PM-01/02-24","2024-02-01","31.12.2026",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",28,"КОЛТАЧ СОЛЮШНС","PM-01/02-24",None,"31.12.2024","Совпадение; end_date обновить до 2026"),
    ("СОВПАДЕНИЕ","ДД АЙ-КОМ","PM-11-03-24","2024-03-11","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",35,"Агентство Ай-Ком ООО","РМ-11-03-24",None,"до полного исполнения...","Совпадение (PM→РМ); end_date — бизнес-условие"),
    ("СОВПАДЕНИЕ","ДД Sa Media","№ PM-01-06-23","2023-06-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",3,"РА СА МЕДИА ООО","PM-01-06-23",None,"31.12.2023 года","Совпадение; end_date обновить"),
    ("СОВПАДЕНИЕ","ДД Орматек","РМ-11-01-2024","2024-01-11","31.12.2025",60,"ДА","INTERMEDIARY_AGREEMENT","EXECUTOR","ADVERTISER","",25,"ОРМАТЕК АО","PM-11-01-2024",None,"31.12.2024","Совпадение; INTERMEDIARY — посреднический договор!"),
    ("УДАЛЁН","ДД Лазурит (удалён)","PM-21-08-23","2023-08-21","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","ADVERTISER","26.11.2025",None,"","",None,None,"Удалён в источнике; активная версия → БД id=20"),
    ("СОВПАДЕНИЕ","ДД Лазурит (активный)","PM-21-08-23","2023-08-21","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","ADVERTISER","",20,"ТДЛАЗУРИТ ООО","PM-21-08-23",None,"31.12.2023","Активная версия совпадает с БД id=20"),
    ("УДАЛЁН","ДД Ай-Гуру (удалён)","PM-08-10-24","2024-10-08","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","04.12.2025",None,"","",None,None,"Удалён в источнике; в БД id=52 ещё активен"),
    ("УДАЛЁН","ДД Нектарин (удалён)","УК-ПМ-1103","2024-03-11","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","20.11.2025",None,"","",None,None,"Удалён в источнике; активная '№ УК-ПМ-1103' → БД id=36"),
    ("УДАЛЁН","ДД Диджитал Альянс (удалён)","ДА-5/0125","2025-01-14","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","03.12.2025",None,"","",None,None,"Удалён в источнике; активная версия → новый"),
    ("НОВЫЙ","ДД Диджитал Альянс","ДА-5/0125","2025-01-14","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить (SQL)"),
    ("ДУБ CSV","ДД Диджитал Альянс (dup1)","ДА-5/0125","2025-01-14","31.12.2025",120,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Дубль в CSV; deferral=120 — расхождение, пропускаем"),
    ("ДУБ CSV","ДД Диджитад альянс (dup2)","ДА-5/0125","2025-01-14","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Опечатка в имени + дубль — пропускаем"),
    ("НОВЫЙ","ДД МБР","РМ-01-04-25","2024-04-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить (суффикс -МБР)"),
    ("НОВЫЙ","ДД РОССТ","РМ-01-04-25","2024-04-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить"),
    ("ДУБ CSV","ДД РОССТ (dup)","РМ-01-04-25","2024-04-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Дубль РОССТ в CSV — пропускаем"),
    ("НОВЫЙ","ДД Медиа Би Эйч","РМ-14-04-25","2024-04-01","31.12.2025",60,"ДА","SERVICE_AGREEMENT","CUSTOMER","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить; роль CUSTOMER"),
    ("НОВЫЙ","ДД Хелиас Медиа","№ АС-АР-42","2024-09-02","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить"),
    ("НОВЫЙ","ДД 9 Ярдов","PM-18-12-24","2024-12-18","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить"),
    ("НОВЫЙ","ДД Евразия","PM 30-02-2025","2025-02-28","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить; дата: 28.02 (30.02 не существует)"),
    ("НОВЫЙ","ДД DPD","№ 306438","2025-01-13","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Нет в БД → вставить"),
    ("КОНФЛИКТ","ДД Фьюче Лаб","PM-16-11-2023","2023-11-16","31.12.2025",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",1,"ДИДЖИТАЛ ИНСПИРЕЙШН ООО","PM-16-11-2023",None,"31.12.2023 года","КОНФЛИКТ: тот же номер, разные контрагенты → ручное решение"),
    ("ТЕСТ","Тест договора 29.05","3425","2026-05-20","31.05.2026",3,"НЕТ","SERVICE_AGREEMENT","CUSTOMER","ADVERTISER","",None,"","",None,None,"Тестовая запись → пропустить"),
    ("ТЕСТ","Тест договора 01.06","2341","2026-06-01","16.06.2026",5,"НЕТ","SERVICE_AGREEMENT","CUSTOMER","ADVERTISER","",None,"","",None,None,"Тестовая запись → пропустить"),
    ("ТЕСТ","Тест договора 1305","12341234","2026-05-14","22.05.2026",8,"НЕТ","SERVICE_AGREEMENT","CUSTOMER","ADVERTISER","",None,"","",None,None,"Тестовая запись → пропустить"),
    ("ТЕСТ","Тест договора 10","1234567","2026-05-01","02.05.2026",5,"ДА","SERVICE_AGREEMENT","CUSTOMER","ADVERTISER","",None,"","",None,None,"Тестовая запись → пропустить"),
    ("ТЕСТ","РМ 18-12-24","РМ 18-12-24","2026-05-05","04.05.2026",60,"ДА","SERVICE_AGREEMENT","EXECUTOR","AD_AGENCY","",None,"","",None,None,"Имя=Номер, дата мая 2026 — подозрительная запись → пропустить"),
]

for r, row in enumerate(rows1, 2):
    status = row[0]
    bg = status_bg.get(status)
    for c, val in enumerate(row, 1):
        cell = ws1.cell(row=r, column=c, value="" if val is None else val)
        cell.font = Font(name="Arial", size=9, bold=(c==1))
        cell.alignment = center() if c == 1 else left_w()
        cell.border = border
        if bg:
            cell.fill = h_fill(bg)

ws1.row_dimensions[1].height = 40
set_col_widths(ws1, [14,26,20,12,12,8,6,24,12,12,12,6,28,20,8,22,50])
ws1.freeze_panes = "B2"

# Legend
lr = len(rows1) + 3
ws1.cell(row=lr, column=1, value="ЛЕГЕНДА:").font = Font(name="Arial", bold=True, size=9)
for ci, (st, co) in enumerate([("СОВПАДЕНИЕ",C_MATCH),("НОВЫЙ",C_NEW),("КОНФЛИКТ",C_CONFLICT),("УДАЛЁН",C_DELETED),("ТЕСТ / ДУБ CSV",C_SKIP)], 2):
    c = ws1.cell(row=lr, column=ci, value=st)
    c.fill = h_fill(co); c.font = Font(name="Arial", size=9, bold=True)
    c.border = border; c.alignment = center()

# ──────────────────────────────────────────────────────
# SHEET 2 — Бэкфил
# ──────────────────────────────────────────────────────
ws2 = wb.create_sheet("Бэкфил")
ws2.row_dimensions[1].height = 40

h2 = ["БД id","БД Контрагент","БД Номер","term_days БЫЛО","term_days СТАНЕТ",
      "end_date_text БЫЛО","end_date_text СТАНЕТ","doc_type (NEW)","nds (NEW)","own_legal_role (NEW)","Примечание"]
for col, h in enumerate(h2, 1):
    cell = ws2.cell(row=1, column=col, value=h)
    style_header(cell, bg="2F5597" if col <= 3 else ("1F7A4D" if col >= 8 else "2F5597"))

bf = [
    (51,"ИНСАЙТ ЛЮДИ ООО","PM-24-12-2024",None,60,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR",""),
    (36,"НЕКТАРИН УК ООО","УК-ПМ-1103",None,60,"31.12.2024","31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date обновлён"),
    (22,"САЙТСИНГ ООО","PM-01-08-23",None,60,"31.12.2023","31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date обновлён"),
    (11,"ЭМДЖИКОМ ООО","РМ 01-12-2023",None,60,"31.12.2023 года","31.12.2026","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date сильно устарел → 2026"),
    (21,"УАЙТ БОКС МЕДИА ООО","РМ 30-11-2023",None,30,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR","deferral=30 (не 60!)"),
    (30,"МЕГАБАЙТ ООО","РМ-30-08-24",None,60,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR",""),
    (55,"БЕЗЕН ХЕЛСКЕА РУС ООО","РМ-31-01-25",None,60,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR",""),
    (46,"КВАНЗА МЕДИА БАИНГ ООО","№222035",None,60,"31.12.2025","31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date уже совпадает"),
    (31,"РОРЕ МЕДИА ООО","РМ-01-04-24",None,60,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR",""),
    (54,"ТБАНК АО","РМ-09-01-25",None,60,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR",""),
    (57,"МУВИ 360 ООО","РМ -10-09-25",None,60,"31.12.2025","31.12.2025","SERVICE_AGREEMENT","ДА","CUSTOMER","end_date совпадает; роль CUSTOMER"),
    (27,"ИЗИ-НЭТ ООО","РМ 05-12-2023",None,60,"до полного исполнения...","—не трогать—","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date = бизнес-условие"),
    (32,"АДЛАБС.РУ ООО","РМ -03-06-2024",None,60,None,"31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR",""),
    (17,"С-МАРКЕТИНГ","РМ-27-12-2023",None,60,"27.12.2024","31.12.2026","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date обновлён → 2026"),
    (28,"КОЛТАЧ СОЛЮШНС","PM-01/02-24",None,60,"31.12.2024","31.12.2026","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date обновлён → 2026"),
    (35,"Агентство Ай-Ком ООО","РМ-11-03-24",None,60,"до полного исполнения...","—не трогать—","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date = бизнес-условие"),
    (3,"РА СА МЕДИА ООО","PM-01-06-23",None,60,"31.12.2023 года","31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date обновлён"),
    (25,"ОРМАТЕК АО","PM-11-01-2024",None,60,"31.12.2024","31.12.2025","INTERMEDIARY_AGREEMENT","ДА","EXECUTOR","Посреднический договор!"),
    (20,"ТДЛАЗУРИТ ООО","PM-21-08-23",None,60,"31.12.2023","31.12.2025","SERVICE_AGREEMENT","ДА","EXECUTOR","end_date обновлён"),
]

for r, row in enumerate(bf, 2):
    for c, val in enumerate(row, 1):
        cell = ws2.cell(row=r, column=c, value="" if val is None else val)
        cell.font = Font(name="Arial", size=9)
        cell.border = border
        cell.alignment = left_w()
        if c == 5 and val is not None:
            cell.fill = h_fill(C_BACKFILL)
        if c == 7 and val and "не трогать" not in str(val) and "совпадает" not in str(row[10]):
            cell.fill = h_fill(C_BACKFILL)
        if c in (8, 9, 10):
            cell.fill = h_fill(C_NEW)
        if c == 11 and val:
            cell.fill = h_fill("FFF9C4")

set_col_widths(ws2, [6,28,20,10,10,22,14,26,6,16,40])
ws2.freeze_panes = "C2"

# ──────────────────────────────────────────────────────
# SHEET 3 — Новые договора
# ──────────────────────────────────────────────────────
ws3 = wb.create_sheet("Новые договора")
h3 = ["CSV Название","Номер в БД","Дата договора","counterparty_name",
      "end_date_text","payment_term_days","doc_type","nds","own_legal_role","counterparty_id","Примечание"]
for col, h in enumerate(h3, 1):
    c = ws3.cell(row=1, column=col, value=h)
    style_header(c)

new_rows = [
    ("ДД Диджитал Альянс","ДА-5/0125","2025-01-14","ДИДЖИТАЛ АЛЬЯНС","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ",""),
    ("ДД МБР","РМ-01-04-25-МБР","2024-04-01","МБР","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ","Суффикс -МБР во избежание конфликта с РОССТ"),
    ("ДД РОССТ","РМ-01-04-25","2024-04-01","РОССТ","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ",""),
    ("ДД Медиа Би Эйч","РМ-14-04-25","2024-04-01","МЕДИА БИ ЭЙЧ","31.12.2025",60,"SERVICE_AGREEMENT","ДА","CUSTOMER","⚠ ПРИВЯЗАТЬ","Роль CUSTOMER — нетипично"),
    ("ДД Хелиас Медиа","АС-АР-42","2024-09-02","ХЕЛИАС МЕДИА","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ",""),
    ("ДД 9 Ярдов","PM-18-12-24","2024-12-18","9 ЯРДОВ","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ",""),
    ("ДД Евразия","PM 30-02-2025","2025-02-28","ЕВРАЗИЯ","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ","30.02 не существует → 28.02"),
    ("ДД DPD","306438","2025-01-13","DPD","31.12.2025",60,"SERVICE_AGREEMENT","ДА","EXECUTOR","⚠ ПРИВЯЗАТЬ",""),
]
for r, row in enumerate(new_rows, 2):
    for c, val in enumerate(row, 1):
        cell = ws3.cell(row=r, column=c, value=val)
        cell.font = Font(name="Arial", size=9)
        cell.border = border
        cell.alignment = left_w()
        cell.fill = h_fill(C_NEW)
        if c == 10:
            cell.fill = h_fill(C_CONFLICT)

set_col_widths(ws3, [22,20,12,24,12,10,24,6,14,18,40])
ws3.freeze_panes = "B2"

# ──────────────────────────────────────────────────────
# SHEET 4 — Конфликты и проблемы
# ──────────────────────────────────────────────────────
ws4 = wb.create_sheet("Конфликты")
h4 = ["Проблема","CSV Название","CSV Номер","БД id","БД Контрагент","Рекомендация"]
for col, h in enumerate(h4, 1):
    c = ws4.cell(row=1, column=col, value=h)
    style_header(c, bg="843C0C")

conflicts = [
    ("Конфликт номеров","ДД Фьюче Лаб","PM-16-11-2023",1,"ДИДЖИТАЛ ИНСПИРЕЙШН ООО",
     "Оба реальные контрагенты. Проверить: возможно Фьюче Лаб работает как посредник через Диджитал Инспирейшн. Решение: вставить Фьюче Лаб под новым номером или добавить суффикс"),
    ("Дубль в CSV (разный deferral)","ДД Диджитал Альянс (×3)","ДА-5/0125",None,"",
     "Три записи с одним номером в источнике: 1 удалена, 1 активная (60 дней), 1 активная (120 дней). Выбрать одну — предлагаем 60 дней (последняя созданная)"),
    ("Дубль в CSV","ДД РОССТ (×2)","РМ-01-04-25",None,"",
     "Две активные записи РОССТ с разными counterpartyId. Выбрать одну. Возможно два разных юрлица под одним названием. Уточнить у юридического отдела"),
    ("Дубль в CSV","ДД Уайт Бокс (×2)","РМ 30-11-2023",21,"УАЙТ БОКС МЕДИА ООО",
     "Две записи с одним номером, одна — deferral 30, другая 60. Принятая версия: 30 дней (4d20ac8b). Вторая запись пропущена"),
    ("Удалён в источнике, активен в БД","ДД Ай-Гуру (удалён)","PM-08-10-24",52,"АЙ-ГУРУ ООО",
     "В CSV запись удалена 04.12.2025, но в нашей БД id=52 ещё активен. Проверить: договор расторгнут? Нужно ли пометить в БД как неактивный?"),
]
for r, row in enumerate(conflicts, 2):
    for c, val in enumerate(row, 1):
        cell = ws4.cell(row=r, column=c, value="" if val is None else val)
        cell.font = Font(name="Arial", size=9)
        cell.border = border
        cell.alignment = left_w()
        cell.fill = h_fill(C_CONFLICT)

set_col_widths(ws4, [28,26,18,8,28,60])
ws4.freeze_panes = "A2"

# ──────────────────────────────────────────────────────
# SHEET 5 — Новые поля
# ──────────────────────────────────────────────────────
ws5 = wb.create_sheet("Новые поля")
h5 = ["Поле (БД)","Тип","Источник CSV","Пример значений","Приоритет","SQL"]
for col, h in enumerate(h5, 1):
    c = ws5.cell(row=1, column=col, value=h)
    style_header(c)

schema = [
    ("doc_type","varchar(50)","docType","SERVICE_AGREEMENT / INTERMEDIARY_AGREEMENT","Высокий",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS doc_type varchar(50);"),
    ("nds","boolean","nds","true / false","Высокий",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS nds boolean;"),
    ("own_legal_role","varchar(20)","ownLegalRole","EXECUTOR / CUSTOMER","Высокий",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS own_legal_role varchar(20);"),
    ("end_date","date","endDate (дата)","2025-12-31","Средний",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS end_date date;\n-- замена/дополнение для end_date_text"),
    ("payment_sk_size","integer","paymentSKSize","20 / 30 / NULL (% вознаграждения)","Низкий",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS payment_sk_size integer;"),
    ("counterparty_type","varchar(20)","type","AD_AGENCY / ADVERTISER","Низкий",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS counterparty_type varchar(20);"),
    ("external_uuid","varchar(36)","id (UUID из ОРД)","e14a624c-3fe7-49c4-...","Низкий",
     "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS external_uuid varchar(36);\n-- для трассировки к ОРД"),
]
prio_bg = {"Высокий": C_MATCH, "Средний": "FFF2CC", "Низкий": C_SKIP}
for r, row in enumerate(schema, 2):
    for c, val in enumerate(row, 1):
        cell = ws5.cell(row=r, column=c, value=val)
        cell.font = Font(name="Arial", size=9)
        cell.border = border
        cell.alignment = left_w()
        cell.fill = h_fill(prio_bg.get(row[4], C_SKIP))

set_col_widths(ws5, [20,14,18,40,10,60])
ws5.freeze_panes = "A2"

out = "/tmp/contracts_comparison.xlsx"
wb.save(out)
print(f"OK: {out}")
sys.stdout.flush()
