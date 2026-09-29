// Особенности площадки в строке очереди трафика (владелец 29.09.2026): какое правило
// применится к креативу и, для Adfox, архив с %user6% + доп. код в один клик.
// Что в каком случае делается с креативом — docs/ШПАРГАЛКА_креатив_под_площадку.md.
import { useState } from 'react'
import { MONO, chip as pill } from '@/components/salesTableKit'

export default function RuleBadges({ r, onDownload }) {
  const [copied, setCopied] = useState(false)
  if (!r.rule_label && !r.rule_problem) return null
  const bad = !!r.rule_problem
  const copy = () => {
    try {
      navigator.clipboard.writeText(r.adfox_code || '')
      setCopied(true); setTimeout(() => setCopied(false), 1500)
    } catch { /* нет доступа к буферу — код всё равно виден в админке */ }
  }
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
      <span title={r.rule_problem || r.rule_label}
        style={{ ...pill(bad ? 'var(--danger-tint)' : 'var(--bg-subtle)', bad ? 'var(--danger-fg)' : 'var(--text-secondary)',
          bad ? 'var(--danger-border)' : 'var(--border-card)'), fontFamily: MONO, fontSize: 10, whiteSpace: 'nowrap' }}>
        {bad ? '⚠ ' : ''}{r.placement_channel === 'adfox' ? 'Adfox' : r.placement_channel === 'outside' ? 'вне контура' : (r.rule_label || '').replace('в href — ', 'href: ')}
      </span>
      {r.placement_channel === 'adfox' && (
        <>
          <button type="button" onClick={() => onDownload(`/traffic/pair/${r.pair_id}/adfox-archive`)}
            title="Архив клиента с %user6% сразу после <body>"
            style={{ ...pill('var(--bg-card)', 'var(--accent)', 'var(--accent-border)'), cursor: 'pointer', fontSize: 10.5 }}>архив Adfox ↓</button>
          {!!r.adfox_code && (
            <button type="button" onClick={copy} title="Дополнительный код для поля %user6% в Adfox"
              style={{ ...pill('var(--bg-card)', copied ? 'var(--income-fg)' : 'var(--text-secondary)', 'var(--border-card)'), cursor: 'pointer', fontSize: 10.5 }}>
              {copied ? 'скопировано' : 'доп. код ⧉'}</button>
          )}
        </>
      )}
    </span>
  )
}
