/**
 * Справочники → «Добавить данные».
 *
 * Один экран заводит всю связку сразу: ВИД → объект справочника → ЮРЛИЦО → ДОГОВОР.
 * Раньше это были три-четыре экрана, а связка между ними ставилась потом руками — и не
 * ставилась: из 211 контрагентов в связках оказалось 70.
 *
 * Собрано по хендоффу `docs/добавление данных.zip` (06.09.2026). Компонента в нём не
 * было — только референс и спека, — поэтому вёрстка своя, но НА НАШИХ примитивах:
 * `salesTableKit` и токены `globals.css`. Хексов в разметке нет; все цвета хендоффа
 * совпадают с нашими переменными, потому что он собран на той же системе.
 *
 * **Своих ПИСАТЕЛЕЙ экран не заводит.** Он зовёт существующие — создание контрагента,
 * реквизиты, создание агентства/рекламодателя/площадки, привязку и создание договора.
 * Второй писатель на те же таблицы означал бы вторые правила проверки и вторые права.
 *
 * Ручка у экрана всё же одна, на чтение: `GET /api/directory-add/context`. Она и есть
 * право `directory_add` — вход на экран. Без неё галочка в конструкторе ролей ничего бы
 * не открывала: сняли — а экран по прямому адресу работает. Она же отвечает, какие блоки
 * доступны: до 06.09.2026 экран решал это САМ, читая права из localStorage, а клиентское
 * решение о правах снимается инструментами браузера.
 *
 * Сохранение идёт ПОСЛЕДОВАТЕЛЬНО и показывает каждый шаг: связка создаётся пятью
 * запросами, и если упадёт третий, первые два уже произошли. Молчать об этом нельзя —
 * человек должен видеть, что завелось, и не заводить контрагента дважды.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import Head from 'next/head'
import api, { auth } from '@/lib/http'
import Navbar from '@/components/Navbar'
import SectionTabs from '@/components/SectionTabs'
import ValuePopover from '@/components/ValuePopover'
import { MONO, UI, card, inp, btn, primaryBtn } from '@/components/salesTableKit'
// Списки — ОБЩИЕ с реестром договоров (lib/contractTerms). Своя копия здесь разошлась бы
// с реестром, а значения сравниваются в базе буквально.
import { COOPERATION_FORMATS, PAYMENT_TERM_CONDITIONS, PROLONGATION_OPTIONS } from '@/lib/contractTerms'

const CAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-muted)' }
const META = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }
const BOX = { ...card, padding: '18px 20px', marginBottom: 14 }

/** Вид определяет НАБОР блоков. Остальные не рисуются — их добавляют чипом. */
const KINDS = [
  { key: 'contractor', title: 'Подрядчик', hint: 'Юрлицо и договор — своего справочника у подрядчика нет', blocks: ['cp', 'contract'] },
  { key: 'agency', title: 'Агентство', hint: 'Справочник агентств, юрлицо, договор', blocks: ['agency', 'cp', 'contract'] },
  { key: 'advertiser', title: 'Рекламодатель', hint: 'Справочник рекламодателей, юрлицо, договор', blocks: ['advertiser', 'cp', 'contract'] },
  { key: 'publisher', title: 'Площадка', hint: 'Справочник площадок, юрлицо, договор', blocks: ['publisher', 'cp', 'contract'] },
]

/** Блок → человеческое имя и право, которое спрашивает его ручка. */
const BLOCKS = {
  agency: { title: 'Агентство', perm: 'dir_agencies' },
  advertiser: { title: 'Рекламодатель', perm: 'dir_advertisers' },
  publisher: { title: 'Площадка', perm: 'dir_publishers' },
  cp: { title: 'Контрагент — юрлицо', perm: 'counterparties' },
  contract: { title: 'Договор', perm: 'contracts' },
}
const ORDER = ['agency', 'advertiser', 'publisher', 'cp', 'contract']

