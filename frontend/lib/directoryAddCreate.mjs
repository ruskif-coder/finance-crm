/**
 * Окно контрагента, вкладка «Заведение»: сохранение новой связки — логика прежней страницы «Добавить данные»
 * (до 05.11.2026 жила в `pages/directory/add.js`), вынесенная сюда.
 *
 * Своих писателей нет: зовутся существующие ручки — контрагент, реквизиты, подписант, агентство / рекламодатель /
 * площадка с привязкой юрлица, бренд, договор, правило СК. Идёт ПОСЛЕДОВАТЕЛЬНО и отчитывается по шагам: связка — это
 * пять-десять запросов, и если упадёт пятый, первые четыре уже произошли.
 *
 * Поэтому до первой записи — `validateNew` (ревью 05.11.2026): права ролей на каждую ручку цепочки (их отдаёт сервер,
 * `GET /directory-add/context`), обязательные поля и формат дат и чисел. Иначе роль без права на справочник получала
 * полусозданного контрагента, а неверная дата падала на последнем шаге — после созданного договора.
 *
 * `values` — плоские ключи режима заведения компонента (`cp.inn`, `bank.rs`, `ct.number`, …), `http` — `{get, post, put}`.
 * Изначальный договор ОРД здесь не сохраняется — он регистрируется на экране ОРД, шаг отчёта об этом говорит.
 */
// Те же разборы, что у «Сохранить» блока в проверке: одна копия, иначе заведение и правка поймут «20 %» и даты по-разному.
import { iso, nn, parsePct as pct } from './readinessApi.mjs'

const RIGHT_LABEL = { cp: 'Контрагенты · правка', agency: 'Агентства · правка', advertiser: 'Рекламодатели · правка',
  publisher: 'Паблишеры · Площадки · правка', contract: 'Договоры · правка', sk: 'Агентские условия · правка' }
const DATES = { 'ct.date': 'дата договора', 'sg.poa_until': 'доверенность до', 'sk.from': 'СК: с', 'sk.till': 'СК: по' }
const INTS = { 'cp.term_days': 'отсрочка контрагента', 'ct.payment_term_days': 'отсрочка договора' }

const realDate = (s) => {
  const m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(String(s).trim())
  if (!m) return false
  const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const last = new Date(Date.UTC(y, mo, 0)).getUTCDate()        // день 0 следующего месяца — последний день этого
  return mo >= 1 && mo <= 12 && d >= 1 && d <= last
}

/** Чего не хватает, чтобы заведение прошло целиком: текстом для человека; пусто — можно сохранять. */
/** Юрлицо при заведении (владелец 05.11.2026): новое · прикрепить существующее (его реквизиты не трогаются) · без юрлица —
 *  только запись справочника, для роли без права на контрагентов (вариант «Б»). */
export const cpMode = (values) => values['cp.mode'] || 'new'

export function validateNew(kind, values, rights) {
  const v = (k) => values[k]
  const out = []
  const mode = cpMode(values)
  if (mode === 'new' && !nn(v('cp.name'))) out.push('Нет полного названия юрлица')
  if (mode === 'attach' && !v('cp.attach_id')) out.push('Выберите юрлицо из списка — или заведите новое')
  if (mode === 'none' && kind === 'contractor') out.push('Подрядчик без юрлица — пустое место: выберите юрлицо или заведите новое')
  if (mode === 'none' && nn(v('ct.number'))) out.push('Договор заводится на юрлицо — выберите или заведите его')
  if (kind === 'agency' && !nn(v('ag.short_name'))) out.push('Агентство: нужно короткое имя — без него агентство не заведётся и юрлицо останется подрядчиком')
  if (kind === 'direct' && !nn(v('ad.short_name')) && !v('ad.existing_id')) out.push('Рекламодатель: нужно короткое имя или выбор существующего')
  if (kind === 'publisher' && !nn(v('pub.domain'))) out.push('Площадка: нужен домен')
  for (const [k, label] of Object.entries(DATES)) if (nn(v(k)) && !realDate(v(k))) out.push(`${label}: дата вида дд.мм.гггг`)
  for (const [k, label] of Object.entries(INTS)) if (nn(v(k)) && !/^\d+$/.test(String(v(k)).trim())) out.push(`${label}: целое число дней`)
  if (nn(v('pub.cpm')) && pct(v('pub.cpm')) == null) out.push('CPM площадки: числом')
  if (nn(v('pub.publisher_vat')) && pct(v('pub.publisher_vat')) == null) out.push('НДС площадки: числом, например 22')
  const sk = nn(v('sk.percent'))
  if (sk && pct(v('sk.percent')) == null) out.push('СК: процент числом')
  if (sk && !nn(v('sk.from'))) out.push('СК: нужна дата «с»')
  if (sk && !nn(v('ct.number'))) out.push('СК: правило ставится на договор — нужен номер договора')
  if (rights) {
    const vat = kind === 'publisher' && nn(v('pub.publisher_vat'))
    const need = [(mode === 'new' || (mode === 'attach' && vat)) && 'cp', kind === 'agency' && 'agency', kind === 'direct' && 'advertiser', kind === 'publisher' && 'publisher',
      nn(v('ct.number')) && 'contract', sk && kind !== 'contractor' && kind !== 'publisher' && 'sk'].filter(Boolean)
    const missing = need.filter(b => !rights[b])
    if (missing.length) out.push(`Нет права: ${missing.map(b => RIGHT_LABEL[b]).join(', ')} — попросите администратора или заведите без этой части`)
  }
  return out
}

