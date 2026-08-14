"""Генерация 6-значной метки сделки (наш «отпечаток», показывается в UI/ссылках).

Алфавит без неоднозначных символов (0/O/1/I/L) — чтобы метку можно было диктовать/писать.
Уникальность гарантируется UNIQUE-индексом в БД; здесь пред-проверка + повтор при коллизии.
"""
import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 32 символа, без 0 O 1 I L


def gen_code(n: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def assign_code(db, deal, attempts: int = 12) -> str:
    """Назначает уникальный code сделке (не коммитит). UNIQUE ловит гонку — при вставке повторить."""
    from app.sales.models import SalesDeal
    for _ in range(attempts):
        c = gen_code()
        if not db.query(SalesDeal.id).filter(SalesDeal.code == c).first():
            deal.code = c
            return c
    raise RuntimeError("Не удалось сгенерировать уникальную метку сделки")
