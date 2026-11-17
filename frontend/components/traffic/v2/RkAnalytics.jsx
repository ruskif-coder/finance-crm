/**
 * Аналитика РК — правая колонка расхлопа дашборда трафика v2 (хендофф design_handoff_traffic_expand_v2, раздел 9,
 * макет «3. аналитика РК: широкая липкая колонка»). Заполняет контейнер по ширине; липкость (680 px, `sticky; top: 0`)
 * ставит страница.
 *
 * Сохранено из боевого расхлопа (pages/traffic/dashboard.js, блок «динамика»): гранулярность дни/недели и окно дат
 * (клипуется к флайту на сервере), график дольками с карточкой дня, средний темп / нужно в день / дней осталось
 * (в режиме недель — ×7), «за день среза» / «эта неделя» и «всего за период» факт против WR с расхождением цветом
 * сервера, цель из медиаплана, отчёт Weborama по ссылке, кнопка «Темп размещения».
 * Управление РК, ответственные и плитки «Задачи / Отчёт / Лог РК» отсюда ушли в пульт.
 *
 * Пороги — боевые (владелец 17.11.2026): недокрут — `under` с сервера (к прогнозу), уровень расхождения с WR —
 * `mismatch.level` / `wr_mismatch.level` с сервера. Своих порогов макета здесь нет.
 */
import { useEffect, useState } from 'react'
import { MONO, UI, inp, PortalPopover, Seg, Z } from '@/components/salesTableKit'
import { DASH, GOAL_LABELS, MISMATCH_FG, dayName, num } from '@/components/traffic/dashboardKit'
import { SEGS, cellKind, columnOf, isFutureDay, needLevel, scaleMax, wrDot } from '@/lib/dynamicsModel.mjs'
import WrLinkRow from '@/components/traffic/WrLinkRow'
import { todayMsk } from '@/lib/dates'
import { axisTicks, ctrText, signedPct, todayIndex, underSource, weekTotals, wrSource } from './analyticsModel'
import { dm } from '@/lib/salesFormat'

// Слои дольки — `lib/dynamicsModel` (хендофф design_handoff_traffic_dynamics, 17.11.2026); здесь только их вид.
const CELL = {
  fact: { background: 'var(--accent)' },
  plan: { background: 'var(--accent-border)' },
  forecast: { background: 'var(--bg-card)', boxShadow: 'inset 0 0 0 1px var(--accent)' },
  shortfall: { background: 'var(--warning-tint)', boxShadow: 'inset 0 0 0 1px var(--warning-border)' },
  boost: { background: 'var(--warning)' },
  empty: { background: 'var(--bg-subtle)' },
}
const CHART_H = 216
const CELL_GAP = 2       // зазор между дольками
const COL_GAP = 3        // зазор между колонками
const COL_PAD = 2        // отступ колонки сверху
const TIP_W = 248

const CAP9 = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const MONO_NUM = { fontFamily: MONO, fontSize: 11.5, textAlign: 'right', whiteSpace: 'nowrap' }

const accentBtn = (off) => ({
  display: 'inline-flex', alignItems: 'center', gap: 6, height: 28, padding: '0 12px', border: 'none', borderRadius: 9,
  background: off ? 'var(--bg-subtle)' : 'var(--accent)', color: off ? 'var(--text-faint)' : 'var(--on-accent)',
  fontFamily: UI, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', cursor: off ? 'not-allowed' : 'pointer',
})

const TempoIcon = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <path d="M2 4.5h7M12 4.5h2M2 11.5h2M7 11.5h7" /><circle cx="10.5" cy="4.5" r="1.6" /><circle cx="5.5" cy="11.5" r="1.6" />
  </svg>
)
const ReallocIcon = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 5h11M10.5 2.5 13 5l-2.5 2.5M14 11H3M5.5 8.5 3 11l2.5 2.5" />
  </svg>
)

/* ── окно дат: черновик держится здесь, наружу уходит только применённое ─────────────── */

