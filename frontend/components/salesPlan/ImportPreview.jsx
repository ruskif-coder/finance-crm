// Загрузка целей «Плана продаж» из Excel (владелец 24.10.2026): сервер читает файл и возвращает «было → станет» и
// ошибки строк, ничего не записывая. «Применить» сохраняет через тот же PUT /sales-plan/targets — с журналом каждой правки.
import { Modal, MONO } from '@/components/salesTableKit'
import { MONTHS, fmtK } from '@/lib/salesPlan.mjs'

const ghost = { height: 36, padding: '0 16px', borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)',
  fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }

export default function ImportPreview({ data, busy, onApply, onClose }) {
  const { changes, errors, year } = data
  const off = busy || !changes.length
  return (
    <Modal width={720} onClose={() => { if (!busy) onClose() }}
      title={<span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>Загрузка целей из Excel</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400 }}>{year} · изменится целей: {changes.length}
          {errors.length ? ` · строк с ошибками: ${errors.length}` : ''}</span></span>}
      footer={<div style={{ display: 'flex', gap: 9, width: '100%', alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>пустые ячейки файла не меняют цель</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 9 }}>
          <button type="button" style={ghost} onClick={onClose} disabled={busy}>Отмена</button>
          <button type="button" onClick={onApply} disabled={off} style={{ ...ghost, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)',
            fontWeight: 700, opacity: off ? 0.5 : 1, cursor: off ? 'default' : 'pointer' }}>{busy ? 'Сохраняю…' : `Применить (${changes.length})`}</button>
        </span>
      </div>}>
      {!!errors.length && (
        <div style={{ background: 'var(--warning-tint)', color: 'var(--warning-fg)', borderRadius: 10, padding: '10px 12px', fontSize: 12.5, marginBottom: 12 }}>
          Эти строки пропущены:{errors.map((e, i) => <div key={i}>· {e}</div>)}
        </div>
      )}
      {!changes.length && <div style={{ padding: 16, color: 'var(--text-secondary)', fontSize: 13 }}>Цели в файле совпадают с сохранёнными — менять нечего.</div>}
      {!!changes.length && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px 120px 120px', gap: 8, padding: '6px 4px', fontFamily: MONO, fontSize: 9.5,
            letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
            <span>строка</span><span>месяц</span><span style={{ textAlign: 'right' }}>было</span><span style={{ textAlign: 'right' }}>станет</span></div>
          {changes.map((c, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 90px 120px 120px', gap: 8, padding: '6px 4px', fontSize: 12.5,
              borderTop: '1px solid var(--border-inner)' }}>
              <span>{c.name}<small style={{ color: 'var(--text-muted)', marginLeft: 6 }}>{c.scope}</small></span>
              <span>{MONTHS[c.month - 1]}</span>
              <span style={{ fontFamily: MONO, textAlign: 'right', color: 'var(--text-muted)' }}>{fmtK(c.was)}</span>
              <span style={{ fontFamily: MONO, textAlign: 'right', fontWeight: 700 }}>{fmtK(c.now)}</span>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