const EMPTY = {
  cp: { name: '', inn: '', kpp: '', ogrn: '', okpo: '', address: '', address_fact: '', phone: '', email: '', website: '', edo_id: '', director_name: '', signer_position: '', signer_basis: '', note: '', bank_name: '', bank_city: '', rs: '', ks: '', bik: '' },
  contract: { contract_number: '', contract_date: '', marketing_name: '', cooperation_format: '', end_date_text: '', prolongation: '', payment_form: '', payment_term_days: '', payment_term_condition: '', document_link: '', note: '' },
  agency: { short_name: '', name_ru: '', name_en: '', holding: '', note: '' },
  advertiser: { short_name: '', name_ru: '', name_en: '', website: '', inn: '', note: '' },
  publisher: { domain: '', name: '', code: '', kind: '', status: 'ПЕРЕГОВОРЫ', network: '', deal_type: '', note: '' },
}

/** Поле ввода.
 *
 *  На уровне модуля: компонент внутри компонента пересоздаётся на каждый ввод и роняет
 *  фокус после каждого символа — это ловит гейт `check-inline`.
 *
 *  Пустое обязательное поле держит красную рамку: ошибку видно НА САМОМ ПОЛЕ, а не
 *  только в списке причин внизу — иначе к причине надо возвращаться глазами. */
function F({ label, value, onChange, placeholder, span, type = 'text', mono, required, hint }) {
  const bad = required && !String(value || '').trim()
  return (
    <div style={{ minWidth: 0, gridColumn: span ? `span ${span}` : undefined }}>
      <div style={{ ...CAPS, marginBottom: 5 }}>
        {label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}
      </div>
      <input type={type} value={value || ''} onChange={e => onChange(e.target.value)}
             placeholder={placeholder}
             style={{ ...inp, width: '100%', height: 36, borderRadius: 10, fontSize: 13,
                      fontFamily: mono ? MONO : UI,
                      borderColor: bad ? 'var(--danger-border)' : 'var(--border-card)' }} />
      {!!hint && <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 4, lineHeight: 1.45 }}>{hint}</div>}
    </div>
  )
}

/** Значение из списка предустановок.
 *
 *  Через `ValuePopover` — канон выбора значения в проекте, а не свой `position:absolute`
 *  (см. навык `styling-new-page`). «Прочее» открывает свободный ввод: словари
 *  накопительные, и запрещать незнакомое значение значит останавливать работу. */
function Pick({ label, value, options, onChange, span, openPop }) {
  const custom = !!value && !options.includes(value)
  return (
    <div style={{ minWidth: 0, gridColumn: span ? `span ${span}` : undefined }} data-pop-root>
      <div style={{ ...CAPS, marginBottom: 5 }}>{label}</div>
      <div onClick={e => openPop(e.currentTarget.getBoundingClientRect(), label, value, options, onChange)}
           style={{ ...inp, width: '100%', height: 36, borderRadius: 10, fontSize: 13,
                    display: 'flex', alignItems: 'center', cursor: 'pointer',
                    borderStyle: 'dashed',
                    color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>
        {value || '—'}
      </div>
      {custom && (
        <input value={value} onChange={e => onChange(e.target.value)} autoFocus
               placeholder="своё значение"
               style={{ ...inp, width: '100%', height: 36, borderRadius: 10, fontSize: 13, marginTop: 6 }} />
      )}
    </div>
  )
}

/** Заголовок блока: выключатель, имя, право справа. */
function Block({ blockKey, on, onToggle, allowed, children, note }) {
  const meta = BLOCKS[blockKey]
  const state = !allowed ? `нет права ${meta.perm}`
    : on ? `${meta.perm} · edit` : 'выключен · данные не сохраняются'
  return (
    <div style={{ ...BOX, borderColor: on && allowed ? 'var(--border-card)' : 'var(--border-inner)',
                  background: allowed ? 'var(--bg-card)' : 'var(--bg-subtle)' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 11,
                      cursor: allowed ? 'pointer' : 'default' }}>
        <input type="checkbox" checked={on} disabled={!allowed} onChange={onToggle}
               style={{ width: 18, height: 18, accentColor: 'var(--accent)', cursor: allowed ? 'pointer' : 'default' }} />
        <span style={{ fontSize: 16, fontWeight: 700,
                       color: on && allowed ? 'var(--text-primary)' : 'var(--text-muted)' }}>
          {meta.title}
        </span>
        <span style={{ ...META, marginLeft: 'auto' }}>{state}</span>
      </label>
      {!allowed && (
        <div style={{ marginTop: 12, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
                      borderRadius: 12, padding: '10px 14px', fontSize: 12.5, color: 'var(--warning-text)' }}>
          Нет права <b style={{ fontFamily: MONO }}>{meta.perm} · edit</b> — блок не заводится.
          Право выдаёт администратор в настройках ролей.
        </div>
      )}
      {on && allowed && <div style={{ marginTop: 16 }}>{children}</div>}
      {on && allowed && !!note && (
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 12, lineHeight: 1.5 }}>{note}</div>
      )}
    </div>
  )
}

