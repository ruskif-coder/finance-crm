/**
 * Окно контрагента: загрузка проверки и «Сохранить» блока (план 2026-11-05, Task 8).
 *
 * Своих писателей у окна нет: блок сохраняется существующими ручками разделов, с их нынешними проверками и правами.
 * Две из них перезаписывают присланное целиком — реквизиты (вместе с примечанием и ВСЕМИ счетами) и агентство /
 * рекламодатель (с примечанием и привязкой к юрлицу), — поэтому отсюда уходит полный набор полей, а не только
 * изменённое. Договор и подписант пишут только присланное — им уходит разница.
 *
 * Модуль без зависимостей: HTTP передаётся снаружи (`{get, post, put}`, отдают тело ответа, отказ — как у axios),
 * поэтому он проверяется `node --test` без браузера (`readinessApi.test.mjs`).
 */

const BLOCKS_WITH_HISTORY = ['cp', 'sg', 'ct', 'tpl', 'ag', 'ad', 'sk', 'ord']

/* ── даты: сервер — ISO, окно — дд.мм.гггг ── */
export const dmy = iso => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '')
  return m ? `${m[3]}.${m[2]}.${m[1]}` : (iso || null)
}
export const iso = text => {
  const s = String(text ?? '').trim()
  if (!s) return null
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(s)
  return m ? `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}` : s
}
export const nn = v => (String(v ?? '').trim() || null)
const intOrNull = v => (v === '' || v === null || v === undefined ? null : Number(v))
const pct = p => (p === null || p === undefined ? null : `${String(p).replace('.', ',')} %`)
export const parsePct = s => { const t = String(s ?? '').replace('%', '').replace(',', '.').trim(); const n = Number(t); return t && Number.isFinite(n) ? n : null }

/* ── ответ сервера → данные компонента (контракт `sampleData.js`) ── */
function touched(checks, blocks, ids) {
  return checks.some(c => blocks.includes(c.block) && ids.includes(c.fix?.ref))
}

/** `money` — форматтер суммы проекта (`lib/salesFormat.grp0`); модуль без зависимостей, поэтому его передаёт страница. */
export function mapReadiness(raw, history = {}, money = String) {
  const checks = raw.checks || []
  const contracts = (raw.contracts || []).map(c => ({
    ...c, date: dmy(c.date),
    // размер и дату файла сервер не хранит — открывается он в карточке договора
    document_file: c.document_file && { ...c.document_file, size: 'файл', uploaded_at: 'в карточке договора', url: `/directory/contracts/${c.id}` },
    collapsed: !touched(checks, ['ct', 'tpl'], [c.id]),            // готовый договор свёрнут в строку
  }))
  const byContract = Object.fromEntries((raw.contracts || []).map(c => [c.id, c.number]))
  const advertisers = raw.advertisers && raw.advertisers.map(a => ({
    ...a, exclude_from_revenue: a.exclude_from_revenue ? 'да' : 'нет',
    collapsed: !touched(checks, ['ad'], [a.id, ...a.brands.map(b => b.id)]),
  }))
  const sk = raw.sk && raw.sk.map(r => ({
    id: r.id, _raw: r,
    // подписи — с сервера (`market.sk_data`): правило бывает на агентство, которое окно не правит (юрлицо у двух агентств)
    target: [r.contract_id && `договор ${r.contract_number || byContract[r.contract_id] || r.contract_id}`,
      r.agency_id && `агентство ${r.agency_name || r.agency_id}`,
      r.advertiser_id && `рекламодатель ${r.advertiser_name || r.advertiser_id}`,
      r.brand_id && 'бренд'].filter(Boolean).join(' · ') || '—',
    recipient: r.agency_name || r.advertiser_name || null, mode: r.mode, percent: pct(r.percent),
    from: dmy(r.valid_from), till: dmy(r.valid_to), kind: r.kind,
  }))
  const ord = raw.ord && {
    contracts: raw.ord.contracts.map(c => ({
      ...c, kind: c.kind === 'final' ? 'доходный' : c.kind ? 'изначальный' : '—',
      status: c.ord_id ? (c.status || 'зарегистрирован') : 'не зарегистрирован',
    })),
    initial: raw.ord.initial.map(i => ({
      ...i, number_date: i.number ? `${i.number}${i.date ? ` от ${dmy(i.date)}` : ''}` : null,
      subject_sum: [i.subject, i.amount != null && `${money(i.amount)} ₽`].filter(Boolean).join(' · ') || null,
      agent_for_publisher: i.agent_for_publisher == null ? null : (i.agent_for_publisher ? 'да' : 'нет'),
      status: i.status || 'не получен',
    })),
  }
  const opts = raw.options || { signers: [], ourSigners: [] }
  return {
    ...raw, mode: 'check', contracts, advertisers, sk, ord, history,
    signers: (raw.signers || []).map(s => ({ ...s, poa_until: dmy(s.poa_until) })),
    options: { signers: opts.signers.map(o => o.label), ourSigners: opts.ourSigners.map(o => o.label) },
    _signerIds: Object.fromEntries([...opts.signers, ...opts.ourSigners].map(o => [o.label, o.id])),
  }
}

