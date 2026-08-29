"""Сборка тел запросов в ОРД из наших записей.

Отдельный слой от транспорта намеренно: тела можно проверять БЕЗ ДОСТУПА к API — на
официальных схемах из спеки, которые лежат фикстурой в `backend/tests/fixtures/`. Тест
`tests/test_ord_payloads.py` ловит недостающие обязательные поля, чужие значения
перечислений и лишние ключи. Обе ошибки, найденные 26.08.2026 при сверке со спекой
(`VirtualFinalContract`, которого в API нет, и разница «три типа на создание, пять на
чтение»), такой тест поймал бы сразу.

ПОЧЕМУ СБОРКА ОТКАЗЫВАЕТСЯ, А НЕ ПОДСТАВЛЯЕТ. Всё, чего в наших данных нет, поднимает
`OrdPayloadError` с текстом, который называет запись и поле. Подставленное «похожее»
уезжает в ЕРИР и не отзывается; пустая форма — чинится за минуту.
"""
from typing import Optional

from app.ord.enums import API_CREATABLE_CONTRACT_TYPES, FINAL_CONTRACT_TYPE


class OrdPayloadError(ValueError):
    """Наших данных не хватает на отправку. Текст называет, чего именно."""


def _need(value, what: str, who: str):
    v = (value or '').strip() if isinstance(value, str) else value
    if v in (None, ''):
        raise OrdPayloadError(f"{who}: не заполнено «{what}»")
    return v


def legal_form(inn: str) -> str:
    """Организационно-правовая форма по длине ИНН.

    Десять цифр — всегда юрлицо, тут выбора нет. Двенадцать — ИП ИЛИ физлицо, и
    различить их по ИНН невозможно: у нас таких 27 из 211 (мерено 26.08.2026), а поля
    формы в справочнике нет. Поэтому двенадцать цифр — отказ с просьбой указать форму,
    а не «наверное, ИП»: неверная форма стороны договора уезжает в ЕРИР.
    """
    digits = (inn or '').strip()
    if len(digits) == 10:
        return 'JuridicalPerson'
    if len(digits) == 12:
        raise OrdPayloadError(
            f"ИНН {digits} из 12 цифр — это ИП или физлицо, различить нельзя. "
            "Укажите форму вручную (поля в справочнике пока нет).")
    raise OrdPayloadError(f"ИНН «{digits}» не похож ни на юрлицо, ни на ИП")


def client(cp) -> dict:
    """CreateClientRequest — юрлицо в ОРД из нашего контрагента.

    `isPhysicalPersonAddressExists` обязателен по спеке. Для юрлица адрес физлица не
    нужен, поэтому false — но само поле опустить нельзя.
    """
    who = f"контрагент «{cp.name}»"
    return {
        'inn': _need(cp.inn, 'ИНН', who),
        'name': _need(cp.name, 'название', who),
        'legalForm': legal_form(cp.inn),
        'isPhysicalPersonAddressExists': False,
        'createMode': 'DirectClient',
    }


def _contract_common(contract, who: str) -> dict:
    """Поля, одинаковые у доходного, расходного и изначального договоров."""
    date = _need(contract.contract_date, 'дата договора', who)
    body = {
        'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
        'type': FINAL_CONTRACT_TYPE,
    }
    number = (contract.contract_number or '').strip()
    if number:
        body['number'] = number
    return body


def final_contract(contract, client_ord_id: str) -> dict:
    """CreateFinalContractRequest — наш договор с плательщиком.

    Тип всегда `ServiceAgreement`: доходный договор — это договор с нами, и он всегда
    услуговый (правило владельца 26.08.2026, см. app/ord/enums.py).
    """
    who = f"договор {contract.contract_number or contract.id}"
    body = _contract_common(contract, who)
    body['clientId'] = _need(client_ord_id, 'идентификатор плательщика в ОРД', who)
    return body


def initial_contract(initial, client_ord_id: str, contractor_ord_id: str,
                     final_ord_id: str, contract_type: Optional[str] = None) -> dict:
    """CreateInitialContractRequest — изначальный договор чужой цепочки.

    `finalContractId` обязателен по спеке: изначальный всегда создаётся ПРИКРЕПЛЁННЫМ к
    доходному. Это и есть подтверждение нашей M:N — прикрепить существующий к другому
    доходному отдельно умеет `POST /contracts/initial/attachexisting`.
    """
    who = f"изначальный договор {initial.number or initial.id}"
    kind = contract_type or initial.type
    if kind not in API_CREATABLE_CONTRACT_TYPES:
        raise OrdPayloadError(
            f"{who}: тип «{kind}» API не принимает на создание "
            f"(допустимы {', '.join(API_CREATABLE_CONTRACT_TYPES)})")
    date = _need(initial.date, 'дата договора', who)
    body = {
        'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
        'type': kind,
        'clientId': _need(client_ord_id, 'идентификатор рекламодателя в ОРД', who),
        'contractorId': _need(contractor_ord_id, 'идентификатор исполнителя в ОРД', who),
        'finalContractId': _need(final_ord_id, 'идентификатор доходного договора', who),
    }
    number = (initial.number or '').strip()
    if number:
        body['number'] = number
    if initial.subject_type:
        body['subjectType'] = initial.subject_type
    if initial.action_type:
        body['actionType'] = initial.action_type
    return body


