# -*- coding: utf-8 -*-
"""Реестр приложений с отбором по договору (окно «Шаблон ДС» → «ДС договора», владелец 28.10.2026): только ДС этого договора."""
import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.models import Contract, User
from app.routers.annexes import list_annexes
from app.sales.models import SalesAnnex


def test_list_is_limited_to_the_contract():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        some = db.query(SalesAnnex).order_by(SalesAnnex.id).first()
        assert some is not None, "на стенде нет ни одного ДС"
        other = db.query(Contract).filter(Contract.id != some.contract_id).order_by(Contract.id).first()
        db.add(SalesAnnex(contract_id=other.id))          # ДС чужого договора — в транзакции теста, откатывается
        db.flush()
        expected = db.query(SalesAnnex).filter(SalesAnnex.contract_id == some.contract_id).count()
        out = list_annexes(contract_id=some.contract_id, db=db, user=admin)
        assert {i["contract_id"] for i in out["items"]} == {some.contract_id}
        assert out["total"] == expected
    finally:
        db.rollback()
        db.close()
