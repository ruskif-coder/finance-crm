import Navbar from '../components/Navbar'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, ReferenceLine, CartesianGrid } from 'recharts'

const api = (token) => axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: { Authorization: `Bearer ${token}` }
})

const fmt = (n) => n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '—'
const fmtPct = (n) => n !== null && n !== undefined ? n.toFixed(1) + '%' : '—'

const MONTH_NAMES = {
  '01':'Янв','02':'Фев','03':'Мар','04':'Апр','05':'Май','06':'Июн',
  '07':'Июл','08':'Авг','09':'Сен','10':'Окт','11':'Ноя','12':'Дек'
}

const formatPeriod = (p) => {
  if (!p) return '—'
  const [year, month] = p.split('-')
  return `${MONTH_NAMES[month] || month} ${year}`
}

const GROUP_COLORS = {
  'ВЫРУЧКА':       { bg: '#f0fdf4', border: '#86efac', text: '#15803d' },
  'СЕБЕСТОИМОСТЬ': { bg: '#fefce8', border: '#fde047', text: '#854d0e' },
  'ОПЕРАЦИОННЫЕ':  { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8' },
  'МАРКЕТИНГ':     { bg: '#fdf4ff', border: '#d8b4fe', text: '#7e22ce' },
  'НАЛОГИ':        { bg: '#fff1f2', border: '#fda4af', text: '#be123c' },
}

// Цвет % выполнения: для доходов хорошо когда факт >= план, для расходов — наоборот
const pctColor = (pct, isIncome) => {
  if (pct === null || pct === undefined) return '#9ca3af'
  if (isIncome) {
    if (pct >= 100) return '#16a34a'
    if (pct >= 90) return '#d97706'
    return '#dc2626'
  } else {
    if (pct <= 100) return '#16a34a'
    if (pct <= 110) return '#d97706'
    return '#dc2626'
  }
}

export default function PlanFact() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedGroups, setExpandedGroups] = useState({})
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 11)
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
  })
  const [dateTo, setDateTo] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
  })

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    load(token)
  }, [dateFrom, dateTo])

  const load = async (token) => {
    setLoading(true)
    try {
      const res = await api(token).get(`/reports/plan-fact?date_from=${dateFrom}&date_to=${dateTo}`)
      setData(res.data)
      const expanded = {}
      res.data.groups.forEach(g => { expanded[g.group] = true })
      setExpandedGroups(expanded)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const toggleGroup = (group) => {
    setExpandedGroups(prev => ({ ...prev, [group]: !prev[group] }))
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '80px', color: '#6b7280' }}>Загрузка План/Факт...</div>
  if (!data) return null

  const { groups, summary, trend } = data

  const trendChart = trend.map(t => ({
    period: formatPeriod(t.period),
    'Выручка, %': t.pct_income,
    'Расходы, %': t.pct_expense,
  }))

  const SummaryCard = ({ label, plan, fact, pct, isIncome }) => {
    const diff = fact - plan
    const color = pctColor(pct, isIncome)
    return (
      <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '16px 20px', flex: 1 }}>
        <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '8px' }}>{label}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', marginBottom: '6px' }}>
          <span style={{ fontSize: '24px', fontWeight: '700', color: '#111827' }}>{fmt(fact)} ₽</span>
          <span style={{ fontSize: '15px', fontWeight: '600', color }}>{fmtPct(pct)}</span>
        </div>
        <div style={{ fontSize: '14px', color: '#6b7280' }}>
          План: {fmt(plan)} ₽ · Откл: <span style={{ color: diff >= 0 ? '#16a34a' : '#dc2626' }}>{diff >= 0 ? '+' : ''}{fmt(diff)} ₽</span>
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6fa' }}>
      <Navbar active="planfact">
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <span style={{ fontSize: '15px', color: '#6b7280' }}>С периода</span>
          <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            style={{ padding: '5px 8px', borderRadius: '6px', border: '1px solid #e5e7eb', fontSize: '15px' }} />
          <span style={{ fontSize: '15px', color: '#6b7280' }}>По период</span>
          <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)}
            style={{ padding: '5px 8px', borderRadius: '6px', border: '1px solid #e5e7eb', fontSize: '15px' }} />
        </div>
      </Navbar>

      <div style={{ padding: '20px 24px' }}>

        {/* Сводные карточки */}
        <div style={{ display: 'flex', gap: '14px', marginBottom: '16px' }}>
          <SummaryCard label="Выручка" plan={summary.plan_income} fact={summary.fact_income} pct={summary.pct_income} isIncome />
          <SummaryCard label="Расходы" plan={summary.plan_expense} fact={summary.fact_expense} pct={summary.pct_expense} isIncome={false} />
          <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '16px 20px', flex: 1 }}>
            <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '8px' }}>Чистая прибыль</div>
            <div style={{ fontSize: '24px', fontWeight: '700', color: summary.fact_net >= 0 ? '#15803d' : '#dc2626', marginBottom: '6px' }}>
              {fmt(summary.fact_net)} ₽
            </div>
            <div style={{ fontSize: '14px', color: '#6b7280' }}>План: {fmt(summary.plan_net)} ₽</div>
          </div>
        </div>

        {/* Тренд выполнения плана по месяцам */}
        <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px', marginBottom: '16px' }}>
          <div style={{ fontWeight: '500', marginBottom: '16px', fontSize: '16px' }}>Выполнение плана по месяцам</div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trendChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="period" tick={{ fontSize: 13 }} />
              <YAxis tick={{ fontSize: 13 }} tickFormatter={v => v + '%'} />
              <Tooltip formatter={v => (v !== null && v !== undefined ? v.toFixed(1) + '%' : '—')} />
              <Legend />
              <ReferenceLine y={100} stroke="#9ca3af" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="Выручка, %" stroke="#16a34a" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Расходы, %" stroke="#dc2626" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Таблица по статьям */}
        <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
            <thead>
              <tr>
                <th style={{ padding: '8px 16px', fontSize: '14px', fontWeight: '500', color: '#6b7280', textAlign: 'left', background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>Статья</th>
                {['План', 'Факт', 'Отклонение', '% выполнения'].map(h => (
                  <th key={h} style={{ padding: '8px 12px', fontSize: '14px', fontWeight: '500', color: '#6b7280', textAlign: 'right', background: '#f9fafb', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map(g => {
                const style = GROUP_COLORS[g.group] || { bg: '#f9fafb', border: '#e5e7eb', text: '#374151' }
                const isExpanded = expandedGroups[g.group]

                return (
                  <>
                    <tr key={g.group} onClick={() => toggleGroup(g.group)}
                      style={{ background: style.bg, borderTop: `2px solid ${style.border}`, cursor: 'pointer' }}>
                      <td style={{ padding: '10px 16px', fontWeight: '600', color: style.text, whiteSpace: 'nowrap' }}>
                        {isExpanded ? '▼' : '►'} {g.group}
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: '600', color: style.text }}>{fmt(g.totals.plan)} ₽</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: '600', color: style.text }}>{fmt(g.totals.fact)} ₽</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: '600', color: g.totals.diff >= 0 ? '#15803d' : '#dc2626' }}>
                        {g.totals.diff >= 0 ? '+' : ''}{fmt(g.totals.diff)} ₽
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: '700', color: pctColor(g.totals.pct, g.is_income) }}>
                        {fmtPct(g.totals.pct)}
                      </td>
                    </tr>

                    {isExpanded && (g.subgroups || []).map(sg => {
                      const hasSubgroup = sg.subgroup && sg.subgroup !== ''
                      const sgKey = g.group + '_' + sg.subgroup

                      return (
                        <>
                          {hasSubgroup && (
                            <tr key={sgKey} onClick={() => toggleGroup(sgKey)}
                              style={{ background: '#f8fafc', borderBottom: '1px solid #e5e7eb', cursor: 'pointer' }}>
                              <td style={{ padding: '7px 16px 7px 20px', fontWeight: '500', fontSize: '14px', color: '#374151', whiteSpace: 'nowrap' }}>
                                {expandedGroups[sgKey] !== false ? '▾' : '▸'} {sg.subgroup}
                              </td>
                              <td style={{ padding: '7px 12px', textAlign: 'right', fontSize: '14px', fontWeight: '500', color: '#374151' }}>{fmt(sg.totals.plan)} ₽</td>
                              <td style={{ padding: '7px 12px', textAlign: 'right', fontSize: '14px', fontWeight: '500', color: '#374151' }}>{fmt(sg.totals.fact)} ₽</td>
                              <td style={{ padding: '7px 12px', textAlign: 'right', fontSize: '14px', fontWeight: '500', color: sg.totals.diff >= 0 ? '#15803d' : '#dc2626' }}>
                                {sg.totals.diff >= 0 ? '+' : ''}{fmt(sg.totals.diff)} ₽
                              </td>
                              <td style={{ padding: '7px 12px', textAlign: 'right', fontSize: '14px', fontWeight: '600', color: pctColor(sg.totals.pct, g.is_income) }}>
                                {fmtPct(sg.totals.pct)}
                              </td>
                            </tr>
                          )}

                          {(expandedGroups[sgKey] !== false) && sg.articles.map(a => (
                            <tr key={a.article} style={{ borderBottom: '1px solid #f3f4f6' }}
                              onMouseEnter={e => e.currentTarget.style.background = '#f0f9ff'}
                              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                              <td style={{ padding: '6px 16px 6px ' + (hasSubgroup ? '36px' : '28px'), color: '#6b7280', fontSize: '14px', whiteSpace: 'nowrap' }}>
                                {a.article}
                              </td>
                              <td style={{ padding: '6px 12px', textAlign: 'right', fontSize: '14px', color: '#374151' }}>{a.plan > 0 ? fmt(a.plan) + ' ₽' : '—'}</td>
                              <td style={{ padding: '6px 12px', textAlign: 'right', fontSize: '14px', color: '#374151' }}>{a.fact > 0 ? fmt(a.fact) + ' ₽' : '—'}</td>
                              <td style={{ padding: '6px 12px', textAlign: 'right', fontSize: '14px', color: a.diff >= 0 ? '#15803d' : '#dc2626' }}>
                                {(a.plan || a.fact) ? (a.diff >= 0 ? '+' : '') + fmt(a.diff) + ' ₽' : '—'}
                              </td>
                              <td style={{ padding: '6px 12px', textAlign: 'right', fontSize: '14px', fontWeight: '500', color: pctColor(a.pct, g.is_income) }}>
                                {fmtPct(a.pct)}
                              </td>
                            </tr>
                          ))}
                        </>
                      )
                    })}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
