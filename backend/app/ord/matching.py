"""Подбор договоров ОРД для сделки.

Две ступени экрана сборки: плательщик → доходный договор, затем доходный +
рекламодатель → изначальный. Обе возвращают ОБОСНОВАНИЕ вместе с результатом:
подстановка без объяснения выглядит магией, а магию перестают проверять.

Доходный договор — это наша строка в `contracts` с проставленным `ord_contract_id`.
Отметку ставит человек (в форме сборки или руками): система соответствия не
угадывает — решение владельца.
"""
import re
from collections import namedtuple
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Contract, Counterparty
from app.ord.models import OrdInitialContract, OrdInitialFinalLink

# `payer` несёт найденного контрагента-плательщика (Counterparty | None) отдельно от
# договора: ступень «Плательщик» экрана сборки обязана показывать найденное юрлицо,
# а не исходную текстовую метку сделки (`deal.payer_name`) — та несёт название
# АГЕНТСТВА, приезжает из Битрикса как есть и у части сделок отсутствует вовсе. Без
# этого поля наружу уходил только договор, и роутеру было неоткуда взять имя, кроме
# как из сырой метки — отсюда «Плательщик — null» на экране, когда метки не было.
FinalResolution = namedtuple('FinalResolution',
                             'contract final_ord_id candidates reason reason_code payer')
InitialProposal = namedtuple('InitialProposal',
                             'contract candidates reason reason_code')


def parse_payer(payer_name: Optional[str]) -> Optional[str]:
    """Юрлицо-плательщик из составной метки сделки.

    Метка вида «Альфа Медиа / Медиана Би Эйч»: до косой черты агентство, после —
    плательщик. Метка без косой черты плательщика не несёт вовсе, и вернуть из неё
    название агентства значило бы искать договор по имени группы.
    """
    if not payer_name:
        return None
    parts = [p.strip() for p in str(payer_name).split('/')]
    if len(parts) < 2:
        return None
    return parts[-1] or None


def _name_key(s: Optional[str]) -> str:
    """Ключ сравнения наименований: без организационно-правовой формы и знаков.

    Зачем: «ООО» пишут то до имени, то после, кавычки то «ёлочками», то без —
    ОРД и наши источники расходятся в написании одного и того же юрлица, и
    сравнение сырых строк на этом не сходится. В ключе остаётся только
    буквенно-цифровое ядро имени.
    """
    s = str(s or '').upper().replace('Ё', 'Е')
    s = re.sub(r'(ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|АКЦИОНЕРНОЕ ОБЩЕСТВО'
               r'|ПУБЛИЧНОЕ|ООО|ЗАО|ПАО|АО|ИП)', ' ', s)
    return re.sub(r'[^А-ЯA-Z0-9]', '', s)


def _payer_counterparty(db: Session, deal) -> tuple:
    """Контрагент-плательщик сделки и причина, если его нет.

    Порядок источников: сначала связь `payer_counterparty_id`, потом разбор текстовой
    метки. Связь надёжнее — её проставил человек, а метка приехала из Битрикса и
    разбирается эвристикой.
    """
    if getattr(deal, 'payer_counterparty_id', None):
        cp = db.query(Counterparty).filter(
            Counterparty.id == deal.payer_counterparty_id).first()
        if cp:
            return cp, None, None

    tail = parse_payer(getattr(deal, 'payer_name', None))
    if not tail:
        return None, 'Плательщик у сделки не указан.', 'no_payer'
    key = _name_key(tail)
    for row in db.query(Counterparty).all():
        if _name_key(row.name) == key:
            return row, None, None
    return None, f'Плательщик «{tail}» не найден среди контрагентов.', 'payer_unknown'


def _payer_contracts(db: Session, cp) -> List[Contract]:
    """Все договоры плательщика — список для выбора на ступени, не только ОРД-помеченные.

    Помеченных у 16 из 40 юрлиц агентств нет вовсе (мерено 26.08.2026), а договор при
    этом существует: отметку ставит человек. Показывать только помеченные значило бы
    предлагать пустой список там, где выбирать есть из чего.
    """
    return (db.query(Contract)
              .filter(Contract.counterparty_id == cp.id)
              .order_by(Contract.contract_date.desc().nullslast()).all())


