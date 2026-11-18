/**
 * Человек в команде сделки/РК: кружок с инициалами, над именем — роль капсом (владелец 18.11.2026: «как у аккаунтов, в 2 этажа
 * с иконкой»). Один вид для блока «Команда» в расхлопе «Моих сделок» и для «акк. · трафик» в пульте РК дашборда трафика.
 * `name` — текст; `children` — вместо текста (например, кнопка смены трафика со списком).
 */
import { MONO } from '@/components/salesTableKit'

export const initials = (n) => (n ? n.split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase() : '—')

const AV = { fontFamily: MONO, width: 24, height: 24, flex: '0 0 24px', borderRadius: 7, background: 'var(--bg-subtle)', display: 'inline-flex',
  alignItems: 'center', justifyContent: 'center', fontSize: 9.5, fontWeight: 700, color: 'var(--text-muted)' }
const ROLE = { fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap, var(--text-muted))' }

export default function PersonChip({ role, name, children }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
      <span style={AV}>{initials(name)}</span>
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span style={ROLE}>{role}</span>
        {children || <span style={{ fontSize: 12.5, fontWeight: 600, color: name ? 'var(--text-primary)' : 'var(--text-faint)', whiteSpace: 'nowrap',
          overflow: 'hidden', textOverflow: 'ellipsis' }}>{name || 'не назначен'}</span>}
      </span>
    </span>
  )
}
