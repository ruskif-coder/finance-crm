/**
 * Канал выставления (хендофф реестра v2, 21.10.2026): отдельная колонка, к статусу не относится. ЭДО — акцентный чип со стрелкой,
 * бумага — нейтральный плотный чип с листом (фиолетовый занят статусом «ждём 1С»). Не задан в договоре — прочерк.
 */
import { MONO } from '@/components/salesTableKit'

const WAY = {
  'ЭДО': { icon: 'M4 12h16M14 6l6 6-6 6', bg: 'var(--accent-tint)', bd: 'var(--accent-border)', fg: 'var(--accent-fg)',
    title: 'Документы идут через Диадок — сканы не нужны' },
  'бумага': { icon: 'M7 3h7l4 4v14H7zM14 3v4h4', bg: 'var(--bg-card)', bd: 'var(--border-hover)', fg: 'var(--text-primary)',
    title: 'Бумажный документооборот — нужны сканы подписанных ДС и УПД, есть стадия «ждём сканы»' },
}

export default function ChannelChip({ way, height = 24 }) {
  const w = WAY[way]
  if (!w) return <span title="Канал не задан в договоре" style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-disabled)' }}>—</span>
  return (
    <span title={w.title} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height, padding: '0 8px', background: w.bg, border: `1px solid ${w.bd}`,
      borderRadius: 7, color: w.fg, fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap', flex: '0 0 auto' }}>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={w.icon} /></svg>
      {way}
    </span>
  )
}
