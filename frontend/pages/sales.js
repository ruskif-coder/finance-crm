import { useState, useEffect } from 'react'
import Head from 'next/head'
import axios from 'axios'
import { useRouter } from 'next/router'
import Navbar, { can } from '../components/Navbar'

const api = axios.create({ baseURL: '/api' })

const LAYERS = ['планируемые', 'реализуемые', 'фактические']
const LAYER_COLOR = {
  'планируемые': 'var(--muted)',
  'реализуемые': 'var(--accent)',
  'фактические': 'var(--success)',
  'Без группы': 'var(--danger)',
}
const PAGE_SIZES = [50, 100, 300, 500]

const fmtMoney = (v) => {
  if (v === null || v === undefined) return '—'
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + ' млн'
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(0) + ' тыс'
  return String(Math.round(v))
}
const fmtDate = (d) => (d ? String(d).slice(0, 10) : '—')

/** Пустое значение показывается явно: незаполненное поле — это факт о данных. */
const Empty = () => <span style={{ color: 'var(--danger)', opacity: 0.65 }}>—</span>
const cell = (v) => (v === null || v === undefined || v === '' ? <Empty /> : v)

// sortable: ключ поддерживается бэкендом в /api/sales/deals.
// Бренд и плательщик пока не сортируются — по ним нет джойна на сервере.
const COLUMNS = [
  { key: 'bitrix_id', label: 'ID', w: 62, sortable: true },
  { key: 'title', label: 'Сделка', w: 260, sortable: true },
  { key: 'pipeline', label: 'Воронка', w: 110, sortable: true },
  { key: 'bitrix_stage', label: 'Стадия', w: 170, sortable: true },
  { key: 'money_layer', label: 'Слой денег', w: 118, sortable: true },
  { key: 'amount', label: 'Сумма', w: 100, right: true, sortable: true },
  { key: 'advertiser', label: 'Рекламодатель', w: 200, sortable: true },
  { key: 'brand', label: 'Бренд', w: 130 },
  { key: 'sales_rep', label: 'Продавец', w: 140, sortable: true },
  { key: 'account_manager', label: 'Аккаунт', w: 140, sortable: true },
  { key: 'counterparty', label: 'Плательщик', w: 160 },
  { key: 'period_from', label: 'Старт РК', w: 96, sortable: true },
  { key: 'period_to', label: 'Конец РК', w: 96, sortable: true },
]

