// Строка выдачи поиска — общая для выпадашки в шапке и страницы результатов.
// Дизайн — хендофф docs/поиск.zip (README §2). В строке ровно три визуальных сигнала:
// подсветка совпадения, метка «архив», подсветка выбранной строки. Сумм и цветов стадий
// нет (решения владельца 27.09.2026): поиск — навигатор, всё остальное на экране объекта.
import { MONO } from '@/components/salesTableKit'
import { internalHref } from '@/lib/search'

export const ARCHIVE_TAG = {
  display: 'inline-flex', alignItems: 'center', padding: '2px 7px', flex: '0 0 auto',
  border: '1px solid var(--border-card)', borderRadius: 6, color: 'var(--text-faint)',
  fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase',
}

const CLIP = { minWidth: 0, flex: '0 1 auto', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const TITLE = { ...CLIP, fontSize: 13, fontWeight: 600 }
const SUB = { ...CLIP, fontSize: 12, color: 'var(--text-muted)' }
const MARK = { background: 'var(--warning-tint)', borderRadius: 3 }

/** Текст с подсветкой всех вхождений запроса, без учёта регистра, с 2 символов. */
export function Marked({ text, q }) {
  const s = String(text ?? '')
  const needle = (q || '').trim().toLowerCase()
  if (needle.length < 2) return s
  const low = s.toLowerCase()
  const parts = []
  let i = 0
  let j = low.indexOf(needle)
  while (j >= 0) {
    if (j > i) parts.push(s.slice(i, j))
    parts.push(<span key={j} style={MARK}>{s.slice(j, j + needle.length)}</span>)
    i = j + needle.length
    j = low.indexOf(needle, i)
  }
  if (i < s.length) parts.push(s.slice(i))
  return parts
}

function Texts({ item, q }) {
  return (
    <>
      <span style={TITLE}><Marked text={item.title} q={q} /></span>
      {!!item.subtitle && <span style={SUB}><Marked text={item.subtitle} q={q} /></span>}
    </>
  )
}

/** Строка выпадашки: 34 px, выбор клавиатурой и наведение — одно состояние. */
export function DropRow({ item, q, active, onOpen, onHover }) {
  return (
    <a href={internalHref(item.href)} onClick={e => { e.preventDefault(); onOpen(item) }} onMouseEnter={onHover}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, minHeight: 34, padding: '0 10px', borderRadius: 9,
        background: active ? 'var(--accent-tint)' : 'transparent', color: 'var(--text-primary)',
        textDecoration: 'none', minWidth: 0,
      }}>
      <Texts item={item} q={q} />
      {item.archived && <span style={{ ...ARCHIVE_TAG, marginLeft: 'auto' }}>архив</span>}
    </a>
  )
}

/** Строка страницы результатов: 38 px, разделитель, наведение — класс `srch-row` (pages/search.js). */
export function PageRow({ item, q, onOpen }) {
  return (
    <a className="srch-row" href={internalHref(item.href)} onClick={e => { e.preventDefault(); onOpen(item) }}
      style={{
        display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 14, alignItems: 'center',
        minHeight: 38, padding: '0 8px', borderBottom: '1px solid var(--border-row)', borderRadius: 9,
        color: 'var(--text-primary)', textDecoration: 'none',
      }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
        <Texts item={item} q={q} />
      </span>
      <span style={{ display: 'flex', justifyContent: 'flex-end', minWidth: 54 }}>
        {item.archived && <span style={ARCHIVE_TAG}>архив</span>}
      </span>
    </a>
  )
}
