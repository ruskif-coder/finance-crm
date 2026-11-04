/**
 * Окно контрагента — ЕДИНАЯ схема полей.
 *
 * Из неё строятся все четыре вида: просмотр, правка блока, «+ добавить» (новый договор, счёт, бренд…)
 * и режим заведения. Добавили поле сюда — оно появилось везде. Двух списков быть не должно.
 *
 * Поле: { k, l, span?, mono?, opts?, ph?, hint?, need?, from?, sys?, ro?, roWhy?, emptyTone?, emptyText? }
 *   k        — ключ в данных (как в sampleData.js)
 *   l        — подпись на экране
 *   span     — true = 2 колонки из 4, 4 = вся строка
 *   opts     — значения для выбора (на проде — ValuePopover, не <select>)
 *   need     — для чего нужно: 'ds' (первый ДС) · 'erid' · 'ord' · 'ops' (операции) · 'none' (позже). По умолчанию 'ds'
 *   from     — у кого получить (подсказка в режиме заведения)
 *   sys      — системное: только показ, в заведении не спрашивается; значение — заглушка, если в данных пусто
 *   ro/roWhy — нередактируемое и почему (показывается в title)
 *   emptyTone— как красить пустое в просмотре: по умолчанию danger; 'warn'; 'none' — прочерк
 *
 * Поправки к пакету дизайнера — по спецификации, «Сверка схемы дизайнера с базой» (04.11.2026). Списки значений —
 * только из `lib/contractTerms`: их буквально сравнивают подбор шаблона и пакет закрытия
 * (гейт `scripts/check-readiness-schema.mjs`).
 */
import { COOPERATION_FORMATS, ISSUE_CHANNELS, PAYMENT_TERM_CONDITIONS, PROLONGATION_OPTIONS } from '@/lib/contractTerms';

const ORG = 'клиент: карточка организации';

/** Формы организации — как в `backend/app/legal_form.FORMS`; значения сравниваются буквально. */
export const LEGAL_FORMS = ['ООО', 'АО', 'ПАО', 'ИП', 'самозанятый', 'физлицо', 'иностранная организация'];
/** Режимы СК — как в `sk_rules.mode`. */
export const SK_MODES = ['постоплата', 'скидка в счёт'];

export const BLOCKS = [
  { id: 'cp',  title: 'Юрлицо и реквизиты',     section: 'counterparties',  editable: true },
  { id: 'sg',  title: 'Подписанты',             section: 'counterparties',  editable: true },
  { id: 'ct',  title: 'Договоры',               section: 'contracts',       editable: true },
  { id: 'tpl', title: 'Шаблоны документов',     section: 'annex_templates', editable: false, editHint: 'правится во вкладке «Шаблоны» договора' },
  { id: 'ag',  title: 'Агентство',              section: 'dir_agencies',    editable: true, kinds: ['agency'] },
  // Рекламодатель — в окне своего юрлица-плательщика; у агентства этого блока нет (владелец 04.11.2026).
  { id: 'ad',  title: 'Рекламодатели и бренды', section: 'dir_advertisers', editable: true, kinds: ['direct'] },
  { id: 'sk',  title: 'Условия СК',             section: 'sk_terms',        editable: true, kinds: ['agency', 'direct'] },
  { id: 'ord', title: 'ОРД',                    section: 'ord',             editable: false, editHint: 'правится на экране ОРД', kinds: ['agency', 'direct'] },
];

export const KINDS = [
  { id: 'contractor', label: 'подрядчик' },
  { id: 'agency',     label: 'агентство' },
  { id: 'direct',     label: 'прямой рекламодатель' },
  { id: 'publisher',  label: 'площадка' },
];