# ── креатив ──────────────────────────────────────────────────────────────────
# Форма распространения: значения из перечня ОРД. Выводится из состава файлов
# (app/routers/launch_prep.py), сюда приходит готовой.
CREATIVE_FORMS = ('Banner', 'BannerHtml5', 'Text', 'TextGraphic', 'Video', 'Audio', 'Other')
# Тип рекламной кампании. Модель оплаты объявляется здесь, а не только в акте:
# по спеке поле обязательно, если не будет заполнено при регистрации статистики показов.
CREATIVE_TYPES = ('CPM', 'CPC', 'CPA', 'Other')


def creative(cset, files, deal, brand, final_ord_id, initial_ord_id=None,
             campaign_type: Optional[str] = None, advertiser_urls=None) -> dict:
    """CreateCreativeRequest — комплект креативов на регистрацию.

    Сверено со схемой 26.08.2026. Три вещи, которые схема говорит не тем голосом, что
    описание, и в которых легко ошибиться:

      · **`kktuCodes` — РОВНО ОДИН код** третьего уровня вида `X.X.X` для обычного
        креатива (несколько допускаются только для кобрендинга, которого у нас нет);
      · **флаги отправляются явно.** В массиве `required` схемы они есть, а в описании
        поля названы необязательными со значением по умолчанию `false` — схема сама себе
        противоречит (генератор вынес туда non-nullable типы). Полагаться ни на одно из
        двух прочтений нельзя;
      · **файл едет base64 ИЛИ ссылкой**, причём ссылка обязана быть доступна БЕЗ
        авторизации. Публичная ссылка спорит с песочницей для превью, поэтому шлём base64.

    `nativeCustomerId` детерминированный — это ключ идемпотентности: без него повтор
    запроса после обрыва связи заводит в ЕРИР второй креатив, который не отозвать.
    """
    who = f"комплект №{cset.no}"

    kktu = (cset.kktu_code or (brand.kktu_code if brand else None) or '').strip()
    if not kktu:
        raise OrdPayloadError(
            f"{who}: не заполнен код ККТУ. Он живёт на бренде и подставляется сюда — "
            f"проставьте его в карточке рекламодателя")
    if len(kktu.split('.')) != 3:
        raise OrdPayloadError(
            f"{who}: код ККТУ «{kktu}» не третьего уровня — реестр принимает только «X.X.X»")

    form = cset.form
    if form and form not in CREATIVE_FORMS:
        raise OrdPayloadError(f"{who}: форма «{form}» не из перечня ОРД")

    media = []
    for f in files:
        media.append({
            'fileName': _need(f.original_name, 'имя файла', who),
            'fileContentBase64': _need(f.content_b64, 'содержимое файла', who),
            'isArchive': bool(f.is_archive),
        })
    if not media:
        raise OrdPayloadError(f"{who}: нет ни одного файла")

    body = {
        # Ключ идемпотентности: наш номер комплекта, а не случайное число.
        'nativeCustomerId': f"set-{cset.id}",
        'creativeGroupName': f"{deal.code}-{cset.no}",
        'finalContractId': _need(final_ord_id, 'доходный договор в ОРД', who),
        # Флаги: шлём явно, не полагаясь на умолчания схемы.
        'isSelfPromotion': bool(getattr(deal, 'is_self_promo', False)),
        'isNative': False,
        'isSocial': False,
        'isSocialQuota': False,
        'isCobranding': False,
        'kktuCodes': [kktu],
        'mediaData': media,
    }
    if initial_ord_id:
        body['initialContractId'] = initial_ord_id
    if form:
        body['form'] = form
    if campaign_type:
        if campaign_type not in CREATIVE_TYPES:
            raise OrdPayloadError(f"{who}: тип кампании «{campaign_type}» не из перечня ОРД")
        body['type'] = campaign_type

    description = (cset.description or (brand.ad_object_description if brand else None) or '').strip()
    if description:
        body['description'] = description[:1000]

    # Посадочные страницы получателей этого комплекта. Их несколько по построению:
    # ссылка ведёт на страницу КОНКРЕТНОГО сайта, а комплект уходит нескольким. Схема
    # это принимает — поле массив; маркер при этом остаётся один, на комплект.
    urls = [u.strip() for u in (advertiser_urls or []) if (u or '').strip()]
    if urls:
        body['advertiserUrls'] = list(dict.fromkeys(urls))

    if deal.period_from:
        body['creativeGroupStartDate'] = deal.period_from.isoformat()
    if deal.period_to:
        body['creativeGroupEndDate'] = deal.period_to.isoformat()
    return body