const errText = (e) => {
  const d = e?.response?.data?.detail ?? e?.detail
  if (Array.isArray(d)) return d.map(x => `${(x.loc || []).slice(-1)[0] || ''}: ${x.msg || ''}`.trim()).join('; ')
  return typeof d === 'string' ? d : 'Шаг не прошёл'
}

export async function createFromWizard(http, kind, values, rights) {
  const v = (k) => values[k]
  const steps = []
  const step = (label, ok = true, link = null) => steps.push({ label, ok, link })
  const problems = validateNew(kind, values, rights)
  if (problems.length) {
    problems.forEach(p => step(p, false))
    return { cpId: null, steps, failed: true, refused: true }
  }
  let cpId = null
  const mode = cpMode(values)
  try {
    const name = mode === 'attach' ? nn(v('cp.attach_name')) : nn(v('cp.name'))
    if (mode === 'attach') {
      // Прикреплённое юрлицо НЕ переписывается: человек выбрал существующую запись, а не принёс новые данные о ней
      cpId = v('cp.attach_id')
      step(`Юрлицо «${name || cpId}» прикреплено`, true, `/directory/counterparties/${cpId}`)
    } else if (mode === 'new') {
      cpId = (await http.post('/counterparties/', { name })).id
      step(`Контрагент «${name}» создан`, true, `/directory/counterparties/${cpId}`)
    }
    if (mode === 'new') {
      const bank = nn(v('bank.bank')) || nn(v('bank.rs'))
        ? [{ bank_name: nn(v('bank.bank')), bank_city: nn(v('bank.city')), rs: nn(v('bank.rs')), ks: nn(v('bank.ks')), bik: nn(v('bank.bik')) }] : []
      await http.put(`/counterparties/${cpId}/requisites`, {
        inn: nn(v('cp.inn')), kpp: nn(v('cp.kpp')), ogrn: nn(v('cp.ogrn')), okpo: nn(v('cp.okpo')),
        address: nn(v('cp.address')), address_fact: nn(v('cp.fact_address')), phone: nn(v('cp.phone')),
        email: nn(v('cp.email')), website: nn(v('cp.site')), edo_id: nn(v('cp.edo_id')), note: null,
        legal_form: nn(v('cp.legal_form')), bank_accounts: bank,
      })
      step(bank.length ? 'Реквизиты и банковский счёт записаны' : 'Реквизиты записаны')
      if (nn(v('cp.term_days')) != null) {
        await http.put(`/counterparties/${cpId}/registry`, { name, inn: nn(v('cp.inn')), status: 'действующий', term_days: Number(v('cp.term_days')) })
        step('Отсрочка записана')
      }
      if (nn(v('sg.name'))) {
        await http.post(`/signers/counterparty/${cpId}`, { director_name: nn(v('sg.name')), signer_position: nn(v('sg.role')),
          signer_basis: nn(v('sg.basis')), valid_until: iso(v('sg.poa_until')) })
        step('Подписант по умолчанию заведён')
      }
    }

    let agencyId = null, advertiserId = null, publisherId = null
    if (kind === 'agency') {
      agencyId = (await http.post('/sales/directories/agencies', { short_name: nn(v('ag.short_name')), name_ru: nn(v('ag.name_ru')),
        name_en: nn(v('ag.name_en')), holding: nn(v('ag.holding')), note: null })).id
      step(`Агентство «${nn(v('ag.short_name'))}» создано`, true, '/directory/agencies')
      if (cpId) {
        await http.post(`/sales/directories/agencies/${agencyId}/counterparties`, { counterparty_id: cpId })
        step('Юрлицо привязано к агентству')
      }
    }
    if (kind === 'direct') {
      advertiserId = v('ad.existing_id') || (await http.post('/sales/directories/producers', {
        short_name: nn(v('ad.short_name')), name_ru: nn(v('ad.name_ru')), name_en: nn(v('ad.name_en')), website: nn(v('ad.site')),
        legal_name: nn(v('ad.legal_name')) || name, inn: nn(v('ad.inn')) || (mode === 'new' ? nn(v('cp.inn')) : null), note: null })).id
      step(v('ad.existing_id') ? 'Рекламодатель выбран из справочника' : `Рекламодатель «${nn(v('ad.short_name'))}» создан`, true, '/directory/advertisers')
      if (cpId) {
        await http.post(`/sales/directories/producers/${advertiserId}/counterparties`, { counterparty_id: cpId })
        step('Юрлицо привязано к рекламодателю')
      }
      if (nn(v('br.name'))) {
        const brandId = (await http.post('/sales/directories/brands', { name: nn(v('br.name')), advertiser_id: advertiserId })).id
        if (nn(v('br.kktu')) || nn(v('br.ad_object')))
          await http.put(`/sales/directories/brands/${brandId}/marking`, { kktu_code: nn(v('br.kktu')), ad_object_description: nn(v('br.ad_object')) })
        step(`Бренд «${nn(v('br.name'))}» заведён`)
      }
    }
    if (kind === 'publisher') {
      publisherId = (await http.post('/publishers', { domain: nn(v('pub.domain')), status: 'ПЕРЕГОВОРЫ', cpm_contract: pct(v('pub.cpm')) })).id
      step(`Площадка «${nn(v('pub.domain'))}» создана`, true, `/publishers/${publisherId}`)
      if (cpId) {
        await http.post(`/publishers/${publisherId}/counterparties`, { counterparty_id: cpId })
        step('Юрлицо привязано к площадке')
      }
      if (cpId && pct(v('pub.publisher_vat')) != null) {
        // НДС площадки — НДС исходящий её юрлица (`counterparties.vat_rate_expense`), его и читают сверка и разаллокация
        await http.put(`/counterparties/${cpId}/defaults`, { vat_rate_expense: pct(v('pub.publisher_vat')) })
        step('НДС площадки записан')
      }
    }

    let contractId = null
    if (cpId && nn(v('ct.number'))) {
      contractId = (await http.post('/contracts/', {
        counterparty_id: cpId, contract_number: nn(v('ct.number')), contract_date: iso(v('ct.date')), marketing_name: nn(v('ct.marketing_name')),
        cooperation_format: nn(v('ct.format')), services: nn(v('ct.services')), end_date_text: nn(v('ct.valid_until')),
        prolongation: nn(v('ct.prolongation')), payment_form: nn(v('ct.pay_form')),
        payment_term_days: nn(v('ct.payment_term_days')) == null ? null : Number(v('ct.payment_term_days')),
        payment_term_condition: nn(v('ct.term_cond')), issue_channel: nn(v('ct.channel')), annex_word: nn(v('ct.annex_word')),
        document_link: nn(v('ct.document_url')), note: nn(v('ct.note')),
      })).id
      step(`Договор № ${nn(v('ct.number'))} создан`, true, `/directory/contracts/${contractId}`)
      const file = v('ct.document_file')?._file
      if (file) {
        const fd = new FormData()
        fd.append('file', file)
        await http.post(`/contracts/${contractId}/upload`, fd)
        step(`Файл «${file.name}» прикреплён`)
      }
      if (publisherId) {
        // Без связки сверка и CPM площадки договор не видят (`sales_publisher_contracts`)
        await http.post(`/publishers/${publisherId}/contracts`, { contract_id: contractId, role: 'с площадкой' })
        step('Договор привязан к площадке')
      }
    }
    if (pct(v('sk.percent')) != null && contractId && (agencyId || advertiserId)) {
      await http.post('/agency-terms/rules', { kind: 'основная', contract_id: contractId, ...(agencyId ? { agency_id: agencyId } : { advertiser_id: advertiserId }),
        mode: nn(v('sk.mode')) || 'постоплата', percent: pct(v('sk.percent')), valid_from: iso(v('sk.from')), valid_to: iso(v('sk.till')) })
      step('Основное правило СК заведено')
    }
    if ((kind === 'agency' || kind === 'direct') && Object.keys(values).some(k => k.startsWith('ordi.') && nn(values[k])))
      step('Изначальный договор рекламодателя регистрируется на экране ОРД — здесь не сохранён', null, '/accounts/ord')
    return { cpId, steps, failed: false }
  } catch (e) {
    step(errText(e), false)
    return { cpId, steps, failed: true }
  }
}