const DatesPanel = ({ rk, range, onApply, onReset }) => {
  const [from, setFrom] = useState((range && range.from) || rk.date_start || '')
  const [to, setTo] = useState((range && range.to) || rk.date_end || '')
  const field = { ...inp, fontFamily: MONO, fontSize: 12, flex: '1 1 0', minWidth: 0, padding: '7px 8px' }
  return (
    <>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Окно внутри флайта РК</span>
      {/* Поля тянутся поровну и сжимаются: иначе панель раздувается и «показать» уезжает за край. */}
      <span style={{ display: 'flex', gap: 8 }}>
        <input type="date" style={field} value={from} onChange={e => setFrom(e.target.value)} />
        <input type="date" style={field} value={to} onChange={e => setTo(e.target.value)} />
      </span>
      <span style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span onClick={onReset} style={{ fontSize: 11.5, color: 'var(--accent-fg)', cursor: 'pointer' }}>сбросить</span>
        <span onClick={() => onApply({ from: from || rk.date_start, to: to || rk.date_end })}
          style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)', cursor: 'pointer' }}>показать</span>
      </span>
    </>
  )
}

/** «дни / недели / даты»: «даты» — окно дат боевого экрана (интервал клипуется к флайту на сервере). */
const GrainSwitch = ({ rk, grain, range, onGrain, onRange }) => {
  const [open, setOpen] = useState(false)
  const value = range ? 'dates' : grain
  // Закрытие по клику мимо — правилом кита: панель портала сама несёт `data-pop-root`.
  useEffect(() => {
    if (!open) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setOpen(false) }
    document.addEventListener('click', off)
    return () => document.removeEventListener('click', off)
  }, [open])
  const pick = (v) => {
    if (v === 'dates') { setOpen(o => !o); return }
    setOpen(false)
    onGrain(v)
  }
  return (
    <span data-pop-root style={{ marginLeft: 'auto', position: 'relative', display: 'inline-flex' }}>
      <Seg value={value} onPick={pick}
        opts={[['day', 'дни'], ['week', 'недели'], ['dates', range ? `${dm(range.from)} — ${dm(range.to)}` : 'даты',
          'Окно дат внутри флайта РК']]} />
      <PortalPopover open={open} minWidth={280} align="right" style={{ padding: 12, gap: 9, zIndex: Z.dropdown }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          <DatesPanel rk={rk} range={range}
            onApply={win => { setOpen(false); onRange(win) }}
            onReset={() => { setOpen(false); onRange(null) }} />
        </span>
      </PortalPopover>
    </span>
  )
}

/* ── график дольками ─────────────────────────────────────────────────────────────── */

const TipRow = ({ cap, val, fg }) => (
  <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, minHeight: 27, borderTop: '1px solid var(--border-row)',
    paddingTop: 5, boxSizing: 'border-box' }}>
    <span style={CAP9}>{cap}</span>
    <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13.5, fontWeight: 700, color: fg || 'var(--text-primary)' }}>{val}</span>
  </span>
)