export const SCH = {
  /* 1. Юрлицо — группы полей */
  cp: [
    ['Наименование и регистрация', [
      { k: 'name', l: 'полное название', span: true, from: ORG },
      { k: 'legal_form', l: 'форма организации', opts: LEGAL_FORMS, from: ORG, need: 'ord', hint: 'по ней ОРД регистрирует клиента' },
      { k: 'inn', l: 'ИНН', mono: true, from: ORG, need: 'ord', ro: true, roWhy: 'от ИНН зависят договоры и ОРД' },
      { k: 'kpp', l: 'КПП', mono: true, from: ORG },
      { k: 'ogrn', l: 'ОГРН', mono: true, from: ORG },
      { k: 'okpo', l: 'ОКПО', mono: true, from: ORG, need: 'none', emptyTone: 'warn' },
    ]],
    ['Адреса и контакты', [
      { k: 'address', l: 'юр. адрес', span: true, from: ORG },
      { k: 'fact_address', l: 'фактический адрес', span: true, from: ORG, need: 'none', emptyTone: 'none', emptyText: '—' },
      { k: 'phone', l: 'телефон', mono: true, from: 'клиент', need: 'none', emptyTone: 'none', emptyText: '—' },
      { k: 'email', l: 'почта для документов', from: 'клиент', need: 'ops', emptyTone: 'none', emptyText: '—' },
      { k: 'site', l: 'сайт', from: 'клиент', need: 'none', emptyTone: 'none', emptyText: '—' },
      { k: 'edo_id', l: 'ID в ЭДО', mono: true, from: 'клиент', need: 'ops', emptyTone: 'none', emptyText: '—' },
    ]],
    ['Расчёты по умолчанию', [
      { k: 'term_days', l: 'отсрочка, дн.', mono: true, from: 'сейлз: условия', need: 'ops', hint: 'по ней считается дебиторка' },
      { k: 'sk_label', l: 'СК контрагента', sys: '—', roWhy: 'правится в реестре контрагентов', need: 'ops' },
      { k: 'vat_in', l: 'НДС входящий', mono: true, sys: '—', roWhy: 'правится в реестре контрагентов', need: 'ops' },
      { k: 'vat_out', l: 'НДС исходящий', mono: true, sys: '—', roWhy: 'правится в реестре контрагентов', need: 'ops' },
    ]],
    ['Учёт', [
      { k: 'item_in', l: 'статья прихода', sys: '—', roWhy: 'правится в реестре контрагентов', need: 'ops' },
      { k: 'item_out', l: 'статья расхода', sys: '—', roWhy: 'правится в реестре контрагентов', need: 'ops' },
      { k: 'status', l: 'статус', sys: 'действующий', roWhy: 'действующий / виртуальный — меняется в реестре контрагентов' },
      { k: 'ord_client_id', l: 'клиент в ОРД', mono: true, sys: '—', roWhy: 'только показ, пишет ОРД' },
    ]],
  ],

  /* Банковские счета — колонки таблицы (counterparty_bank_accounts).
     Служебные поля строки: main, changed_at, changed_by(_id), confirmed { at, by, how } ◆ — правка bank/bik/ks/rs сбрасывает confirmed. */
  bank: [
    { k: 'bank', l: 'банк', w: 'minmax(170px,1.3fr)' },
    { k: 'bik', l: 'БИК', mono: true, w: '110px', ph: '9 цифр', re: /^\d{9}$/ },
    { k: 'ks', l: 'к/с', mono: true, w: '200px', ph: '20 цифр', re: /^\d{20}$/ },
    { k: 'rs', l: 'р/с', mono: true, w: '200px', ph: '20 цифр', re: /^\d{20}$/ },
    { k: 'city', l: 'город', w: '110px' },
  ],

  /* Подписанты — колонки (counterparty_signers). Скан основания — отдельная колонка «ссылка/файл + скрепка» (signer.scan ◆). */
  signer: [
    { k: 'name', l: 'ФИО', w: 'minmax(170px,1.3fr)', ph: 'ФИО полностью' },
    { k: 'role', l: 'должность', w: 'minmax(140px,1fr)' },
    { k: 'basis', l: 'основание', w: '160px', ph: 'Устав / Доверенность № …' },
    { k: 'poa_until', l: 'доверенность до', mono: true, w: '110px', ph: 'дд.мм.гггг', need: 'none' },
  ],

  /* 3. Договор — группы полей (contracts, contract_signers). Документ — отдельной строкой «ссылка + скрепка». */
  ct: [
    ['Реквизиты договора', [
      { k: 'number', l: 'номер', mono: true, from: 'юрист: подписанный договор', ph: 'РМ-03/26' },
      { k: 'date', l: 'дата', mono: true, from: 'юрист: подписанный договор', ph: 'дд.мм.гггг' },
      { k: 'marketing_name', l: 'маркетинговое имя', span: true, from: 'сейлз', need: 'none', emptyTone: 'none', emptyText: '—' },
    ]],
    ['Стороны и предмет', [
      { k: 'own_company', l: 'наше юрлицо', sys: '—', roWhy: 'единственное наше — выбирать не из чего; экран появится со вторым юрлицом', hint: 'own_company.for_contract' },
      { k: 'own_legal_role', l: 'наша роль', sys: '—', roWhy: 'ручка договора её не пишет — только показ', from: 'юрист' },
      { k: 'format', l: 'формат сотрудничества', opts: COOPERATION_FORMATS, from: 'сейлз', emptyText: 'не указан', hint: 'от него подберётся шаблон ДС' },
      { k: 'services', l: 'услуги', from: 'сейлз', need: 'none' },
    ]],
    ['Подписи', [
      { k: 'customer_signer', l: 'подписант заказчика', span: true, opts: '@signers', from: 'клиент', emptyText: 'не выбран', noNew: true },   // при заведении — подписант юрлица по умолчанию
      { k: 'our_signer', l: 'наш подписант', span: true, opts: '@ourSigners', from: 'мы', emptyText: 'не выбран', noNew: true },
    ]],
    ['Расчёты', [
      { k: 'vat', l: 'НДС договора', sys: '—', roWhy: 'ручка договора его не пишет; ставка — у нашего юрлица на дату документа', from: 'юрист', need: 'ops' },
      { k: 'pay_form', l: 'форма оплаты', from: 'сейлз: условия', need: 'ops', emptyTone: 'none', emptyText: '—' },
      { k: 'payment_term_days', l: 'отсрочка, дн.', mono: true, from: 'сейлз: условия', need: 'ops' },
      { k: 'term_cond', l: 'условие отсрочки', opts: PAYMENT_TERM_CONDITIONS, from: 'сейлз: условия', need: 'ops' },
    ]],
    ['Срок и документы', [
      { k: 'valid_until', l: 'действует до', mono: true, from: 'юрист: подписанный договор', need: 'none', ph: 'дд.мм.гггг', hint: 'свободный текст, как в договоре' },
      { k: 'prolongation', l: 'пролонгация', opts: PROLONGATION_OPTIONS, from: 'юрист', need: 'none' },
      { k: 'channel', l: 'канал выдачи', opts: ISSUE_CHANNELS, from: 'клиент' },
      { k: 'edo_status', l: 'статус ЭДО · подписан', sys: '—', roWhy: 'приходит из ЭДО' },
      { k: 'annex_word', l: 'ДС или Приложение', opts: ['ДС', 'Приложение'], from: 'юрист' },
      { k: 'annex_start_no', l: 'с какого № ДС', mono: true, sys: '—', roWhy: 'меняется в карточке договора (нумерация ДС)', from: 'юрист' },
      { k: 'note', l: 'примечание', span: true, from: 'аккаунт', need: 'none', emptyTone: 'none', emptyText: '—' },
    ]],
  ],
  /* Документ договора: ссылка ЭДО (document_url) ИЛИ файл (document_file). Хватит одного. */
  ctDoc: { link: 'document_url', file: 'document_file', from: 'юрист: скан или ЭДО', need: 'none' },

  /* 5. Агентство (sales_agencies) */
  ag: [
    ['Наименование', [
      { k: 'short_name', l: 'короткое имя', from: 'сейлз', hint: 'short_name — так в интерфейсе' },
      { k: 'holding', l: 'холдинг', from: 'сейлз', need: 'none' },
      { k: 'name_en', l: 'название EN', from: 'сейлз', need: 'none' },
      { k: 'name_ru', l: 'название RU', from: 'сейлз', need: 'none' },
    ]],
  ],

  /* 6. Рекламодатель (sales_advertisers) */
  adv: [
    ['Наименование и реквизиты', [
      { k: 'legal_name', l: 'юр. название', span: true, ph: 'как в документах: АО «…»', from: ORG, hint: 'подставляется в ДС как {юр_название}' },
      { k: 'short_name', l: 'короткое имя', from: 'сейлз' },
      { k: 'inn', l: 'ИНН', mono: true, from: 'клиент', need: 'ord' },
      { k: 'name_en', l: 'название EN', from: 'сейлз', need: 'none' },
      { k: 'name_ru', l: 'название RU', from: 'сейлз', need: 'none' },
      { k: 'site', l: 'сайт', from: 'клиент', need: 'none', emptyTone: 'none', emptyText: '—' },
      { k: 'payers', l: 'юрлица-плательщики', sys: '—', roWhy: 'связка с контрагентами — в справочнике рекламодателей', need: 'ops' },
    ]],
    ['Продажи и учёт', [
      { k: 'sales_owner', l: 'ответственный сейлз', sys: '—', roWhy: 'назначается в справочнике рекламодателей', need: 'none' },
      { k: 'exclude_from_revenue', l: 'исключать из выручки', sys: 'нет', roWhy: 'меняется в справочнике рекламодателей', need: 'none' },
      { k: 'direct', l: 'прямой рекламодатель', span: true, sys: 'на сделке', roWhy: 'признак хранится на сделке (ord_direct_advertiser)' },
    ]],
  ],
  /* Бренды (sales_brands) — колонки */
  brand: [
    { k: 'name', l: 'бренд', w: 'minmax(140px,1fr)', need: 'erid', from: 'сейлз', ro: true },   // ro — только у новой строки: переименование — в справочнике
    { k: 'kktu', l: 'ККТУ', mono: true, w: '100px', ph: 'X.X.X', need: 'erid', from: 'сейлз: справочник ОРД', re: /^\d+\.\d+\.\d+$/ },
    { k: 'ad_object', l: 'описание объекта рекламы', w: 'minmax(200px,1.6fr)', need: 'erid', from: 'клиент: бриф' },
  ],

  /* 7. СК (sk_rules, sk_special_terms) — колонки */
  sk: [
    { k: 'target', l: 'на что', w: 'minmax(170px,1.3fr)', ph: 'номер договора этого юрлица', noNew: true },   // при заведении — новый договор
    { k: 'recipient', l: 'получатель', w: 'minmax(110px,1fr)', fixed: true },
    { k: 'mode', l: 'режим', w: '110px', ph: 'постоплата', opts: SK_MODES },
    { k: 'percent', l: 'процент', mono: true, w: '70px', ph: '20 %', align: 'right' },
    { k: 'from', l: 'с', mono: true, w: '90px', ph: 'дд.мм.гггг' },
    { k: 'till', l: 'по', mono: true, w: '90px', ph: 'дд.мм.гггг' },
    { k: 'kind', l: 'вид', w: 'minmax(120px,1fr)', ph: 'основная', fixed: true },
  ],

  /* 8. ОРД — изначальный договор рекламодателя (ord_initial_contracts) */
  ordInit: [
    { k: 'number_date', l: 'номер · дата', mono: true, ph: 'ИД-… от дд.мм.гггг' },
    { k: 'subject_sum', l: 'предмет · сумма', ph: 'услуги · 12 000 000 ₽' },
    { k: 'agent_for_publisher', l: 'агент за площадку', ph: 'да / нет' },
  ],

  /* Площадка: добавка к договору (sales_publisher_contracts) */
  publisher: [
    ['Площадка', [
      { k: 'domain', l: 'домен площадки', mono: true, from: 'площадка', need: 'ops', ph: 'example.ru' },
      { k: 'publisher_vat', l: 'НДС площадки', mono: true, from: 'площадка', need: 'ops', hint: 'НДС исходящий её контрагента' },
      { k: 'cpm', l: 'CPM по договору', mono: true, from: 'сейлз: условия', need: 'ops', hint: 'хранится у площадки' },
      { k: 'intermediary', l: 'посредник', sys: '—', roWhy: 'выбирается на карточке площадки', need: 'none' },
    ]],
  ],
};

