/**
 * Реестр медиапланов v2 — управление над и под таблицей (хендофф design_handoff_mp_registry, 17.11.2026):
 * чипы этапов, «Мои», блок «Порядок», «По месяцам», заголовок месяца, низ со страницами.
 * Правила (числа, порядок, страницы) — lib/mpRegistryModel.mjs; здесь только вид.
 */
import { MONO, UI, pageWindow } from '@/components/salesTableKit'
import { shortMoney, toneOf } from '@/lib/mpRegistryModel.mjs'

const box = { display: 'inline-flex', padding: 2, borderRadius: 11, background: 'var(--bg-card)', border: '1px solid var(--border-card)' }
const segItem = (on) => ({
  display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 11px', borderRadius: 9, border: 'none',
  background: on ? 'var(--accent-tint)' : 'transparent', boxShadow: on ? 'inset 0 0 0 1px var(--accent-border)' : 'none',
  color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontFamily: UI, fontSize: 12.5, fontWeight: on ? 700 : 600,
  whiteSpace: 'nowrap', cursor: 'pointer', transition: 'background 160ms ease',
})
const dot = (bg, size = 7) => ({ width: size, height: size, borderRadius: '50%', background: bg, flex: `0 0 ${size}px` })

export const Chevron = ({ open, color }) => (
  <span style={{ display: 'inline-flex', color, transform: `rotate(${open ? 90 : 0}deg)`, transition: 'transform 220ms cubic-bezier(0.22,1,0.36,1)' }}>
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m6 3.5 4.5 4.5L6 12.5" /></svg>
  </span>
)

/** Чипы этапов сделки: «Все» и группы, у каждой число. Один выбор. */
export function StageChips({ buckets, counts, value, onPick }) {
  const all = [{ key: 'all', label: 'Все' }, ...buckets]
  return (
    <span style={box}>
      {all.map(b => {
        const on = value === b.key
        return (
          <button key={b.key} type="button" onClick={() => onPick(b.key)} style={segItem(on)}
            title={b.key === 'none' ? 'Медиапланы без привязанной сделки' : undefined}>
            {b.key !== 'all' && <span style={dot(toneOf(b.key)[0])} />}
            {b.label}
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: on ? 'var(--accent-fg)' : 'var(--text-muted)' }}>{counts[b.key] || 0}</span>
          </button>
        )
      })}
    </span>
  )
}

/** Переключатель-«тумблер» с подписью и необязательным числом («Мои 13», «По месяцам»). */
export function Toggle({ on, label, n, title, onClick }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={on}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 32, padding: '0 12px 0 8px', boxSizing: 'border-box',
        borderRadius: 10, background: 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
        fontFamily: UI, fontSize: 12.5, fontWeight: 700, color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
      <span style={{ position: 'relative', width: 26, height: 15, borderRadius: 8, background: on ? 'var(--accent)' : 'var(--text-disabled)', transition: 'background 160ms ease' }}>
        <span style={{ position: 'absolute', top: 2, left: on ? 13 : 2, width: 11, height: 11, borderRadius: '50%', background: 'var(--bg-card)', transition: 'left 160ms ease' }} />
      </span>
      {label}
      {n != null && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{n}</span>}
    </button>
  )
}

export const QUICK_SORTS = [['id', 'ID', 'Сначала новые медиапланы'], ['updated_at', 'Обновлён', 'Последние изменения сверху'],
  ['amount_gross', 'Сумма', 'Крупные сверху'], ['period', 'Период', 'По месяцу размещения']]

/** Блок «Порядок»: быстрый выбор колонки и кнопка направления. Колонка не из блока — в блоке ничего не подсвечено. */
export function SortBlock({ sortKey, dir, onSort, onDir }) {
  return (
    <>
      <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>Порядок</span>
      <span style={box}>
        {QUICK_SORTS.map(([k, label, t]) => {
          const on = sortKey === k
          return (
            <button key={k} type="button" title={t} onClick={() => onSort(k)} style={{ ...segItem(on), gap: 5 }}>
              {label}<span style={{ fontFamily: MONO, fontSize: 11 }}>{on ? (dir === 'desc' ? '↓' : '↑') : ''}</span>
            </button>
          )
        })}
      </span>
      <button type="button" onClick={onDir} title={`${dir === 'desc' ? 'по убыванию' : 'по возрастанию'} · нажмите, чтобы развернуть`}
        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, padding: 0, boxSizing: 'border-box',
          borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-secondary)', cursor: 'pointer',
          fontFamily: MONO, fontSize: 13, fontWeight: 700 }}>{dir === 'desc' ? '↓' : '↑'}</button>
    </>
  )
}