/** Карточка дня. Будущий день — только план и «нужно в день»; факт прочерком, а не нулём. */
const DayTip = ({ b, i, n, label, needPerDay, future, speed }) => {
  const past = !future
  const ctr = past && b.shows ? b.clicks / b.shows * 100 : null
  const rows = past ? [
    ['Показы план', num(b.plan)],
    ...(b.boost_extra ? [['В т. ч. темп размещения', `+${num(b.boost_extra)}`, 'var(--warning-fg)']] : []),
    ['Показы факт', num(b.shows), 'var(--accent-fg)'],
    ['Клики', num(b.clicks)],
    ['CTR', ctr == null ? DASH : `${ctr.toFixed(2).replace('.', ',')} %`],
    ...(b.wr_shows != null ? [
      ['Показы WR', num(b.wr_shows), 'var(--text-secondary)'],
      ['Расхождение с WR', b.mismatch ? signedPct(b.mismatch.pct) : DASH, MISMATCH_FG[b.mismatch?.level] || 'var(--text-faint)'],
    ] : []),
  ] : [
    ['Показы план', num(b.plan)],
    ...(b.boost_extra ? [['В т. ч. темп размещения', `+${num(b.boost_extra)}`, 'var(--warning-fg)']] : []),
    // Будущий день: прогноз по темпу и недокрут дня = план − прогноз, не меньше нуля (хендофф 17.11.2026).
    ...(speed != null && b.days === 1 ? [
      ['Прогноз по темпу', num(speed), 'var(--accent-fg)'],
      ['Недокрут дня', `−${num(Math.max(0, (b.plan || 0) - speed))}`, 'var(--warning-fg)'],
    ] : [['Показы факт', DASH, 'var(--text-disabled)']]),
    // У будущего дня его план и есть «нужно в день»; у недели — отдельной строкой.
    ...(b.days > 1 && needPerDay != null ? [['Нужно в день', num(needPerDay)]] : []),
  ]
  // Справа от столбца; после 17-го дня из 30 — слева (макет).
  const leftSide = (i + 1) > n * 17 / 30
  const side = leftSide ? { right: `${Math.round((n - i) / n * 100)}%` } : { left: `${Math.round((i + 1) / n * 100)}%` }
  const note = past ? (b.repaced ? 'план пересчитан под недокрут' : '') : 'нужно в день, чтобы выполнить план'
  return (
    <span style={{ position: 'absolute', zIndex: Z.base + 5, top: 14, ...side, width: TIP_W, display: 'flex', flexDirection: 'column',
      padding: '12px 14px 10px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14,
      boxShadow: 'var(--shadow-card)', pointerEvents: 'none', boxSizing: 'border-box' }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, paddingBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>
          {b.days > 1 ? `${dayName(b.date_from)} — ${dayName(b.date_to)}` : dayName(b.date_from)}</span>
        <span style={{ ...CAP9, marginLeft: 'auto', whiteSpace: 'nowrap' }}>{label}</span>
      </span>
      {rows.map(([cap, val, fg]) => <TipRow key={cap} cap={cap} val={val} fg={fg} />)}
      {!!note && <span style={{ paddingTop: 6, fontSize: 11, color: 'var(--warning-fg)' }}>{note}</span>}
    </span>
  )
}

const Swatch = ({ style }) => <span style={{ width: 9, height: 9, borderRadius: 2, boxSizing: 'border-box', ...style }} />

/** Линия «нужно в день»: от колонки первого будущего дня до правого края, в зазоре над долькой своего уровня. */
const NeedLine = ({ need, level, from, n }) => {
  const cell = (CHART_H - COL_PAD - (SEGS - 1) * CELL_GAP) / SEGS
  const bottom = level * (cell + CELL_GAP) - 1
  const left = `calc((100% - ${(n - 1) * COL_GAP}px) * ${from} / ${n} + ${from * COL_GAP}px)`
  return (
    <>
      <span style={{ position: 'absolute', left, right: 0, bottom, borderTop: '1.5px dashed var(--warning-fg)', pointerEvents: 'none' }} />
      <span title="Сколько нужно крутить в день до конца периода, чтобы выполнить план"
        style={{ position: 'absolute', right: 0, bottom: bottom + 5, padding: '1px 8px', borderRadius: 9, background: 'var(--bg-card)',
          border: '1px solid var(--warning-border)', fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--warning-fg)',
          whiteSpace: 'nowrap' }}>нужно {num(need)} / дн</span>
    </>
  )
}

