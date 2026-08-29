/**
 * Цепочка обвязки ОРД в карточке сделки.
 *
 * Четыре ступени: плательщик → доходный договор → изначальный договор → креативы.
 * Каждая несёт СОСТОЯНИЕ и ОБОСНОВАНИЕ.
 *
 * Обоснование не украшение. Связи нашего рекламодателя с юрлицом ОРД нет по решению
 * владельца, поэтому подсказка бывает догадкой по названию — а она срабатывает у 24
 * из 91. Человек, подтверждающий подстановку, должен видеть, откуда она взялась.
 *
 * Форма строки — из хендоффа `design_handoff_deal_card_stages`: маркер · лейбл в две
 * строки · значение с подсказкой · действия. Палитра только переменными: хардкод-хексы
 * в проекте запрещены, а нужные оттенки уже заведены.
 */
import Link from 'next/link'
import { useState } from 'react'
import { UI, MONO, card, btnSm } from '../salesTableKit'
import BrandMarkingDialog, { saveBrandMarking } from './BrandMarking'
import { fmtDateFull } from '../../lib/salesFormat'
import api, { auth } from '../../lib/http'
import InitialPicker from './InitialPicker'
import PayerPicker from './PayerPicker'
import FinalPicker from './FinalPicker'

const DOT = { done: 'var(--income)', todo: 'var(--warning)', lock: 'var(--border-hover)' }
const VAL_FG = { done: 'var(--text-primary)', todo: 'var(--warning-text)', lock: 'var(--text-faint)' }
const DOT_TITLE = { done: 'готово', todo: 'ждёт человека', lock: 'ещё не открылась' }

const OpenIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M13 5h6v6" /><path d="M19 5l-8 8" />
    <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </svg>
)

const ICON_BTN = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 28, height: 28, flex: '0 0 28px', background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', color: 'var(--text-secondary)',
  borderRadius: 9, cursor: 'pointer', textDecoration: 'none',
}

/**
 * Заполненность карточки договора в реестре: шкала из пикселей и призыв дозаполнить.
 *
 * Это не проверка на входе, а напоминание: без адреса, ИНН и срока оплаты ЕРИД не
 * выпустить и акт не сдать, но узнаётся это через месяц, на сдаче отчётности.
 */
const FillBadge = ({ fill }) => {
  const [ok, total, missing] = fill
  const full = ok === total
  const c = full ? 'var(--income)' : 'var(--warning)'
  return (
    <span title={full
      ? 'Карточка договора в реестре заполнена полностью'
      : `В реестре не заполнено: ${missing} — без них ЕРИД не выпустить`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
        background: full ? 'var(--income-tint)' : 'var(--warning-tint)',
        color: full ? 'var(--income)' : 'var(--warning-text)',
        border: `1px solid ${full ? 'var(--income-border)' : 'var(--warning-border)'}`,
        borderRadius: 6, padding: '2px 7px', fontFamily: MONO, fontSize: 9,
        fontWeight: 700, whiteSpace: 'nowrap' }}>
      <span style={{ display: 'inline-flex', gap: 1 }}>
        {Array.from({ length: total }, (_, k) => (
          <span key={k} style={{ width: 4, height: 7, borderRadius: 1,
            background: k < ok ? c : 'var(--bg-subtle)' }} />
        ))}
      </span>
      {full ? 'карточка заполнена' : `дозаполнить ${total - ok}`}
    </span>
  )
}

function Row({ o }) {
  const parts = String(o.label).split(' ')
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '14px 108px minmax(0,1fr) auto',
      gap: 12, alignItems: 'baseline', padding: '8px 0',
      borderTop: '1px solid var(--border-row)' }}>
      <span title={DOT_TITLE[o.state]} style={{ width: 8, height: 8, borderRadius: 2,
        background: DOT[o.state], alignSelf: 'center' }} />

      {/* Лейбл в две строки: колонка узкая, а «Изначальный договор» в одну не влезает
          и рвётся по-разному от строки к строке. */}
      <span style={{ display: 'flex', flexDirection: 'column', fontFamily: MONO, fontSize: 9,
        letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)',
        lineHeight: 1.35 }}>
        <span>{parts[0]}</span>
        {parts.length > 1 && <span>{parts.slice(1).join(' ')}</span>}
      </span>

      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: VAL_FG[o.state] }}>
            {o.value}
          </span>
          {!!o.meta && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{o.meta}</span>}
          {!!o.fill && <FillBadge fill={o.fill} />}
        </span>
        {!!o.hint && (
          <span style={{ fontSize: 11, lineHeight: 1.4,
            color: o.state === 'lock' ? 'var(--text-faint)' : 'var(--text-secondary)' }}>
            {o.hint}
          </span>
        )}
        {!!o.more && (
          <button type="button" onClick={o.more.onClick}
            style={{ background: 'none', border: 0, padding: '2px 0 0', fontSize: 11.5,
              color: 'var(--accent)', cursor: 'pointer', fontFamily: UI, textAlign: 'left' }}>
            {o.more.label}
          </button>
        )}
      </span>

      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flex: '0 0 auto' }}>
        {!!o.action && (
          <button type="button" onClick={o.action.onClick} style={btnSm(o.action.primary)}>
            {o.action.label}
          </button>
        )}
        {!!o.href && (
          <Link href={o.href} title={o.openTitle} target="_blank" rel="noreferrer" style={ICON_BTN}>
            <OpenIcon />
          </Link>
        )}
      </span>
    </div>
  )
}

