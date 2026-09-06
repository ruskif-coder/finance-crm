/**
 * Реестр приложений к договору (ДС) — справочник.
 *
 * Учёт номеров, о котором просил владелец: что выпущено, под каким номером, по какому
 * договору и на какие сделки разнесено. Черновики идут первыми — это незакрытая работа,
 * а не архив.
 *
 * Вёрстка по канону реестров справочников (`pages/directory/counterparties/index.js`):
 * CSS-grid одной сеткой на шапку и строки, сортировка кликом по заголовку, поиск и
 * выпадающие фильтры в шапке карточки. Свои стили тут заводить нельзя — расходятся.
 *
 * Экран только читает и открывает: приложение создаётся там, где есть сделка и сумма
 * (карточка сделки), а не в реестре документов.
 */
import { useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/http'
import Navbar from '@/components/Navbar'
import SectionTabs from '@/components/SectionTabs'
import { MONO, UI, IconBtn } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'
import { T } from '@/lib/tokens'

const dm = (d) => (d ? new Date(d).toLocaleDateString('ru-RU') : '—')

// Сетка одна на шапку и строки. Порядок колонок — владелец 05.09.2026: сперва ЧЬЁ и по
// какому договору, потом сам документ, в конце выгрузка.
const COLS = [
  ['payer', 'minmax(230px,1.4fr)', 'Юрлицо', 'counterparty_name'],
  ['inn', '116px', 'ИНН', 'counterparty_inn'],
  ['contract', '150px', 'Договор', 'contract_number'],
  ['cdate', '96px', 'Дата дог.', 'contract_date'],
  ['number', '132px', 'Приложение', 'no'],
  ['date', '96px', 'Дата', 'date'],
  ['period', '176px', 'Период', 'period_from'],
  ['deals', '132px', 'Сделки'],
  ['amount', '128px', 'Сумма с НДС', 'total_amount'],
  ['files', '92px', ''],
]
const RIGHT = new Set(['amount'])

/** Заголовок-сортировщик. Объявлен на уровне модуля: компонент, созданный внутри другого,
 *  пересоздаётся на каждый рендер, и React размонтирует поддерево (гейт check-inline). */
function HeadCell({ k, label, sortKey, sortCol, sortDir, onSort }) {
  const active = sortCol === sortKey
  return (
    <div onClick={() => onSort(sortKey)} style={{ padding: '0 8px 10px', fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: active ? 'var(--accent)' : 'var(--text-faint)', textAlign: RIGHT.has(k) ? 'right' : 'left', cursor: sortKey ? 'pointer' : 'default', userSelect: 'none', whiteSpace: 'nowrap' }}>
      {label}{active && <span> {sortDir === 'asc' ? '↑' : '↓'}</span>}
    </div>
  )
}
const GRID = COLS.map(c => c[1]).join(' ')

export default function AnnexRegistry() {
  const router = useRouter()
  const [items, setItems] = useState([])
  // Реестр отдаётся с потолком. Сколько всего — приходит отдельным числом: молча
  // обрезанный список выглядит как «документ пропал», и искать будут документ, а не
  // страницу.
  const [total, setTotal] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [stateFilter, setStateFilter] = useState('')
  const [payerFilter, setPayerFilter] = useState('')
  const [sortCol, setSortCol] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/annexes', auth())
        setItems(r.data.items || [])
        setTotal(r.data.total ?? (r.data.items || []).length)
        setTruncated(!!r.data.truncated)
      } catch (e) { setError(e.response?.data?.detail || 'Не удалось загрузить реестр') }
      finally { setLoading(false) }
    })()
  }, [])

  const handleSort = (col) => {
    if (!col) return
    setSortDir(d => (sortCol === col ? (d === 'asc' ? 'desc' : 'asc') : 'asc'))
    setSortCol(col)
  }

  const q = search.trim().toLowerCase()
  const filtered = items
    .filter(a => {
      if (stateFilter === 'draft' && !a.is_draft) return false
      if (stateFilter === 'issued' && a.is_draft) return false
      if (payerFilter && a.counterparty_name !== payerFilter) return false
      if (q) {
        const hay = [a.number, a.counterparty_name, a.counterparty_inn, a.contract_number,
                     ...(a.deals || []).map(d => d.code)]
        if (!hay.some(v => (v || '').toLowerCase().includes(q))) return false
      }
      return true
    })
    .sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol]
      let cmp
      if (typeof av === 'number' || typeof bv === 'number') cmp = (av || 0) - (bv || 0)
      else cmp = String(av || '').localeCompare(String(bv || ''), 'ru')
      return sortDir === 'asc' ? cmp : -cmp
    })

  const payers = [...new Set(items.map(a => a.counterparty_name).filter(Boolean))].sort(
    (a, b) => a.localeCompare(b, 'ru'))

  const resetFilters = () => {
    setSearch(''); setStateFilter(''); setPayerFilter('')
    setSortCol('date'); setSortDir('desc')
  }

  /** Скачать документ строки. Имя файла приходит с сервера — там же, где собирается. */
  const grab = async (e, id, kind) => {
    e.stopPropagation()
    setBusy(`${id}:${kind}`)
    try {
      const r = await api.get(`/annexes/${id}/${kind}`, { ...auth(), responseType: 'blob' })
      const cd = r.headers['content-disposition'] || ''
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd)
      const url = URL.createObjectURL(r.data)
      const link = document.createElement('a')
      link.href = url
      link.download = m ? decodeURIComponent(m[1]) : `ДС.${kind}`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      // Отказ приходит блобом: без чтения тела на экране было бы общее «не удалось»,
      // хотя сервер прислал, ЧЕГО не хватает для выпуска документа.
      let msg = 'Не удалось выгрузить документ'
      try { msg = JSON.parse(await err.response.data.text()).detail || msg } catch (_) { /* не JSON */ }
      setError(msg)
    } finally { setBusy('') }
  }

  /** Выгрузка в Excel. Порядок строк ЗАДАЁТ ЭКРАН — сервер получает готовый список id и
   *  соблюдает его, поэтому выгрузка совпадает с тем, что человек видел перед нажатием. */
  const exportXlsx = async () => {
    setBusy('xlsx')
    try {
      const r = await api.post('/annexes/export.xlsx', { ids: filtered.map(a => a.id) },
                               { ...auth(), responseType: 'blob' })
      const cd = r.headers['content-disposition'] || ''
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd)
      const url = URL.createObjectURL(r.data)
      const link = document.createElement('a')
      link.href = url
      link.download = m ? decodeURIComponent(m[1]) : 'Приложения.xlsx'
      link.click()
      URL.revokeObjectURL(url)
    } catch (e) { setError(e.response?.data?.detail || 'Не удалось выгрузить реестр') }
    finally { setBusy('') }
  }

  const chipSel = { appearance: 'none', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '7px 26px 7px 12px', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: UI, outline: 'none', backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%278%27 height=%275%27%3E%3Cpath d=%27M0 0l4 5 4-5z%27 fill=%27%23A3ABBD%27/%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center' }
  const cell = { padding: '0 8px', fontSize: 13, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
  const fileBtn = { display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 7px', border: '1px solid var(--border-card)', borderRadius: 7, background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 10, fontWeight: 700, cursor: 'pointer' }

  return (
    <>
      <Head><title>Приложения к договорам</title></Head>
      <Navbar active="directories" />
      <div style={{ padding: '20px 26px 50px', background: 'var(--bg-canvas)', minHeight: '100vh', fontFamily: UI }}>
        <SectionTabs section="directory" />

        {error && <div style={{ background: 'var(--danger-tint)', color: T.danger, padding: '10px 14px', borderRadius: 12, marginBottom: 12, fontSize: 13 }}>{error}</div>}

        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '18px 24px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>Приложения</h1>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${searchOpen || search ? 'var(--accent)' : 'var(--border-card)'}`, borderRadius: 10, padding: '0 10px', height: 34, width: searchOpen || search ? 260 : 150, transition: 'width 200ms ease' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'var(--text-faint)', strokeWidth: 1.8, strokeLinecap: 'round' }}><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg>
              <input value={search} onFocus={() => setSearchOpen(true)} onBlur={() => setSearchOpen(false)} onChange={e => setSearch(e.target.value)} placeholder="Номер, ИНН, договор…" style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontSize: 13, fontFamily: UI, color: 'var(--text-primary)' }} />
            </div>
            <select value={stateFilter} onChange={e => setStateFilter(e.target.value)} style={chipSel}>
              <option value="">Все состояния</option>
              <option value="issued">Выпущенные</option>
              <option value="draft">Черновики</option>
            </select>
            <select value={payerFilter} onChange={e => setPayerFilter(e.target.value)} style={chipSel}>
              <option value="">Все юрлица</option>
              {payers.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <IconBtn title="Сбросить фильтры" onClick={resetFilters}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
              <IconBtn title="Выгрузить в Excel — в том же порядке, что на экране" onClick={exportXlsx}><svg width="15" height="15" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg></IconBtn>
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '2px 0 6px' }}>
            <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              показано {filtered.length} из {total}
            </span>
            {truncated && (
              <span style={{ fontSize: 11.5, color: 'var(--warning-text)' }}>
                загружены только последние {items.length} — поиск и выгрузка идут по ним
              </span>
            )}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 12, fontSize: 11.5, color: 'var(--text-muted)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><i style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--income)' }} />выпущено</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><i style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--text-faint)' }} />черновик</span>
            </span>
          </div>

          {loading ? <div style={{ padding: 30, color: 'var(--text-muted)' }}>Загрузка…</div> : (
            <div style={{ overflowX: 'auto' }}>
              <div style={{ minWidth: 1300 }}>
                <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, borderBottom: '1px solid var(--border-card)' }}>
                  {COLS.map(([k, w, label, sortKey]) => (
                    <HeadCell key={k} k={k} label={label} sortKey={sortKey}
                              sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  ))}
                </div>
                {filtered.map(a => (
                  <div key={a.id} onClick={() => router.push(`/directory/annexes/${a.id}`)}
                       style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border-row)', borderRadius: 10, cursor: 'pointer' }}
                       onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-subtle)' }}
                       onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                    <div style={{ ...cell, fontWeight: 600 }} title={a.counterparty_name || ''}>
                      <i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, marginRight: 7, background: a.is_draft ? 'var(--text-faint)' : 'var(--income)' }} />
                      {a.counterparty_name || '—'}
                    </div>
                    <div style={{ ...cell, fontFamily: MONO, fontSize: 12 }}>{a.counterparty_inn || '—'}</div>
                    <div style={{ ...cell, fontFamily: MONO, fontSize: 12 }} title={a.contract_number || ''}>{a.contract_number || '—'}</div>
                    <div style={{ ...cell, fontFamily: MONO, fontSize: 12 }}>{dm(a.contract_date)}</div>
                    <div style={{ ...cell, fontWeight: 700 }}>
                      {a.number || <span style={{ color: 'var(--text-faint)', fontWeight: 600 }}>черновик</span>}
                    </div>
                    <div style={{ ...cell, fontFamily: MONO, fontSize: 12 }}>{dm(a.date)}</div>
                    <div style={{ ...cell, fontFamily: MONO, fontSize: 12 }}>{dm(a.period_from)} — {dm(a.period_to)}</div>
                    <div style={cell}>
                      {(a.deals || []).length
                        ? a.deals.map(d => (
                            <a key={d.id} href={`/sales/deals/${d.code || d.id}`} onClick={e => e.stopPropagation()}
                               style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none', marginRight: 6 }}>
                              {d.code || d.id}
                            </a>
                          ))
                        : '—'}
                    </div>
                    <div style={{ ...cell, textAlign: 'right', fontFamily: MONO, fontWeight: 700 }}>{grp(a.total_amount)}</div>
                    <div style={{ ...cell, display: 'inline-flex', gap: 5, overflow: 'visible' }}>
                      <span onClick={e => grab(e, a.id, 'docx')} style={fileBtn}>
                        {busy === `${a.id}:docx` ? '…' : 'DOC'}
                      </span>
                      <span onClick={e => grab(e, a.id, 'pdf')} style={fileBtn}>
                        {busy === `${a.id}:pdf` ? '…' : 'PDF'}
                      </span>
                    </div>
                  </div>
                ))}
                {/* Пусто и «ещё грузится» — разные утверждения, и выглядеть должны по-разному. */}
                {!filtered.length && (
                  <div style={{ padding: '18px 0 22px', fontSize: 13, color: 'var(--text-secondary)' }}>
                    {items.length ? 'Ничего не нашлось по запросу.' : 'Приложений пока нет — они создаются из карточки сделки.'}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
