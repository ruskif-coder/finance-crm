/**
 * «Скопировать сделку» в шапке карточки (владелец 15.10.2026) — продление кампании: копия со всеми данными, медиапланом (последний
 * завизированный; у запущенной — тот, что на ней), креативами и площадками на новый период (`POST /launch-prep/deal/{id}/prolong`).
 * Копия идёт на сборку по матрице требований; не хватает чего-то — остаётся на «Брони», и окно называет недостающее.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/api'
import { todayMsk } from '@/lib/dates'
import { Modal, btn, primaryBtn, inp, UI } from '@/components/salesTableKit'

// Финансовый период — месяц; по умолчанию следующий за периодом исходной сделки (владелец 15.10.2026).
// Календарный день — строкой, без new Date(): разбор метки сдвигал бы месяц на сутки по часовому поясу.
const nextMonth = (iso) => {
  const [y, m] = (iso ? String(iso).slice(0, 7) : todayMsk().slice(0, 7)).split('-').map(Number)
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`
}
// Границы месяца: даты размещения по умолчанию — весь месяц, правятся только внутри него.
const bounds = (ym) => {
  const [y, m] = ym.split('-').map(Number)
  const last = [31, (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
  return [`${ym}-01`, `${ym}-${last}`]
}

export default function CopyDealButton({ deal }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState(() => nextMonth(deal.period_from))
  const [[from, to], setPeriod] = useState(() => bounds(nextMonth(deal.period_from)))
  const pickMonth = (ym) => { if (!ym) return; setMonth(ym); setPeriod(bounds(ym)) }
  const [mMin, mMax] = bounds(month)
  // Пролонгация на этот месяц уже есть — предупреждаем ДО нажатия (владелец 15.10.2026): дубль — двойной план и повторная рассылка.
  const [existing, setExisting] = useState([])
  useEffect(() => {
    if (!open || !month) return
    let dead = false
    api.get(`/launch-prep/deal/${deal.id}/prolong-check`, { ...auth(), params: { month } })
      .then(r => { if (!dead) setExisting(r.data.existing || []) }).catch(() => { if (!dead) setExisting([]) })
    return () => { dead = true }
  }, [open, month, deal.id])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(null)

  const run = async () => {
    if (!from || !to) { setErr('Укажите даты размещения'); return }
    if (to < from) { setErr('Конец размещения раньше начала'); return }
    if (from < mMin || to > mMax) { setErr('Даты размещения — внутри финансового периода'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/launch-prep/deal/${deal.id}/prolong`, { month, period_from: from, period_to: to, force: existing.length > 0 }, auth())
      setDone(r.data)   // итог показываем всегда: у копии медиаплан без визы (владелец 15.10.2026)
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось скопировать сделку') }
    finally { setBusy(false) }
  }

  return (
    <>
      <button type="button" onClick={() => { setOpen(true); setDone(null); setErr('') }} title="Копия сделки на новый период: медиаплан, креативы, площадки"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--bg-card)', border: '1px solid var(--border-card)',
          color: 'var(--text-secondary)', borderRadius: 10, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
        Скопировать сделку
      </button>
      {open && (
        <Modal title={done ? 'Копия создана' : 'Скопировать сделку'} width={480} onClose={() => !busy && setOpen(false)}
          footer={done ? <>
            <button type="button" style={btn(false)} onClick={() => router.push(`/sales/deals/${done.code || done.id}`)}>Открыть копию</button>
            {done.mp_id
              ? <button type="button" style={primaryBtn} onClick={() => router.push(`/accounts/mp/${done.mp_id}`)}>Проверить медиаплан</button>
              : <button type="button" style={primaryBtn} onClick={() => setOpen(false)}>Готово</button>}
          </> : <>
            <button type="button" style={btn(false)} disabled={busy} onClick={() => setOpen(false)}>Отмена</button>
            <button type="button" style={existing.length ? { ...primaryBtn, background: 'var(--warning)' } : primaryBtn} disabled={busy} onClick={run}>
              {busy ? 'Копирую…' : existing.length ? 'Всё равно скопировать' : 'Скопировать'}</button>
          </>}>
          {done ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13, lineHeight: 1.55 }}>
              <div>Копия <b>{done.code}</b> создана · стадия «{done.stage}».</div>
              {!!done.mp_id && (
                <div style={{ padding: '9px 11px', borderRadius: 10, background: 'var(--warning-tint)', border: '1px solid var(--warning-border)' }}>
                  <b style={{ color: 'var(--warning-fg)' }}>Медиаплан требует визы.</b> Откройте его, проверьте цифры нового периода, отметьте
                  «проверено» у размещений и прогноза и сохраните.
                </div>
              )}
              {!!(done.missing_files || []).length && (
                <div style={{ padding: '9px 11px', borderRadius: 10, background: 'var(--danger-tint)', border: '1px solid var(--danger-border)' }}>
                  <b style={{ color: 'var(--danger-fg)' }}>Не найдены файлы креативов ({done.missing_files.length}).</b> В копии их нет — загрузите
                  заново в блоке «Креативы»:
                  <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{done.missing_files.map((m, i) => <li key={i}>{m}</li>)}</ul>
                </div>
              )}
              {!!(done.missing || []).length && (
                <div>Для перехода на сборку не хватает:
                  <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{done.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
              <div style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Копия получит все данные сделки, медиаплан, креативы и площадки на новый период. ЕРИД не переносится.
              </div>
              <div style={{ padding: '8px 11px', borderRadius: 10, background: 'var(--warning-tint)', border: '1px solid var(--warning-border)',
                color: 'var(--warning-fg)', fontWeight: 700 }}>
                Медиаплан копии нужно будет завизировать заново
              </div>
              <label><div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 3 }}>Финансовый период</div>
                <input type="month" value={month} onChange={e => pickMonth(e.target.value)} style={{ ...inp, width: 180 }} /></label>
              <div style={{ display: 'flex', gap: 10 }}>
                <label style={{ flex: 1 }}><div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 3 }}>Старт размещения</div>
                  <input type="date" value={from} min={mMin} max={mMax} onChange={e => setPeriod([e.target.value, to])} style={{ ...inp, width: '100%' }} /></label>
                <label style={{ flex: 1 }}><div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 3 }}>Конец размещения</div>
                  <input type="date" value={to} min={mMin} max={mMax} onChange={e => setPeriod([from, e.target.value])} style={{ ...inp, width: '100%' }} /></label>
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Даты по умолчанию — весь месяц; сузить можно только внутри финансового периода.</div>
              {!!existing.length && (
                <div style={{ padding: '9px 11px', borderRadius: 10, background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', lineHeight: 1.5 }}>
                  <b style={{ color: 'var(--warning-fg)' }}>Пролонгация на этот месяц уже есть:</b>{' '}
                  {existing.map((c, i) => <span key={c}>{i ? ', ' : ''}<a href={`/sales/deals/${c.replace(/^#/, '')}`} style={{ color: 'var(--accent)', fontWeight: 700 }}>{c}</a></span>)}.
                  {' '}Вторая копия — двойной план и повторная рассылка тех же креативов площадкам.
                </div>
              )}
              {!!err && <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
            </div>
          )}
        </Modal>
      )}
    </>
  )
}
