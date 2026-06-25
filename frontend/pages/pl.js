import Navbar from '../components/Navbar'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

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

export default function PL() {
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
    loadPL(token)
  }, [dateFrom, dateTo])

  const loadPL = async (token) => {
    setLoading(true)
    try {
      const res = await api(token).get(`/reports/pl?date_from=${dateFrom}&date_to=${dateTo}`)
      setData(res.data)
      // По умолчанию раскрываем все группы
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

  if (loading) return <div style={{ textAlign: 'center', padding: '80px', color: '#6b7280' }}>Загрузка P&L...</div>
  if (!data) return null

  const { periods, groups, summary } = data
  const colWidth = `${Math.max(100, Math.floor(700 / (periods.length || 1)))}px`

  const thStyle = {
    padding: '8px 12px', fontSize: '14px', fontWeight: '500', color: '#6b7280',
    whiteSpace: 'nowrap', textAlign: 'right', background: '#f9fafb',
    borderBottom: '2px solid #e5e7eb', position: 'sticky', top: 0, zIndex: 10
  }

  const SummaryRow = ({ label, field, isProfit, isMargin, marginField, bold }) => (
    <>
      <tr style={{ background: isProfit ? '#f0fdf4' : '#f8fafc', borderBottom: '1px solid #e5e7eb' }}>
        <td style={{ padding: '9px 16px', fontSize: '15px', fontWeight: bold ? '600' : '500', color: isProfit ? '#15803d' : '#374151', position: 'sticky', left: 0, background: isProfit ? '#f0fdf4' : '#f8fafc', whiteSpace: 'nowrap', minWidth: '220px' }}>
          {label}
        </td>
        {periods.map(p => (
          <td key={p} style={{ padding: '9px 12px', fontSize: '15px', fontWeight: bold ? '600' : '500', textAlign: 'right', color: summary[p]?.[field] >= 0 ? (isProfit ? '#15803d' : '#374151') : '#dc2626', whiteSpace: 'nowrap' }}>
            {fmt(summary[p]?.[field])} ₽
          </td>
        ))}
        <td style={{ padding: '9px 12px', fontSize: '15px', fontWeight: '600', textAlign: 'right', whiteSpace: 'nowrap', color: Object.values(summary).reduce((s,v) => s + (v[field]||0), 0) >= 0 ? (isProfit ? '#15803d' : '#374151') : '#dc2626' }}>
          {fmt(Object.values(summary).reduce((s,v) => s + (v[field]||0), 0))} ₽
        </td>
      </tr>
      {isMargin && marginField && (
        <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e5e7eb' }}>
          <td style={{ padding: '5px 16px 9px', fontSize: '13px', color: '#6b7280', position: 'sticky', left: 0, background: '#f8fafc' }}>Маржа</td>
          {periods.map(p => (
            <td key={p} style={{ padding: '5px 12px 9px', fontSize: '13px', color: '#6b7280', textAlign: 'right' }}>
              {fmtPct(summary[p]?.[marginField])}
            </td>
          ))}
          <td style={{ padding: '5px 12px 9px', fontSize: '13px', color: '#6b7280', textAlign: 'right' }}>—</td>
        </tr>
      )}
    </>
  )

  return (
    <div style={{ minHeight: '100vh', background: '#f5f6fa' }}>
      <Navbar active="pl">
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
        <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '15px' }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, textAlign: 'left', position: 'sticky', left: 0, zIndex: 20, minWidth: '220px' }}>Статья</th>
                {periods.map(p => (
                  <th key={p} style={{ ...thStyle, minWidth: colWidth }}>{formatPeriod(p)}</th>
                ))}
                <th style={{ ...thStyle, minWidth: '120px', borderLeft: '2px solid #e5e7eb' }}>ИТОГО</th>
              </tr>
            </thead>
            <tbody>

              {/* Группы статей */}
              {groups.map(g => {
                const style = GROUP_COLORS[g.group] || { bg: '#f9fafb', border: '#e5e7eb', text: '#374151' }
                const isExpanded = expandedGroups[g.group]
                const isIncome = g.group === 'ВЫРУЧКА'

                return (
                  <>
                    {/* Заголовок группы */}
                    <tr key={g.group} onClick={() => toggleGroup(g.group)}
                      style={{ background: style.bg, borderTop: `2px solid ${style.border}`, cursor: 'pointer' }}>
                      <td style={{ padding: '10px 16px', fontWeight: '600', fontSize: '15px', color: style.text, position: 'sticky', left: 0, background: style.bg, whiteSpace: 'nowrap' }}>
                        {isExpanded ? '▼' : '►'} {g.group}
                      </td>
                      {periods.map(p => {
                        const val = isIncome ? (g.totals[p]?.income || 0) : (g.totals[p]?.expense || 0)
                        return <td key={p} style={{ padding: '10px 12px', fontWeight: '600', textAlign: 'right', color: style.text, whiteSpace: 'nowrap' }}>{fmt(val)} ₽</td>
                      })}
                      <td style={{ padding: '10px 12px', fontWeight: '700', textAlign: 'right', color: style.text, whiteSpace: 'nowrap', borderLeft: '2px solid #e5e7eb' }}>
                        {fmt(periods.reduce((s, p) => s + (isIncome ? (g.totals[p]?.income||0) : (g.totals[p]?.expense||0)), 0))} ₽
                      </td>
                    </tr>

                    {/* Подгруппы и статьи */}
                    {isExpanded && (g.subgroups || []).map(sg => {
                      const hasSubgroup = sg.subgroup && sg.subgroup !== ''
                      const sgKey = g.group + '_' + sg.subgroup

                      return (
                        <>
                          {/* Заголовок подгруппы (если есть) */}
                          {hasSubgroup && (
                            <tr key={sgKey} onClick={() => toggleGroup(sgKey)}
                              style={{ background: '#f8fafc', borderBottom: '1px solid #e5e7eb', cursor: 'pointer' }}>
                              <td style={{ padding: '7px 16px 7px 20px', fontWeight: '500', fontSize: '14px', color: '#374151', position: 'sticky', left: 0, background: '#f8fafc', whiteSpace: 'nowrap' }}>
                                {expandedGroups[sgKey] !== false ? '▾' : '▸'} {sg.subgroup}
                              </td>
                              {periods.map(p => {
                                const val = isIncome ? (sg.totals[p]?.income || 0) : (sg.totals[p]?.expense || 0)
                                return <td key={p} style={{ padding: '7px 12px', fontSize: '14px', fontWeight: '500', textAlign: 'right', color: '#374151', whiteSpace: 'nowrap' }}>{val > 0 ? fmt(val) + ' ₽' : '—'}</td>
                              })}
                              <td style={{ padding: '7px 12px', fontSize: '14px', fontWeight: '500', textAlign: 'right', whiteSpace: 'nowrap', borderLeft: '2px solid #e5e7eb' }}>
                                {fmt(periods.reduce((s, p) => s + (isIncome ? (sg.totals[p]?.income||0) : (sg.totals[p]?.expense||0)), 0))} ₽
                              </td>
                            </tr>
                          )}

                          {/* Строки статей */}
                          {(expandedGroups[sgKey] !== false) && sg.articles.map(a => (
                            <tr key={a.article} style={{ borderBottom: '1px solid #f3f4f6' }}
                              onMouseEnter={e => e.currentTarget.style.background = '#f0f9ff'}
                              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                              <td style={{ padding: '6px 16px 6px ' + (hasSubgroup ? '36px' : '28px'), color: '#6b7280', fontSize: '14px', position: 'sticky', left: 0, background: 'white', whiteSpace: 'nowrap' }}>
                                {a.article}
                              </td>
                              {periods.map(p => {
                                const val = isIncome ? (a.periods[p]?.income || 0) : (a.periods[p]?.expense || 0)
                                return <td key={p} style={{ padding: '6px 12px', textAlign: 'right', color: val > 0 ? '#374151' : '#d1d5db', fontSize: '14px', whiteSpace: 'nowrap' }}>{val > 0 ? fmt(val) + ' ₽' : '—'}</td>
                              })}
                              <td style={{ padding: '6px 12px', textAlign: 'right', fontSize: '14px', color: '#374151', whiteSpace: 'nowrap', borderLeft: '2px solid #e5e7eb' }}>
                                {fmt(periods.reduce((s, p) => s + (isIncome ? (a.periods[p]?.income||0) : (a.periods[p]?.expense||0)), 0))} ₽
                              </td>
                            </tr>
                          ))}
                        </>
                      )
                    })}

                    {g.group === 'СЕБЕСТОИМОСТЬ' && <SummaryRow label="▶ ВАЛОВАЯ ПРИБЫЛЬ" field="gross_profit" isProfit isMargin marginField="gross_margin" bold />}
                    {g.group === 'МАРКЕТИНГ' && <SummaryRow label="▶ EBITDA" field="ebitda" isProfit isMargin marginField="ebitda_margin" bold />}
                    {g.group === 'НАЛОГИ' && <SummaryRow label="▶ ЧИСТАЯ ПРИБЫЛЬ" field="net_profit" isProfit isMargin marginField="net_margin" bold />}
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