/* ── отказ ручки → подсказка у поля ── */
const FIELD_OF = {
  cp: [['КПП', 'kpp'], ['ИНН', 'inn'], ['ОГРН', 'ogrn'], ['Форма организации', 'legal_form'], ['Название', 'name'], ['Отсрочка', 'term_days']],
  ct: [['номер', 'number'], ['Вид ДС', 'annex_word'], ['ссылк', 'document_url'], ['дата', 'date']],
}
function toErrors(e, block) {
  const d = e?.response?.data?.detail ?? e?.detail ?? e?.message ?? 'Не сохранилось'
  const text = Array.isArray(d) ? d.map(x => x.msg || String(x)).join('; ') : String(d)
  const hit = (FIELD_OF[block] || []).find(([word]) => text.includes(word))
  const key = hit ? (e?.ref != null ? `${e.ref}.${hit[1]}` : hit[1]) : '_'
  return { [key]: text }
}
const withRef = (ref, p) => p.catch(e => { throw Object.assign(e ?? {}, { ref }) })
const changed = (a, b, keys) => keys.filter(k => (a?.[k] ?? null) !== (b?.[k] ?? null))

/* ── сохранение по блокам ── */
const CT_FIELDS = {
  number: ['contract_number', nn], date: ['contract_date', iso], marketing_name: ['marketing_name', nn],
  format: ['cooperation_format', nn], services: ['services', nn], pay_form: ['payment_form', nn],
  payment_term_days: ['payment_term_days', intOrNull], term_cond: ['payment_term_condition', nn],
  valid_until: ['end_date_text', nn], prolongation: ['prolongation', nn], channel: ['issue_channel', nn],
  annex_word: ['annex_word', nn], note: ['note', nn], document_url: ['document_link', nn],
}
const ctPayload = (c, keys) => Object.fromEntries(keys.filter(k => CT_FIELDS[k]).map(k => [CT_FIELDS[k][0], CT_FIELDS[k][1](c[k])]))

