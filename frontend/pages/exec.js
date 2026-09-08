/**
 * Дашборд руководителя.
 *
 * Отвечает на четыре вопроса, а не показывает всё: зарабатываем ли, где деньги
 * остановились, продано ли на будущее, что горит. Спека — `docs/SPEC_дашборд_руководителя.md`.
 *
 * Экран для одного человека. Поэтому нет разрезов по ответственным, нет области видимости
 * и НЕТ мобильной версии — осознанное решение владельца, а не долг.
 *
 * В карте навигации его нет намеренно: он сквозной, не принадлежит ни одному контуру, и
 * попадают на него пиктограммой в верхней панели — как на «Операции» рубль, а на настройки
 * шестерёнку. Гейт `check-nav` знает об этом исключении.
 *
 * ГЛАВНОЕ ПРАВИЛО ЭКРАНА: пустое не выдавать за ноль. Месяц закрывается с задержкой, и
 * «выручка 0» за незакрытый месяц — не «не заработали», а «ещё не провели». Сервер отдаёт
 * `has_revenue` и последний закрытый месяц, экран это проговаривает словами.
 */
import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import api, { auth } from '@/lib/api'
import { card, CAP, MONO, UI, btnSm, th, td } from '@/components/salesTableKit'
import { grp, mln, pctDot } from '@/lib/salesFormat'

const BOX = { ...card, padding: '18px 20px' }
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const moLabel = (s) => (s ? `${MONTHS[+s.slice(5, 7) - 1]} ${s.slice(2, 4)}` : '—')

/** Крупное число блока маржи. Прочерк, если периода ещё нет в учёте. */
function Big({ label, value, unit = 'млн', tone, has = true }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={CAP}>{label}</div>
      <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, lineHeight: 1.1,
                    fontVariantNumeric: 'tabular-nums', color: tone || 'var(--text-primary)' }}>
        {has && value != null ? value : '—'}
        {has && value != null && <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-faint)' }}> {unit}</span>}
      </div>
    </div>
  )
}

/** Полоса месяца в блоке загрузки: продано сейчас против сопоставимой точки прошлого года. */
function BookingBar({ row, max }) {
  const w = (v) => (max > 0 ? Math.max(2, Math.round((v / max) * 100)) : 0)
  const behind = row.prev_same_date > 0 && row.amount < row.prev_same_date
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '58px 1fr 92px', gap: 10, alignItems: 'center' }}>
      <div style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{moLabel(row.month)}</div>
      <div style={{ display: 'grid', gap: 3 }}>
        <div style={{ height: 12, borderRadius: 4, width: `${w(row.amount)}%`,
                      background: behind ? 'var(--warning)' : 'var(--accent)', minWidth: 2 }} />
        <div style={{ height: 5, borderRadius: 3, width: `${w(row.prev_same_date)}%`,
                      background: 'var(--border-card)', minWidth: 2 }}
             title={`На эту же дату год назад: ${grp(row.prev_same_date)} ₽`} />
      </div>
      <div style={{ fontFamily: MONO, fontSize: 12.5, textAlign: 'right', fontVariantNumeric: 'tabular-nums',
                    color: behind ? 'var(--warning-text)' : 'var(--text-primary)' }}>
        {mln(row.amount, 1)}
      </div>
    </div>
  )
}