const DynChart = ({ st, label }) => {
  const [hov, setHov] = useState(-1)
  const bs = st.buckets
  const n = bs.length
  const today = todayMsk()
  // Новые слои — только в режиме «дни» (README: недели и даты в макете не проверялись).
  const daily = bs.every(b => b.days === 1)
  const speed = daily ? st.speed : null
  const need = daily ? st.need_per_day : null
  const max = scaleMax(bs, { need, speed })
  const ti = todayIndex(bs, today)
  const ticks = axisTicks(bs, ti)
  const future = bs.map(b => daily && isFutureDay(b, today))
  const firstFuture = future.indexOf(true)
  const lvl = needLevel(need, max)
  const showNeed = lvl != null && firstFuture >= 0
  const dots = bs.map(b => wrDot(b.mismatch))
  const anyDot = dots.some(Boolean)
  const boosted = bs.some(b => b.boost_extra)
  const legend = [
    ['факт', CELL.fact], ['план дня', CELL.plan],
    ...(speed != null && firstFuture >= 0 ? [['прогноз по темпу', CELL.forecast], ['недокрут', CELL.shortfall]] : []),
    ...(boosted ? [['темп размещения', CELL.boost]] : []),
  ]
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ position: 'relative', display: 'flex', alignItems: 'stretch', gap: COL_GAP, height: CHART_H }}>
        {bs.map((b, i) => {
          const cells = columnOf(b, max, { speed, future: future[i] })
          return (
            <span key={String(b.date_from)} onMouseEnter={() => setHov(i)} onMouseLeave={() => setHov(h => (h === i ? -1 : h))}
              style={{ flex: '1 1 0', minWidth: 4, display: 'flex', flexDirection: 'column', gap: CELL_GAP, padding: `${COL_PAD}px 1px 0`,
                borderRadius: '5px 5px 0 0', background: hov === i ? 'var(--bg-subtle)' : 'transparent', cursor: 'default' }}>
              {Array.from({ length: SEGS }, (_, k) => (
                <span key={k} style={{ flex: '1 1 0', borderRadius: 2.5, boxSizing: 'border-box', ...CELL[cellKind(SEGS - k, cells)] }} />
              ))}
            </span>
          )
        })}
        {showNeed && <NeedLine need={need} level={lvl} from={firstFuture} n={n} />}
        {hov >= 0 && hov < n && <DayTip b={bs[hov]} i={hov} n={n} label={label} needPerDay={st.need_per_day}
          future={future[hov] || !bs[hov].days_past} speed={future[hov] ? speed : null} />}
      </span>
      {/* Точки расхождения с WR — под колонкой дня, цвет по уровню с сервера (боевые пороги) */}
      {anyDot && (
        <span style={{ position: 'relative', height: 8 }}>
          {dots.map((c, i) => (c ? (
            <span key={i} title={`${dm(bs[i].date_from)} · расхождение с WR ${signedPct(bs[i].mismatch.pct)}`}
              style={{ position: 'absolute', top: 1, left: `calc(${(i + 0.5) / n * 100}% - 3px)`, width: 6, height: 6, borderRadius: 3, background: c }} />
          ) : null))}
        </span>
      )}
      <span style={{ position: 'relative', height: 12, fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>
        {ticks.map(t => (
          <span key={t.i} style={{ position: 'absolute', top: 0, whiteSpace: 'nowrap',
            left: `${(t.i + 0.5) / t.n * 100}%`,
            transform: t.i === 0 ? 'translateX(-25%)' : t.i === t.n - 1 ? 'translateX(-75%)' : 'translateX(-50%)',
            ...(t.today ? { color: 'var(--text-secondary)', fontWeight: 700 } : {}) }}>{t.label}</span>
        ))}
      </span>
      <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '4px 12px', paddingTop: 2, fontSize: 10.5, color: 'var(--text-muted)' }}>
        {legend.map(([l, look]) => (
          <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Swatch style={look} />{l}</span>
        ))}
        {showNeed && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 12, borderTop: '1.5px dashed var(--warning-fg)' }} />нужно в день</span>
        )}
        {anyDot && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--warning)' }} />расхождение с WR</span>
        )}
      </span>
    </span>
  )
}

/* ── четыре числа ────────────────────────────────────────────────────────────────── */

