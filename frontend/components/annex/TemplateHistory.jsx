/**
 * История версий шаблона (макет 13.10.2026): слева версии, справа изменения выбранной.
 * Откат не стирает историю: он создаёт НОВУЮ версию с текстом выбранной (сервер, `POST …/restore`).
 */
import { MONO } from '@/components/salesTableKit'

const MARKS = {
  '+': ['var(--income-tint)', 'var(--income-fg)'],
  '−': ['var(--danger-tint)', 'var(--danger-fg)'],
  '~': ['var(--accent-tint)', 'var(--accent-fg)'],
  '↕': ['var(--bg-subtle)', 'var(--text-secondary)'],
  '🔒': ['var(--warning-tint)', 'var(--warning-fg)'],
  '↳': ['var(--bg-subtle)', 'var(--text-secondary)'],
  '≡': ['var(--bg-subtle)', 'var(--text-secondary)'],
}
const SERIF = "'Times New Roman', Georgia, serif"

const changesWord = (n) => `${n} ${n === 1 ? 'изменение' : n < 5 ? 'изменения' : 'изменений'}`

function VersionRow({ h, on, current, used, onPick }) {
  return (
    <div onClick={onPick}
         style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 10px', borderRadius: 9, background: on ? 'var(--bg-tint)' : 'transparent', border: `1px solid ${on ? 'var(--accent-border)' : 'transparent'}`, cursor: 'pointer' }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <b style={{ fontFamily: MONO, fontSize: 12 }}>v{h.v}</b>
        {current && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--income-fg)' }}>текущая</span>}
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{h.date}</span>
      </span>
      <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{h.author} · {changesWord(h.changes.length)}</span>
      {used !== undefined && (
        <span style={{ fontFamily: MONO, fontSize: 9, color: used && !current ? 'var(--warning-fg)' : 'var(--text-faint)' }}>
          {used ? `по ней собрано ${used} ДС` : 'ДС по этой версии нет'}
        </span>
      )}
    </div>
  )
}

function Change({ c }) {
  const [mark, title, desc, old, now] = c
  const m = MARKS[mark] || MARKS['~']
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', border: '1px solid var(--border-card)', borderRadius: 11 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 20, height: 20, borderRadius: 6, background: m[0], color: m[1], fontFamily: MONO, fontSize: 11, fontWeight: 700, flex: '0 0 20px' }}>{mark}</span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{title}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{desc}</span>
      </span>
      {!!(old || now) && (
        <span style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 29, fontFamily: SERIF, fontSize: 13, lineHeight: 1.45 }}>
          <span style={{ color: 'var(--danger-fg)', textDecoration: 'line-through', textDecorationColor: 'var(--danger-border)' }}>{old}</span>
          <span style={{ color: 'var(--income-fg)' }}>{now}</span>
        </span>
      )}
    </div>
  )
}

export default function TemplateHistory({ list, version, usage, selected, onSelect, onRollback }) {
  const row = list.find(h => h.v === selected) || list[0]
  const used = (v) => (usage ? usage[v] || 0 : undefined)   // счётчика «собрано ДС» с сервера пока нет — строка не показывается
  return (
    <div style={{ flex: '1 1 auto', minHeight: 'min(560px, 70vh)', display: 'flex', overflow: 'hidden' }}>
      <div style={{ flex: '0 0 300px', borderRight: '1px solid var(--border-inner)', padding: '12px 10px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={{ padding: '0 8px 6px', fontFamily: MONO, fontSize: 9, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>Версии шаблона</span>
        {list.map(h => <VersionRow key={h.v} h={h} on={h.v === row.v} current={h.v === version} used={used(h.v)} onPick={() => onSelect(h.v)} />)}
      </div>
      <div style={{ flex: '1 1 0', minWidth: 0, overflowY: 'auto', padding: '18px 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>Версия {row.v}</span>
          <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{row.date} · {row.author}</span>
          {row.v !== version && !!onRollback && (
            <span onClick={() => onRollback(row)} title="Откат создаёт новую версию — старая не перезаписывается"
                  style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 13px', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
              Вернуть эту версию
            </span>
          )}
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {row.v === version
            ? 'Текущая версия. Изменения относительно предыдущей:'
            : `Изменения относительно предыдущей версии.${used(row.v) !== undefined ? ` По этой версии собрано ${used(row.v)} ДС — они остаются как есть.` : ''}`}
        </span>
        {row.changes.map((c, i) => <Change key={i} c={c} />)}
      </div>
    </div>
  )
}
