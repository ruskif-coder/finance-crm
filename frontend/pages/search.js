/**
 * Результаты глобального поиска. Спецификация: docs/SPEC_глобальный_поиск.md, дизайн —
 * хендофф docs/поиск.zip (README §4–5).
 *
 * Сквозной экран, как /exec: пункта меню и своего права нет, открывается только из строки
 * поиска в шапке. Данных он не владеет — каждая группа закрыта на сервере правом своего
 * типа, поэтому «нет доступа» здесь не бывает: скрытое неотличимо от ненайденного.
 *
 * Запрос приходит через sessionStorage, а не `?q=`: ИНН и названия юрлиц в адресе осели бы
 * в журналах Caddy. Цена — результатами нельзя поделиться ссылкой (принято владельцем).
 */
import { useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import { MONO, UI } from '@/components/salesTableKit'
import { PageRow } from '@/components/search/ResultRow'
import useSearch from '@/components/search/useSearch'
import {
  SEARCH_HINT, SEARCH_HINT_TEXT, SEARCH_MAX, TYPE_LABELS, internalHref, readQuery, saveQuery, searchApi, searchError,
  searchable,
} from '@/lib/search'

const PER_PAGE = 50
const CARD = {
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)',
  borderRadius: 18,
}
const BTN = {
  display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: UI, fontSize: 12, fontWeight: 600,
  cursor: 'pointer',
}
const anchorOf = (type) => `g-${type}`

// Карточки групп появляются лесенкой; наведение строк и чипов — классами (инлайн-стиль
// наведения не умеет). Отступ якоря — под липкую шапку.
const PAGE_CSS = `
  @keyframes srchRise { from { opacity:0; transform:translateY(10px) } to { opacity:1; transform:none } }
  @keyframes srchPulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }
  @media (prefers-reduced-motion: reduce) { .srch-card { animation:none !important } }
  .srch-row:hover { background: var(--bg-tint) }
  .srch-chip:hover, .srch-more:hover { border-color: var(--border-hover) !important; color: var(--accent) !important }
  .srch-page-input::placeholder { color: var(--text-disabled) }
`

