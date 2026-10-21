# -*- coding: utf-8 -*-
"""Уведомления по заявкам юристу. Новая заявка — контуру юристов (реестр события). Взята, выполнена, отклонена — автору заявки
и ВСЕМ юристам (владелец 16.10.2026: как конвейер согласований у трафиков — кто успел, тот и посмотрел). Того, кто действует,
шина не уведомляет сама."""
from app.notify.bus import emit
from app.notify.recipients import by_staff_group


def _people(db, r) -> list:
    """Автор заявки и весь контур юристов (включая того, кто взял)."""
    return list(dict.fromkeys([r.created_by, *by_staff_group(db, "legal")]))

_CLOSE = {"сделана": "legal_request_done", "отклонена": "legal_request_rejected"}


def _title(r, contract_number) -> str:
    return f"ДС {('#' + str(r.annex_id))} · договор № {contract_number or '—'}"


def new(db, r, contract_number, actor):
    emit(db, "legal_request_new", title=f"Заявка юристу: {_title(r, contract_number)}", body=r.text[:300],
         link="/finance/legal-requests", entity_type="contract", entity_id=r.contract_id, actor=actor)


def taken(db, r, contract_number, actor):
    emit(db, "legal_request_taken", title=f"Юрист взял заявку: {_title(r, contract_number)}", body=r.text[:300],
         link=f"/directory/annexes/{r.annex_id}", entity_type="contract", entity_id=r.contract_id, actor=actor,
         user_ids=_people(db, r))


def closed(db, r, contract_number, actor):
    word = "выполнена" if r.status == "сделана" else "отклонена"
    emit(db, _CLOSE[r.status], title=f"Заявка юристу {word}: {_title(r, contract_number)}",
         body=(r.answer or r.text)[:300], link=f"/directory/annexes/{r.annex_id}",
         entity_type="contract", entity_id=r.contract_id, actor=actor, user_ids=_people(db, r))


def base_changed(db, base_title, version, behind_n, actor):
    emit(db, "annex_base_changed", title=f"Базовый шаблон ДС «{base_title}» изменился (v{version})",
         body=f"Кастомных шаблонов договоров отстало от базы: {behind_n}. Решить по каждому — «Юр запросы» → «Базовый шаблон изменился».",
         link="/finance/legal-requests", entity_type="annex_template", actor=actor)