const Nums = ({ rk, st, week }) => {
  const per = week ? ' / нед' : ' / дн'
  const k = week ? 7 : 1
  const need = st.need_per_day
  const behind = need != null && st.speed != null && need > st.speed
  const fcPct = rk.forecast != null && rk.plan_show ? Math.round(rk.forecast / rk.plan_show * 100) : null
  const items = [
    { cap: 'Средний темп', val: st.speed == null ? DASH : num(st.speed * k), unit: st.speed == null ? '' : per },
    { cap: week ? 'Нужно в неделю' : 'Нужно в день', val: need == null ? (rk.flight_over ? 'флайт закончен' : DASH) : num(need * k),
      unit: need == null ? '' : per, fg: behind ? 'var(--warning-fg)' : undefined },
    { cap: 'Дней осталось', val: st.days_left == null ? DASH : String(st.days_left), unit: '' },
    { cap: 'Прогноз', val: fcPct == null ? DASH : String(fcPct), unit: fcPct == null ? '' : ' % плана',
      title: rk.forecast != null ? `прогноз ${num(rk.forecast)} из ${num(rk.plan_show)}` : '' },
  ]
  return (
    <span style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))' }}>
      {items.map((x, i) => (
        <span key={x.cap} title={x.title || ''} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '0 14px',
          borderLeft: `1px solid ${i ? 'var(--border-inner)' : 'transparent'}` }}>
          <span style={CAP9}>{x.cap}</span>
          <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, whiteSpace: 'nowrap', color: x.fg || 'var(--text-primary)' }}>
            {x.val}<span style={{ fontSize: 10.5, fontWeight: 400, color: 'var(--text-muted)' }}>{x.unit}</span>
          </span>
        </span>
      ))}
    </span>
  )
}

/* ── факт против WR ──────────────────────────────────────────────────────────────── */

const StatBlock = ({ cap, t, cover }) => (
  <span style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 76px 70px', gap: '5px 8px', alignItems: 'baseline' }}>
    <span style={{ ...CAP9, fontWeight: 700, color: 'var(--text-primary)' }}>{cap}</span>
    <span style={{ ...CAP9, textAlign: 'right' }}>факт</span>
    <span style={{ ...CAP9, textAlign: 'right' }}>WR</span>
    {[['Показы', num(t.shows), t.wr ? num(t.wr.shows) : DASH],
      ['Переходы', num(t.clicks), t.wr ? num(t.wr.clicks) : DASH],
      ['CTR', ctrText(t.ctr), ctrText(t.wr?.ctr)]].map(([l, a, w]) => (
      <span key={l} style={{ display: 'contents' }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{l}</span>
        <span style={{ ...MONO_NUM, fontWeight: 700 }}>{a}</span>
        <span style={{ ...MONO_NUM, color: 'var(--text-muted)' }}>{w}</span>
      </span>
    ))}
    <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>Расхождение с WR</span>
    <span />
    <span title={[t.mismatch?.hint || (t.mismatch ? '' : 'Weborama по этому периоду не измеряла'), cover].filter(Boolean).join(' · ')}
      style={{ ...MONO_NUM, fontWeight: 700, color: MISMATCH_FG[t.mismatch?.level] || 'var(--text-faint)' }}>
      {t.mismatch ? signedPct(t.mismatch.pct) : DASH}</span>
  </span>
)

const Stats = ({ st, week }) => {
  const T = st.totals
  if (!T) return null
  const cover = T.wr_placements && T.wr_placements < T.placements ? `по ${T.wr_placements} из ${T.placements} площадок` : ''
  const firstCap = week ? 'Эта неделя' : T.as_of ? `За ${dm(T.as_of)}` : 'Сегодня'
  return (
    <span style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 14, paddingTop: 12,
      borderTop: '1px solid var(--border-inner)' }}>
      <StatBlock cap={firstCap} t={week ? weekTotals(st, todayMsk()) : T.today} cover={cover} />
      <StatBlock cap="Всего за период" t={T.period} cover={cover} />
    </span>
  )
}

