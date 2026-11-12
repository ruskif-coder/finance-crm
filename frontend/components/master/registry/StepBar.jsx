/**
 * Полоса «что сделать сейчас» (хендофф реестра v3, 12.11.2026) — первая в блоке «ДС · комплекты · документы» расхлопа.
 * Разметка — из макета (`Мастер-сделки - реестр v3.dc.html`); что показать — `lib/masterStepBar.js`.
 */
import { useState } from 'react'
import Link from 'next/link'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { stepBar } from '@/lib/masterStepBar'
import { MONO } from '@/components/salesTableKit'

const TONE = {
  act: ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)'],
  wait: ['var(--bg-subtle)', 'var(--border-card)', 'var(--text-primary)'],
  bad: ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger-fg)'],
  ok: ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)'],
}
const BTN = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 14px', boxSizing: 'border-box', borderRadius: 9, fontSize: 12,
  fontWeight: 700, whiteSpace: 'nowrap', textDecoration: 'none' }
const Svg = ({ d, w = 2 }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
)

export default function StepBar({ m, canEdit, onDone, setErr }) {
  const [busy, setBusy] = useState(false)
  const b = stepBar(m, canEdit)
  const [bg, border, fg] = TONE[b.tone] || TONE.wait
  const run = async () => {
    const { btn } = b
    let body = btn.body
    if (btn.track) {
      const track = window.prompt('Трек-номер отправки (можно оставить пустым)')
      if (track === null) return
      body = { ...body, reason: track.trim() || null }
    }
    setBusy(true); setErr('')
    try {
      const r = btn.status ? await api.post(`/master-deals/${m.code}/status`, { to: btn.status }, auth())
        : await api.post(`/master-deals/${m.code}/sent`, body, auth())
      onDone(r.data)
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось отметить') } finally { setBusy(false) }
  }
  return (
    <div data-noexp style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', maxWidth: 1120, boxSizing: 'border-box', borderRadius: 10,
      background: bg, border: `1px solid ${border}`, cursor: 'default' }}>
      <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 1, width: 44, height: 38, flex: '0 0 44px',
        borderRadius: 9, background: 'var(--bg-card)', border: `1px solid ${border}` }}>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, lineHeight: 1, color: fg }}>{b.no}</span>
        <span style={{ fontFamily: MONO, fontSize: 8, letterSpacing: '.06em', color: 'var(--text-faint)' }}>из 6</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: '1 1 auto' }}>
        <span style={{ fontSize: 13.5, fontWeight: 700, color: fg, lineHeight: 1.35 }}>{b.title}</span>
        {!!b.sub && <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.4 }}>{b.sub}</span>}
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
        {b.zip && (
          <span onClick={() => downloadFile(`/master-deals/${m.code}/zip?diadoc=true`, null, setErr)}
            title="Все документы, которые нужно загрузить в Диадок: ДС и комплекты · pdf и xml"
            style={{ ...BTN, padding: '0 12px', border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-primary)', cursor: 'pointer' }}>
            <Svg d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 20h14" />Скачать для Диадока · zip</span>
        )}
        {!!b.btn && (
          <button type="button" disabled={busy} onClick={run} title={b.btn.title}
            style={{ ...BTN, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1 }}>
            <Svg d="M5 12.5l4.5 4.5L19 7.5" w={2.4} />{b.btn.label}</button>
        )}
        {!!b.link && (
          <Link href={b.link.href}
            style={{ ...BTN, background: b.link.tone === 'act' ? 'var(--accent)' : 'var(--bg-card)', border: `1px solid ${b.link.tone === 'act' ? 'var(--accent)' : 'var(--danger-border)'}`,
              color: b.link.tone === 'act' ? 'var(--on-accent)' : 'var(--danger-fg)' }}>{b.link.label}</Link>
        )}
      </span>
    </div>
  )
}