/**
 * Состояния четырёх ступеней. Отдельно от разметки: их же читает шапка секции,
 * а два счётчика, посчитанные каждый по-своему, однажды разойдутся.
 */
export function ordStates(a) {
  if (!a) return ['lock', 'lock', 'lock', 'lock']
  const payer = a.payer.ok ? 'done' : 'todo'
  // «не найден» ≠ «ступень не открылась»: плательщик известен, искать доходный
  // договор можно прямо сейчас. lock остаётся, только пока нет плательщика.
  const final = a.final.ok ? 'done' : (a.payer.ok ? 'todo' : 'lock')
  const initial = a.initial.ok ? 'done' : (a.final.ok ? 'todo' : 'lock')
  // Четвёртая ступень с 27.08.2026 рабочая: она открывается вместе с изначальным
  // договором и закрывается, когда маркирован КАЖДЫЙ креатив сделки.
  const creatives = a.creatives.ok ? 'done' : (a.initial.ok ? 'todo' : 'lock')
  return [payer, final, initial, creatives]
}

/** Полоски и счётчик «N из 4» для шапки секции — видны и когда она свёрнута. */
export function OrdPips({ assembly }) {
  const states = ordStates(assembly)
  const done = states.filter(s => s === 'done').length
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
      <span style={{ display: 'flex', gap: 2 }}>
        {states.map((s, i) => (
          <span key={i} style={{ width: 18, height: 7, borderRadius: 2, background: DOT[s] }} />
        ))}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700,
        color: done === states.length ? 'var(--income)' : 'var(--warning)' }}>
        {done} из {states.length}
      </span>
    </span>
  )
}

/**
 * Состояние приходит СВЕРХУ, а не грузится здесь.
 *
 * Раньше запрос жил внутри этого компонента, а секция карточки ленивая: свёрнутый блок
 * не монтируется, запрос не уходит, и свёрнутый вид показывал «не проверено» до первого
 * разворачивания. То есть ровно то, ради чего свёрнутый вид и делали — увидеть состояние
 * не разворачивая, — не работало. Владелец карточки грузит один раз на открытие страницы
 * и питает и плашки, и полоски в заголовке, и этот развёрнутый вид из одного источника.
 */
