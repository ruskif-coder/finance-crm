/**
 * «Деньги» — стартовый экран собственника. Заменил «Сводку руководителя» (владелец 18.11.2026: «замени этим экран»);
 * хендофф docs/design_handoff_money_navy.zip, процессы учёта под него — docs/Деньги - процессы и учёт.md.
 *
 * Адрес /exec и пиктограмма в верхней панели прежние: экран сквозной, в карте навигации его нет намеренно (гейт check-nav
 * знает это исключение). Доступ — только админ, как у прежней сводки.
 *
 * Что живое, что демо (аудит учёта 18.11.2026): счета, календарь, «можно тратить», «решить сегодня», «что если», «нам должны»,
 * качество данных, накопительный остаток и детализация — из учёта. «Деньги в обороте» и «Заёмные» — демо с пометкой;
 * «План / факт» и «Горизонт денег» — заготовки, как в макете. Пометки снимаются вместе с появлением данных.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { UI, fs, tys } from '@/components/money/kit'
import { MONTHS_NOM, buildDays, parseDate, receivables, scenarios } from '@/components/money/model'
import Header from '@/components/money/Header'
import Hero from '@/components/money/Hero'
import Todo, { todoItems } from '@/components/money/Todo'
import Accounts from '@/components/money/Accounts'
import Calendar, { WhatIfBar } from '@/components/money/Calendar'
import { Turnover, Loans, PlanFactStub, HorizonStub } from '@/components/money/DemoBlocks'
import { Receivables, Quality } from '@/components/money/Receivables'
import Cumulative from '@/components/money/Cumulative'
import MonthTable from '@/components/money/MonthTable'

const THR_KEY = 'money_threshold'
const THR_DEFAULT = 500000

function useThreshold() {
  const [thr, setThrState] = useState(THR_DEFAULT)
  useEffect(() => { try { const v = Number(localStorage.getItem(THR_KEY)); if (v > 0) setThrState(v) } catch { /* приватное окно */ } }, [])
  const setThr = (v) => { setThrState(v); try { localStorage.setItem(THR_KEY, String(v)) } catch { /* приватное окно */ } }
  return [thr, setThr]
}

/** Самый тяжёлый должник с просрочкой: больше всех дней, при равенстве — больше сумма. */
function worstOverdue(inv) {
  const by = {}
  inv.filter(x => x.d < 0).forEach(x => {
    const k = x.cp_id ?? x.who
    const c = by[k] || (by[k] = { who: x.who, amount: 0, days: 0, n: 0 })
    c.amount += x.amount; c.days = Math.max(c.days, -x.d); c.n += 1
  })
  return Object.values(by).sort((a, b) => b.days - a.days || b.amount - a.amount)[0] || null
}

export default function MoneyScreen() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [mode, setMode] = useState('contract')
  const [scen, setScen] = useState({})
  const [day, setDay] = useState(0)
  const [dz, setDz] = useState('')
  const [thr, setThr] = useThreshold()

  const load = useCallback(async () => {
    setErr('')
    try { setData((await api.get('/money/overview', auth())).data) } catch (e) {
      setErr(e?.response?.status === 403 ? 'Экран доступен только администратору.' : 'Не удалось загрузить данные. Обновите страницу.')
    }
  }, [])
  useRefreshOnReturn(() => load())
  useEffect(() => { load() }, [load])

  const real = mode === 'real'
  const calc = useMemo(() => {
    if (!data) return null
    const R = buildDays(data, { real, scen })
    const R0 = buildDays(data, { real })
    const inv = receivables(data)
    const upto = R0.days.slice(0, R0.mi + 1).flatMap(x => x.ops).filter(o => o.v < 0 && o.flag !== 'late' && o.flag !== 'today' && !/налог/i.test(o.cat || ''))   // налог не переносят; флага «обязательный» у статьи пока нет
    const move = upto.sort((a, b) => a.v - b.v)[0] || null
    return { R, R0, inv, move, overdue: worstOverdue(inv), sc: scenarios(data) }
  }, [data, real, scen])

  const scenOn = !!(scen.moveOut || scen.payIn)
  const scenText = calc && [scen.moveOut && calc.move ? `${calc.move.who} ${tys(calc.move.amount)} → после горизонта` : '',
    scen.payIn ? `${scen.payIn.who} гасит просрочку ${tys(scen.payIn.amount)}` : ''].filter(Boolean).join(' · ')
  const today = data && parseDate(data.today)

  return (
    <>
      <Head><title>Деньги | SIMB-AD ERP</title></Head>
      <Navbar />
      <div className="navy-scr" style={{ minHeight: '100vh', fontFamily: UI, color: 'var(--text-primary)' }}>
        <div style={{ maxWidth: 1880, margin: '0 auto', boxSizing: 'border-box', padding: '22px 26px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!!err && <div style={{ padding: '14px 18px', borderRadius: 14, background: 'var(--bad-tint)', border: '1px solid var(--bad-border)', color: 'var(--bad-fg)' }}>{err}</div>}
          {data && calc && <>
            <Header today={data.today} thr={thr} setThr={setThr} mode={mode} setMode={setMode} />
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr) minmax(0,0.78fr)', gap: 16 }}>
              <Hero R={calc.R} data={data} real={real} thr={thr} />
              <Todo items={todoItems({ R0: calc.R0, thr, data, overdue: calc.overdue, move: calc.move, scen, setScen, pickDay: setDay, pickBucket: setDz })} />
              <Accounts data={data} />
            </div>
            {scenOn && <WhatIfBar text={scenText} from={fs(calc.R0.minB)} to={{ s: fs(calc.R.minB), v: calc.R.minB }} thr={thr} onReset={() => setScen({})} />}
            <Calendar R={calc.R} real={real} thr={thr} day={day} setDay={setDay} />
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.55fr) minmax(0,1fr)', gap: 16, alignItems: 'stretch' }}>
              <Turnover />
              <Loans />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr) minmax(0,1fr) minmax(0,0.95fr)', gap: 16, alignItems: 'stretch' }}>
              <Receivables inv={calc.inv} dz={dz} setDz={setDz} />
              <PlanFactStub monthName={MONTHS_NOM[today.getMonth()]} />
              <HorizonStub />
              <Quality rows={data.quality} />
            </div>
            <Cumulative data={data} sc={calc.sc} thr={thr} mode={mode} />
            <MonthTable months={data.months} />
          </>}
        </div>
      </div>
    </>
  )
}