const SAVERS = {
  async cp(http, id, d, prev) {
    const c = d.counterparty
    const banks = [...d.banks].sort((a, b) => Number(!!b.main) - Number(!!a.main))   // основной — первым: порядок и есть «основной»
    await http.put(`/counterparties/${id}/requisites`, {
      inn: nn(c.inn), kpp: nn(c.kpp), ogrn: nn(c.ogrn), okpo: nn(c.okpo), address: nn(c.address),
      address_fact: nn(c.fact_address), phone: nn(c.phone), email: nn(c.email), website: nn(c.site),
      edo_id: nn(c.edo_id), note: c.note ?? null, legal_form: nn(c.legal_form),
      bank_accounts: banks.map(b => ({ bank_name: nn(b.bank), bank_city: nn(b.city), rs: nn(b.rs), ks: nn(b.ks), bik: nn(b.bik) })),
    })
    if (changed(c, prev.counterparty, ['name', 'term_days']).length)
      await http.put(`/counterparties/${id}/registry`, { name: nn(c.name), inn: nn(c.inn), status: prev.counterparty.status, term_days: intOrNull(c.term_days) })
  },
  async sg(http, id, d, prev) {
    const was = Object.fromEntries(prev.signers.map(s => [s.id, s]))
    const body = s => ({ director_name: nn(s.name), signer_position: nn(s.role), signer_basis: nn(s.basis), valid_until: iso(s.poa_until) })
    for (const s of d.signers) {
      if (s._new) {
        const made = await http.post(`/signers/counterparty/${id}`, body(s))
        if (s._replaces) {
          // архив подписанта по умолчанию ручка отклоняет — новая доверенность сперва становится основной (ревью 05.11)
          if (was[s._replaces]?.is_default) await http.put(`/signers/${made.id}/default`)
          await http.put(`/signers/${s._replaces}/archive`, { on: true })
        }
        continue
      }
      const keys = changed(s, was[s.id], ['name', 'role', 'basis', 'poa_until'])
      if (keys.length) {
        const full = body(s), map = { name: 'director_name', role: 'signer_position', basis: 'signer_basis', poa_until: 'valid_until' }
        await http.put(`/signers/${s.id}`, Object.fromEntries(keys.map(k => [map[k], full[map[k]]])))
      }
      if (s.is_default && !was[s.id]?.is_default) await http.put(`/signers/${s.id}/default`)
    }
  },
  async ct(http, id, d, prev) {
    const was = Object.fromEntries(prev.contracts.map(c => [c.id, c]))
    for (const c of d.contracts) {
      if (c._new) {
        await http.post('/contracts/', { counterparty_id: id, ...ctPayload(c, Object.keys(CT_FIELDS).filter(k => c[k] != null && c[k] !== '')) })
        continue
      }
      const keys = changed(c, was[c.id], Object.keys(CT_FIELDS))
      if (keys.length) await withRef(c.id, http.put(`/contracts/${c.id}`, ctPayload(c, keys)))
      for (const [k, side] of [['customer_signer', 'заказчик'], ['our_signer', 'исполнитель']]) {
        if ((c[k] ?? null) !== (was[c.id]?.[k] ?? null))
          await withRef(c.id, http.put(`/signers/contract/${c.id}/${side}`, { signer_id: prev._signerIds?.[c[k]] ?? null }))
      }
    }
  },
  async ag(http, id, d) {
    const a = d.agency
    await http.put(`/sales/directories/agencies/${a.id}`, { short_name: nn(a.short_name), name_en: nn(a.name_en), name_ru: nn(a.name_ru), holding: nn(a.holding), note: a.note ?? null })
  },
  async ad(http, id, d, prev) {
    const was = Object.fromEntries(prev.advertisers.map(a => [a.id, a]))
    for (const a of d.advertisers) {
      if (changed(a, was[a.id], ['short_name', 'name_en', 'name_ru', 'legal_name', 'site', 'inn']).length)
        await http.put(`/sales/directories/producers/${a.id}`, { short_name: nn(a.short_name), name_en: nn(a.name_en), name_ru: nn(a.name_ru),
          legal_name: nn(a.legal_name), website: nn(a.site), counterparty_id: a.counterparty_id ?? null, inn: nn(a.inn), note: a.note ?? null })
      const brands = Object.fromEntries((was[a.id]?.brands || []).map(b => [b.id, b]))
      for (const b of a.brands || []) {
        let bid = b.id
        if (b._new) {
          if (!nn(b.name)) continue
          bid = (await http.post('/sales/directories/brands', { name: nn(b.name), advertiser_id: a.id })).id
        }
        if (b._new ? (nn(b.kktu) || nn(b.ad_object)) : changed(b, brands[b.id], ['kktu', 'ad_object']).length)
          await http.put(`/sales/directories/brands/${bid}/marking`, { kktu_code: nn(b.kktu), ad_object_description: nn(b.ad_object) })
      }
    }
  },
  async sk(http, id, d, prev) {
    const was = Object.fromEntries(prev.sk.map(r => [r.id, r]))
    for (const r of d.sk) {
      const upd = { mode: nn(r.mode), percent: parsePct(r.percent), valid_from: iso(r.from), valid_to: iso(r.till) }
      if (r._new) {
        // договор — по точному номеру: вхождение подставило бы «1» вместо «12» (ревью 05.11)
        const want = String(r.target ?? '').replace(/^договор\s+/i, '').trim()
        const ct = prev.contracts.find(c => c.number && c.number.trim() === want)
        if (upd.percent == null || !upd.valid_from) throw { detail: 'Новое правило: нужны процент и дата «с»' }
        const adv = prev.advertisers || []
        const owner = prev.agency ? { agency_id: prev.agency.id } : adv.length === 1 ? { advertiser_id: adv[0].id } : null
        if (!ct || !owner) throw { detail: 'Новое правило: укажите договор этого юрлица в «на что»; правило для нескольких рекламодателей заводится в «Агентских условиях»' }
        await http.post('/agency-terms/rules', { kind: 'основная', contract_id: ct.id, ...owner, ...upd })
        continue
      }
      if (changed(r, was[r.id], ['mode', 'percent', 'from', 'till']).length)
        await http.put(`/agency-terms/rules/${r.id}`, { ...r._raw, ...upd })
    }
  },
}

export function createReadinessApi(http, { money } = {}) {
  const last = {}
  const api = {
    async load(cpId) {
      const raw = await http.get(`/directory-add/readiness/${cpId}`)
      const blocks = (raw.blocks || []).filter(b => BLOCKS_WITH_HISTORY.includes(b))
      const logs = await Promise.all(blocks.map(b => api.history(cpId, b).catch(() => [])))
      last[cpId] = mapReadiness(raw, Object.fromEntries(blocks.map((b, i) => [b, logs[i]])), money)
      return last[cpId]
    },
    history: (cpId, block) => http.get(`/directory-add/readiness/${cpId}/history?block=${block}`).then(r => r.items || []),
    lookup: (inn, kpp) => http.get(`/directory-add/lookup?inn=${encodeURIComponent(inn || '')}${kpp ? `&kpp=${encodeURIComponent(kpp)}` : ''}`),
    async saveBlock(cpId, block, draft) {
      const saver = SAVERS[block]
      if (!saver) return { errors: { _: 'Этот блок правится на своём экране' } }
      try {
        await saver(http, cpId, draft, last[cpId] || await api.load(cpId))
      } catch (e) {
        return { errors: toErrors(e, block) }
      }
      return { data: await api.load(cpId) }
    },
  }
  return api
}
