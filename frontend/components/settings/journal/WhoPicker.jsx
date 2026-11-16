// «Кто» — плашка со своим списком вместо селекта (макет design_handoff_journal, 16.11.2026): сотрудники и кабинеты
// отдельными блоками, со счётчиками от сервера по текущим фильтрам.
import { MONO, PortalPopover } from '../../salesTableKit'

const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }
const label = (a) => (a.kind === 'cabinet' && a.site ? `${a.site} · ${a.name}` : a.name)

function Opt({ on, text, n, onPick }) {
  return (
    <button type="button" className="j-opt" onClick={onPick}
      style={{ ...plain, display: 'flex', alignItems: 'center', gap: 8, width: '100%', flex: '0 0 30px', height: 30, boxSizing: 'border-box',
        padding: '0 9px', borderRadius: 8, fontSize: 12.5, fontWeight: on ? 700 : 500, whiteSpace: 'nowrap',
        color: on ? 'var(--accent-fg)' : 'var(--text-primary)', background: on ? 'var(--accent-tint)' : 'transparent' }}>
      <span style={{ flex: '1 1 auto', overflow: 'hidden', textOverflow: 'ellipsis' }}>{text}</span>
      {n != null && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>}
    </button>
  )
}

const Head = ({ text }) => (
  <span style={{ display: 'flex', alignItems: 'center', flex: '0 0 24px', padding: '0 9px', fontFamily: MONO, fontSize: 9, fontWeight: 700,
    letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>{text}</span>
)

export default function WhoPicker({ actors, value, contour, open, setOpen, onPick }) {
  const cur = actors.find(a => a.id === value)
  const all = contour === 'cabinet' ? 'Все кабинеты' : 'Все пользователи'
  const staff = actors.filter(a => a.kind === 'staff'), cabs = actors.filter(a => a.kind === 'cabinet')
  const on = !!value
  return (
    <span data-pop-root style={{ position: 'relative' }}>
      <button type="button" onClick={() => setOpen(!open)}
        style={{ ...plain, display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 10px', borderRadius: 9, fontSize: 12,
          whiteSpace: 'nowrap', background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
          color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontWeight: on ? 700 : 600 }}>
        {cur ? label(cur) : all}<span style={{ fontSize: 8, color: 'var(--text-faint)' }}>▾</span>
      </button>
      <PortalPopover open={open} minWidth={270} maxHeight={420} style={{ padding: 5, width: 270 }}>
        <Opt on={!value} text={all} onPick={() => onPick('')} />
        {staff.length > 0 && <Head text="Сотрудники" />}
        {staff.map(a => <Opt key={a.id} on={a.id === value} text={label(a)} n={a.count} onPick={() => onPick(a.id)} />)}
        {cabs.length > 0 && <Head text="Кабинеты паблишеров" />}
        {cabs.map(a => <Opt key={a.id} on={a.id === value} text={label(a)} n={a.count} onPick={() => onPick(a.id)} />)}
      </PortalPopover>
    </span>
  )
}