export default function AssemblyOrd({ dealId, data, err, canEdit, onReload }) {
  const [picking, setPicking] = useState(false)   // '' | 'payer' | 'final' | 'initial'
  const [bindErr, setBindErr] = useState('')
  const [marking, setMarking] = useState(null)   // бренд, чью маркировку правим
  const done = () => { setPicking(false); if (onReload) onReload() }

  // force — осознанная привязка договора вне связей выгрузки ОРД; подтверждение
  // спрашивает сам выбор, здесь только передаём решение дальше.
  const bind = async (initialContractId, force = false) => {
    setBindErr('')
    try {
      await api.put(`/ord/deal/${dealId}/initial`,
        { initial_contract_id: initialContractId, force }, auth())
      done()
    } catch (e) { setBindErr(e.response?.data?.detail || 'Не удалось привязать договор') }
  }

  const shown = err || bindErr
  if (shown) return <div style={{ ...card, padding: 13, color: 'var(--dot-overdue)' }}>{shown}</div>
  if (!data) return <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>

  const { payer, final, initial } = data
  const brand = data.creatives?.brand
  const chosen = initial.bound || initial.proposal
  // Менять можно и ПОСЛЕ привязки (находка I4): подсказка, приведшая к выбору, бывает
  // догадкой самого экрана, и передумать должно быть можно — «показать все»/«сменить»
  // не исчезают ровно тогда, когда нужны сильнее всего.
  const canPick = final.ok && canEdit
  const [sPayer, sFinal, sInitial, sCreatives] = ordStates(data)

  const rows = [
    {
      label: 'Плательщик',
      state: sPayer,
      value: payer.ok ? (payer.name || 'без названия') : 'не определён',
      hint: payer.reason,
      action: canEdit
        ? { label: payer.ok ? 'сменить' : 'выбрать', primary: !payer.ok,
            onClick: () => setPicking('payer') }
        : null,
      href: payer.counterparty_id ? `/directory/counterparties/${payer.counterparty_id}` : null,
      openTitle: 'Открыть карточку контрагента',
    },
    {
      label: 'Доходный договор',
      state: sFinal,
      value: final.ok ? (final.contract.number || 'без номера') : 'не найден',
      meta: final.ok && final.contract.date ? `от ${fmtDateFull(final.contract.date)}` : '',
      fill: final.fill,
      hint: final.reason,
      // Ступень открыта, как только известен плательщик: договор заводится с ним,
      // и «нет договора» — повод завести его здесь, а не тупик.
      action: (canEdit && payer.ok)
        ? { label: final.ok ? 'сменить' : 'выбрать', primary: !final.ok,
            onClick: () => setPicking('final') }
        : null,
      href: '/directory/contracts',
      openTitle: 'Открыть реестр договоров',
    },
    {
      label: 'Изначальный договор',
      state: sInitial,
      value: chosen ? (chosen.number || 'без номера') : 'не выбран',
      meta: chosen
        ? `${chosen.advertiser?.name || '—'} · через ${chosen.contractor?.name || '—'}`
        : '',
      fill: initial.fill,
      hint: initial.reason,
      action: canPick
        ? (initial.bound
          ? { label: 'сменить', primary: false, onClick: () => setPicking('initial') }
          : { label: initial.proposal ? 'подтвердить' : 'выбрать', primary: true,
            onClick: () => (initial.proposal ? bind(initial.proposal.id) : setPicking('initial')) })
        : null,
      more: canPick && initial.candidates.length
        ? { label: `показать все ${initial.candidates.length}`, onClick: () => setPicking('initial') }
        : null,
      href: '/accounts/ord',
      openTitle: 'Открыть справочник ОРД',
    },
    {
      // Ступень пока не работает, но справочная часть у неё есть уже сейчас: код ККТУ
      // уходит в КАЖДЫЙ креатив этой сделки, и смотреть на него логично там же, где на
      // договорную цепочку. Заполняется он на бренде — отсюда только видно и открыть.
      label: 'Креативы и ЕРИД',
      state: sCreatives,
      // Значение ступени — сколько маркировано: это и есть её предмет. Код ККТУ ушёл
      // в подпись: он условие выпуска, а не результат.
      value: data.creatives.total
        ? (data.creatives.total === 1 && data.creatives.erids[0]
          ? data.creatives.erids[0].erid
          : `${data.creatives.marked} из ${data.creatives.total}`)
        : '—',
      meta: [brand?.kktu_code ? `ККТУ ${brand.kktu_code}` : (brand ? 'ККТУ не заполнен' : ''),
        // Контур маркера виден рядом с ним: демовский снаружи неотличим от боевого,
        // а в размещение годится только настоящий.
        (data.creatives.erids || []).some(e => e.env && e.env !== 'prod') ? 'песочница' : '',
      ].filter(Boolean).join(' · '),
      hint: data.creatives.reason,
      action: (canEdit && brand)
        ? { label: brand.kktu_code ? 'маркировка' : 'заполнить',
            primary: !brand.kktu_code, onClick: () => setMarking(brand) }
        : null,
    },
  ]

  return (
    <div style={{ fontFamily: UI }}>
      {rows.map(o => <Row key={o.label} o={o} />)}
      {picking === 'payer' && (
        <PayerPicker dealId={dealId} chosenId={payer.counterparty_id}
          onDone={done} onClose={() => setPicking(false)} />
      )}
      {picking === 'final' && (
        <FinalPicker dealId={dealId} onDone={done} onClose={() => setPicking(false)} />
      )}
      {picking === 'initial' && (
        <InitialPicker dealId={dealId} onPick={bind}
          onDone={done} onClose={() => setPicking(false)} />
      )}
      {!!marking && (
        <BrandMarkingDialog brand={marking} onClose={() => setMarking(null)}
          onSave={async (payload) => {
            await saveBrandMarking(marking.id, payload)
            setMarking(null)
            if (onReload) onReload()
          }} />
      )}
    </div>
  )
}
