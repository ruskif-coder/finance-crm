/**
 * Карточка сделки в режиме «Карточки» «Моих сделок» (экран 10 хендоффа v5): код, услуга, сумма; бренд, рекламодатель ·
 * агентство, период; блок стадии (заголовок, срочность, мини-виджет из фактов строки, у «Сборки» — четыре плашки); команда;
 * кнопка и «Отложить».
 * Данные — строка очереди (`/sales/account-queue`), те же, что в списке; щелчок по карточке открывает модалку.
 */
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO } from '@/components/salesTableKit'
import { CopyIcon } from '@/components/CopyCode'
import { dm } from '@/lib/salesFormat'
import { periodEnd } from '@/lib/dates'
import { mln } from '@/components/accounts/dashboard/ladder'
import { CAP, ini } from '@/components/accounts/deals/nowWidgets'

// Тон плашки «Сборки» — как у `FactChip` карточки сделки: готово / нужно действие / не требуется или рано.
const CHIP = { ok: ['var(--income-tint)', 'var(--income-border)', 'var(--income)'], warn: ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-text)'],
  off: ['var(--bg-card)', 'var(--border-card)', 'var(--text-muted)'] }

/** «Сборка» на карточке — те же четыре плашки, что в расхлопе (ОРД · креативы · пиксель · ДС), с той же ручки «Сейчас». */
function AssemblyChips({ code }) {
  const [chips, setChips] = useState(null)
  useEffect(() => {
    let alive = true
    api.get(`/sales/account-deals/${code}/now`, auth()).then(r => alive && setChips(r.data.chips || [])).catch(() => alive && setChips([]))
    return () => { alive = false }
  }, [code])
  if (!chips) return <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>Загрузка…</span>
  if (!chips.length) return null
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 6 }}>
      {chips.map(c => {
        const t = CHIP[c.tone] || CHIP.off
        return (
          <span key={c.key} title={`${c.label}: ${c.value}`} style={{ minWidth: 0, padding: '5px 8px', borderRadius: 8, background: t[0], border: `1px solid ${t[1]}` }}>
            <span style={{ display: 'block', ...CAP, fontSize: 8.5 }}>{c.label}</span>
            <span style={{ display: 'block', fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: t[2], whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.value}</span>
          </span>)
      })}
    </div>
  )
}

const URG = { overdue: ['горит', 'var(--danger-fg)', 'var(--danger)'], today: ['сегодня', 'var(--warning-text)', 'var(--warning)'] }

function headOf(r) {
  if (r.reason) return r.reason
  return r.turn?.mine ? 'ваш ход' : `ждём: ${r.turn?.who || r.action_note || '—'}`
}

function Mini({ state }) {
  const prog = state.find(e => e.type === 'progress')
  const boxes = state.filter(e => e.type === 'fact' || e.type === 'alert' || e.type === 'check').slice(0, 4)
  if (prog) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ height: 6, borderRadius: 3, background: 'var(--bg-card)', border: '1px solid var(--border-card)', overflow: 'hidden' }}>
          <span style={{ display: 'block', height: '100%', width: `${Math.min(100, prog.x / (prog.y || 100) * 100)}%`, background: 'var(--warning)' }} /></span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>{prog.k} {prog.x}{prog.unit ? ` ${prog.unit}` : ` / ${prog.y}`}</span>
      </div>
    )
  }
  if (!boxes.length) return null
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(4, boxes.length)}, minmax(0,1fr))`, gap: 6 }}>
      {boxes.map((e, i) => {
        const label = e.type === 'check' ? e.v : (e.k || (e.type === 'alert' ? 'внимание' : ''))
        const value = e.type === 'check' ? (e.ok ? 'готово' : 'нет') : (e.k ? e.v : e.v || e.text)
        const fg = e.type === 'alert' || (e.type === 'check' && !e.ok) ? 'var(--warning-text)' : e.type === 'check' ? 'var(--income-fg)' : 'var(--text-primary)'
        return (
          <span key={i} style={{ minWidth: 0, padding: '5px 8px', borderRadius: 8, border: '1px dashed var(--border-card)', background: 'var(--bg-card)' }}>
            <span style={{ display: 'block', ...CAP, fontSize: 8.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
            <span style={{ display: 'block', fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={value}>{value || '—'}</span>
          </span>)
      })}
    </div>
  )
}

export default function DealCard({ row: r, canEdit, onOpen, onAction, onSnooze }) {
  const urg = URG[r.urgency]
  const a = r.action
  const team = [['сейлз', r.sales_rep], ['трафик', r.traffic_manager]]
  return (
    <div onClick={() => onOpen(r)} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14, padding: '12px 12px 10px',
      display: 'flex', flexDirection: 'column', gap: 8, cursor: 'pointer', boxShadow: 'var(--shadow-card)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }} onClick={e => e.stopPropagation()}>
          <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)' }}>{r.code}</span>
          <CopyIcon text={r.code} size={12} title="Скопировать код сделки" />
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 7px', borderRadius: 7, border: '1px solid var(--border-card)', fontSize: 11.5, fontWeight: 600, minWidth: 0 }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: r.product_color || 'var(--accent)' }} />
          <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.product || '—'}</span>
          {!!r.inventory && <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>{r.inventory}</span>}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>{mln(r.amount)}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
        <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
          <b style={{ fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.brand || r.title || '—'}</b>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {[r.advertiser, r.agency].filter(Boolean).join(' · ') || '—'}</span>
        </span>
        {/* Период РК — как в колонке «Период» списка: месяц, под ним даты (владелец 14.11.2026) */}
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', fontFamily: MONO, whiteSpace: 'nowrap' }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: r.period_from ? 'var(--text-primary)' : 'var(--text-faint)' }}>{r.period_from ? r.period_from.slice(0, 7) : '—'}</span>
          {!!r.period_from && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{dm(r.period_from)}–{dm(periodEnd(r.period_from, r.period_to))}</span>}
        </span>
      </div>
      <div style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 10, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 12.5, fontWeight: 700, flex: 1, minWidth: 0 }}>{headOf(r)}</span>
          {!!urg && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontFamily: MONO, fontSize: 10, fontWeight: 700, color: urg[1], whiteSpace: 'nowrap' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: urg[2] }} />{urg[0]}</span>}
        </div>
        {r.slot === 'prep' ? <AssemblyChips code={r.code || r.id} /> : <Mini state={r.state || []} />}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {team.map(([role, name]) => (
          <span key={role} style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            <span style={{ fontFamily: MONO, width: 22, height: 22, flex: '0 0 22px', borderRadius: 6, background: 'var(--bg-subtle)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700, color: 'var(--text-muted)' }}>{ini(name)}</span>
            <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}><span style={{ ...CAP, fontSize: 8 }}>{role}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: name ? 'var(--text-primary)' : 'var(--text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name || 'не назначен'}</span></span>
          </span>))}
      </div>
      <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
        {a ? <button type="button" onClick={() => onAction(r, a)} disabled={!canEdit && a.do !== 'link' && a.do !== 'expand'}
          style={{ flex: 1, height: 32, borderRadius: 9, border: 0, background: 'var(--accent)', color: 'var(--on-accent)', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>{a.label}</button>
          : <span style={{ flex: 1, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: 'var(--text-faint)' }}>{r.action_note || 'действий нет'}</span>}
        <button type="button" onClick={() => onSnooze(r)} title="Отложить" aria-label="Отложить"
          style={{ width: 32, height: 32, borderRadius: 9, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer' }}>⏱</button>
      </div>
    </div>
  )
}