export default function ExecDashboard() {
  const [scale, setScale] = useState('month')
  const [anchor, setAnchor] = useState(null)      // null = сервер сам возьмёт последний закрытый
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    setErr('')
    try {
      const q = new URLSearchParams({ scale, ...(anchor ? { anchor } : {}) })
      const { data } = await api.get(`/exec/overview?${q}`, auth())
      setD(data)
      if (!anchor) setAnchor(data.period.anchor)
    } catch (e) {
      setErr(e?.response?.status === 403
        ? 'Экран доступен только администратору.'
        : 'Не удалось загрузить сводку. Обновите страницу.')
    }
  }, [scale, anchor])

  useEffect(() => { load() }, [load])

  const step = (dir) => {
    if (!anchor) return
    const back = scale === 'quarter' ? 3 : 1
    let y = +anchor.slice(0, 4), m = +anchor.slice(5, 7) + dir * back
    while (m <= 0) { m += 12; y -= 1 }
    while (m > 12) { m -= 12; y += 1 }
    setAnchor(`${y}-${String(m).padStart(2, '0')}`)
  }

  const m = d?.margin
  const bookMax = Math.max(1, ...(d?.booking?.months || []).flatMap(r => [r.amount, r.prev_same_date]))

  return (
    <>
      <Head><title>Сводка руководителя</title></Head>
      <Navbar />
      <div style={{ maxWidth: 1240, margin: '0 auto', padding: '22px 24px 60px', fontFamily: UI }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 18 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>Сводка</h1>
          <div style={{ display: 'flex', gap: 6 }}>
            <button style={btnSm(scale === 'month')} onClick={() => setScale('month')}>Месяц</button>
            <button style={btnSm(scale === 'quarter')} onClick={() => setScale('quarter')}>Квартал</button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
            <button style={btnSm(false)} onClick={() => step(-1)}>←</button>
            <span style={{ fontFamily: MONO, fontSize: 13, minWidth: 130, textAlign: 'center' }}>
              {d?.period?.label || '…'}
            </span>
            <button style={btnSm(false)} onClick={() => step(1)}>→</button>
          </div>
        </div>

        {!!err && (
          <div style={{ ...BOX, borderColor: 'var(--danger-border)', color: 'var(--danger)', marginBottom: 14 }}>{err}</div>
        )}

        {d && (
          <div style={{ display: 'grid', gap: 14 }}>

            {/* ── Маржа ─────────────────────────────────────────────────────── */}
            <div style={BOX}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 18 }}>
                <Big label="Выручка" value={mln(m.revenue, 1)} has={m.has_revenue} />
                <Big label="Себестоимость" value={mln(m.cogs, 1)} has={m.has_data} />
                <Big label="Валовая прибыль" value={mln(m.gross, 1)} has={m.has_revenue}
                     tone={m.gross >= 0 ? 'var(--income)' : 'var(--danger)'} />
                <Big label="Маржинальность" value={pctDot(m.gross_pct)} unit="" has={m.has_revenue} />
                <Big label="EBITDA" value={mln(m.ebitda, 1)} has={m.has_revenue}
                     tone={m.ebitda >= 0 ? 'var(--income)' : 'var(--danger)'} />
              </div>

              {/* Незакрытый период называется своим именем, а не рисуется нулём. */}
              {!m.has_revenue && (
                <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 10,
                              background: 'var(--warning-tint)', color: 'var(--warning-text)', fontSize: 12.5 }}>
                  Выручка за этот период ещё не проведена — период не закрыт.
                  Последний закрытый месяц: <b>{moLabel(d.last_revenue_month)}</b>.
                </div>
              )}

              <div style={{ marginTop: 16, borderTop: '1px solid var(--border-row)', paddingTop: 14 }}>
                <div style={CAP}>Валовая прибыль по месяцам</div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 5, height: 60 }}>
                  {d.margin_series.map(s => {
                    const top = Math.max(1, ...d.margin_series.map(x => Math.abs(x.gross)))
                    const h = Math.round((Math.abs(s.gross) / top) * 52)
                    return (
                      <div key={s.month} title={`${moLabel(s.month)}: ${grp(s.gross)} ₽`}
                           style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                        <div style={{ height: s.has_revenue ? Math.max(2, h) : 2, borderRadius: 3,
                                      background: !s.has_revenue ? 'var(--border-card)'
                                        : s.gross >= 0 ? 'var(--accent)' : 'var(--danger)' }} />
                      </div>
                    )
                  })}
                </div>
                <div style={{ display: 'flex', gap: 5, marginTop: 5 }}>
                  {d.margin_series.map(s => (
                    <div key={s.month} style={{ flex: 1, textAlign: 'center', fontFamily: MONO,
                                                fontSize: 9, color: 'var(--text-faint)' }}>
                      {MONTHS[+s.month.slice(5, 7) - 1]}
                    </div>
                  ))}
                </div>
              </div>

              {/* Граница блока названа прямо: иначе читатель решит, что разрез просто не вывели. */}
              <div style={{ marginTop: 12, fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5 }}>
                В разрезе клиента маржа не считается: доход приходит от рекламодателя, расход
                уходит площадке, и связать их можно только через приложение к договору.
                Появится, когда заработает мост сделка → деньги.
              </div>
            </div>

            {/* ── Что горит ─────────────────────────────────────────────────── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 14 }}>
              {d.alerts.map(a => (
                <a key={a.key} href={a.href} style={{ ...BOX, textDecoration: 'none', display: 'block' }}>
                  <div style={CAP}>{a.label}</div>
                  <div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                                color: a.value ? 'var(--danger)' : 'var(--text-faint)' }}>
                    {a.unit === 'money' ? mln(a.value, 1) : grp(a.value)}
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-faint)' }}>
                      {a.unit === 'money' ? ' млн' : ''}
                    </span>
                  </div>
                  {!!a.hint && <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 4 }}>{a.hint}</div>}
                </a>
              ))}
            </div>

            {/* ── Загрузка месяцев ──────────────────────────────────────────── */}
            <div style={BOX}>
              <div style={CAP}>Продано по месяцам флайта</div>
              <div style={{ display: 'grid', gap: 9 }}>
                {d.booking.months.map(r => <BookingBar key={r.month} row={r} max={bookMax} />)}
              </div>
              <div style={{ display: 'flex', gap: 14, marginTop: 12, fontSize: 11, color: 'var(--text-faint)' }}>
                <span>▬ продано сейчас</span><span>▁ на ту же дату год назад</span>
              </div>
              {/* Оговорка стоит У ГРАФИКА, а не в примечании внизу: без неё блок опасен. */}
              {d.booking.prev_year_gap.deals > 0 && (
                <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5 }}>
                  Сравнение читать по направлению, <b>не в разах</b>: период флайта завели в
                  октябре 2025, и у {d.booking.prev_year_gap.deals} сделок прошлого года
                  (на {mln(d.booking.prev_year_gap.amount, 0)} млн) его нет вовсе — база
                  сравнения неполная.
                </div>
              )}
            </div>

            {/* ── Воронка ───────────────────────────────────────────────────── */}
            <div style={BOX}>
              <div style={CAP}>Где стоят сделки</div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr>
                  <th style={th}>Фаза</th>
                  <th style={th}>Стадия</th>
                  <th style={{ ...th, textAlign: 'right' }}>Сделок</th>
                  <th style={{ ...th, textAlign: 'right' }}>Сумма</th>
                </tr></thead>
                <tbody>
                  {d.funnel.map((r, i) => {
                    const first = i === 0 || d.funnel[i - 1].phase !== r.phase
                    return (
                      <tr key={r.stage}>
                        <td style={{ ...td, fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>
                          {first ? r.phase : ''}
                        </td>
                        <td style={{ ...td, color: r.deals ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                          {r.stage}
                          {r.lost && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}> · потеря</span>}
                        </td>
                        <td style={{ ...td, textAlign: 'right', fontFamily: MONO,
                                     fontVariantNumeric: 'tabular-nums',
                                     color: r.deals ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                          {r.deals || '—'}
                        </td>
                        <td style={{ ...td, textAlign: 'right', fontFamily: MONO,
                                     fontVariantNumeric: 'tabular-nums',
                                     color: r.amount ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                          {r.amount ? mln(r.amount, 1) + ' млн' : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

          </div>
        )}
      </div>
    </>
  )
}
