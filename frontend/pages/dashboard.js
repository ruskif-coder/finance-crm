import Navbar from '../components/Navbar'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, LineChart, Line } from 'recharts'

const api = (token) => axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n || 0))
const fmtM = (n) => (n / 1000000).toFixed(2) + ' млн'

const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const BANK_COLORS = { 'АльфаБанк': '#2563eb', 'ОПТ Банк': '#16a34a', 'Совкомбанк': '#d97706', 'Наличные': '#7c3aed' }

const MONTH_NAMES = {
  '01': 'Янв', '02': 'Фев', '03': 'Мар', '04': 'Апр',
  '05': 'Май', '06': 'Июн', '07': 'Июл', '08': 'Авг',
  '09': 'Сен', '10': 'Окт', '11': 'Ноя', '12': 'Дек'
}

const formatPeriod = (p) => {
  if (!p) return '—'
  const [year, month] = p.split('-')
  return `${MONTH_NAMES[month] || month} ${year}`
}

export default function Dashboard() {
  const router = useRouter()
  const [tab, setTab] = useState('dds')
  const [ddsData, setDdsData] = useState({ periods: [], banks: [] })
  const [ddsSummary, setDdsSummary] = useState(null)
  const [pl, setPl] = useState([])
  const [planFact, setPlanFact] = useState([])
  const [balance, setBalance] = useState(null)
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [selectedBank, setSelectedBank] = useState('all')
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 11)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [dateTo, setDateTo] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [expandedPeriod, setExpandedPeriod] = useState(null)
  const [groupBy, setGroupBy] = useState('period')

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    setName(localStorage.getItem('name') || '')
    loadAll(token)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) loadDds(token)
  }, [dateFrom, dateTo, selectedBank, groupBy])

  const loadAll = async (token) => {
    setLoading(true)
    try {
      const a = api(token)
      const [ddsRes, summaryRes, plRes, pfRes, balRes] = await Promise.all([
        a.get(`/reports/dds?date_from=${dateFrom}&date_to=${dateTo}&group_by=${groupBy}`),
        a.get('/reports/dds/summary'),
        a.get('/reports/pl'),
        a.get('/reports/plan-fact'),
        a.get('/reports/balance'),
      ])
      setDdsData(ddsRes.data || { periods: [], banks: [] })
      setDdsSummary(summaryRes.data || null)
      setPl(Array.isArray(plRes.data) ? plRes.data : [])
      setPlanFact(Array.isArray(pfRes.data) ? pfRes.data : [])
      setBalance(balRes.data || null)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const loadDds = async (token) => {
    try {
      const a = api(token)
      const bankParam = selectedBank !== 'all' ? `&bank=${selectedBank}` : ''
      const res = await a.get(`/reports/dds?date_from=${dateFrom}&date_to=${dateTo}${bankParam}&group_by=${groupBy}`)
      setDdsData(res.data || { periods: [], banks: [] })
    } catch (e) {}
  }

  const logout = () => { localStorage.clear(); router.push('/login') }

  const tabs = [
    { id: 'dds', label: 'ДДС' },
    { id: 'pl', label: 'P&L', link: '/pl' },
    { id: 'balance', label: 'Баланс', link: '/balance' },
    { id: 'planfact', label: 'План / Факт' },
  ]

  const periods = ddsData?.periods || []

  const ddsChart = periods.map(p => ({
    period: formatPeriod(p.period),
    'Поступления': Math.round(p.total_income || 0),
    'Списания': Math.round(p.total_expense || 0),
    'Остаток': Math.round(p.cumulative || 0),
  }))

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <Navbar active="dds" />

      <div style={{ padding: '24px 32px' }}>

        {loading ? <div style={{ textAlign: 'center', padding: '60px', color: 'var(--muted)' }}>Загрузка...</div> : <>

          {/* ДДС */}
          {tab === 'dds' && (
            <div>
              {/* Сводные метрики */}
              {ddsSummary && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '12px', marginBottom: '20px' }}>
                  {(() => {
                    const actualBalance = ddsSummary.total_balance ?? ddsSummary.net
                    const planNet = (ddsSummary.plan_income || 0) - (ddsSummary.plan_expense || 0)
                    const forecastBalance = actualBalance + planNet
                    return [
                      { label: 'Актуальный баланс', val: fmt(actualBalance) + ' ₽', color: actualBalance >= 0 ? 'var(--success)' : 'var(--danger)' },
                      { label: 'Прогнозный баланс', val: fmt(forecastBalance) + ' ₽', color: forecastBalance >= 0 ? 'var(--primary)' : 'var(--danger)', sub: `план: +${fmt(ddsSummary.plan_income || 0)} ₽ / -${fmt(ddsSummary.plan_expense || 0)} ₽` },
                      { label: 'План поступлений', val: fmt(ddsSummary.plan_income) + ' ₽', color: 'var(--warning)' },
                      { label: 'План расходов', val: fmt(ddsSummary.plan_expense) + ' ₽', color: 'var(--warning)' },
                    ]
                  })().map(m => (
                    <div key={m.label} style={{ background: 'var(--card)', borderRadius: '12px', padding: '14px 18px' }}>
                      <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>{m.label}</div>
                      <div style={{ fontSize: '18px', fontWeight: '600', color: m.color }}>{m.val}</div>
                      {m.sub && <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>{m.sub}</div>}
                    </div>
                  ))}
                </div>
              )}

              {/* Остатки по банкам */}
              {ddsSummary && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '12px', marginBottom: '20px' }}>
                  {(ddsSummary.by_bank || []).map(b => (
                    <div key={b.bank} style={{ background: 'var(--card)', borderRadius: '12px', padding: '14px 18px', borderLeft: `4px solid ${BANK_COLORS[b.bank] || '#6b7280'}` }}>
                      <div style={{ fontSize: '12px', fontWeight: '500', marginBottom: '6px' }}>{b.bank}</div>
                      <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Поступило: {fmt(b.income)} ₽</div>
                      <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Списано: {fmt(b.expense)} ₽</div>
                      <div style={{ fontSize: '16px', fontWeight: '600', marginTop: '6px', color: b.balance >= 0 ? 'var(--success)' : 'var(--danger)' }}>{fmt(b.balance)} ₽</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Фильтры */}
              <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '16px 20px', marginBottom: '16px', display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>С периода</label>
                  <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                    style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border)', fontSize: '13px' }} />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>По период</label>
                  <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)}
                    style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border)', fontSize: '13px' }} />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>Банк</label>
                  <select value={selectedBank} onChange={e => setSelectedBank(e.target.value)}
                    style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border)', fontSize: '13px' }}>
                    <option value="all">Все банки</option>
                    {BANKS.map(b => <option key={b} value={b}>{b}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>Группировка</label>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button onClick={() => setGroupBy('period')}
                      style={{ padding: '6px 12px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '13px', background: groupBy === 'period' ? 'var(--primary)' : 'var(--card)', color: groupBy === 'period' ? 'white' : 'var(--text)', border: '1px solid var(--border)' }}>
                      По периоду
                    </button>
                    <button onClick={() => setGroupBy('date')}
                      style={{ padding: '6px 12px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '13px', background: groupBy === 'date' ? 'var(--primary)' : 'var(--card)', color: groupBy === 'date' ? 'white' : 'var(--text)', border: '1px solid var(--border)' }}>
                      По дате
                    </button>
                  </div>
                </div>
              </div>

              {/* График поступления/списания */}
              <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '20px', marginBottom: '16px' }}>
                <div style={{ fontWeight: '500', marginBottom: '16px' }}>Движение денег по месяцам</div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={ddsChart}>
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={v => (v / 1000000).toFixed(0) + 'M'} />
                    <Tooltip formatter={v => fmt(v) + ' ₽'} />
                    <Legend />
                    <Bar dataKey="Поступления" fill="#16a34a" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Списания" fill="#dc2626" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* График накопительного остатка */}
              <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '20px', marginBottom: '16px' }}>
                <div style={{ fontWeight: '500', marginBottom: '16px' }}>Накопительный остаток</div>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={ddsChart}>
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={v => (v / 1000000).toFixed(0) + 'M'} />
                    <Tooltip formatter={v => fmt(v) + ' ₽'} />
                    <Line type="monotone" dataKey="Остаток" stroke="var(--primary)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Таблица по месяцам */}
              <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ fontWeight: '500', marginBottom: '16px' }}>Детализация по месяцам</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border)' }}>
                      {['Период', 'Поступления', 'Списания', 'Чистый поток', 'Накопит. остаток', ''].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--muted)', fontWeight: '500' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {periods.map((row, i) => (
                      <>
                        <tr key={i}
                          style={{ borderBottom: '1px solid var(--border)', cursor: 'pointer', background: expandedPeriod === row.period ? '#f0f7ff' : 'transparent' }}
                          onClick={() => setExpandedPeriod(expandedPeriod === row.period ? null : row.period)}>
                          <td style={{ padding: '10px', fontWeight: '500' }}>{formatPeriod(row.period)}</td>
                          <td style={{ padding: '10px', color: 'var(--success)' }}>{fmt(row.total_income)} ₽</td>
                          <td style={{ padding: '10px', color: 'var(--danger)' }}>{fmt(row.total_expense)} ₽</td>
                          <td style={{ padding: '10px', color: row.net >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: '500' }}>
                            {row.net >= 0 ? '+' : ''}{fmt(row.net)} ₽
                          </td>
                          <td style={{ padding: '10px', color: 'var(--primary)', fontWeight: '500' }}>{fmt(row.cumulative)} ₽</td>
                          <td style={{ padding: '10px', color: 'var(--muted)', fontSize: '11px' }}>{expandedPeriod === row.period ? '▲' : '▼'}</td>
                        </tr>
                        {expandedPeriod === row.period && Object.entries(row.by_bank || {}).map(([bank, data]) => (
                          <tr key={bank} style={{ borderBottom: '1px solid var(--border)', background: '#f8fafc' }}>
                            <td style={{ padding: '6px 10px 6px 24px', color: 'var(--muted)', fontSize: '12px' }}>
                              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: BANK_COLORS[bank] || '#6b7280', marginRight: '6px' }}></span>
                              {bank}
                            </td>
                            <td style={{ padding: '6px 10px', color: 'var(--success)', fontSize: '12px' }}>{fmt(data.income)} ₽</td>
                            <td style={{ padding: '6px 10px', color: 'var(--danger)', fontSize: '12px' }}>{fmt(data.expense)} ₽</td>
                            <td style={{ padding: '6px 10px', color: data.net >= 0 ? 'var(--success)' : 'var(--danger)', fontSize: '12px' }}>
                              {data.net >= 0 ? '+' : ''}{fmt(data.net)} ₽
                            </td>
                            <td colSpan={2}></td>
                          </tr>
                        ))}
                      </>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ borderTop: '2px solid var(--border)', background: 'var(--bg)' }}>
                      <td style={{ padding: '10px', fontWeight: '600' }}>ИТОГО</td>
                      <td style={{ padding: '10px', color: 'var(--success)', fontWeight: '600' }}>{fmt(periods.reduce((s, r) => s + (r.total_income || 0), 0))} ₽</td>
                      <td style={{ padding: '10px', color: 'var(--danger)', fontWeight: '600' }}>{fmt(periods.reduce((s, r) => s + (r.total_expense || 0), 0))} ₽</td>
                      <td style={{ padding: '10px', fontWeight: '600' }}>{fmt(periods.reduce((s, r) => s + (r.net || 0), 0))} ₽</td>
                      <td colSpan={2}></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}

          {tab === 'pl' && (
            <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '40px', textAlign: 'center', color: 'var(--muted)' }}>
              P&L — в разработке. Обсудим структуру следующим шагом.
            </div>
          )}

          {tab === 'balance' && (
            <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '40px', textAlign: 'center', color: 'var(--muted)' }}>
              Баланс — в разработке. Обсудим структуру следующим шагом.
            </div>
          )}

          {tab === 'planfact' && (
            <div style={{ background: 'var(--card)', borderRadius: '12px', padding: '40px', textAlign: 'center', color: 'var(--muted)' }}>
              План/Факт — в разработке. Обсудим структуру следующим шагом.
            </div>
          )}

        </>}
      </div>
    </div>
  )
}