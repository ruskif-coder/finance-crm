// Строка экрана «Пользователи» по макету design_handoff_users (16.11.2026): правки кликом по плашкам, без нативных
// <select> и без кнопки сохранения в строке — сохраняет одно «Сохранить N» на странице.
import { MONO, PortalPopover } from '../../salesTableKit'
import { emailOk, isMasterRole } from './usersModel'

export const COLS = '14px minmax(170px,1.1fr) minmax(220px,1.4fr) 196px 148px 204px minmax(230px,1.2fr) 84px'
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' }
const pill = { display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, boxSizing: 'border-box', padding: '0 9px',
  borderRadius: 7, fontSize: 11.5, whiteSpace: 'nowrap', userSelect: 'none', maxWidth: '100%' }
const panel = { padding: 5, width: 230 }      // радиус 12, тень и слой — у самого PortalPopover

function Option({ on, label, n, onPick }) {
  return (
    <button type="button" className="u-opt" onClick={onPick}
      style={{ ...plain, display: 'flex', alignItems: 'center', gap: 8, width: '100%', height: 30, flex: '0 0 30px', boxSizing: 'border-box',
        padding: '0 9px', borderRadius: 8, fontSize: 12.5, fontWeight: on ? 700 : 500, whiteSpace: 'nowrap',
        color: on ? 'var(--accent-fg)' : 'var(--text-primary)', background: on ? 'var(--accent-tint)' : 'transparent' }}>
      <span style={{ flex: '1 1 auto', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      {n != null && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>}
    </button>
  )
}

function Inline({ value, onChange, placeholder, bad, mono, fg, label }) {
  return (
    <input className="u-inline" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      aria-label={label} data-bad={bad ? '' : undefined}
      style={{ width: '100%', minWidth: 0, height: 28, boxSizing: 'border-box', padding: '0 8px', background: 'transparent',
        border: `1px solid ${bad ? 'var(--warning)' : 'transparent'}`, borderRadius: 8, outline: 'none',
        fontFamily: mono ? MONO : 'inherit', fontSize: mono ? 11.5 : 13, fontWeight: mono ? 400 : 700, color: fg }} />
  )
}

export default function UserRow({ d, savedActive, me, changed, roles, rolesByKey, counts, profiles, pw, copied, open, setOpen, up, onPatch,
  onGenPw, onClearPw, onCopy, onRemove }) {
  const role = rolesByKey[d.role]
  const admin = d.role === 'admin'
  const prof = profiles.find(p => p.id === d.pid)
  const profLabel = prof ? prof.label + (prof.is_default ? ' (умолч.)' : '') : '— по умолчанию —'
  // «удалить» — только у СОХРАНЁННОГО деактивированного: сервер удаляет лишь неактивных, а деактивация и удаление в одной пачке
  // уходили одним «delete» без is_active и роняли всё сохранение (ревью 16.11.2026)
  const removeLabel = d.isNew ? 'отменить' : (d.active || savedActive) ? '' : 'удалить'
  return (
    <div className="u-row" style={{ position: 'relative', display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center',
      minHeight: 44, padding: '0 20px', borderBottom: '1px solid var(--border-row)', background: d.isNew ? 'var(--bg-tint)' : 'transparent' }}>
      <span title={d.isNew ? 'Новый пользователь — появится после сохранения' : changed ? 'Есть несохранённые изменения' : ''}
        style={{ width: 7, height: 7, borderRadius: 2, background: d.isNew ? 'var(--income)' : changed ? 'var(--accent)' : 'transparent' }} />

      <Inline value={d.name} onChange={v => onPatch('name', v)} placeholder="Имя и фамилия" label={`Имя · ${d.id}`}
        bad={!String(d.name).trim()} fg={d.active ? 'var(--text-primary)' : 'var(--text-muted)'} />
      <Inline value={d.email} onChange={v => onPatch('email', v)} placeholder="email@simb-ad.com" label={`Email · ${d.id}`}
        bad={!emailOk(d.email)} mono fg={d.active ? 'var(--text-secondary)' : 'var(--text-faint)'} />

      <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
        <button type="button" onClick={() => !me && setOpen(open === 'role' ? '' : 'role')}
          title={me ? 'Свою роль менять нельзя' : 'Роль — клик открывает список'}
          style={{ ...plain, ...pill, cursor: me ? 'default' : 'pointer', fontWeight: admin ? 700 : 600,
            background: admin ? 'var(--accent-tint)' : 'var(--bg-subtle)', border: `1px solid ${admin ? 'var(--accent-border)' : 'var(--border-card)'}`,
            color: admin ? 'var(--accent-fg)' : 'var(--text-secondary)' }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{role ? role.label : d.role}</span>
          {isMasterRole(role) && <span title="Мастер группы" style={{ color: 'var(--warning)', fontSize: 11 }}>★</span>}
          {!me && <span style={{ fontSize: 8, color: 'var(--text-faint)' }}>▾</span>}
        </button>
        <PortalPopover open={open === 'role'} minWidth={230} maxHeight={300} flip={up} style={panel}>
          {roles.map(r => (
            <Option key={r.key} on={r.key === d.role} label={r.label + (isMasterRole(r) ? ' ★' : '')} n={counts[r.key] || 0}
              onPick={() => { onPatch('role', r.key); setOpen('') }} />
          ))}
        </PortalPopover>
      </span>

      <span>
        <button type="button" onClick={() => !me && onPatch('active', !d.active)}
          title={me ? 'Себя деактивировать нельзя' : d.active ? 'Клик: деактивировать — вход будет закрыт, данные останутся' : 'Клик: вернуть доступ'}
          style={{ ...plain, ...pill, fontWeight: 700, cursor: me ? 'default' : 'pointer',
            background: d.active ? 'var(--income-tint)' : 'var(--bg-card)', border: `1px solid ${d.active ? 'var(--income-border)' : 'var(--border-card)'}`,
            color: d.active ? 'var(--income-fg)' : 'var(--text-muted)' }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: d.active ? 'var(--income)' : 'var(--text-disabled)' }} />
          {d.active ? 'активен' : 'деактивирован'}
        </button>
      </span>

      <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
        <button type="button" onClick={() => setOpen(open === 'prof' ? '' : 'prof')} title="Профиль уведомлений — клик открывает список"
          style={{ ...plain, ...pill, fontWeight: 600, background: prof ? 'var(--bg-subtle)' : 'var(--bg-card)',
            border: `1px solid ${prof ? 'var(--border-card)' : 'var(--border-inner)'}`, color: prof ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{profLabel}</span>
          <span style={{ fontSize: 8, color: 'var(--text-faint)' }}>▾</span>
        </button>
        <PortalPopover open={open === 'prof'} minWidth={230} maxHeight={300} flip={up} style={panel}>
          <Option on={!d.pid} label="— по умолчанию —" onPick={() => { onPatch('pid', null); setOpen('') }} />
          {profiles.map(p => (
            <Option key={p.id} on={p.id === d.pid} label={p.label + (p.is_default ? ' (умолч.)' : '')}
              onPick={() => { onPatch('pid', p.id); setOpen('') }} />
          ))}
        </PortalPopover>
      </span>

      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        {pw ? (<>
          <span title="Новый пароль — покажем один раз, после сохранения его не увидеть"
            style={{ ...pill, fontFamily: MONO, fontWeight: 700, padding: '0 8px', background: 'var(--warning-tint)',
              border: '1px solid var(--warning-border)', color: 'var(--warning-fg)' }}>{pw}</span>
          <button type="button" onClick={onCopy} style={{ ...plain, fontSize: 11.5, fontWeight: 600, color: 'var(--accent-fg)', whiteSpace: 'nowrap' }}>
            {copied ? 'скопирован ✓' : 'копировать'}</button>
          {!d.isNew && <button type="button" onClick={onClearPw} title="Не менять пароль" className="u-quiet"
            style={{ ...plain, fontSize: 11.5, color: 'var(--text-faint)' }}>×</button>}
        </>) : (<>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>не менять</span>
          <button type="button" onClick={onGenPw} className="u-link"
            style={{ ...plain, fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>сбросить</button>
        </>)}
      </span>

      <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {!!removeLabel && (
          <button type="button" onClick={onRemove} className={d.isNew ? 'u-quiet' : 'u-danger'}
            title={d.isNew ? 'Не добавлять' : 'Удалить насовсем — спросим подтверждение'}
            style={{ ...plain, fontSize: 10.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{removeLabel}</button>
        )}
      </span>
    </div>
  )
}
