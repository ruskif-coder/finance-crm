// Окно «Обновить данные в DSP» (владелец 02.10.2026). Приводит уже заведённую РК к
// текущим данным системы: ссылки, пиксели, таргеты; копии нацеливания — только ЕРИД.
// Сначала сервер читает состояние ИЗ DSP и показывает «было → станет»
// (`/campaign/{id}/dsp-refresh`), потом пишет по одному пункту — полоса хода настоящая,
// а не анимация по таймеру. Итог и отказы DSP — словами; действие уходит в журнал.
import { useEffect, useState } from 'react'
import { Modal, btnSm, primaryBtn, MONO, th, td } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import api from '@/lib/api'

const KIND = { creative: 'креатив', targeting: 'таргетинг', erid: 'ЕРИД копии' }
const FIELD = { link: 'ссылка', adomain: 'конечный URL', pixel: 'пиксель WR', erid: 'ЕРИД' }

export default function DspRefreshModal({ row, auth, onClose, onDone }) {
  const [plan, setPlan] = useState(null)
  const [err, setErr] = useState('')
  const [run, setRun] = useState(null)      // { done, total, current }
  const [res, setRes] = useState(null)      // { ok: [...], failed: [...] }

  useEffect(() => {
    let alive = true
    api.get(`/traffic-dashboard/campaign/${row.id}/dsp-refresh`, auth())
      .then(r => { if (alive) setPlan(r.data) })
      .catch(e => { if (alive) setErr(e?.response?.data?.detail || 'Не удалось прочитать состояние в DSP') })
    return () => { alive = false }
  }, [row.id, auth])

  const todo = (plan?.items || []).filter(i => !i.error)

  const go = async () => {
    setErr('')
    const ok = [], failed = []
    for (let i = 0; i < todo.length; i += 1) {
      const it = todo[i]
      setRun({ done: i, total: todo.length, current: it.what })
      try {
        await api.post(`/traffic-dashboard/campaign/${row.id}/dsp-refresh/item`,
          { kind: it.kind, ref: String(it.ref) }, auth())
        ok.push(it.what)
      } catch (e) {
        failed.push(`${it.what}: ${e?.response?.data?.detail || 'ошибка'}`)
      }
    }
    setRun({ done: todo.length, total: todo.length, current: null })
    try {
      await api.post(`/traffic-dashboard/campaign/${row.id}/dsp-refresh/done`,
        { applied: ok.length, failed }, auth())
    } catch { /* журнал — не повод прятать итог */ }
    setRes({ ok, failed })
    onDone && onDone()
  }

  const busy = !!run && !res
  const pct = run ? Math.round((run.done / Math.max(run.total, 1)) * 100) : 0
  const summary = plan
    ? `К обновлению: ${todo.length} · без изменений: ${plan.unchanged}`
      + ((plan.items || []).some(i => i.error) ? ` · не прочитано: ${plan.items.filter(i => i.error).length}` : '')
    : null

  const footer = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
      {err && <span style={{ fontSize: 12.5, color: 'var(--danger-fg)', marginRight: 'auto' }}>⚠ {err}</span>}
      <button style={btnSm(false)} onClick={onClose} disabled={busy}>{res ? 'Закрыть' : 'Отмена'}</button>
      {!res && (
        <button style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 8,
          cursor: busy ? 'progress' : 'pointer', opacity: !plan || !todo.length ? 0.6 : 1 }}
          disabled={busy || !plan || !todo.length} onClick={go}>
          {busy && <Cube variant="spinner" size={14} />}
          {busy ? `обновляю ${run.done} из ${run.total}…` : todo.length ? `Обновить в DSP (${todo.length})` : 'Обновлять нечего'}
        </button>
      )}
    </div>
  )

  return (
    <Modal title={`Обновить данные в DSP · ${row.deal_code}`} summary={summary} footer={footer} width={820}
      onClose={() => { if (!busy) onClose() }}>
      {!plan && !err && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, color: 'var(--text-muted)' }}>
          <Cube variant="spinner" size={14} /> читаю состояние креативов и таргетингов из DSP…
        </div>
      )}
      {(plan?.notes || []).map((n, i) => (
        <div key={i} style={{ fontSize: 12.5, color: 'var(--warning-text)', padding: '4px 0' }}>⚠ {n}</div>
      ))}

      {run && (
        <div style={{ margin: '6px 0 12px' }}>
          <div style={{ height: 8, borderRadius: 6, background: 'var(--bg-subtle)', overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: res?.failed?.length ? 'var(--warning-text)' : 'var(--accent)',
              transition: 'width .35s ease' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontSize: 12.5, color: 'var(--text-muted)' }}>
            {busy && <Cube variant="spinner" size={12} />}
            {busy ? `${run.done} из ${run.total} · ${run.current}` : `готово: ${run.total} из ${run.total}`}
          </div>
        </div>
      )}

      {res && (
        <div style={{ padding: '10px 12px', margin: '0 0 10px', borderRadius: 10, fontSize: 13, lineHeight: 1.5,
          background: res.failed.length ? 'var(--warning-tint)' : 'var(--income-tint)',
          color: res.failed.length ? 'var(--warning-text)' : 'var(--income-fg)' }}>
          Обновлено в DSP: {res.ok.length}{res.failed.length ? ` · DSP не принял: ${res.failed.length}` : ''}
          {res.failed.map((f, i) => <div key={i}>⚠ {f}</div>)}
        </div>
      )}

      {plan && !plan.items.length && !(plan.notes || []).length && (
        <div style={{ padding: '10px 0', fontSize: 13, color: 'var(--income-fg)' }}>
          В DSP всё совпадает с текущими данными — обновлять нечего.
        </div>
      )}
      {plan && !!plan.items.length && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr><th style={th}>Что</th><th style={th}>Поле</th><th style={th}>Сейчас в DSP</th><th style={th}>Станет</th></tr>
          </thead>
          <tbody>
            {plan.items.flatMap(it => (it.error ? [(
              <tr key={`${it.kind}${it.ref}`}>
                <td style={{ ...td, padding: '7px 10px' }}>{it.what}</td>
                <td colSpan={3} style={{ ...td, padding: '7px 10px', color: 'var(--danger-fg)' }}>не прочитано: {it.error}</td>
              </tr>
            )] : it.changes.map((ch, i) => (
              <tr key={`${it.kind}${it.ref}${ch.field}`}>
                <td style={{ ...td, padding: '7px 10px' }}>
                  {i === 0 && (<>
                    <div style={{ fontWeight: 600 }}>{it.what}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{KIND[it.kind]}</div>
                  </>)}
                </td>
                <td style={{ ...td, padding: '7px 10px', color: 'var(--text-secondary)' }}>{FIELD[ch.field] || ch.field}</td>
                <td style={{ ...td, padding: '7px 10px', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all' }}>{ch.was || '—'}</td>
                <td style={{ ...td, padding: '7px 10px', fontFamily: MONO, fontSize: 11, wordBreak: 'break-all' }}>{ch.will}</td>
              </tr>
            ))))}
          </tbody>
        </table>
      )}
    </Modal>
  )
}
