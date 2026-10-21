/**
 * Общие мелочи экрана раскладки мастер-сделки (дизайн docs/мастер сделка.zip): подписи, склонения, стили ячеек.
 */
import { MONO, UI } from '@/components/salesTableKit'

export const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-cap)' }
export const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
export const R = { fontFamily: MONO, fontSize: 12.5, textAlign: 'right', whiteSpace: 'nowrap' }
export const NW = { whiteSpace: 'nowrap' }

/** Кнопка-обводка экрана мастер-сделки (шаги выставления, статус, конвейер) — одна вместо трёх локальных копий (аудит 20.10).
 *  tone: accent — шаг доступен; muted — серый текст; danger — красный. size: sm | md | lg. */
export const lineBtn = ({ tone = 'accent', size = 'md', busy = false } = {}) => ({
  ...{ sm: { padding: '3px 10px', borderRadius: 7, fontSize: 11.5 }, md: { padding: '5px 12px', borderRadius: 8, fontSize: 12 },
    lg: { height: 34, padding: '0 14px', borderRadius: 10, fontSize: 12.5, display: 'inline-flex', alignItems: 'center' } }[size],
  fontWeight: 700, fontFamily: UI, whiteSpace: 'nowrap', cursor: busy ? 'default' : 'pointer', background: 'var(--bg-card)', textDecoration: 'none',
  border: `1px solid ${tone === 'accent' ? 'var(--accent-fg)' : 'var(--border-card)'}`,
  color: { accent: 'var(--accent-fg)', muted: 'var(--text-muted)', danger: 'var(--danger-fg)', secondary: 'var(--text-secondary)' }[tone],
})

export const num = (v) => parseFloat(String(v).replace(/\s/g, '').replace(',', '.'))

// Склонение по числу: plural(2, ['ДС', 'ДС', 'ДС']), plural(5, ['комплект', 'комплекта', 'комплектов']).
export const plural = (n, [one, few, many]) => {
  const a = Math.abs(n) % 100, b = a % 10
  if (a > 10 && a < 20) return many
  if (b > 1 && b < 5) return few
  if (b === 1) return one
  return many
}

export const groupLabel = (g) => [g.brand, g.service].filter(Boolean).join(' · ') || 'весь пакет'

export const SETTING_LABEL = {
  addons_separate: ['допы отдельным ДС', (v) => (v ? 'да' : 'нет')],
  bonus_addons: ['бонусные допы', (v) => (v === 'zero' ? 'строкой с нулём' : 'не включать')],
  ds_by_brand: ['строки ДС по бренду', (v) => (v ? 'да' : 'нет')],
  ds_by_service: ['строки ДС по услуге', (v) => (v ? 'да' : 'нет')],
  upd_by_brand: ['закрывающие по бренду', (v) => (v ? 'да' : 'нет')],
  upd_by_service: ['закрывающие по услуге', (v) => (v ? 'да' : 'нет')],
}

export const sameSettings = (a, b) => Object.keys(SETTING_LABEL).every(k => a?.[k] === b?.[k])
  && JSON.stringify([...(a?.moved || [])].sort()) === JSON.stringify([...(b?.moved || [])].sort())

export const Dot = ({ c }) => <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: 2, background: c, marginRight: 6, flex: '0 0 7px' }} />

export function Note({ tone = 'warn', children, style }) {
  // [подложка, рамка, текст, маркер]: маркер — яркий цвет смысла (--warning = оранжевый), текст — тёмный тон той же гаммы.
  const t = { warn: ['var(--warning-bg)', 'var(--warning-border)', 'var(--warning-fg)', 'var(--warning)'],
    ok: ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)', 'var(--income)'],
    bad: ['var(--danger-bg)', 'var(--danger-border)', 'var(--danger-fg)', 'var(--danger)'] }[tone]
  return (
    <div style={{ display: 'flex', gap: 10, padding: '10px 14px', borderRadius: 12, background: t[0], border: `1px solid ${t[1]}`, color: t[2], fontSize: 12.5, lineHeight: 1.5, ...style }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: t[3], marginTop: 6, flex: '0 0 7px' }} /><span style={{ minWidth: 0 }}>{children}</span>
    </div>
  )
}
