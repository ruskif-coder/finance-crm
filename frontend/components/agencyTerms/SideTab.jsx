// Вкладки «Агентства» и «Рекламодатели» по хендоффу 27.10.2026: KPI, поиск и чипы, плоская таблица «договор × правило».
// Договор без правила — строкой «условие не задано» сверху; клик по строке — окно правила. Дерево отдаёт сервер
// (`/agency-terms/tree`), строки собирает `lib/agencyTerms.mjs`.
import { useMemo, useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { FEATURES, SIDE_FILTERS, filterSide, flattenSide, precisionCells, sideKpi } from '@/lib/agencyTerms.mjs'
import { fmtDate, todayMsk } from '@/lib/dates'
import { CAPS, Card, FilterChip, fmtPct, KpiStrip, ModePill, modeTone, Scroll, Title } from './kit'

const COLS = 'minmax(130px,1fr) minmax(150px,1.1fr) minmax(170px,1.2fr) 140px 70px minmax(150px,1.2fr) 190px 64px 112px'
const DOT = { all: 'var(--text-disabled)', empty: 'var(--warning)', 'постоплата': modeTone('постоплата')[2], 'скидка в счёт': modeTone('скидка в счёт')[2] }

function Tags({ rule, names, skip }) {
  const tags = FEATURES.filter(([k]) => rule[k] != null && !skip.includes(k)).map(([k, label]) => `${label} ${(names[k] || {})[rule[k]] || `№${rule[k]}`}`)
  if (!tags.length) return <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>на весь договор</span>
  return (
    <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap', minWidth: 0 }}>
      {tags.map((t) => <span key={t} style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 7px', background: 'var(--bg-subtle)',
        border: '1px solid var(--border-inner)', borderRadius: 6, fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{t}</span>)}
    </span>
  )
}

function Row({ r, side, names, canEdit, onOpen, defaults }) {
  const sideKey = side === 'agency' ? 'agency_id' : 'advertiser_id'
  const rule = r.rule
  const empty = !rule
  const open = () => onOpen(rule || (canEdit ? { kind: 'основная', contract_id: r.contractId, [sideKey]: r.ownerId, ...defaults(r.entity) } : null))
  const precTitle = rule ? FEATURES.filter(([k]) => rule[k] != null).map(([, l]) => l).join(', ') : ''
  return (
    <div onClick={open} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', padding: '8px 10px', borderRadius: 9,
      borderTop: `1px solid ${r.first ? 'var(--border-row)' : 'transparent'}`, cursor: rule || canEdit ? 'pointer' : 'default',
      background: empty ? 'var(--warning-bg)' : 'transparent' }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        {r.first && <>
          <span style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.owner}</span>
          <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{r.ownerSub}</span></>}
      </span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.entity}</span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{names.contract_id?.[r.contractId] || '—'}</span>
      {empty ? (
        <span style={{ gridColumn: 'span 5', display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--warning-fg)' }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--warning)' }} />условие не задано — СК по сделкам этого договора не посчитается</span>
      ) : <>
        <ModePill mode={rule.mode} off={!!r.inactive} />
        <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, textAlign: 'right', color: r.inactive ? 'var(--text-muted)' : 'var(--text-primary)' }}>{fmtPct(rule.percent)}</span>
        <Tags rule={rule} names={names} skip={['contract_id', sideKey]} />
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <span style={{ fontFamily: MONO, fontSize: 11, color: r.inactive ? 'var(--text-muted)' : 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
            {rule.valid_to ? `с ${fmtDate(rule.valid_from)} по ${fmtDate(rule.valid_to)}` : `с ${fmtDate(rule.valid_from)} · бессрочно`}</span>
          {!!r.inactive && <span style={{ ...CAPS, color: 'var(--text-faint)' }}>{r.inactive}</span>}
        </span>
        <span title={precTitle} style={{ display: 'inline-flex', gap: 2 }}>
          {precisionCells(rule).map((on, i) => <span key={i} style={{ width: 9, height: 9, borderRadius: 2, background: on ? 'var(--accent)' : 'var(--border-inner)' }} />)}
        </span>
      </>}
      <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {empty ? (canEdit && <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 104, height: 28, boxSizing: 'border-box',
          border: '1px dashed var(--accent-border)', borderRadius: 8, color: 'var(--accent)', fontSize: 12, fontWeight: 700 }}>+ условие</span>)
          : <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{canEdit ? 'править' : 'смотреть'} →</span>}
      </span>
    </div>
  )
}

export default function SideTab({ items, side, names, canEdit, onOpen, mode, setMode }) {
  const [q, setQ] = useState('')
  const rows = useMemo(() => flattenSide(items, todayMsk()), [items])
  const k = useMemo(() => sideKpi(items, rows), [items, rows])
  const shown = useMemo(() => filterSide(rows, { q, mode, contractName: (id) => names.contract_id?.[id] }), [rows, q, mode, names])
  const count = (m) => (m === 'all' ? rows.length : filterSide(rows, { mode: m }).length)
  // Новое условие — как у других договоров того же юрлица, иначе 30 % постоплата (владелец 27.10.2026)
  const defaults = (entity) => {
    const same = rows.find((x) => x.rule && !x.inactive && x.entity === entity)
    return same ? { mode: same.rule.mode, percent: same.rule.percent } : { mode: 'постоплата', percent: 30 }
  }
  const who = side === 'agency' ? 'Агентств' : 'Рекламодателей'
  return (
    <>
      <KpiStrip items={[
        [who, k.owners, 'var(--text-primary)', `юрлиц ${k.entities} · договоров ${k.contracts}`],
        ['Без условия', k.noRule, k.noRule ? 'var(--warning-fg)' : 'var(--text-primary)', 'договоров — СК по их сделкам не посчитается', () => setMode('empty')],
        ['Действующих правил', k.active, 'var(--accent-fg)', `постоплата ${k.post} · скидка ${k.disc}`],
        ['Не действуют', k.inactive, 'var(--text-muted)', 'срок вышел или ещё не начался', () => setMode('inactive')],
      ]} />
      <Card title={<Title>Основная СК · по договорам</Title>} note={`строка — договор × правило · показано ${shown.length} · без условия — сверху`}
        right={<span style={{ flex: '1 1 100%', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`${side === 'agency' ? 'агентство' : 'рекламодатель'}, юрлицо, договор`}
            style={{ width: 240, height: 32, boxSizing: 'border-box', padding: '0 11px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
              borderRadius: 10, fontSize: 12.5, outline: 'none', fontFamily: 'inherit', color: 'var(--text-primary)' }} />
          {SIDE_FILTERS.map(([m, label]) => <FilterChip key={m} on={mode === m} label={label} dot={DOT[m]} count={count(m)} onClick={() => setMode(m)} />)}
          {mode === 'inactive' && <FilterChip on label="не действуют" dot="var(--text-disabled)" count={count('inactive')} onClick={() => setMode('all')} />}
        </span>}>
        <Scroll min={1320}>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, padding: '0 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS }}>
            <span>{side === 'agency' ? 'Агентство' : 'Рекламодатель'}</span><span>Юрлицо</span><span>Договор</span><span>Способ</span>
            <span style={{ textAlign: 'right' }}>СК</span><span>Уточнение</span><span>Действует</span><span>Точность</span><span />
          </div>
          {shown.map((r) => <Row key={r.key} r={r} side={side} names={names} canEdit={canEdit} onOpen={onOpen} defaults={defaults} />)}
        </Scroll>
        {!shown.length && <span style={{ padding: '26px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Под фильтр ничего не попало</span>}
      </Card>
    </>
  )
}

