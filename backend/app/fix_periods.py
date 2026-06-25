import re
from app.database import SessionLocal
from app.models import Operation

MONTHS = {
    'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4,
    'май': 5, 'июнь': 6, 'июль': 7, 'август': 8,
    'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12
}

def normalize_period(period, date):
    """Нормализует период в формат YYYY-MM"""
    if not period or not date:
        return date.strftime('%Y-%m') if date else None

    p = str(period).lower().strip()

    # Уже правильный формат YYYY-MM
    if re.match(r'^\d{4}-\d{2}$', p):
        return p

    # Формат "месяц YYYY"
    for month_name, month_num in MONTHS.items():
        if month_name in p:
            year_match = re.search(r'\d{4}', p)
            year = int(year_match.group()) if year_match else date.year
            return f"{year}-{month_num:02d}"

    # Квартал — берём дату операции
    if 'квартал' in p or 'кварт' in p:
        return date.strftime('%Y-%m')

    # Всё остальное мусорное — берём дату операции
    return date.strftime('%Y-%m')

db = SessionLocal()
ops = db.query(Operation).all()
updated = 0

for op in ops:
    new_period = normalize_period(op.period, op.date)
    if new_period != op.period:
        op.period = new_period
        updated += 1

db.commit()
db.close()
print(f"Обновлено периодов: {updated} из {len(ops)}")