function Group({ group, q, index, onOpen }) {
  const [extra, setExtra] = useState([])
  const [more, setMore] = useState(group.more)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { setExtra([]); setMore(group.more); setErr('') }, [group, q])

  const loadMore = async () => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      const d = await searchApi(q, { types: [group.type], perType: PER_PAGE,
                                     offset: group.items.length + extra.length })
      const g = (d.groups || []).find(x => x.type === group.type)
      setExtra(prev => [...prev, ...(g ? g.items : [])])
      setMore(!!g?.more)
    } catch (e) {
      setErr(searchError(e))
    } finally {
      setBusy(false)
    }
  }

  const items = [...group.items, ...extra]
  return (
    <section id={anchorOf(group.type)} className="srch-card" style={{
      ...CARD, padding: '14px 18px 10px', display: 'flex', flexDirection: 'column', minWidth: 0,
      scrollMarginTop: 90,
      animation: `srchRise .4s cubic-bezier(0.22,1,0.36,1) ${(0.05 + index * 0.05).toFixed(2)}s both`,
    }}>
      <span style={{ padding: '0 8px 6px', fontFamily: MONO, fontSize: 10, fontWeight: 700,
                     letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        {TYPE_LABELS[group.type] || group.type}
      </span>
      {items.map(it => <PageRow key={it.id} item={it} q={q} onOpen={onOpen} />)}
      {(more || !!err) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 8px 2px', flexWrap: 'wrap' }}>
          {more && (
            <button type="button" className="srch-more" onClick={loadMore} disabled={busy}
              style={{ ...BTN, color: busy ? 'var(--text-faint)' : 'var(--accent)' }}>
              {busy ? 'Загружаю…' : 'Показать ещё'}
            </button>
          )}
          {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
        </div>
      )}
    </section>
  )
}

/** Одна карточка по центру вместо групп: мало символов, идёт поиск, пусто, ошибка. */
function Note({ tone = 'plain', title, text, onRetry }) {
  const error = tone === 'error'
  return (
    <div style={{
      ...CARD, boxShadow: 'none', background: error ? 'var(--danger-bg)' : 'var(--bg-card)',
      borderColor: error ? 'var(--danger-border)' : 'var(--border-card)',
      padding: '30px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
    }}>
      <span style={{
        fontSize: 14, fontWeight: 700,
        color: error ? 'var(--danger-fg)' : tone === 'loading' ? 'var(--accent)' : 'var(--text-secondary)',
        animation: tone === 'loading' ? 'srchPulse 1.2s ease-in-out infinite' : 'none',
      }}>{title}</span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>{text}</span>
      {onRetry && (
        <button type="button" onClick={onRetry}
          style={{ ...BTN, height: 32, marginTop: 6, padding: '0 14px', fontSize: 12.5, color: 'var(--accent)' }}>
          Повторить
        </button>
      )}
    </div>
  )
}

export default function SearchPage() {
  const router = useRouter()
  const [q, setQ] = useState('')
  useEffect(() => { setQ(readQuery()) }, [])
  useEffect(() => { const s = searchable(q); if (s) saveQuery(s) }, [q])

  const { q: forQ, groups, error, retry } = useSearch(q, { perType: PER_PAGE })
  const s = searchable(q)
  const ready = !!s && forQ === s
  const full = q.length >= SEARCH_MAX

  let note = null
  if (!s) note = <Note title="Введите хотя бы 2 символа" text={SEARCH_HINT_TEXT} />
  else if (error) note = <Note tone="error" title="Поиск не ответил" text={error} onRetry={retry} />
  else if (!ready) note = <Note tone="loading" title="Ищу…" text="новая выдача появится после ответа сервера" />
  else if (!groups.length) note = <Note title="Ничего не найдено" text={SEARCH_HINT_TEXT} />

  return (
    <>
      <Head><title>Поиск | SIMB-AD ERP</title></Head>
      <Navbar />
      <style>{PAGE_CSS}</style>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '22px 16px 60px', fontFamily: UI,
                    display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
        <div style={{ ...CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, height: 46, boxSizing: 'border-box',
                          padding: '0 14px', background: 'var(--bg-subtle)',
                          border: '1px solid var(--accent-border)', borderRadius: 12 }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2"
              strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.2-3.2" /></svg>
            <input className="srch-page-input" value={q} onChange={e => setQ(e.target.value)}
              placeholder={SEARCH_HINT} aria-label="Поиск" maxLength={SEARCH_MAX} autoFocus
              style={{ flex: 1, minWidth: 0, height: '100%', background: 'transparent', border: 'none',
                       outline: 'none', fontFamily: UI, fontSize: 15, fontWeight: 600,
                       color: 'var(--text-primary)' }} />
            <span style={{ fontFamily: MONO, fontSize: 10, whiteSpace: 'nowrap',
                           color: full ? 'var(--danger-fg)' : 'var(--text-faint)' }}>
              {q.length} / {SEARCH_MAX}
            </span>
          </label>
          {ready && groups.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase',
                             color: 'var(--text-faint)', paddingRight: 4 }}>перейти к</span>
              {groups.map(g => (
                <a key={g.type} href={`#${anchorOf(g.type)}`} className="srch-chip"
                  style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 11px',
                           borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                           color: 'var(--text-secondary)', fontSize: 12, fontWeight: 600,
                           textDecoration: 'none', whiteSpace: 'nowrap' }}>
                  {TYPE_LABELS[g.type] || g.type}
                </a>
              ))}
            </div>
          )}
        </div>

        {note}
        {!note && groups.map((g, i) => (
          <Group key={`${forQ}-${g.type}`} group={g} q={forQ} index={i}
            onOpen={it => router.push(internalHref(it.href))} />
        ))}
      </div>
    </>
  )
}