/** Цель из медиаплана рядом с фактом. Значения — свободный ввод строкой: показываем как есть, вердикта не выносим. */
const GoalStrip = ({ goals, st }) => {
  const set = GOAL_LABELS.filter(([k]) => goals && goals[k])
  const T = st && st.totals
  const cover = T && T.wr_placements ? `расхождение — по ${T.wr_placements} из ${T.placements} площадок` : ''
  const outside = T && T.wr_outside ? `вне DSP: WR ${num(T.wr_outside)}` : ''
  return (
    <span style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px 18px', padding: '9px 12px', borderRadius: 11,
      background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
      <span style={CAP9}>Цель · KPI приёмки</span>
      {set.length ? (
        <span style={{ marginLeft: 'auto', display: 'inline-flex', flexWrap: 'wrap', gap: '4px 18px' }}>
          {set.map(([k, l]) => (
            <span key={k} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{l.toLowerCase()} <b style={{ fontFamily: MONO,
              color: 'var(--text-primary)' }}>{String(goals[k]).trim()}</b></span>
          ))}
          {!!goals.ctr && T?.period?.ctr != null && (
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>факт за период {ctrText(T.period.ctr)}</span>
          )}
        </span>
      ) : (
        <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-faint)' }}>В медиаплане не заданы — принимать не по чему.</span>
      )}
      {!!(cover || outside) && (
        <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{[cover, outside].filter(Boolean).join(' · ')}</span>
      )}
    </span>
  )
}

/* ── откуда недокрут / расхождение с Weborama ────────────────────────────────────── */

const TopRow = ({ name, w, bg, val, pct, title }) => (
  <span title={title || ''} style={{ display: 'grid', gridTemplateColumns: '130px 1fr 66px 40px', gap: 10, alignItems: 'center' }}>
    <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
    <span style={{ height: 6, borderRadius: 3, background: 'var(--bg-subtle)' }}>
      <span style={{ display: 'block', height: 6, width: w, borderRadius: 3, background: bg }} />
    </span>
    <span style={{ ...MONO_NUM, fontSize: 11, fontWeight: 700 }}>{val}</span>
    <span style={{ ...MONO_NUM, fontSize: 10, color: 'var(--text-muted)' }}>{pct}</span>
  </span>
)

const Source = ({ rk, d, st, onRealloc }) => {
  const [src, setSrc] = useState('under')
  const under = src === 'under'
  const U = underSource(d && d.placements, rk.under)
  const W = wrSource(d && d.placements)
  const rkMm = st && st.totals && st.totals.period && st.totals.period.mismatch
  const mix = under ? U.mix : W.mix
  const total = under
    ? { cap: 'к прогнозу', val: U.total ? `−${num(U.total)}` : 'нет', fg: U.total ? 'var(--warning-fg)' : 'var(--text-faint)',
      title: U.diverges ? `Сумма по площадкам −${num(U.total)}, недокрут РК −${num(rk.under)}: часть площадок без прогноза или с перекрутом`
        : 'Сумма недокрута площадок к их прогнозу — тот же расчёт, что в строке РК' }
    : { cap: 'за период', val: rkMm ? signedPct(rkMm.pct) : DASH, fg: MISMATCH_FG[rkMm?.level] || 'var(--text-faint)',
      title: rkMm?.hint || 'Weborama за период не измеряла' }
  const empty = under ? 'Недокрута по площадкам нет.' : 'Weborama по площадкам не мерила — сравнивать нечего.'
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 28 }}>
        <Seg value={src} onPick={setSrc} opts={[['under', 'Откуда недокрут'], ['wr', 'Расхождение с Weborama']]} />
        <span style={{ ...CAP9, whiteSpace: 'nowrap' }}>{total.cap}</span>
        <span title={total.title} style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap',
          color: total.fg }}>{total.val}</span>
        <button type="button" onClick={onRealloc} title="Перераспределить объём отстающих площадок между теми, кто в темпе"
          style={{ ...accentBtn(false), marginLeft: 4 }}><ReallocIcon />Перераспределить</button>
      </span>
      {mix.length ? (
        <>
          <span style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', gap: 2 }}>
            {mix.map(m => <span key={m.key} title={m.title} style={{ flex: `${m.w} 1 0`, background: m.bg }} />)}
          </span>
          <span style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 10.5, color: 'var(--text-muted)' }}>
            {mix.map(m => (
              <span key={m.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap' }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: m.bg }} />{m.label}
              </span>
            ))}
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 2 }}>
            {under
              ? U.top.map(t => <TopRow key={t.id} name={t.name} w={t.w} bg={t.bg} val={`−${num(t.amount)}`} pct={t.pct} />)
              : W.top.map(t => <TopRow key={t.id} name={t.name} w={t.w} bg={t.bg} val={signedPct(t.pct)} pct="" title={t.title} />)}
          </span>
        </>
      ) : (
        <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{empty}</span>
      )}
    </span>
  )
}

