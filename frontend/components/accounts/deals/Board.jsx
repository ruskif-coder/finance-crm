/**
 * Режим «Карточки» «Моих сделок» (экраны 10–11 хендоффа v5): колонка на стадию контура. Шапка колонки — число, сумма,
 * подпись, полоса «ваш ход / всё хорошо / ждём»; шапки липкие. В колонке — «Ваш ход», затем «Ждём», затем «Всё хорошо».
 */
import { STICKY_TOP } from '@/components/accounts/deals/TurnGroups'
import { MONO } from '@/components/salesTableKit'
import { mln } from '@/components/accounts/dashboard/ladder'
import { CONTOURS, good, mine } from '@/components/accounts/deals/contours'
import DealCard from '@/components/accounts/deals/DealCard'

const SUB = {
  'sandbox:prep': 'медиаплан ещё не у клиента', 'sandbox:client': 'клиент смотрит МП', 'sandbox:nudge': 'МП у клиента 14–45 дней',
  'sandbox:stuck': 'МП у клиента дольше 45 дней',
  'work:booking': 'подтвердить за 15 дней до старта', 'work:prep': 'креативы, площадки, ЕРИД, РК',
  'work:live': 'следим за откруткой', 'work:recon': 'сверить и отправить в ДО · норма 3 дня',
}
const PARTS = [['mine', 'ваш ход', 'var(--acc-turn, var(--accent))'], ['good', 'всё хорошо', 'var(--income)'], ['wait', 'ждём', 'var(--border-hover)']]
const partOf = (r) => (mine(r) ? 'mine' : good(r) ? 'good' : 'wait')
const SECTION = { mine: 'Ваш ход', wait: 'Ждём', good: 'Всё хорошо' }

function Head({ st, contour, rows }) {
  const n = { mine: 0, good: 0, wait: 0 }
  rows.forEach(r => { n[partOf(r)] += 1 })
  return (
    <div style={{ position: 'sticky', top: STICKY_TOP, zIndex: 5, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14,
      padding: '10px 14px', boxShadow: 'var(--shadow-card)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <b style={{ fontSize: 14 }}>{st.label}</b>
        <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>{rows.length}</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{mln(rows.reduce((s, r) => s + (r.amount || 0), 0))}</span>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{SUB[`${contour}:${st.key}`] || ''}</div>
      <div style={{ display: 'flex', gap: 2, margin: '7px 0 5px', height: 4 }}>
        {PARTS.filter(([k]) => n[k]).map(([k, , c]) => <span key={k} style={{ flex: n[k], borderRadius: 2, background: c }} />)}
        {!rows.length && <span style={{ flex: 1, borderRadius: 2, background: 'var(--bg-subtle)' }} />}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {PARTS.filter(([k]) => n[k]).map(([k, l, c]) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontFamily: MONO, fontSize: 10.5, color: k === 'mine' ? 'var(--accent-fg)' : k === 'good' ? 'var(--income-fg)' : 'var(--text-muted)' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: c }} />{l} {n[k]}</span>))}
      </div>
    </div>
  )
}

export default function Board({ rows, contour, picked, canEdit, onOpen, onAction, onSnooze }) {
  const c = CONTOURS.find(x => x.key === contour)
  if (!c) return null
  const stages = picked.length ? c.stages.filter(st => picked.includes(st.key)) : c.stages
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${stages.length}, minmax(0,1fr))`, gap: 14, alignItems: 'start' }}>
      {stages.map(st => {
        const list = rows.filter(st.match)
        return (
          <div key={st.key} style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
            <Head st={st} contour={contour} rows={list} />
            {['mine', 'wait', 'good'].map(part => {
              const cards = list.filter(r => partOf(r) === part)
              if (!cards.length) return null
              return (
                <div key={part} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', padding: '0 4px',
                    color: part === 'mine' ? 'var(--accent-fg)' : part === 'good' ? 'var(--income-fg)' : 'var(--text-muted)' }}>{SECTION[part]} · {cards.length}</span>
                  {cards.map(r => <DealCard key={r.id} row={r} canEdit={canEdit} onOpen={onOpen} onAction={onAction} onSnooze={onSnooze} />)}
                </div>
              )
            })}
            {!list.length && <span style={{ fontSize: 12, color: 'var(--text-faint)', padding: '6px 4px' }}>сделок нет</span>}
          </div>
        )
      })}
    </div>
  )
}
