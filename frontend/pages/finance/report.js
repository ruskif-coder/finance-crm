import Navbar from '@/components/Navbar'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { makeApi as api } from '@/lib/http'
import { UI, MONO, card, th, td, inp, primaryBtn } from '@/components/salesTableKit'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const FinReportMobile = dynamic(() => import('@/components/mobile/FinReportMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })

// Финансовый отчёт — новый P&L рядом со старым (/pl). Старый намеренно оставлен
// как есть, пока пользователи не сверят цифры: два отчёта дают разные суммы,
// и разница объясняется блоком контроля внизу страницы.

const fmt = (n) => n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '—'
const fmtPct = (n) => (n === null || n === undefined) ? '—' : n.toFixed(1) + '%'

const MONTH_NAMES = {
  '01':'Янв','02':'Фев','03':'Мар','04':'Апр','05':'Май','06':'Июн',
  '07':'Июл','08':'Авг','09':'Сен','10':'Окт','11':'Ноя','12':'Дек'
}
const formatPeriod = (p) => {
  if (!p) return '—'
  const [year, month] = p.split('-')
  return `${MONTH_NAMES[month] || month} ${year}`
}

// Итоговые строки вставляются после соответствующей строки-группы.
const TOTALS_AFTER = {
  cogs:       { label: 'ВАЛОВАЯ ПРИБЫЛЬ',        field: 'gross_profit',      margin: 'gross_margin' },
  marketing:  { label: 'ОПЕРАЦИОННАЯ ПРИБЫЛЬ',   field: 'operating_profit',  margin: 'operating_margin' },
}

// Переключатель режимов. Стили приведены к общему набору (радиус/границы/шрифт как у btn),
// hint у опций сохранён: он объясняет смысл режима, без него выбор непонятен.
const Toggle = ({ value, onChange, options }) => (
  <div style={{ display: 'inline-flex', border: '1px solid var(--border-card)', borderRadius: 10, overflow: 'hidden' }}>
    {options.map(o => (
      <button key={o.value} onClick={() => onChange(o.value)} title={o.hint || ''}
        style={{
          padding: '8px 13px', fontSize: 13, border: 'none', cursor: 'pointer', fontFamily: UI,
          background: value === o.value ? 'var(--accent)' : 'var(--bg-card)',
          color: value === o.value ? '#fff' : 'var(--text-secondary)',
          fontWeight: value === o.value ? 700 : 600,
        }}>{o.label}</button>
    ))}
  </div>
)

export default function FinReport() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState({})
  const [basis, setBasis] = useState('accrual')
  const [vat, setVat] = useState('net')
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 11)
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
  })
  const [dateTo, setDateTo] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
  })

  // Выбор базы и режима НДС запоминается: человек работает в одном режиме неделями,
  // и сбрасывать его на каждый заход — раздражать без причины.
  useEffect(() => {
    const b = localStorage.getItem('finreport_basis')
    const v = localStorage.getItem('finreport_vat')
    if (b) setBasis(b)
    if (v) setVat(v)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    localStorage.setItem('finreport_basis', basis)
    localStorage.setItem('finreport_vat', vat)
    load(token)
  }, [dateFrom, dateTo, basis, vat])

  const load = async (token) => {
    setLoading(true)
    try {
      const res = await api(token).get(
        `/finreport?basis=${basis}&vat=${vat}&date_from=${dateFrom}&date_to=${dateTo}`)
      setData(res.data)
      const e = {}
      res.data.groups.forEach(g => { e[g.key] = false })
      setExpanded(e)
    } catch (e) {
      if (e.response?.status === 401) router.push('/login')
    } finally {
      setLoading(false)
    }
  }

  const exportXlsx = async () => {
    const token = localStorage.getItem('token')
    const res = await api(token).get(
      `/finreport/export?basis=${basis}&vat=${vat}&date_from=${dateFrom}&date_to=${dateTo}`,
      { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `Финотчёт_${basis === 'accrual' ? 'начисление' : 'оплата'}_${vat === 'net' ? 'без_НДС' : 'с_НДС'}_${dateFrom}-${dateTo}.xlsx`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  }

  // Подпись под заголовком: выбранный период и режим — чтобы не гадать, что на экране.
  const subtitle = [
    `${formatPeriod(dateFrom).toLowerCase()} — ${formatPeriod(dateTo).toLowerCase()}`,
    basis === 'accrual' ? 'по начислению' : 'по оплате',
    vat === 'net' ? 'без НДС' : 'с НДС',
  ].join(' · ')

  // Шапка + строка управления рисуются всегда, даже пока грузится:
  // иначе панель прыгает при каждой смене режима.
  // Именно JSX-переменные, а не локальные компоненты: компонент, объявленный
  // внутри рендера, каждый раз новый тип — поля периода теряют фокус при вводе.
  const header = (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: UI, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>Финансовый отчёт</span>
        <span style={{ fontFamily: MONO, fontSize: 13, color: 'var(--text-muted)' }}>{subtitle}</span>
      </div>
      <button onClick={exportXlsx} style={primaryBtn}>Выгрузить в Excel</button>
    </div>
  )

  const controls = (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
                  padding: '14px 16px', borderBottom: '1px solid var(--border-card)' }}>
      <Toggle value={basis} onChange={setBasis} options={[
        { value: 'accrual', label: 'По начислению', hint: 'По месяцу оказания услуги, все операции' },
        { value: 'cash', label: 'По оплате', hint: 'По месяцу платежа, только оплаченные' },
      ]} />
      <Toggle value={vat} onChange={setVat} options={[
        { value: 'net', label: 'Без НДС', hint: 'Корректно для P&L: НДС транзитный' },
        { value: 'gross', label: 'С НДС', hint: 'Брутто-суммы, уплаченный НДС — расходом' },
      ]} />
      <div style={{ flex: '1 1 auto' }} />
      <input type="month" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ ...inp, fontFamily: MONO }} />
      <span style={{ color: 'var(--text-muted)', fontFamily: MONO }}>—</span>
      <input type="month" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ ...inp, fontFamily: MONO }} />
    </div>
  )

  if (loading || !data) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Финансовый отчёт | Финансовый учёт</title></Head>
        <Navbar active="finreport" />
        <div style={{ padding: '20px 24px' }}>
          {header}
          <div style={{ ...card, overflow: 'hidden' }}>
            {controls}
            <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-muted)', fontFamily: MONO, fontSize: 13 }}>
              Загрузка отчёта...
            </div>
          </div>
        </div>
      </div>
    )
  }

  const { periods, groups, summary, control } = data
  const colWidth = `${Math.max(100, Math.floor(700 / (periods.length || 1)))}px`
  const sumAll = (field) => periods.reduce((s, p) => s + (summary[p]?.[field] || 0), 0)

  // Шапка таблицы липкая по вертикали; первая колонка — по горизонтали.
  const thBase = {
    ...th, textAlign: 'right', padding: '10px 10px', background: 'var(--bg-subtle)',
    position: 'sticky', top: 0, zIndex: 10, borderBottom: '2px solid var(--border-card)',
  }
  // Числовая ячейка: моноширинный, вправо, без переносов.
  const num = { ...td, fontFamily: MONO, textAlign: 'right', whiteSpace: 'nowrap' }
  // Липкая первая колонка. bg обязателен и обязан совпадать с фоном строки,
  // иначе при горизонтальной прокрутке числа просвечивают сквозь название статьи.
  const stick = (bg) => ({ position: 'sticky', left: 0, background: bg, whiteSpace: 'nowrap', minWidth: 240 })
  // «ИТОГО» отделено вертикальной границей от периодов.
  const totalCol = { borderLeft: '2px solid var(--border-card)' }
  const totalStyle = { background: 'var(--accent-tint)', borderTop: '2px solid var(--border-card)' }

  const TotalRow = ({ label, field, marginField, strong }) => {
    const bg = strong ? 'var(--accent-tint)' : 'var(--bg-subtle)'
    return (
      <>
        <tr style={strong ? totalStyle : { background: 'var(--bg-subtle)' }}>
          <td style={{ ...td, ...stick(bg), fontFamily: UI, fontSize: 14, fontWeight: 700 }}>{label}</td>
          {periods.map(p => (
            <td key={p} style={{ ...num, fontWeight: 700,
                                 color: (summary[p]?.[field] || 0) >= 0 ? 'var(--income)' : 'var(--expense)' }}>
              {fmt(summary[p]?.[field])} ₽
            </td>
          ))}
          <td style={{ ...num, ...totalCol, fontWeight: 700,
                       color: sumAll(field) >= 0 ? 'var(--income)' : 'var(--expense)' }}>
            {fmt(sumAll(field))} ₽
          </td>
        </tr>
        {marginField && (
          <tr style={{ background: 'var(--bg-subtle)' }}>
            <td style={{ ...td, ...stick('var(--bg-subtle)'), fontFamily: UI, fontSize: 12, color: 'var(--text-muted)', padding: '4px 10px 9px' }}>Маржа</td>
            {periods.map(p => (
              <td key={p} style={{ ...num, fontSize: 12, color: 'var(--text-muted)', padding: '4px 10px 9px' }}>
                {fmtPct(summary[p]?.[marginField])}
              </td>
            ))}
            <td style={{ ...num, ...totalCol, fontSize: 12, color: 'var(--text-muted)', padding: '4px 10px 9px' }}>—</td>
          </tr>
        )}
      </>
    )
  }

  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
        <Head><title>Финансовый отчёт | Финансовый учёт</title></Head>
        <Navbar active="finreport" />
        <FinReportMobile
          basis={basis} setBasis={setBasis} vat={vat} setVat={setVat}
          dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
          data={data} exportXlsx={exportXlsx}
        />
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', fontFamily: UI }}>
      <Head><title>Финансовый отчёт | Финансовый учёт</title></Head>
      <Navbar active="finreport" />

      <div style={{ padding: '20px 24px' }}>
        {header}

        <div style={{ ...card, overflow: 'hidden' }}>
          {controls}
          {/* скролл живёт внутри карточки — страница по горизонтали не растягивается */}
          <div style={{ overflow: 'auto', maxWidth: '100%' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ ...thBase, textAlign: 'left', position: 'sticky', left: 0, zIndex: 20, minWidth: 240 }}>Статья</th>
                  {periods.map(p => <th key={p} style={{ ...thBase, minWidth: colWidth }}>{formatPeriod(p)}</th>)}
                  <th style={{ ...thBase, ...totalCol, minWidth: 120 }}>ИТОГО</th>
                </tr>
              </thead>
              <tbody>
                {groups.map(g => {
                  const isOpen = expanded[g.key]
                  const t = TOTALS_AFTER[g.key]
                  return (
                    <>
                      {/* клик по строке-группе раскрывает/сворачивает её статьи */}
                      <tr key={g.key} onClick={() => setExpanded(prev => ({ ...prev, [g.key]: !prev[g.key] }))}
                        style={{ background: 'var(--bg-subtle)', borderTop: '2px solid var(--border-card)', cursor: 'pointer' }}>
                        <td style={{ ...td, ...stick('var(--bg-subtle)'), fontFamily: UI, fontWeight: 700 }}>
                          {isOpen ? '▼' : '►'} {g.label}
                        </td>
                        {periods.map(p => (
                          <td key={p} style={{ ...num, fontWeight: 700 }}>{fmt(g.totals[p])} ₽</td>
                        ))}
                        <td style={{ ...num, ...totalCol, fontWeight: 700 }}>
                          {fmt(periods.reduce((s, p) => s + (g.totals[p] || 0), 0))} ₽
                        </td>
                      </tr>

                      {isOpen && g.subgroups.map(sg => (
                        <>
                          {sg.subgroup && (
                            <tr key={g.key + '_' + sg.subgroup} style={{ background: 'var(--bg-subtle)' }}>
                              <td style={{ ...td, ...stick('var(--bg-subtle)'), fontFamily: UI, fontWeight: 600, fontSize: 12.5, color: 'var(--text-secondary)', paddingLeft: 26 }}>
                                {sg.subgroup}
                              </td>
                              {periods.map(p => (
                                <td key={p} style={{ ...num, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
                                  {sg.totals[p] ? fmt(sg.totals[p]) + ' ₽' : '—'}
                                </td>
                              ))}
                              <td style={{ ...num, ...totalCol, fontSize: 12.5, fontWeight: 600 }}>
                                {fmt(periods.reduce((s, p) => s + (sg.totals[p] || 0), 0))} ₽
                              </td>
                            </tr>
                          )}
                          {sg.articles.map(a => (
                            <tr key={g.key + '_' + sg.subgroup + '_' + a.article}>
                              <td style={{ ...td, ...stick('var(--bg-card)'), fontFamily: UI, fontSize: 12.5, color: 'var(--text-muted)', paddingLeft: sg.subgroup ? 40 : 28 }}>
                                {a.article}
                              </td>
                              {periods.map(p => (
                                <td key={p} style={{ ...num, fontSize: 12.5,
                                                     color: a.periods[p] ? 'var(--text-secondary)' : 'var(--text-faint)' }}>
                                  {a.periods[p] ? fmt(a.periods[p]) + ' ₽' : '—'}
                                </td>
                              ))}
                              <td style={{ ...num, ...totalCol, fontSize: 12.5, color: 'var(--text-secondary)' }}>
                                {fmt(periods.reduce((s, p) => s + (a.periods[p] || 0), 0))} ₽
                              </td>
                            </tr>
                          ))}
                        </>
                      ))}

                      {t && <TotalRow label={'▶ ' + t.label} field={t.field} marginField={t.margin} strong />}
                    </>
                  )
                })}

                <TotalRow label="▶ ПРИБЫЛЬ ДО НАЛОГА" field="profit_before_tax" />
                <TotalRow label="▶ ЧИСТАЯ ПРИБЫЛЬ" field="net_profit" marginField="net_margin" strong />
              </tbody>
            </table>
          </div>
        </div>

        {/* Блок контроля: то, что не попало в расчёт. Без него любые расхождения
            со старым отчётом выглядят как ошибка, а не как объяснимая разница. */}
        <div style={{ ...card, marginTop: 16, padding: '14px 18px' }}>
          <div style={{ ...th, borderBottom: 'none', padding: '0 0 10px' }}>Контроль — что не вошло в отчёт</div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              {(control.excluded || []).map(e => (
                <tr key={e.reason}>
                  <td style={{ ...td, padding: '6px 0', color: 'var(--text-secondary)' }}>{e.reason}</td>
                  <td style={{ ...td, padding: '6px 0', fontFamily: MONO, textAlign: 'right', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{fmt(e.amount)} ₽</td>
                </tr>
              ))}
              {!!control.unclassified_total && (
                <tr>
                  <td style={{ ...td, padding: '6px 0', color: 'var(--warning)' }}>Требует разметки — учтено в расчёте отдельной строкой</td>
                  <td style={{ ...td, padding: '6px 0', fontFamily: MONO, textAlign: 'right', whiteSpace: 'nowrap', color: 'var(--warning)' }}>{fmt(control.unclassified_total)} ₽</td>
                </tr>
              )}
              {vat === 'net' && !!control.zero_vat_rows && (
                <tr>
                  <td style={{ ...td, padding: '6px 0', color: 'var(--text-secondary)' }}>
                    Необлагаемые суммы, ставка 0 ({control.zero_vat_rows} операций) — очищать нечего
                  </td>
                  <td style={{ ...td, padding: '6px 0', fontFamily: MONO, textAlign: 'right', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{fmt(control.zero_vat_amount)} ₽</td>
                </tr>
              )}
              {!!control.no_period_rows && (
                <tr>
                  <td style={{ ...td, padding: '6px 0', color: 'var(--expense)' }}>
                    {basis === 'cash' ? 'Операций без даты платежа' : 'Операций без периода'} — не попали в отчёт
                  </td>
                  <td style={{ ...td, padding: '6px 0', fontFamily: MONO, textAlign: 'right', color: 'var(--expense)' }}>{control.no_period_rows}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
