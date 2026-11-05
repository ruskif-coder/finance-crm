// Отчёт Weborama по ссылке — РК с внешним пикселем (владелец 05.11.2026). Пиксель ставил не наш аккаунт; клиент
// делится «постоянной ссылкой» на отчёт, и сервер ночью снимает по ней суточные показы в сверку
// (`backend/app/weborama/permalink.py`). Здесь — вписать/сменить ссылку и снять показы сейчас.
import { useState } from 'react'
import { MONO, btnSm, inp } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import api, { auth } from '@/lib/api'
import { fmtDateTime } from '@/lib/dates'
import { grp } from '@/lib/salesFormat'
import safeHref from '@/lib/safeHref'

const ru = (d) => (d ? String(d).slice(0, 10).split('-').reverse().join('.') : '')

export default function WrLinkRow({ campaignId, link, mayEdit, onChange }) {
  const [edit, setEdit] = useState(false)
  const [val, setVal] = useState(link?.url || '')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)      // {text, bad}

  const call = async (fn) => {
    setBusy(true); setMsg(null)
    try {
      const r = await fn()
      const res = r.data.result
      setMsg(res && !res.ok ? { text: res.error, bad: true }
        : (res ? { text: res.note || `снято дней: ${res.days}, показов ${grp(res.shows)}` } : null))
      onChange?.(r.data.wr_link)
      setEdit(false)
    } catch (e) { setMsg({ text: e?.response?.data?.detail || 'Не удалось', bad: true }) } finally { setBusy(false) }
  }
  const save = () => call(() => api.put(`/traffic-dashboard/campaign/${campaignId}/wr-link`, { url: val.trim() || null }, auth()))
  const sync = () => call(() => api.post(`/traffic-dashboard/campaign/${campaignId}/wr-link/sync`, {}, auth()))

  const url = link?.url
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 12, padding: '8px 12px',
      borderRadius: 10, background: 'var(--bg-subtle)', fontSize: 12 }}>
      <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
        отчёт weborama · внешний пиксель</span>
      {edit ? (
        <>
          <input value={val} onChange={e => setVal(e.target.value)} placeholder="https://adap-interface.wbrm.ru/…/reportcenter/permalink/link/hash/…"
            style={{ ...inp, flex: '1 1 420px', minWidth: 260, padding: '5px 9px', fontSize: 12 }} />
          <button style={btnSm(true)} disabled={busy} onClick={save}>Сохранить</button>
          <button style={btnSm(false)} disabled={busy} onClick={() => { setEdit(false); setVal(url || ''); setMsg(null) }}>Отмена</button>
        </>
      ) : url ? (
        <>
          <a href={safeHref(url)} target="_blank" rel="noopener noreferrer" title={url}
            style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {url.replace(/^https:\/\//, '')}</a>
          <span style={{ color: link.last_day ? 'var(--text-secondary)' : 'var(--warning-text)' }}>
            {link.last_day ? `показы по ${ru(link.last_day)} · ${grp(link.shows)}` : 'показов по ссылке ещё нет'}
            {link.synced_at ? <span style={{ color: 'var(--text-faint)' }}> · снято {fmtDateTime(link.synced_at)}</span> : null}
          </span>
          {mayEdit && (
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
              <button style={{ ...btnSm(false), display: 'inline-flex', alignItems: 'center', gap: 6 }} disabled={busy} onClick={sync}>
                {busy && <Cube variant="spinner" size={12} />}{busy ? 'Забираю…' : 'Обновить'}</button>
              <button style={btnSm(false)} disabled={busy} onClick={() => { setVal(url); setEdit(true) }}>Изменить</button>
            </span>
          )}
        </>
      ) : (
        <>
          <span style={{ color: 'var(--text-muted)' }}>ссылки нет — сверка с Weborama только по ручному итогу на карточке сделки</span>
          {mayEdit && <button style={{ ...btnSm(false), marginLeft: 'auto' }} onClick={() => setEdit(true)}>Вписать ссылку</button>}
        </>
      )}
      {!!msg && <span style={{ flexBasis: '100%', fontSize: 11.5, color: msg.bad ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{msg.text}</span>}
    </div>
  )
}
