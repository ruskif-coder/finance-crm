import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { grp0 as fmt, mln } from '../../lib/salesFormat'
import { T } from '../../lib/tokens'
import { monoLbl, Marker, rise } from './kit'
import ReportShell, { ReportSection } from './ReportShell'

// Мобильный баланс (< 1024px). Раньше страница несла собственные сеточные
// media-правила (repeat(auto-fit, minmax(...))) — они авто-адаптировались по
// ширине, но давали другой ритм/отступы, чем у остальных отчётов. Теперь вид
// собран на общем каркасе ReportShell/ReportSection, тот же класс данных и
// расчёт (full/receivables/payables), что и на десктопе, приходят готовыми
// из pages/finance/balance.js — компонент только сводит к списку и рисует.
const mlnK = (n) => mln(n || 0, 2)

const AGING_META = {
  overdue: { label: 'Просрочка', color: T.danger },
  current: { label: 'Текущая',   color: T.warningText },
  future:  { label: 'План',      color: T.accent },
  unknown: { label: 'Без периода', color: 'var(--text-faint)' },
}
const BUCKET_ORDER = ['overdue', 'current', 'future', 'unknown']

const MONTH_SHORT = { '01':'янв','02':'фев','03':'мар','04':'апр','05':'май','06':'июн','07':'июл','08':'авг','09':'сен','10':'окт','11':'ноя','12':'дек' }
const formatPeriod = (p) => { if (!p) return '—'; const [y, m] = String(p).split('-'); return m ? `${MONTH_SHORT[m] || m} ${y}` : p }
const formatDate = (d) => { if (!d) return '—'; const [y, m, day] = String(d).split('-'); return day ? `${day}.${m}.${y}` : d }

const BANK_STYLES = {
  'АльфаБанк':  'var(--bank-alfa)',
  'ОПТ Банк':   'var(--bank-opt)',
  'Совкомбанк': 'var(--bank-sovkom)',
  'Наличные':   'var(--bank-cash)',
}

function Kpi({ label, val, unit, color }) {
  return (
    <div style={{ padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={monoLbl}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, letterSpacing: '-.03em', color, whiteSpace: 'nowrap' }}>{val}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)' }}>{unit}</span>
      </div>
    </div>
  )
}

function AgingBadges({ aging }) {
  const entries = BUCKET_ORDER.filter(b => aging[b] > 0)
  if (entries.length === 0) return null
  return (
    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 4 }}>
      {entries.map(b => (
        <span key={b} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 6, background: 'var(--bg-card)', color: 'var(--text-secondary)' }}>
          <Marker c={AGING_META[b].color} size={6} />{fmt(aging[b])}
        </span>
      ))}
    </div>
  )
}