def resolve_final(db: Session, deal) -> FinalResolution:
    """Доходный договор сделки — наш договор с проставленной отметкой ОРД.

    Возвращает и найденного плательщика (`payer`), не только договор: ступень
    «Плательщик» экрана сборки должна показывать это найденное юрлицо, а не
    исходную текстовую метку сделки (`deal.payer_name`) — та несёт название
    агентства, а не плательщика, и у части сделок отсутствует вовсе. `payer`
    заполнен во всех ветках, где контрагент найден, — включая `not_in_ord` и
    `ambiguous`: плательщик там уже определён, не определился только договор.
    """
    cp, reason, code = _payer_counterparty(db, deal)
    if cp is None:
        return FinalResolution(None, None, [], reason, code, None)

    # Выбор человека побеждает вычисление. Проверяется здесь, а не в экране: тем же
    # ответом живут и карточка, и будущая сдача отчётности, и правило «кто решает»
    # не должно зависеть от того, кто спрашивает.
    if getattr(deal, 'ord_final_contract_id', None):
        chosen = (db.query(Contract)
                    .filter(Contract.id == deal.ord_final_contract_id).first())
        if chosen is not None:
            when = chosen.contract_date.strftime('%d.%m.%Y') if chosen.contract_date else 'без даты'
            mark = ('' if chosen.ord_contract_id
                    else ' Отметки ОРД у него пока нет — ЕРИД по нему не выпустить.')
            return FinalResolution(
                chosen, chosen.ord_contract_id, _payer_contracts(db, cp),
                f'Выбран вручную: {chosen.contract_number or "без номера"} от {when}.{mark}',
                'chosen', cp)

    found: List[Contract] = (
        db.query(Contract)
          .filter(Contract.counterparty_id == cp.id,
                  Contract.ord_contract_id.isnot(None),
                  Contract.ord_kind == 'final')
          .order_by(Contract.contract_date.desc().nullslast()).all())

    if not found:
        # Договор у контрагента может быть, но без отметки ОРД. Это не поломка:
        # отметку ставит человек, и до неё сборка по этой сделке не поедет.
        return FinalResolution(
            None, None, [],
            f'У плательщика «{cp.name}» нет договора с отметкой ОРД. '
            f'Свяжите договор с ОРД в реестре договоров.', 'not_in_ord', cp)

    if len(found) == 1:
        c = found[0]
        when = c.contract_date.strftime('%d.%m.%Y') if c.contract_date else 'без даты'
        return FinalResolution(
            c, c.ord_contract_id, found,
            f'Единственный договор плательщика «{cp.name}» с отметкой ОРД — '
            f'{c.contract_number or "без номера"} от {when}.', 'ok', cp)

    # Меряли: такого не встречалось ни разу (305 из 305 однозначны). Если случилось —
    # данные поехали, и человек должен это увидеть, а не получить молча первый попавшийся.
    return FinalResolution(
        None, None, found,
        f'У плательщика «{cp.name}» договоров с отметкой ОРД {len(found)} — '
        f'выберите нужный.', 'ambiguous', cp)


# ── предложение изначального договора ────────────────────────────────────────

def _explain_single(number: str, advertiser: str) -> str:
    return f'Под {number} это единственный договор с рекламодателем «{advertiser}».'


def _explain_last_used(number: str, count: int, deal_code: str, deal_date: str) -> str:
    return (f'Под {number} подходящих договоров {count}. Взят тот, по которому '
            f'собирали в прошлый раз — сделка {deal_code} от {deal_date}.')


def _explain_name_match(number: str, count: int, advertiser: str) -> str:
    return (f'Под {number} договоров {count}. Выбран по совпадению названия с '
            f'рекламодателем «{advertiser}» — это догадка, проверьте.')


def _explain_ambiguous(number: str, count: int) -> str:
    return (f'Под {number} подходящих договоров {count}, прошлых сборок не было — '
            f'выберите нужный.')


def _explain_none(number: str) -> str:
    return f'Под {number} нет ни одного изначального договора.'


