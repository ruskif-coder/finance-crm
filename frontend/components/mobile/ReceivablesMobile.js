import { useState } from 'react'
import { MONO, UI } from '../salesTableKit'
import { grp, mln, fmtDateShort, fmtDateFull } from '../../lib/salesFormat'
import { T } from '../../lib/tokens'
import { monoLbl, Marker, rise } from './kit'
import ReportShell, { ReportSection } from './ReportShell'

// Мобильная дебиторка (< 1024px) по хендоффу design_handoff_receivables_mobile.
// Получает уже вычисленные данные из pages/receivables.js (единый источник логики).
const fmt = (n) => grp(n || 0)
const mlnK = (n) => mln(n || 0, 2)
const formatDate = fmtDateShort
const fullDate = fmtDateFull

// Цвета типов (из хендоффа)
const C = {
  plan: '#5B7CF0', planTxt: T.accent, planTint: T.accentTint,
  cur: T.warning, curTxt: '#C27510', curTint2: T.warningText, curTint: T.warningTint,
  over: '#E5484D', overTxt: T.danger, overTint: '#FBE4E6',
  accent: T.accent,
}
const TYPE = {
  future: { ru: 'план', bar: C.plan, chipBg: C.planTint, chipFg: C.planTxt, amt: 'var(--text-primary)' },
  current: { ru: 'текущая', bar: C.cur, chipBg: C.curTint, chipFg: C.curTint2, amt: C.curTxt },
  overdue: { ru: 'просрочка', bar: C.over, chipBg: C.overTint, chipFg: C.overTxt, amt: C.overTxt },
}
const AXIS = ['−61', '−60', '−30', '+15', '+30', '+60', '60+']

// доминирующее состояние контрагента по максимальной сумме корзины
const domState = (aging) => {
  const e = [['overdue', aging?.overdue || 0], ['current', aging?.current || 0], ['future', aging?.future || 0]]
  e.sort((a, b) => b[1] - a[1])
  return e[0][1] > 0 ? e[0][0] : 'future'
}
const opState = (b) => (b === 'overdue' ? 'overdue' : b === 'current' ? 'current' : 'future')

// KPI-ячейка
function Kpi({ marker, label, val, unit, color, badge, sub }) {
  return (
    <div style={{ padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, ...monoLbl }}>{marker && <Marker c={marker} />}{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, letterSpacing: '-.03em', color, whiteSpace: 'nowrap' }}>{val}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{unit}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 18 }}>
        {badge && <span style={{ fontSize: 11, fontWeight: 700, color: badge.fg, background: badge.bg, borderRadius: 6, padding: '2px 7px' }}>{badge.text}</span>}
        {sub && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{sub}</span>}
      </div>
    </div>
  )
}

// Столбец баров: 14 ячеек
function Bar({ amount, max, color, selected, onClick, axis }) {
  const filled = amount > 0 ? Math.max(1, Math.round(amount / max * 14)) : 0
  return (
    <div onClick={onClick} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, cursor: 'pointer',
      background: selected ? '#F0F3FF' : 'transparent', borderRadius: 6, padding: '3px 2px', transition: 'background .15s' }}>
      <div style={{ display: 'flex', flexDirection: 'column-reverse', gap: 1, height: 112, width: '100%' }}>
        {Array.from({ length: 14 }, (_, i) => (
          <div key={i} style={{ flex: 1, borderRadius: 2, background: i < filled ? color : 'var(--border-inner)' }} />
        ))}
      </div>
      <span style={{ fontFamily: MONO, fontSize: 8, color: 'var(--text-faint)' }}>{axis}</span>
    </div>
  )
}