// Строка контрагента (дебиторка) или статьи (кредиторка) со сворачиванием в операции.
// notes/canEditNote переданы только для дебиторки — на десктопе примечание тоже
// доступно лишь там (DebtPanel mode='receivables').
function DebtRow({ r, isReceivables, open, onToggle, notes, setNotes, savedNotes, saveNote, canEditNote, noteStatus }) {
  const key = isReceivables ? r.counterparty_id : r.article_id
  const title = isReceivables ? r.counterparty : r.article
  const amountColor = isReceivables ? 'var(--income)' : 'var(--expense)'
  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div onClick={onToggle} style={{ padding: '10px 8px', borderRadius: 10, cursor: 'pointer', background: open ? '#F6F8FF' : 'transparent' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: amountColor, whiteSpace: 'nowrap' }}>{fmt(r.amount)} ₽</span>
          <span style={{ color: 'var(--text-faint)', fontSize: 10 }}>{open ? '▴' : '▾'}</span>
        </div>
        <div style={{ marginTop: 3, fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>
          {isReceivables && r.term_days ? `${r.term_days} дн. · ` : ''}{r.op_count} опер.
        </div>
        <AgingBadges aging={r.aging} />
      </div>
      {open && (
        <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '6px 0 8px', padding: 10, ...rise(0, '.24s') }}>
          {isReceivables && (
            <div style={{ display: 'flex', gap: 14, ...monoLbl, fontSize: 9, marginBottom: 8 }}>
              <span>ИНН {r.inn || '—'}</span>
              {!!r.term_days && <span>отсрочка {r.term_days} дн.</span>}
            </div>
          )}
          {r.operations.map(op => {
            const meta = AGING_META[op.aging_bucket] || AGING_META.unknown
            const secondary = isReceivables ? op.article : op.counterparty
            return (
              <div key={op.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderTop: '1px solid var(--border-inner)' }}>
                <Marker c={meta.color} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{secondary || op.invoice || '—'}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{op.period ? `${formatPeriod(op.period)} · ` : ''}срок {formatDate(op.due_date)}</div>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: amountColor, whiteSpace: 'nowrap' }}>{fmt(op.amount)} ₽</span>
              </div>
            )
          })}
          {isReceivables && (
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--border-inner)' }}>
              <div style={{ ...monoLbl, fontSize: 9, marginBottom: 5 }}>Коммент</div>
              {canEditNote ? (
                <textarea value={notes[key] ?? ''} onChange={e => setNotes(prev => ({ ...prev, [key]: e.target.value }))}
                  onBlur={e => { const v = e.target.value; if (v !== (savedNotes[key] ?? '')) saveNote(key, v) }}
                  placeholder="комментарий менеджера…"
                  style={{ width: '100%', boxSizing: 'border-box', minHeight: 44, resize: 'vertical', border: '1px solid var(--border-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontFamily: UI, color: 'var(--text-secondary)', background: 'var(--bg-card)', outline: 'none', lineHeight: 1.4 }} />
              ) : (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.note || '—'}</div>
              )}
              {noteStatus[key] === 'saving' && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>сохранение…</span>}
              {noteStatus[key] === 'saved' && <span style={{ fontSize: 11, color: 'var(--income)' }}>✓ сохранено</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DebtSection({ title, dataset, isReceivables, expandedRows, toggleRow, notes, setNotes, savedNotes, saveNote, canEditNote, noteStatus }) {
  const total = dataset.summary.total_amount
  const count = isReceivables ? dataset.summary.counterparty_count : dataset.summary.article_count
  // Десктоп по умолчанию (overdueOnly=true) исключает из построчных сумм операции
  // с aging_bucket 'future' и 'unknown' — совпадает с DebtPanel.filteredRows в
  // pages/finance/balance.js. Общий итог секции (total) при этом берётся из
  // dataset.summary.total_amount как есть, не пересчитывается.
  const filteredRows = dataset.rows.map(r => {
    const ops = r.operations.filter(o => o.aging_bucket === 'overdue' || o.aging_bucket === 'current')
    if (ops.length === 0) return null
    const amount = ops.reduce((s, o) => s + o.amount, 0)
    const aging = { overdue: 0, current: 0, future: 0, unknown: 0 }
    ops.forEach(o => { aging[o.aging_bucket] += o.amount })
    return { ...r, operations: ops, amount, op_count: ops.length, aging }
  }).filter(Boolean)
  // Сортировка только для отображения (по убыванию суммы) — суммы не пересчитываются,
  // берутся как есть из отфильтрованных данных.
  const rows = [...filteredRows].sort((a, b) => b.amount - a.amount)
  return (
    <ReportSection title={title} padding="14px 14px 8px" gap={6}
      aside={<span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: isReceivables ? 'var(--income)' : 'var(--expense)' }}>{fmt(total)} ₽</span>}>
      <div>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 4 }}>{count} {isReceivables ? 'контрагентов' : 'статей'}</div>
        {rows.length === 0 && <div style={{ padding: 20, textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Нет данных</div>}
        {rows.map(r => (
          <DebtRow key={isReceivables ? r.counterparty_id : r.article_id} r={r} isReceivables={isReceivables}
            open={!!expandedRows[isReceivables ? r.counterparty_id : r.article_id]}
            onToggle={() => toggleRow(isReceivables ? r.counterparty_id : r.article_id)}
            notes={notes} setNotes={setNotes} savedNotes={savedNotes} saveNote={saveNote} canEditNote={canEditNote} noteStatus={noteStatus} />
        ))}
      </div>
    </ReportSection>
  )
}

export default function BalanceMobile({
  data, receivablesData, payablesData,
  notes, setNotes, savedNotes, saveNote, canEditNote, noteStatus,
}) {
  const [expandedReceivables, setExpandedReceivables] = useState({})
  const [expandedPayables, setExpandedPayables] = useState({})

  return (
    <ReportShell title="Баланс">
      {/* Активы / обязательства / чистые активы */}
      <ReportSection padded={false}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr' }}>
          <div style={{ borderRight: '1px solid var(--border-row)' }}>
            <Kpi label="Активы" val={mlnK(data.total_assets)} unit="млн ₽" color="var(--income)" />
          </div>
          <div style={{ borderRight: '1px solid var(--border-row)' }}>
            <Kpi label="Обязательства" val={mlnK(data.total_payables)} unit="млн ₽" color="var(--expense)" />
          </div>
          <div>
            <Kpi label="Чистые активы" val={mlnK(data.net_assets)} unit="млн ₽" color={data.net_assets >= 0 ? 'var(--income)' : 'var(--expense)'} />
          </div>
        </div>
      </ReportSection>

      {/* Денежные средства по банкам */}
      <ReportSection title="Денежные средства" padding="14px 14px 10px" gap={4}
        aside={<span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--income)' }}>{fmt(data.total_cash)} ₽</span>}>
        <div>
          {data.banks.map(b => (
            <div key={b.bank} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
              <Marker c={BANK_STYLES[b.bank] || 'var(--text-secondary)'} size={8} />
              <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.bank}</span>
              <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: b.balance >= 0 ? 'var(--income)' : 'var(--expense)' }}>{fmt(b.balance)} ₽</span>
            </div>
          ))}
          {data.banks.length === 0 && <div style={{ padding: 16, textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Нет счетов</div>}
        </div>
      </ReportSection>

      {/* Дебиторская задолженность */}
      <DebtSection title="Дебиторская задолженность" dataset={receivablesData} isReceivables
        expandedRows={expandedReceivables} toggleRow={(k) => setExpandedReceivables(prev => ({ ...prev, [k]: !prev[k] }))}
        notes={notes} setNotes={setNotes} savedNotes={savedNotes} saveNote={saveNote} canEditNote={canEditNote} noteStatus={noteStatus} />

      {/* Кредиторская задолженность */}
      <DebtSection title="Кредиторская задолженность" dataset={payablesData} isReceivables={false}
        expandedRows={expandedPayables} toggleRow={(k) => setExpandedPayables(prev => ({ ...prev, [k]: !prev[k] }))} />
    </ReportShell>
  )
}
