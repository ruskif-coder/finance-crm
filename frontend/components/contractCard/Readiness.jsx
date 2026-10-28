/**
 * «Готовность к ДС» (хендофф «договорZ», владелец 28.10.2026 — без кнопки «Собрать ДС»): проверки с сервера (`readiness`), зелёный чип ✓,
 * красный ✕; клик по красному ведёт к месту правки — подписант открывает список подписантов стороны, остальное прокручивает к блоку
 * или открывает карточку контрагента / режим правки шапки.
 */
import { box, plural } from '@/components/contractCard/ui'

const OK = 'M5 12.5l4.5 4.5L19 7.5'
const BAD = 'M6 6l12 12M18 6L6 18'

export default function Readiness({ checks = [], onGo }) {
  const bad = checks.filter(c => !c.ok)
  return (
    <section style={{ ...box, background: bad.length ? 'var(--danger-bg)' : 'var(--bg-card)', border: `1px solid ${bad.length ? 'var(--danger-border)' : 'var(--border-card)'}`,
                      padding: '14px 20px', display: 'flex', alignItems: 'center', gap: '12px 14px', flexWrap: 'wrap', overflow: 'hidden' }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, flex: '0 0 auto' }}>
        <span style={{ fontSize: 15, fontWeight: 700 }}>Готовность к ДС</span>
        <span style={{ fontSize: 11.5, color: bad.length ? 'var(--danger-fg)' : 'var(--income-fg)', whiteSpace: 'nowrap' }}>
          {bad.length ? `не хватает ${bad.length} ${plural(bad.length, 'пункта', 'пунктов', 'пунктов')}` : 'всё на месте'}
        </span>
      </span>
      <span style={{ flex: '1 1 100%', minWidth: 0, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {checks.map(c => {
          const t = c.ok ? ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)'] : ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger-fg)']
          const go = !c.ok && c.target ? () => onGo(c.target) : undefined
          return (
            <span key={c.key} onClick={go} title={c.text}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 8, background: t[0], border: `1px solid ${t[1]}`, color: t[2],
                           fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', cursor: go ? 'pointer' : 'default' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d={c.ok ? OK : BAD} /></svg>
              {c.label}
            </span>
          )
        })}
      </span>
    </section>
  )
}