// Строка контрагента-должника
function DebtorRow({ r, open, onToggle, notes, setNotes, savedNotes, saveNote, canEditNote, noteStatus }) {
  const st = domState(r.aging)
  const t = TYPE[st]
  const key = r.counterparty_id
  return (
    <div style={{ borderBottom: '1px solid var(--border-row)' }}>
      <div onClick={onToggle} style={{ padding: '10px 8px', borderRadius: 10, cursor: 'pointer', background: open ? '#F6F8FF' : 'transparent' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.counterparty}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: t.amt, whiteSpace: 'nowrap' }}>{fmt(r.amount)} ₽</span>
          <span style={{ color: 'var(--text-faint)', fontSize: 10 }}>{open ? '▴' : '▾'}</span>
        </div>
        <div style={{ marginTop: 5, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: t.chipBg, color: t.chipFg, borderRadius: 6, padding: '2px 7px', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>
            <Marker c={t.bar} size={6} />{t.ru}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{r.term_days} дн. · {r.op_count} опер.</span>
        </div>
      </div>
      {open && (
        <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, margin: '6px 0 8px', padding: 10, ...rise(0, '.24s') }}>
          <div style={{ display: 'flex', gap: 14, ...monoLbl, fontSize: 9, marginBottom: 8 }}>
            <span>ИНН {r.inn || '—'}</span><span>отсрочка {r.term_days} дн.</span>
          </div>
          {r.operations.map(op => {
            const t2 = TYPE[opState(op.aging_bucket)]
            return (
              <div key={op.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderTop: '1px solid var(--border-inner)' }}>
                <Marker c={t2.bar} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{op.invoice || op.article || '—'}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{op.period ? `период ${String(op.period).replace(/^(\d{4})-(\d{2})$/, '$2.$1')} · ` : ''}срок {formatDate(op.due_date)}</div>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: t2.amt, whiteSpace: 'nowrap' }}>{fmt(op.amount)} ₽</span>
              </div>
            )
          })}
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--border-inner)' }}>
            <div style={{ ...monoLbl, fontSize: 9, marginBottom: 5 }}>Коммент</div>
            {canEditNote ? (
              <textarea value={notes[key] ?? ''} onChange={e => setNotes(prev => ({ ...prev, [key]: e.target.value }))}
                onBlur={e => { const v = e.target.value; if (v !== (savedNotes[key] ?? '')) saveNote(key, v) }}
                placeholder="комментарий менеджера…"
                style={{ width: '100%', boxSizing: 'border-box', minHeight: 44, resize: 'vertical', border: '1px solid var(--border-card)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontFamily: UI, color: 'var(--text-secondary)', background: 'var(--bg-card)', outline: 'none', lineHeight: 1.4 }} />
            ) : (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', textWrap: 'pretty' }}>{r.note || '—'}</div>
            )}
            {noteStatus[key] === 'saving' && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>сохранение…</span>}
            {noteStatus[key] === 'saved' && <span style={{ fontSize: 11, color: 'var(--income)' }}>✓ сохранено</span>}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ReceivablesMobile({
  asOf, onlyActual, setOnlyActual, downloadExport,
  kpi, buckets, ageMax, structure, structCells, structTotal,
  rows, totalFiltered, rowsCount, expanded, toggleExpand,
  notes, setNotes, savedNotes, saveNote, canEditNote, noteStatus,
}) {
  const [selBucket, setSelBucket] = useState(null)
  const sel = selBucket != null ? buckets[selBucket] : null
  const pct = (a) => (structTotal > 0 ? Math.round(a / structTotal * 100) : 0)

  const seg = (active) => ({ flex: 1, border: 'none', borderRadius: 8, padding: '7px 0', fontFamily: UI, fontSize: 13, fontWeight: active ? 700 : 600, cursor: 'pointer', background: active ? 'var(--accent-tint)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-secondary)' })

  const filters = (
    <>
      <div style={{ display: 'inline-flex', flex: '0 0 auto', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, background: 'var(--bg-card)', width: 200 }}>
        <button onClick={() => setOnlyActual(true)} style={seg(onlyActual)}>Актуальные</button>
        <button onClick={() => setOnlyActual(false)} style={seg(!onlyActual)}>Все</button>
      </div>
      <button onClick={downloadExport} aria-label="Выгрузить в Excel" style={{ marginLeft: 'auto', width: 38, height: 38, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>
      </button>
    </>
  )

  return (
    <ReportShell title="Дебиторка" meta={`на ${fullDate(asOf)}`} filters={filters}>
      {/* KPI 2×2 */}
      <ReportSection padded={false}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ borderRight: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label="Итого дебиторка" val={mlnK(kpi.total)} unit="млн ₽" color="var(--text-primary)" sub={`${kpi.cpCount} контрагентов · ${kpi.opCount} счетов`} />
          </div>
          <div style={{ borderBottom: '1px solid var(--border-row)' }}>
            <Kpi marker={C.over} label="Просрочено" val={mlnK(kpi.overdue.a)} unit="млн ₽" color={C.overTxt} badge={{ text: `${kpi.pctOf(kpi.overdue.a)}% · ${kpi.overdue.c} опер.`, bg: C.overTint, fg: C.overTxt }} />
          </div>
          <div style={{ borderRight: '1px solid var(--border-row)' }}>
            <Kpi marker={C.cur} label="Текущая" val={mlnK(kpi.current.a)} unit="млн ₽" color={C.curTxt} sub={`${kpi.pctOf(kpi.current.a)}% · ${kpi.current.c} операций`} />
          </div>
          <div>
            <Kpi marker={C.plan} label="План" val={mlnK(kpi.future.a)} unit="млн ₽" color={C.accent} sub={`${kpi.pctOf(kpi.future.a)}% · ${kpi.future.c} операции`} />
          </div>
        </div>
      </ReportSection>

      {/* Структура по срокам */}
      <ReportSection title="Структура по срокам" aside={<span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>дни от срока</span>}>
        {/* сводка */}
        <div style={{ background: '#F6F8FF', borderRadius: 12, padding: '10px 12px', minHeight: 44, display: 'flex', alignItems: 'center', gap: 10 }}>
          {sel ? (<>
            <Marker c={TYPE[sel.type].bar} />
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{sel.label}</span>
            <span style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <div style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(sel.amount)} ₽</div>
              <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{TYPE[sel.type].ru} · {sel.count} операций</div>
            </span>
          </>) : (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-muted)' }}><Marker c="var(--border-inner)" />нажмите на столбец</span>
          )}
        </div>
        {/* бары */}
        <div style={{ display: 'flex', gap: 5 }}>
          {buckets.map((b, i) => (
            <Bar key={b.key} amount={b.amount} max={ageMax} color={TYPE[b.type].bar} axis={AXIS[i]} selected={selBucket === i} onClick={() => setSelBucket(selBucket === i ? null : i)} />
          ))}
        </div>
        {/* полоска долей */}
        <div style={{ display: 'flex', gap: 1, height: 8 }}>
          {structCells.map((c, i) => <div key={i} style={{ flex: 1, borderRadius: 2, background: c }} />)}
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-muted)' }}>
          {structure.map(s => (
            <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Marker c={s.color} />{s.label.toLowerCase()} {pct(s.a)}%</span>
          ))}
        </div>
      </ReportSection>

      {/* Контрагенты-должники */}
      <ReportSection title="Контрагенты-должники" padding="14px 14px 8px" gap={6} aside={<span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{rows.length} из {rowsCount}</span>}>
        <div>
          {rows.length === 0 && <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Нет задолженности по фильтрам</div>}
          {rows.map(r => (
            <DebtorRow key={r.counterparty_id} r={r} open={!!expanded[r.counterparty_id]} onToggle={() => toggleExpand(r.counterparty_id)}
              notes={notes} setNotes={setNotes} savedNotes={savedNotes} saveNote={saveNote} canEditNote={canEditNote} noteStatus={noteStatus} />
          ))}
          {rows.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 12, marginTop: 4, borderTop: '1px solid var(--border-inner)' }}>
              <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого</span>
              <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{fmt(totalFiltered)} ₽</span>
            </div>
          )}
        </div>
      </ReportSection>
    </ReportShell>
  )
}