/* ── колонка целиком ─────────────────────────────────────────────────────────────── */

/**
 * @param rk        строка РК из `/traffic-dashboard` (id, deal_code, product, plan_show, forecast, under, flight_over,
 *                  date_start, date_end)
 * @param d         расхлоп `/traffic-dashboard/campaign/{id}` (placements, goals, wr_link, days_left, boost) или undefined
 * @param st        ответ `/traffic-dashboard/campaign/{id}/stat` или undefined, пока грузится
 * @param grain     'day' | 'week'
 * @param range     { from, to } | null — окно дат
 * @param onGrain   (g) => void — страница: сбросить окно, запомнить гранулярность, перечитать stat
 * @param onRange   (win | null) => void — страница: запомнить окно (null — сброс) и перечитать stat
 * @param onTempo   () => void — открыть «Темп размещения»
 * @param onRealloc () => void — открыть перераспределение
 * @param mayEdit   может ли менять ссылку отчёта Weborama
 * @param onWrLinkChange (wl) => void — страница: обновить d.wr_link и перечитать stat
 */
export function RkAnalytics({ rk, d, st, grain = 'day', range = null, onGrain, onRange, onTempo, onRealloc, mayEdit, onWrLinkChange }) {
  const week = grain === 'week'
  const over = d?.days_left === 0
  const boost = d?.boost
  const label = `${rk.deal_code || ''} · ${rk.product || ''}`.replace(/ · $/, '')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '10px 18px 16px', boxSizing: 'border-box', width: '100%',
      minWidth: 0, fontFamily: UI, color: 'var(--text-primary)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 800, whiteSpace: 'nowrap' }}>Динамика показов</span>
        <GrainSwitch rk={rk} grain={grain} range={range} onGrain={onGrain} onRange={onRange} />
        {/* Видна всем с доступом к дашборду: аккаунт открывает окно в режиме чтения. Флайт кончился — неактивна. */}
        <button type="button" disabled={over} onClick={onTempo} aria-label="Темп размещения" style={accentBtn(over)}
          title={over ? 'Флайт закончился — поднимать нечего'
            : 'Изменить темп размещения: поднять остаток РК на процент на несколько дней или перераспределить объём между площадками'
              + (boost ? ` · сейчас +${boost.pct} % до ${dm(boost.until)}` : '')}>
          <TempoIcon />Темп размещения{boost ? ` · +${boost.pct} %` : ''}
        </button>
      </span>

      {!st ? (
        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>Загружаю динамику…</span>
      ) : !(st.buckets || []).length ? (
        <span style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: 1.45 }}>Графика нет: у РК не заведён план или не указан флайт.</span>
      ) : (
        <>
          <DynChart st={st} label={label} />
          <Nums rk={rk} st={st} week={week} />
          <Stats st={st} week={week} />
        </>
      )}

      {!!d && <GoalStrip goals={d.goals} st={st} />}
      {/* Отчёт Weborama по ссылке — внешний пиксель (05.11.2026): сверка РК в целом снимается по ссылке клиента */}
      {!!d?.wr_link && <WrLinkRow campaignId={rk.id} link={d.wr_link} mayEdit={mayEdit} onChange={onWrLinkChange} />}
      {!!d && <Source rk={rk} d={d} st={st} onRealloc={onRealloc} />}
    </div>
  )
}

export default RkAnalytics
