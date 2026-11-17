/**
 * «Что поменяется» — перед «Пересоздать» (конструктор ДС) и «Обновить из сделки» (карточка мастер-сделки). Владелец 17.11.2026:
 * «по аналогии с DSP — показывать, что поменяется». Повод — M-0004: бренд переименовали в справочнике, а выпущенный ДС и основание
 * УПД остались со старым именем; пересборку жали вслепую.
 *
 * `load()` → `{ changes: [{doc?, where, was, now}], need_back?, may_back?, status? }` — сервер пересобирает вхолостую и откатывает.
 * `need_back` — пакет дальше «согласования»: применение вернёт его туда (нужны право и причина). `apply(reason)` — сохранить.
 */
import { useEffect, useState } from 'react'
import { Modal, MONO, btn, inp, primaryBtn } from '@/components/salesTableKit'
import { detailText } from '@/lib/loadError'
import { grp, rub2 } from '@/lib/salesFormat'

// числа — общим форматом (lib/salesFormat): целые — разрядами, с копейками — до двух знаков
const show = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'number' ? (Number.isInteger(v) ? grp(v) : rub2(v)) : String(v))
const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)', fontWeight: 700 }

function Change({ c }) {
  return (
    <div style={{ padding: '9px 0', borderBottom: '1px solid var(--border-row)', display: 'grid', gridTemplateColumns: '180px minmax(0,1fr)', gap: 12 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>{c.where}</span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0, fontSize: 12.5, lineHeight: 1.45, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
        <span style={{ color: 'var(--danger-fg)', textDecoration: 'line-through', textDecorationColor: 'var(--danger-border)' }}>{show(c.was)}</span>
        <span style={{ color: 'var(--income-fg)' }}>{show(c.now)}</span>
      </span>
    </div>
  )
}

export default function ChangesModal({ title, load, apply, applyLabel, onClose }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let live = true
    load().then(d => { if (live) setData(d) }).catch(e => { if (live) setErr(detailText(e, 'Не удалось собрать предпросмотр')) })
    return () => { live = false }
  }, [load])

  const changes = data?.changes || []
  const docs = [...new Set(changes.map(c => c.doc || ''))]
  const back = !!data?.need_back
  const blocked = back && !data?.may_back
  const ready = !!data && !blocked && (!back || reason.trim().length > 0) && !busy
  const run = async () => {
    setBusy(true); setErr('')
    try { await apply(back ? reason.trim() : null); onClose() } catch (e) { setErr(detailText(e, 'Не удалось применить')) } finally { setBusy(false) }
  }

  return (
    <Modal title={title} width={820} onClose={onClose}
      summary={!data ? (err ? null : 'Собираю документ заново, ничего не сохраняя…')
        : changes.length ? `Изменится мест: ${changes.length}. Номер и дата документа останутся прежними.`
          : 'Изменений нет — документ уже собран по текущим данным.'}
      footer={<>
        {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
        <span style={{ marginLeft: 'auto' }} />
        <button type="button" style={btn(false)} onClick={onClose}>Отмена</button>
        <button type="button" disabled={!ready} style={{ ...primaryBtn, opacity: ready ? 1 : 0.5, cursor: ready ? 'pointer' : 'not-allowed' }} onClick={run}>
          {busy ? 'Применяю…' : applyLabel}</button>
      </>}>
      {back && (
        <div style={{ margin: '6px 0 12px', padding: '10px 14px', borderRadius: 10, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
          color: 'var(--warning-fg)', fontSize: 12.5, lineHeight: 1.5 }}>
          Пакет на стадии «{data.status}». Обновление вернёт его на «согласование»: ДС снова уйдут клиенту на подпись, комплекты — бухгалтеру
          (ответ 1С снимется, номера счёта и УПД останутся). Бухгалтер и аккаунт получат уведомление.
          {blocked ? <div style={{ marginTop: 6, fontWeight: 700 }}>Вернуть пакет может роль с правом «возврат стадии».</div> : (
            <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} placeholder="Причина: что переделываем (обязательно)"
              style={{ ...inp, width: '100%', marginTop: 8, resize: 'vertical' }} />
          )}
        </div>
      )}
      {docs.map(d => (
        <div key={d} style={{ marginBottom: 10 }}>
          {!!d && <div style={{ ...CAP, padding: '8px 0 2px' }}>{d}</div>}
          {changes.filter(c => (c.doc || '') === d).map((c, i) => <Change key={i} c={c} />)}
        </div>
      ))}
    </Modal>
  )
}