const G = (cols, gap = 12) => ({ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap })

export default function AddData() {
  const [kind, setKind] = useState('agency')
  const [extra, setExtra] = useState([])          // блоки, добавленные вне вида
  const [off, setOff] = useState([])              // выключенные руками
  const [v, setV] = useState(EMPTY)               // значения живут отдельно от переключателей
  const [steps, setSteps] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [rights, setRights] = useState({})
  const [mktTouched, setMktTouched] = useState(false)
  const [pop, setPop] = useState(null)
  const fileRef = useRef(null)
  const [file, setFile] = useState(null)

  // Набор доступных блоков считает СЕРВЕР. Пока ответ не пришёл, все блоки закрыты:
  // открыть по умолчанию и закрыть после ответа значило бы мигнуть тем, чего человеку
  // нельзя. 403 здесь — не ошибка сети, а отсутствие права на экран.
  useEffect(() => {
    let alive = true
    api.get('/directory-add/context', auth())
      .then(({ data }) => { if (alive) setRights(data.blocks || {}) })
      .catch(e => {
        if (!alive) return
        setRights(Object.fromEntries(ORDER.map(k => [k, false])))
        setErr(e?.response?.status === 403
          ? 'Нет права «Добавить данные» — попросите администратора выдать раздел роли.'
          : 'Не удалось получить права на экран. Обновите страницу.')
      })
    return () => { alive = false }
  }, [])

  const kindMeta = KINDS.find(k => k.key === kind)
  /** Видимые блоки: набор вида плюс добавленные чипом, в общем порядке. */
  const visible = ORDER.filter(b => kindMeta.blocks.includes(b) || extra.includes(b))
  const isOn = (b) => visible.includes(b) && !off.includes(b) && !!rights[b]

  /** Смена вида сбрасывает ТОЛЬКО переключатели: значения полей живут в `v` и остаются —
   *  человек мог начать с агентства и понять, что это рекламодатель. */
  const pickKind = (k) => { setKind(k); setExtra([]); setOff([]) }
  const toggle = (b) => () => setOff(s => (s.includes(b) ? s.filter(x => x !== b) : [...s, b]))
  const set = (block, key) => (val) => setV(f => ({ ...f, [block]: { ...f[block], [key]: val } }))
  const step = (text, ok, link) => setSteps(s => [...s, { text, ok, link }])

  const openPop = (rect, title, value, options, onChange) =>
    setPop({ rect, title, value, options, onChange })

  /** Маркетинговое название подтягивается из заводимого объекта, пока не написали своё. */
  const mktSource = useMemo(() => (
    (isOn('publisher') && (v.publisher.name.trim() || v.publisher.domain.trim()))
    || (isOn('agency') && v.agency.short_name.trim())
    || (isOn('advertiser') && v.advertiser.short_name.trim()) || ''
  ), [visible, off, rights, v.publisher.name, v.publisher.domain, v.agency.short_name, v.advertiser.short_name])

  useEffect(() => {
    if (mktTouched) return
    setV(f => (f.contract.marketing_name === mktSource ? f
      : { ...f, contract: { ...f.contract, marketing_name: mktSource } }))
  }, [mktSource, mktTouched])

  /** Что мешает сохранить — считается ДО нажатия, чтобы кнопка не отвечала отказом. */
  const problems = []
  if (!visible.some(isOn)) problems.push({ text: 'Не включён ни один блок', at: '' })
  if (isOn('cp') && !v.cp.name.trim()) problems.push({ text: 'Нет наименования юрлица', at: 'Контрагент' })
  if (isOn('contract') && !isOn('cp')) problems.push({ text: 'Договор заводится на юрлицо — включите блок контрагента', at: 'Договор' })
  if (isOn('contract') && !v.contract.contract_number.trim()) problems.push({ text: 'Нет номера договора', at: 'Договор' })
  if (isOn('agency') && !v.agency.short_name.trim()) problems.push({ text: 'Нет краткого названия агентства', at: 'Агентство' })
  if (isOn('advertiser') && !v.advertiser.short_name.trim()) problems.push({ text: 'Нет краткого названия рекламодателя', at: 'Рекламодатель' })
  if (isOn('publisher') && !v.publisher.domain.trim()) problems.push({ text: 'Нет домена площадки', at: 'Площадка' })

  const nn = (x) => (String(x || '').trim() || null)

  const save = async () => {
    setBusy(true); setErr(''); setSteps([])
    try {
      let cpId = null
      if (isOn('cp')) {
        const r = await api.post('/counterparties/', { name: v.cp.name.trim() }, auth())
        cpId = r.data.id
        step(`Контрагент «${v.cp.name.trim()}» создан`, true, `/directory/counterparties/${cpId}`)
        const c = v.cp
        await api.put(`/counterparties/${cpId}/requisites`, {
          inn: nn(c.inn), kpp: nn(c.kpp), ogrn: nn(c.ogrn), okpo: nn(c.okpo),
          address: nn(c.address), address_fact: nn(c.address_fact), phone: nn(c.phone),
          email: nn(c.email), website: nn(c.website), edo_id: nn(c.edo_id),
          director_name: nn(c.director_name), signer_position: nn(c.signer_position),
          signer_basis: nn(c.signer_basis), note: nn(c.note),
          bank_accounts: (c.bank_name || c.rs)
            ? [{ bank_name: nn(c.bank_name), bank_city: nn(c.bank_city), rs: nn(c.rs), ks: nn(c.ks), bik: nn(c.bik) }]
            : [],
        }, auth())
        step('Реквизиты и банковский счёт записаны', true)
      }

      if (isOn('agency')) {
        const r = await api.post('/sales/directories/agencies', {
          short_name: v.agency.short_name.trim(), name_ru: nn(v.agency.name_ru),
          name_en: nn(v.agency.name_en), holding: nn(v.agency.holding), note: nn(v.agency.note),
        }, auth())
        step(`Агентство «${v.agency.short_name.trim()}» создано`, true, '/directory/agencies')
        if (cpId) {
          await api.post(`/sales/directories/agencies/${r.data.id}/counterparties`, { counterparty_id: cpId }, auth())
          step('Юрлицо привязано к агентству', true)
        }
      }
      if (isOn('advertiser')) {
        const r = await api.post('/sales/directories/producers', {
          short_name: v.advertiser.short_name.trim(), name_ru: nn(v.advertiser.name_ru),
          name_en: nn(v.advertiser.name_en), website: nn(v.advertiser.website),
          inn: nn(v.advertiser.inn), note: nn(v.advertiser.note),
        }, auth())
        step(`Рекламодатель «${v.advertiser.short_name.trim()}» создан`, true, '/directory/advertisers')
        if (cpId) {
          await api.post(`/sales/directories/producers/${r.data.id}/counterparties`, { counterparty_id: cpId }, auth())
          step('Юрлицо привязано к рекламодателю', true)
        }
      }
      if (isOn('publisher')) {
        const p = v.publisher
        const r = await api.post('/publishers', {
          domain: p.domain.trim(), name: nn(p.name), code: nn(p.code), kind: nn(p.kind),
          status: p.status || 'ПЕРЕГОВОРЫ', network: nn(p.network), deal_type: nn(p.deal_type),
          note: nn(p.note),
        }, auth())
        step(`Площадка «${p.domain.trim()}» создана`, true, `/publishers/${r.data.id}`)
        if (cpId) {
          await api.post(`/publishers/${r.data.id}/counterparties`, { counterparty_id: cpId }, auth())
          step('Юрлицо привязано к площадке', true)
        }
      }

      if (isOn('contract') && cpId) {
        const k = v.contract
        const r = await api.post('/contracts/', {
          counterparty_id: cpId, contract_number: k.contract_number.trim(),
          contract_date: nn(k.contract_date), marketing_name: nn(k.marketing_name),
          cooperation_format: nn(k.cooperation_format), end_date_text: nn(k.end_date_text),
          prolongation: nn(k.prolongation), payment_form: nn(k.payment_form),
          payment_term_days: k.payment_term_days === '' ? null : Number(k.payment_term_days),
          payment_term_condition: nn(k.payment_term_condition),
          document_link: nn(k.document_link), note: nn(k.note),
        }, auth())
        step(`Договор № ${k.contract_number.trim()} создан`, true,
             `/directory/contracts?q=${encodeURIComponent(k.contract_number.trim())}`)
        if (file) {
          const fd = new FormData()
          fd.append('file', file)
          await api.post(`/contracts/${r.data.id}/upload`, fd,
            { ...auth(), headers: { ...(auth().headers || {}), 'Content-Type': 'multipart/form-data' } })
          step(`Файл «${file.name}» прикреплён`, true)
        }
      }
      setV(EMPTY); setFile(null); setMktTouched(false)
    } catch (e) {
      const msg = e.response?.data?.detail || 'Шаг не прошёл'
      step(typeof msg === 'string' ? msg : JSON.stringify(msg), false)
      setErr('Сохранение прервалось. Что успело создаться — в списке ниже; повторное нажатие заведёт их ещё раз.')
    } finally { setBusy(false) }
  }

  const outside = ORDER.filter(b => !kindMeta.blocks.includes(b) && !extra.includes(b))

  return (
    <>
      <Head><title>Добавить данные · Справочники | SIMB-AD ERP</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 26px 60px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SectionTabs section="directory" />
        {/* По левому краю, без центрирования (владелец 06.09.2026): форму заполняют
            сверху вниз, и колонка, плавающая по центру широкого экрана, уводит взгляд. */}
        <div style={{ maxWidth: 1500 }}>

          {!!err && (
            <div style={{ ...BOX, background: 'var(--danger-tint)', borderColor: 'var(--danger-border)', color: 'var(--danger)' }}>
              {err}
            </div>
          )}

          {/* Вид выбирается на старте: от него зависит НАБОР блоков. */}
          <div style={BOX}>
            <div style={{ ...CAPS, marginBottom: 12 }}>Что добавляем</div>
            <div style={G(4, 10)}>
              {KINDS.map(k => {
                const active = kind === k.key
                return (
                  <div key={k.key} onClick={() => pickKind(k.key)}
                       style={{ padding: '13px 15px', borderRadius: 14, cursor: 'pointer',
                                border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-card)'}`,
                                background: active ? 'var(--accent-tint)' : 'var(--bg-card)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <i style={{ width: 8, height: 8, borderRadius: 2, background: active ? 'var(--accent)' : 'var(--border-card)' }} />
                      <span style={{ fontSize: 14, fontWeight: 700, color: active ? 'var(--accent)' : 'var(--text-primary)' }}>{k.title}</span>
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.45 }}>{k.hint}</div>
                  </div>
                )
              })}
            </div>
            {/* Блок вне вида добавляется чипом: так с этого экрана заводится и один
                договор, и один рекламодатель. */}
            {!!outside.length && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
                <span style={{ ...META }}>добавить блок вне вида</span>
                {outside.map(b => (
                  <span key={b} onClick={() => setExtra(s => [...s, b])}
                        style={{ border: '1px dashed var(--border-card)', borderRadius: 10,
                                 padding: '5px 11px', fontSize: 12, fontWeight: 600,
                                 color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    + {BLOCKS[b].title}
                  </span>
                ))}
              </div>
            )}
          </div>

          {visible.includes('agency') && (
            <Block blockKey="agency" on={isOn('agency')} onToggle={toggle('agency')} allowed={!!rights.agency}>
              <div style={G(3)}>
                <F label="Краткое название" required value={v.agency.short_name} onChange={set('agency', 'short_name')} placeholder="OKKAM" />
                <F label="Название по-русски" value={v.agency.name_ru} onChange={set('agency', 'name_ru')} />
                <F label="Название по-английски" value={v.agency.name_en} onChange={set('agency', 'name_en')} />
                <F label="Холдинг" value={v.agency.holding} onChange={set('agency', 'holding')} />
                <F label="Примечание" span={2} value={v.agency.note} onChange={set('agency', 'note')} />
              </div>
            </Block>
          )}

          {visible.includes('advertiser') && (
            <Block blockKey="advertiser" on={isOn('advertiser')} onToggle={toggle('advertiser')} allowed={!!rights.advertiser}
                   note="Бренды принадлежат рекламодателю и заводятся в его справочнике — здесь их нет.">
              <div style={G(3)}>
                <F label="Краткое название" required value={v.advertiser.short_name} onChange={set('advertiser', 'short_name')} placeholder="Dr. Reddy’s" />
                <F label="Название по-русски" value={v.advertiser.name_ru} onChange={set('advertiser', 'name_ru')} />
                <F label="Название по-английски" value={v.advertiser.name_en} onChange={set('advertiser', 'name_en')} />
                <F label="Сайт" value={v.advertiser.website} onChange={set('advertiser', 'website')} />
                <F label="ИНН" mono value={v.advertiser.inn} onChange={set('advertiser', 'inn')} />
                <F label="Примечание" value={v.advertiser.note} onChange={set('advertiser', 'note')} />
              </div>
            </Block>
          )}

          {visible.includes('publisher') && (
            <Block blockKey="publisher" on={isOn('publisher')} onToggle={toggle('publisher')} allowed={!!rights.publisher}>
              <div style={G(4)}>
                <F label="Домен" required mono value={v.publisher.domain} onChange={set('publisher', 'domain')} placeholder="apteka.ru" />
                <F label="Название" value={v.publisher.name} onChange={set('publisher', 'name')} placeholder="по умолчанию домен" />
                <F label="Код" mono value={v.publisher.code} onChange={set('publisher', 'code')} placeholder="APT" />
                <F label="Вид" value={v.publisher.kind} onChange={set('publisher', 'kind')} />
                <F label="Сеть" value={v.publisher.network} onChange={set('publisher', 'network')} placeholder="пусто = независимая" />
                <F label="Вид договора" value={v.publisher.deal_type} onChange={set('publisher', 'deal_type')} />
                <F label="Примечание" span={2} value={v.publisher.note} onChange={set('publisher', 'note')} />
              </div>
            </Block>
          )}

          {visible.includes('cp') && (
            <Block blockKey="cp" on={isOn('cp')} onToggle={toggle('cp')} allowed={!!rights.cp}>
              {/* Две колонки: слева то, чем юрлицо опознаётся в документах и в ЭДО,
                  справа — связь с ним. Порядок владельца 06.09.2026. */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
                <div style={{ paddingRight: 20 }}>
                  <div style={{ ...CAPS, marginBottom: 12 }}>Основные реквизиты</div>
                  <div style={{ display: 'grid', gap: 12 }}>
                    <F label="Наименование" required value={v.cp.name} onChange={set('cp', 'name')} placeholder="ООО «Ромашка»" />
                    <div style={G(2)}>
                      <F label="ИНН" mono value={v.cp.inn} onChange={set('cp', 'inn')} />
                      <F label="КПП" mono value={v.cp.kpp} onChange={set('cp', 'kpp')} />
                      <F label="ОГРН" mono value={v.cp.ogrn} onChange={set('cp', 'ogrn')} />
                      <F label="ОКПО" mono value={v.cp.okpo} onChange={set('cp', 'okpo')} />
                    </div>
                  </div>
                </div>
                <div style={{ paddingLeft: 20, borderLeft: '1px solid var(--border-inner)' }}>
                  <div style={{ ...CAPS, marginBottom: 12 }}>Контакты и адреса</div>
                  <div style={{ display: 'grid', gap: 12 }}>
                    <div style={G(2)}>
                      <F label="Телефон" mono value={v.cp.phone} onChange={set('cp', 'phone')} />
                      <F label="Email" value={v.cp.email} onChange={set('cp', 'email')} />
                    </div>
                    <F label="Юридический адрес" value={v.cp.address} onChange={set('cp', 'address')} />
                    <F label="Фактический адрес" value={v.cp.address_fact} onChange={set('cp', 'address_fact')} />
                    <div style={G(2)}>
                      <F label="Сайт" value={v.cp.website} onChange={set('cp', 'website')} />
                      <F label="ЭДО" mono value={v.cp.edo_id} onChange={set('cp', 'edo_id')} />
                    </div>
                    <F label="Примечание" value={v.cp.note} onChange={set('cp', 'note')} />
                  </div>
                </div>
              </div>

              <div style={{ borderTop: '1px solid var(--border-inner)', margin: '18px 0 0', paddingTop: 16 }}>
                <div style={{ ...CAPS, marginBottom: 12 }}>Подписант документов</div>
                <div style={G(3)}>
                  <F label="ФИО подписанта" value={v.cp.director_name} onChange={set('cp', 'director_name')} placeholder="Иванов Иван Иванович" />
                  <F label="Должность" value={v.cp.signer_position} onChange={set('cp', 'signer_position')} placeholder="Генеральный директор" />
                  <F label="Основание полномочий" value={v.cp.signer_basis} onChange={set('cp', 'signer_basis')} placeholder="Устава" />
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.5 }}>
                  Эти три поля печатаются в приложении к договору: «в лице Генерального
                  директора Иванова Ивана Ивановича, действующего на основании Устава».
                  Замер 06.09.2026: заполнены у 2 контрагентов из 211 — без них приложение
                  не выгружается.
                </div>
              </div>

              <div style={{ borderTop: '1px solid var(--border-inner)', margin: '18px 0 0', paddingTop: 16 }}>
                <div style={{ ...CAPS, marginBottom: 12 }}>Банковский счёт</div>
                <div style={G(5)}>
                  <F label="Банк" span={2} value={v.cp.bank_name} onChange={set('cp', 'bank_name')} />
                  <F label="Город" value={v.cp.bank_city} onChange={set('cp', 'bank_city')} />
                  <F label="Р/С" mono value={v.cp.rs} onChange={set('cp', 'rs')} />
                  <F label="БИК" mono value={v.cp.bik} onChange={set('cp', 'bik')} />
                  <F label="К/С" mono span={2} value={v.cp.ks} onChange={set('cp', 'ks')} />
                </div>
              </div>
            </Block>
          )}

          {visible.includes('contract') && (
            <Block blockKey="contract" on={isOn('contract')} onToggle={toggle('contract')} allowed={!!rights.contract}
                   note="Стартовый номер приложений задаётся после создания — в реестре договоров, колонка «ДС с».">
              <div style={G(4)}>
                <F label="№ договора" required value={v.contract.contract_number} onChange={set('contract', 'contract_number')} placeholder="РМ 30-11-2023" />
                <F label="Дата" type="date" value={v.contract.contract_date} onChange={set('contract', 'contract_date')} />
                <div style={{ gridColumn: 'span 2' }}>
                  <F label="Название маркетинговое" value={v.contract.marketing_name}
                     onChange={val => { setMktTouched(true); set('contract', 'marketing_name')(val) }}
                     placeholder={mktSource ? 'подтянется из объекта выше' : 'например, OKKAM'} />
                  <div style={{ fontSize: 11.5, marginTop: 4,
                                color: mktTouched && mktSource ? 'var(--warning-text)' : 'var(--text-faint)' }}>
                    {!mktSource ? 'подтягивать нечего — объект не заводится'
                      : mktTouched
                        ? <>задано вручную · <span onClick={() => setMktTouched(false)}
                            style={{ color: 'var(--accent)', cursor: 'pointer', fontWeight: 700 }}>вернуть автоподстановку</span></>
                        : 'подтянуто из заводимого объекта'}
                  </div>
                </div>
                <Pick label="Формат сотрудничества" span={2} options={COOPERATION_FORMATS}
                      value={v.contract.cooperation_format} onChange={set('contract', 'cooperation_format')} openPop={openPop} />
                <F label="Окончание" value={v.contract.end_date_text} onChange={set('contract', 'end_date_text')} placeholder="дата или текст" />
                <Pick label="Пролонгация" options={PROLONGATION_OPTIONS}
                      value={v.contract.prolongation} onChange={set('contract', 'prolongation')} openPop={openPop} />
                <F label="Форма оплаты" value={v.contract.payment_form} onChange={set('contract', 'payment_form')}
                   placeholder="списка пока нет"
                   hint="Словаря значений в проекте нет: поле пусто у всех 173 договоров" />
                <F label="Отсрочка, дней" mono value={v.contract.payment_term_days} onChange={set('contract', 'payment_term_days')} />
                <Pick label="Условие отсрочки" span={2} options={PAYMENT_TERM_CONDITIONS}
                      value={v.contract.payment_term_condition} onChange={set('contract', 'payment_term_condition')} openPop={openPop} />
                <F label="Ссылка в ЭДО" span={2} value={v.contract.document_link} onChange={set('contract', 'document_link')} placeholder="https://diadoc.kontur.ru/…" />
                <F label="Примечание" span={2} value={v.contract.note} onChange={set('contract', 'note')} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
                <input ref={fileRef} type="file" style={{ display: 'none' }}
                       onChange={e => setFile(e.target.files?.[0] || null)} />
                <button type="button" onClick={() => fileRef.current?.click()} style={btn(false)}>
                  {file ? `📎 ${file.name}` : '📎 Прикрепить файл договора'}
                </button>
                {!!file && (
                  <button type="button" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = '' }}
                          style={{ ...btn(false), color: 'var(--danger)' }}>Убрать</button>
                )}
                <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                  до 20 МБ. Ссылка ведёт в Диадок, файл лежит у нас — это разные вещи
                </span>
              </div>
            </Block>
          )}

          {/* Готовность: обе стороны названы, а не только запрет. */}
          <div style={{ ...BOX,
            background: problems.length ? 'var(--warning-bg)' : 'var(--income-tint)',
            borderColor: problems.length ? 'var(--warning-border)' : 'var(--income-border)' }}>
            <div style={{ ...CAPS, marginBottom: problems.length ? 10 : 0,
                          color: problems.length ? 'var(--warning-text)' : 'var(--income-fg)' }}>
              {problems.length ? 'Пока нельзя сохранить' : 'Можно заводить'}
            </div>
            {problems.map((p, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '4px 0', fontSize: 13 }}>
                <i style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--danger)' }} />
                <span>{p.text}</span>
                {!!p.at && <span style={{ ...META, marginLeft: 'auto' }}>{p.at}</span>}
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button onClick={save} disabled={busy || !!problems.length}
                    style={{ ...primaryBtn, height: 38,
                             background: problems.length ? 'var(--accent-soft)' : 'var(--accent)',
                             cursor: problems.length ? 'not-allowed' : 'pointer' }}>
              {busy ? 'Завожу…' : `Завести · ${kindMeta.title.toLowerCase()}`}
            </button>
            <button onClick={() => { setV(EMPTY); setFile(null); setMktTouched(false); setSteps([]); setErr('') }}
                    style={btn(false)}>Очистить форму</button>
          </div>

          {/* Журнал сохранения: связка создаётся пятью запросами, и после сбоя человек
              должен видеть, что уже произошло — иначе нажмёт ещё раз. */}
          {!!steps.length && (
            <div style={{ ...BOX, marginTop: 14 }}>
              <div style={{ ...CAPS, marginBottom: 12 }}>Что сделано</div>
              {steps.map((s, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', fontSize: 13 }}>
                  <span style={{ width: 20, height: 20, borderRadius: 6, display: 'inline-flex',
                                 alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 12,
                                 background: s.ok ? 'var(--income-tint)' : 'var(--danger-tint)',
                                 color: s.ok ? 'var(--income-fg)' : 'var(--danger)' }}>
                    {s.ok ? '✓' : '!'}
                  </span>
                  <span>{s.text}</span>
                  {!!s.link && <a href={s.link} style={{ marginLeft: 'auto', color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>открыть →</a>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Выбор значения — канон проекта, а не свой absolute: список не обрезается
          соседними карточками и закрывается по клику вне себя. */}
      {pop && (
        <ValuePopover anchor={pop.rect} title={pop.title} value={pop.value}
                      clearLabel="— не задано —"
                      options={pop.options.map(o => ({ value: o, label: o }))}
                      onPick={val => { pop.onChange(val || ''); setPop(null) }}
                      onAddNew={name => { pop.onChange(name); setPop(null) }}
                      onClose={() => setPop(null)} />
      )}
    </>
  )
}