/** Заголовок месяца: растянут на видимую ширину таблицы (`100cqw`) и при прокрутке вбок не уезжает. */
export function GroupHead({ g, buckets, onToggle }) {
  const mix = buckets.filter(b => g.mix[b.key])
  const hint = g.continued ? 'продолжение' : g.current ? 'текущий месяц' : g.past ? `прошедший месяц${g.closed ? ' · свёрнут' : ''}` : ''
  return (
    <div onClick={onToggle} style={{ display: 'flex', alignItems: 'center', height: 42, borderBottom: '1px solid var(--border-inner)', background: 'var(--bg-subtle)', cursor: 'pointer' }}>
      <span style={{ position: 'sticky', left: 0, display: 'flex', alignItems: 'center', gap: 12, padding: '0 14px', boxSizing: 'border-box', width: 'var(--mpr-vw, 100cqw)',
        whiteSpace: 'nowrap', overflow: 'hidden' }}>
        <Chevron open={!g.closed} color="var(--text-secondary)" />
        <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{g.label}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>{g.n} МП</span>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color: 'var(--text-primary)' }}>{shortMoney(g.gross)}</span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>с НДС</span>
        <span style={{ display: 'inline-flex', gap: 10, marginLeft: 6 }}>
          {mix.map(b => (
            <span key={b.key} title={b.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
              <span style={dot(toneOf(b.key)[0])} />{b.label} <span style={{ fontFamily: MONO, fontWeight: 700 }}>{g.mix[b.key]}</span>
            </span>
          ))}
        </span>
        {g.visa > 0 && (
          <span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 7px', borderRadius: 6, background: 'var(--warning-tint)',
            border: '1px solid var(--warning-border)', fontSize: 11, fontWeight: 700, color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}>{g.visa} без визы</span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-faint)' }}>{hint}</span>
      </span>
    </div>
  )
}

const pgBtn = (on, off) => ({
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 30, height: 30, padding: '0 6px', boxSizing: 'border-box',
  // текущая страница — «таблетка» выбранного (NAVY: --hot; в прежних темах --hot = прежний вид)
  borderRadius: 9, border: `1px solid ${on ? 'var(--hot)' : 'var(--border-card)'}`, background: on ? 'var(--hot)' : 'var(--bg-card)',
  fontFamily: MONO, fontSize: 12.5, fontWeight: on ? 700 : 600, color: on ? 'var(--hot-fg)' : 'var(--text-secondary)',
  cursor: off ? 'default' : 'pointer', opacity: off ? 0.35 : 1,
})
const Arrow = ({ d }) => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
)

/** Низ таблицы: «Показаны 1–100 из 260», размер страницы, номера страниц. Всегда виден. */
export function RegistryFooter({ view, size, sizes = [100, 300, 500], onSize, onPage }) {
  const { page, pages, total, from, to } = view
  return (
    <div style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 14, height: 52, padding: '0 16px', borderTop: '1px solid var(--border-inner)', background: 'var(--bg-card)' }}>
      <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
        Показаны <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{total ? `${from}–${to}` : '0'}</span> из <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{total}</span>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)', marginLeft: 10 }}>на странице</span>
      <span style={{ display: 'inline-flex', padding: 2, borderRadius: 10, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
        {sizes.map(n => {
          const on = n === size
          return (
            <button key={n} type="button" onClick={() => onSize(n)} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 11px', borderRadius: 8, border: 'none',
              background: on ? 'var(--hot)' : 'transparent', boxShadow: on ? 'var(--shadow-card)' : 'none', color: on ? 'var(--hot-fg)' : 'var(--text-secondary)',
              fontFamily: MONO, fontSize: 12, fontWeight: on ? 700 : 600, cursor: 'pointer' }}>{n}</button>
          )
        })}
      </span>
      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <button type="button" title="Предыдущая страница" disabled={page <= 0} onClick={() => onPage(page - 1)} style={pgBtn(false, page <= 0)}><Arrow d="M10 3.5 5.5 8l4.5 4.5" /></button>
        {pageWindow(page, pages).map((n, i) => (n === null
          ? <span key={`gap${i}`} style={{ color: 'var(--text-faint)', padding: '0 2px' }}>…</span>
          : <button key={n} type="button" onClick={() => onPage(n)} style={pgBtn(n === page, false)}>{n + 1}</button>))}
        <button type="button" title="Следующая страница" disabled={page >= pages - 1} onClick={() => onPage(page + 1)} style={pgBtn(false, page >= pages - 1)}><Arrow d="m6 3.5 4.5 4.5L6 12.5" /></button>
      </span>
    </div>
  )
}
