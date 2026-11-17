// Шапка экрана «Статус системы» справа (макет design_handoff_status, 16.11.2026): время проверки, «авто · 30 с»,
// «Проверить», «Оповещения» и «Техобслуживание» поповерами. Техобслуживание — тот же модуль, что и раньше
// (`/api/maintenance`): объявление за 10 минут, область «портал / кабинеты» (владелец 02.11.2026), снимается руками.
import { useEffect, useState } from 'react'
import { MONO, PortalPopover } from '@/components/salesTableKit'
import { fmtTime } from '@/lib/dates'

const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }
export const headBtn = { ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 13px', background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }
const pin = (on) => ({ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 9, fontSize: 12, whiteSpace: 'nowrap',
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
  color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontWeight: on ? 700 : 600 })
const POP = { width: 360, padding: 14, gap: 10, borderRadius: 14, boxShadow: 'var(--shadow-float)', maxHeight: 520 }

export function Toggle({ on }) {
  return (
    <span style={{ flex: '0 0 26px', position: 'relative', width: 26, height: 15, borderRadius: 8, background: on ? 'var(--accent)' : 'var(--text-disabled)', transition: 'background 150ms ease' }}>
      <span style={{ position: 'absolute', top: 2, left: on ? 13 : 2, width: 11, height: 11, borderRadius: 6, background: 'var(--bg-card)', transition: 'left 150ms ease' }} />
    </span>
  )
}

/** Закрытие поповера кликом мимо: всё, что внутри `[data-pop-root]` (триггер и панель), не закрывает. */
function useOutside(open, close) {
  useEffect(() => {
    if (!open) return undefined
    const h = (e) => { if (!e.target.closest('[data-pop-root]')) close() }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open, close])
}

const NOTIF_ROWS = [
  ['bad', 'var(--danger)', 'Отказ', 'сразу, как только проверка упала'],
  ['warn', 'var(--warning)', 'Не настроено или истекает', 'одной сводкой раз в сутки, в 09:00'],
  ['ok', 'var(--income)', 'Вернулось в норму', 'сразу, с временем простоя'],
]

export function NotifyButton({ cfg, onChange }) {
  const [open, setOpen] = useState(false)
  useOutside(open, () => setOpen(false))
  if (!cfg) return null
  return (
    <span data-pop-root style={{ position: 'relative' }}>
      <button type="button" className="st-head" onClick={() => setOpen(o => !o)} style={headBtn}>
        Оповещения<span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, color: cfg.on ? 'var(--income-fg)' : 'var(--text-faint)' }}>{cfg.on ? 'вкл' : 'выкл'}</span>
      </button>
      <PortalPopover open={open} align="right" minWidth={360} offset={6} style={POP}>
        <span style={{ fontSize: 13.5, fontWeight: 800 }}>Оповещения о смене состояния</span>
        <span style={{ fontSize: 12, lineHeight: 1.45, color: 'var(--text-muted)' }}>Уходят администраторам, когда проверка меняет состояние, а не при каждом прогоне.</span>
        <span style={{ display: 'flex', flexDirection: 'column' }}>
          {NOTIF_ROWS.map(([k, dot, label, hint]) => (
            <button key={k} type="button" onClick={() => onChange({ [k]: !cfg[k] })}
              style={{ ...plain, display: 'flex', alignItems: 'center', gap: 10, minHeight: 40, borderTop: '1px solid var(--border-row)' }}>
              <span style={{ flex: '0 0 7px', width: 7, height: 7, borderRadius: 2, background: dot }} />
              <span style={{ flex: '1 1 auto', display: 'flex', flexDirection: 'column', gap: 1 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>{label}</span><span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{hint}</span>
              </span>
              <Toggle on={cfg[k]} />
            </button>
          ))}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, paddingTop: 2 }}>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)', paddingRight: 4 }}>Куда</span>
          {[['tg', 'Телеграм'], ['mail', 'Почта']].map(([k, label]) => (
            <button key={k} type="button" onClick={() => onChange({ [k]: !cfg[k] })} style={pin(cfg[k])}>{label}</button>
          ))}
          <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>администраторы{cfg.admins != null ? ` · ${cfg.admins}` : ''}</span>
        </span>
      </PortalPopover>
    </span>
  )
}


/** Плашка в шапке: идёт / объявлено. */
export function MaintBadge({ st }) {
  if (!st || st.mode === 'off') return null
  const where = [st.portal && 'сотрудники', st.cabinet && 'кабинеты паблишеров'].filter(Boolean).join(' и ')
  return (
    <span title={`Заглушку видят ${where}; администраторы работают как обычно`} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 26, padding: '0 10px', borderRadius: 8,
      background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', fontSize: 12, fontWeight: 700, color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}>
      {st.mode === 'active' ? 'идёт техобслуживание' : `техобслуживание с ${fmtTime(st.from)}`}
    </span>
  )
}

export function MaintButton({ st, onAnnounce, onCancel }) {
  const [open, setOpen] = useState(false)
  const [scope, setScope] = useState({ portal: true, cabinet: true })
  useOutside(open, () => setOpen(false))
  if (!st) return null
  const on = st.mode !== 'off'
  const title = st.mode === 'active' ? 'Завершить техобслуживание?' : on ? 'Отменить объявление?' : 'Включить техобслуживание?'
  const text = on
    ? (st.mode === 'active' ? 'Портал и кабинеты паблишеров снова откроются для всех.' : 'Заглушка не появится, работа продолжится как обычно.')
    : 'Через 10 минут выбранные контуры увидят заглушку вместо портала. Администраторы работают как обычно. Фоновые задания не останавливаются.'
  const apply = () => { setOpen(false); on ? onCancel() : onAnnounce(scope) }
  return (
    <span data-pop-root style={{ position: 'relative' }}>
      <button type="button" className="st-head" onClick={() => setOpen(o => !o)} style={headBtn}>{on ? 'Завершить' : 'Техобслуживание'}</button>
      <PortalPopover open={open} align="right" minWidth={320} offset={6} style={{ ...POP, width: 320 }}>
        <span style={{ fontSize: 13.5, fontWeight: 800 }}>{title}</span>
        <span style={{ fontSize: 12, lineHeight: 1.45, color: 'var(--text-muted)' }}>{text}</span>
        {!on && (
          <span style={{ display: 'flex', gap: 6 }}>
            {[['portal', 'Портал'], ['cabinet', 'Кабинеты паблишеров']].map(([k, label]) => (
              <button key={k} type="button" onClick={() => setScope(s => ({ ...s, [k]: !s[k] }))} style={pin(scope[k])}>{label}</button>
            ))}
          </span>
        )}
        <span style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={() => setOpen(false)} style={{ ...headBtn, height: 30, fontWeight: 600 }}>Отмена</button>
          <button type="button" disabled={!on && !(scope.portal || scope.cabinet)} onClick={apply} className="st-cta"
            style={{ ...headBtn, height: 30, border: 'none', background: 'var(--accent)', color: 'var(--bg-card)' }}>
            {st.mode === 'active' ? 'Завершить' : on ? 'Отменить' : 'Включить'}</button>
        </span>
      </PortalPopover>
    </span>
  )
}
