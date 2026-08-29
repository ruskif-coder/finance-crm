"""
Перечисления ОРД и их русские подписи.

Значения приходят из API кодами (`MediationContract`), а в выгрузке кабинета и на
экране живут подписями («Посреднический договор»). Перевод нужен в обе стороны:
импорт выгрузки читает подписи, отправка в ОРД пишет коды.

Соответствие сверено по количествам строк в выгрузке от 2026-08-25 и зафиксировано
здесь: подпись в кабинете — внешний контракт, менять её нельзя, а опечатка в ней
даёт молчаливый None вместо кода и строку, которую ОРД отвергнет.
"""
from app.ord.enums import (ACTION_TYPES, CONTRACT_TYPES, INVOICE_ROLES, LEGAL_FORMS,
                           SUBJECT_TYPES, code_by_label, label_by_code)


def test_contract_types_cover_what_the_cabinet_shows():
    assert CONTRACT_TYPES['ServiceAgreement'] == 'Договор оказания услуг'
    assert CONTRACT_TYPES['MediationContract'] == 'Посреднический договор'
    assert set(CONTRACT_TYPES) == {
        'ServiceAgreement', 'MediationContract', 'AdditionalAgreement',
        'SelfPromotionContract', 'VirtualFinalContract', 'EcidContract'}


def test_subject_and_action_types_match_the_export():
    assert SUBJECT_TYPES['OrgDistribution'] == 'Договор на организацию распространения рекламы'
    assert SUBJECT_TYPES['Distribution'] == 'Договор на распространение рекламы'
    assert SUBJECT_TYPES['Mediation'] == 'Посредничество'
    assert ACTION_TYPES['Contracting'] == 'Заключение договоров'
    assert ACTION_TYPES['Distribution'] == 'Действия в целях распространения рекламы'


def test_translation_is_two_way():
    assert code_by_label(CONTRACT_TYPES, 'Посреднический договор') == 'MediationContract'
    assert label_by_code(CONTRACT_TYPES, 'MediationContract') == 'Посреднический договор'


def test_unknown_label_is_none_not_a_guess():
    """Незнакомая подпись обязана вернуть None.

    Подставить «похожее» здесь значит отправить в ЕРИР договор не того вида —
    ошибка, которую увидит только проверяющий, и то не сразу.
    """
    assert code_by_label(CONTRACT_TYPES, 'Договор поставки') is None
    assert code_by_label(CONTRACT_TYPES, '') is None
    assert code_by_label(CONTRACT_TYPES, None) is None


def test_label_lookup_survives_unknown_code():
    """Обратно — наоборот: код из ОРД мог появиться новый, показать его лучше,
    чем упасть на экране справочника."""
    assert label_by_code(CONTRACT_TYPES, 'BrandNewType') == 'BrandNewType'


def test_legal_forms_and_invoice_roles_are_pinned():
    assert set(LEGAL_FORMS) == {
        'JuridicalPerson', 'IndividualEntrepreneur', 'PhysicalPerson',
        'InternationalJuridicalPerson', 'InternationalPhysicalPerson'}
    assert set(INVOICE_ROLES) == {'Rr', 'Ors', 'Rd', 'Ra'}