def _last_used_initial(db: Session, deal) -> Optional[int]:
    """Прошлый выбор по паре «агентство × рекламодатель».

    Не таблица, а запрос: таблица была бы состоянием, которое умеет протухнуть,
    а запрос всегда отражает то, что реально выбирали.

    Сортировка — по date_create, а не по id. Измерено 25.08.2026 на 899 сделках:
    822 инверсии (91%) между порядком id и порядком date_create — номер отражает
    порядок синхронизации с Битриксом, а не хронологию, и «последняя сделка по id»
    почти всегда не последняя по факту. id остаётся вторым ключом — чтобы при
    совпавшей дате порядок был детерминированным (тот же приём, что у resolve_final
    для Contract.contract_date).
    """
    from app.sales.models import SalesDeal
    if not (deal.agency_id and deal.advertiser_id):
        return None
    prev = (db.query(SalesDeal)
              .filter(SalesDeal.agency_id == deal.agency_id,
                      SalesDeal.advertiser_id == deal.advertiser_id,
                      SalesDeal.ord_initial_contract_id.isnot(None),
                      SalesDeal.id != deal.id)
              .order_by(SalesDeal.date_create.desc().nullslast(),
                        SalesDeal.id.desc()).first())
    return prev.ord_initial_contract_id if prev else None


def propose_initial(db: Session, deal, final_ord_id: str) -> InitialProposal:
    """Предложить изначальный договор под уже определённым доходным."""
    from app.sales.models import SalesAdvertiser, SalesDeal

    candidates: List[OrdInitialContract] = (
        db.query(OrdInitialContract)
          .join(OrdInitialFinalLink,
                OrdInitialFinalLink.initial_contract_id == OrdInitialContract.id)
          .filter(OrdInitialFinalLink.final_ord_id == final_ord_id)
          .order_by(OrdInitialContract.date.desc()).all())

    number = final_ord_id
    contract = (db.query(Contract)
                  .filter(Contract.ord_contract_id == final_ord_id).first())
    if contract and contract.contract_number:
        number = contract.contract_number

    if not candidates:
        return InitialProposal(None, [], _explain_none(number), 'none')

    adv = (db.query(SalesAdvertiser)
             .filter(SalesAdvertiser.id == deal.advertiser_id).first()
           if deal.advertiser_id else None)
    adv_name = (adv.short_name or adv.name) if adv else '—'

    # 1) память о прошлом выборе — самый надёжный источник
    remembered = _last_used_initial(db, deal)
    if remembered:
        for c in candidates:
            if c.id == remembered:
                prev = (db.query(SalesDeal)
                          .filter(SalesDeal.ord_initial_contract_id == remembered,
                                  SalesDeal.id != deal.id)
                          # дата, не id — см. докстринг _last_used_initial: номер
                          # отражает порядок синка с Битриксом, а не хронологию.
                          .order_by(SalesDeal.date_create.desc().nullslast(),
                                    SalesDeal.id.desc()).first())
                code = (prev.code or str(prev.id)) if prev else '—'
                when = (prev.date_create.strftime('%d.%m.%Y')
                        if prev and prev.date_create else '—')
                return InitialProposal(
                    c, candidates,
                    _explain_last_used(number, len(candidates), code, when), 'last_used')

    # 2) совпадение по имени — слабый источник, обоснование называет его догадкой
    if adv:
        key = _name_key(adv_name)
        matched = [c for c in candidates if _name_key(c.advertiser_name) == key]
        # len(candidates) == 1 здесь не разбирается отдельно: тогда matched[0] это
        # и есть candidates[0], и безусловная проверка `if len(candidates) == 1`
        # ниже по функции отдаёт ровно тот же InitialProposal.
        if len(matched) == 1 and len(candidates) > 1:
            return InitialProposal(
                matched[0], candidates,
                _explain_name_match(number, len(candidates), adv_name), 'name_match')
        if len(matched) > 1:
            return InitialProposal(None, matched,
                                   _explain_ambiguous(number, len(matched)), 'ambiguous')

    if len(candidates) == 1:
        return InitialProposal(candidates[0], candidates,
                               _explain_single(number, adv_name), 'single')

    return InitialProposal(None, candidates,
                           _explain_ambiguous(number, len(candidates)), 'ambiguous')