/** Цели в режиме заведения: метка у пункта «нужно получить». */
export const NEED_TAG = {
  ds:   { label: 'ДС',       bg: 'var(--accent-tint)', fg: 'var(--accent-fg)' },
  erid: { label: 'ЕРИД',     bg: 'var(--violet-tint)', fg: 'var(--violet-fg)' },
  ord:  { label: 'ОРД',      bg: 'var(--violet-tint)', fg: 'var(--violet-fg)' },
  ops:  { label: 'операции', bg: 'var(--bg-subtle)',   fg: 'var(--text-secondary)' },
  none: { label: 'позже',    bg: 'var(--bg-subtle)',   fg: 'var(--text-faint)' },
};

/** Тон алерта. bad — документ или ЕРИД не соберётся; warn — скоро помешает или расходится. */
export const TONE = {
  bad:  { bg: 'var(--danger-tint)',  border: 'var(--danger-border)',  fg: 'var(--danger-fg)',  dot: 'var(--danger)' },
  warn: { bg: 'var(--warning-tint)', border: 'var(--warning-border)', fg: 'var(--warning-fg)', dot: 'var(--warning)' },
  ok:   { bg: 'var(--income-tint)',  border: 'var(--income-border)',  fg: 'var(--income-fg)',  dot: 'var(--income)' },
};

/** Блоки юрлица — объединение блоков всех его видов в порядке BLOCKS (ДПД МЕДИА — и агентство, и площадка). */
export const blocksForKinds = kinds => BLOCKS.filter(b => !b.kinds || b.kinds.some(k => kinds.includes(k)));
export const blocksForKind = kind => blocksForKinds([kind]);