export default function Sales() {
  const router = useRouter()
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [perms, setPerms] = useState({})
  const [pageSize, setPageSize] = useState(100)
  const [sort, setSort] = useState({ key: 'period_from', dir: 'desc' })
  const [f, setF] = useState({ date_from: '', date_to: '', money_layer: '', pipeline: '', search: '' })

  const params = (extra = {}) => {
    const p = { ...extra }
    Object.entries(f).forEach(([k, v]) => { if (v) p[k] = v })
    return p
  }

  const load = async (newOffset = 0, size = pageSize, s = sort) => {
    setLoading(true); setError('')
    const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` }
    try {
      const [reg, sum] = await Promise.all([
        api.get('/sales/deals', {
          params: params({ limit: size, offset: newOffset, sort: s.key, direction: s.dir }),
          headers,
        }),
        api.get('/sales/dashboard', { params: params(), headers }),
      ])
      setRows(reg.data.items); setTotal(reg.data.total); setOffset(newOffset)
      setSummary(sum.data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Не удалось загрузить данные')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    try { setPerms(JSON.parse(localStorage.getItem('permissions') || '{}')) } catch (e) { setPerms({}) }
    load(0)
  }, [])

  const inputStyle = {
    padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 'var(--radius-input)',
    fontSize: 13, background: 'var(--bg-card)', color: 'inherit',
  }
  const btn = (primary) => ({
    padding: '7px 15px', borderRadius: 'var(--radius-btn)', border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500,
    background: primary ? 'var(--accent)' : 'var(--bg-subtle)', color: primary ? '#fff' : 'inherit',
  })
  const th = (c) => ({
    position: 'sticky', top: 0, background: 'var(--bg-subtle)', zIndex: 1,
    padding: '9px 10px', textAlign: c.right ? 'right' : 'left', fontSize: 11.5,
    fontWeight: 600, whiteSpace: 'nowrap', minWidth: c.w,
    color: sort.key === c.key ? 'var(--accent)' : 'var(--muted)',
    borderBottom: '1px solid var(--border-card)',
    cursor: c.sortable ? 'pointer' : 'default',
    userSelect: 'none',
  })

  // Первый клик по колонке — по убыванию (обычно интересует «самое большое сверху»),
  // повторный — переключение направления.
  const toggleSort = (c) => {
    if (!c.sortable) return
    const dir = sort.key === c.key && sort.dir === 'desc' ? 'asc' : 'desc'
    const next = { key: c.key, dir }
    setSort(next); load(0, pageSize, next)
  }
  const td = (c) => ({
    padding: '7px 10px', fontSize: 12.5, textAlign: c.right ? 'right' : 'left',
    borderBottom: '1px solid var(--border-row)', maxWidth: c.w,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
    fontVariantNumeric: c.right ? 'tabular-nums' : 'normal',
  })

  const t = summary?.totals

  return (
    <>
      <Head><title>Реестр сделок</title></Head>
      <Navbar active="sales" />
      <div style={{ maxWidth: 1920, margin: '0 auto', padding: '20px 24px 50px' }}>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap', marginBottom: 14 }}>
          <h1 style={{ fontSize: 19, fontWeight: 600, margin: 0 }}>Реестр сделок</h1>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>
            {summary?.last_sync_at
              ? `синхронизировано: ${new Date(summary.last_sync_at).toLocaleString('ru-RU')}`
              : 'источник: выгрузка Excel, Битрикс24 не подключён'}
          </span>
        </div>

        {/* Сводка по текущему фильтру */}
        {t && (
          <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', marginBottom: 14, fontSize: 13 }}>
            <span><b>{t.deals}</b> сделок</span>
            <span><b>{fmtMoney(t.amount)}</b></span>
            {summary.by_layer.map(b => (
              <span key={b.name} style={{ color: LAYER_COLOR[b.name] }}>
                {b.name}: <b>{b.deals}</b> · {fmtMoney(b.amount)}
              </span>
            ))}
            <span style={{ color: t.deals_without_period ? 'var(--danger)' : 'var(--muted)' }}>
              без периода: <b>{t.deals_without_period}</b>
            </span>
            <span style={{ color: t.reconciles ? 'var(--success)' : 'var(--danger)' }}>
              сверка: {t.reconciles ? 'сходится' : 'РАСХОЖДЕНИЕ'}
            </span>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          <input style={{ ...inputStyle, width: 210 }} placeholder="поиск по названию или ID"
            value={f.search} onChange={e => setF({ ...f, search: e.target.value })} />
          <input style={{ ...inputStyle, width: 110 }} placeholder="с (2026-01)"
            value={f.date_from} onChange={e => setF({ ...f, date_from: e.target.value })} />
          <input style={{ ...inputStyle, width: 110 }} placeholder="по (2026-12)"
            value={f.date_to} onChange={e => setF({ ...f, date_to: e.target.value })} />
          <select style={inputStyle} value={f.money_layer} onChange={e => setF({ ...f, money_layer: e.target.value })}>
            <option value="">все слои</option>
            {LAYERS.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <select style={inputStyle} value={f.pipeline} onChange={e => setF({ ...f, pipeline: e.target.value })}>
            <option value="">все воронки</option>
            {(summary?.by_pipeline || []).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
          <button style={btn(true)} onClick={() => load(0)}>Показать</button>
          <button style={btn(false)} onClick={() => {
            setF({ date_from: '', date_to: '', money_layer: '', pipeline: '', search: '' })
            setTimeout(() => load(0), 0)
          }}>Сбросить</button>
          {can(perms, 'sales_dashboard', 'edit') && (
            <button style={btn(false)} onClick={async () => {
              try {
                await api.post('/sales/sync', {}, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
                load(offset)
              } catch (e) { setError(e.response?.data?.detail || 'Синхронизация недоступна') }
            }}>Синхронизировать</button>
          )}
        </div>

        {error && (
          <div style={{
            background: 'var(--danger-tint)', border: '1px solid var(--danger)', color: 'var(--danger)',
            padding: '10px 14px', borderRadius: 'var(--radius-card-sm)', marginBottom: 14, fontSize: 13,
          }}>{error}</div>
        )}

        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-card)',
          borderRadius: 'var(--radius-card)', overflow: 'hidden',
        }}>
          <div style={{ overflowX: 'auto', maxHeight: '62vh' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{COLUMNS.map(c => (
                <th key={c.key} style={th(c)} onClick={() => toggleSort(c)}
                    title={c.sortable ? 'Сортировать' : 'Сортировка недоступна'}>
                  {c.label}
                  {sort.key === c.key && <span> {sort.dir === 'desc' ? '↓' : '↑'}</span>}
                </th>
              ))}</tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id}>
                    {COLUMNS.map(c => {
                      let v = r[c.key]
                      if (c.key === 'amount') v = r.amount === null ? null : fmtMoney(r.amount)
                      if (c.key === 'period_from' || c.key === 'period_to') v = r[c.key] ? fmtDate(r[c.key]) : null
                      return (
                        <td key={c.key} style={{
                          ...td(c),
                          color: c.key === 'money_layer' ? LAYER_COLOR[r.money_layer] : undefined,
                          fontWeight: c.key === 'money_layer' ? 600 : undefined,
                        }} title={typeof v === 'string' ? v : undefined}>{cell(v)}</td>
                      )
                    })}
                  </tr>
                ))}
                {!loading && !rows.length && (
                  <tr><td colSpan={COLUMNS.length} style={{ padding: 26, textAlign: 'center', color: 'var(--muted)' }}>
                    Ничего не найдено
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12, fontSize: 13, flexWrap: 'wrap' }}>
          <button style={btn(false)} disabled={offset === 0}
            onClick={() => load(Math.max(0, offset - pageSize))}>← Назад</button>
          <span style={{ color: 'var(--muted)' }}>
            {total ? `${offset + 1}–${Math.min(offset + pageSize, total)} из ${total}` : '0'}
          </span>
          <button style={btn(false)} disabled={offset + pageSize >= total}
            onClick={() => load(offset + pageSize)}>Вперёд →</button>
          <span style={{ color: 'var(--muted)', marginLeft: 8 }}>строк:</span>
          <select style={inputStyle} value={pageSize} onChange={e => {
            const size = Number(e.target.value)
            setPageSize(size); load(0, size)
          }}>
            {PAGE_SIZES.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          {loading && <span style={{ color: 'var(--muted)' }}>загрузка…</span>}
        </div>
      </div>
    </>
  )
}
