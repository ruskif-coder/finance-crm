/**
 * Виджеты блока «Сейчас» «Моих сделок» (v5): шаги стадий, плитки, «Рекламная кампания», сделка без РК в нашей DSP, заголовок
 * стадии. Общие для расхлопа строки и модалки режима «Карточки» (`DealNow`).
 */
import { MONO } from '@/components/salesTableKit'
import { dm, grp, rub0 } from '@/lib/salesFormat'
import { mln } from '@/components/accounts/dashboard/ladder'
import { GOAL_LABELS } from '@/components/traffic/dashboardKit'

export const CAP = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap, var(--text-muted))' }
export const BOX = { background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 12, padding: '12px 14px' }
export const ACT = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: 26, padding: '0 9px', border: '1px solid var(--border-card)',
  borderRadius: 8, background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: MONO, whiteSpace: 'nowrap' }
export const NEXT = {
  mp_prep: 'после отправки МП — ждём ответа клиента', mp_sent: 'клиент согласует МП — переведите в «Бронь»',
  booking: 'сделка перейдёт в «Готовятся к старту», трафик начнёт сборку',
  prep: 'сборка продолжается в карточке сделки — по первому незакрытому пункту', live: 'разбор с трафиком: перераспределить объём или продлить',
}
export const ICON = {
  brief: 'M9 3.5h6v3H9zM9 5H6.5a1 1 0 0 0-1 1v13.5a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H15M9 11.5h6M9 15.5h4',
  report: 'M3.5 20.5h17M7 16.5v-6M12 16.5v-13M17 16.5v-9',
  card: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
}
export const ini = (n) => (n ? n.split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase() : '—')
export const pct = (v) => (v == null ? '—' : `${String(Math.round(v * 10) / 10).replace('.', ',')} %`)

export function Steps({ steps, at }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, minWidth: 0 }}>
      <span style={CAP}>Сейчас</span>
      <span style={{ flex: 1, display: 'flex', gap: 3, minWidth: 0 }}>
        {steps.map((l, k) => (
          <span key={l} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={{ height: 4, borderRadius: 2, background: k < at ? 'var(--income)' : k === at ? 'var(--accent)' : 'var(--border-card)' }} />
            <span style={{ fontFamily: MONO, fontSize: 9.5, color: k === at ? 'var(--accent-fg)' : 'var(--text-faint)', fontWeight: k === at ? 700 : 400,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l}</span>
          </span>
        ))}
      </span>
    </div>
  )
}

export function Tile({ l, v, s, fg }) {
  return (
    <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 11px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10 }}>
      <span style={{ ...CAP, fontSize: 9 }}>{l}</span>
      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: fg || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{v}</span>
      {!!s && <span style={{ fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s}</span>}
    </span>
  )
}

export function Campaign({ c, wide, endIn, now }) {
  // Макет v5 (экран 02): шесть показателей в ряд без плиток, полоса открутки с отметкой плана на сегодня и словами
  // справа, строка «Цель · KPI приёмки» из целей медиаплана (как есть, без вердикта — их сверяет человек).
  const lagging = c.today_pct != null && c.done_pct != null && c.done_pct < c.today_pct * 0.85
  const m = [
    ['План показов', grp(c.plan), c.plan_sum != null ? rub0(c.plan_sum) : ''],
    ['Факт', c.fact != null ? grp(c.fact) : '—', c.fact_sum != null ? `${rub0(c.fact_sum)} по цене плана` : '', 'var(--accent-fg)'],
    ['Переходы', grp(c.clicks), c.ctr != null ? `CTR ${pct(c.ctr)}` : ''],
    ['Потенциал недокрута', c.gap != null ? grp(c.gap) : '—', c.forecast != null ? `прогноз ${grp(c.forecast)}` : '', c.gap ? 'var(--warning-fg)' : 'var(--income-fg)'],
    ['Крутит площадок', `${c.on} / ${c.placements}`, c.flight_over ? 'период закончился' : endIn != null ? `дней осталось ${Math.max(0, endIn)}` : ''],
    ['Расхождение', c.diff?.v ?? '—', c.diff?.s ?? '', c.diff?.bad ? 'var(--warning-fg)' : null],
  ]
  const kpi = GOAL_LABELS.filter(([k]) => c.goals && c.goals[k])
  const words = lagging ? `отстаёт на ${Math.round((1 - c.done_pct / c.today_pct) * 100)} % от плана` : now
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gridTemplateColumns: wide ? 'repeat(6, minmax(0,1fr))' : 'repeat(3, minmax(0,1fr))', gap: '12px 14px' }}>
        {m.map(([l, v, s2, fg]) => (
          <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <span title={l} style={{ ...CAP, fontSize: 9, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l}</span>
            <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, color: fg || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{v}</span>
            <span title={s2} style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s2}</span>
          </span>))}
      </div>
      {c.done_pct != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span title={`открутка ${pct(c.done_pct)} · план на сегодня ${pct(c.today_pct)}`}
            style={{ position: 'relative', flex: '1 1 180px', height: 8, borderRadius: 4, background: 'var(--bg-card)', border: '1px solid var(--border-card)' }}>
            <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, c.done_pct)}%`, borderRadius: 4, background: lagging ? 'var(--warning)' : 'var(--income)' }} />
            {c.today_pct != null && <span style={{ position: 'absolute', left: `${Math.min(100, c.today_pct)}%`, top: -3, bottom: -3, width: 2, marginLeft: -2, background: 'var(--text-primary)' }} />}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: lagging ? 'var(--warning-fg)' : 'var(--income-fg)', whiteSpace: 'nowrap' }}>открутка {pct(c.done_pct)}</span>
          {c.today_pct != null && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>план на сегодня {pct(c.today_pct)}</span>}
          {!!words && <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>{words}</span>}
        </div>
      )}
      {kpi.length > 0 && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', padding: '7px 12px', borderRadius: 9, background: 'var(--bg-card)', border: '1px solid var(--border-inner)' }}>
          <span style={{ ...CAP, fontSize: 9 }}>Цель · KPI приёмки</span>
          {kpi.map(([k, l]) => <span key={k} style={{ display: 'inline-flex', gap: 5, fontSize: 12.5, color: 'var(--text-secondary)' }}>{l}
            <span style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>{c.goals[k]}</span></span>)}
        </span>
      )}
    </div>
  )
}

export function OwnRun({ o, flow }) {
  // Сделка, которую аккаунт запускает сам: РК в нашей DSP нет — план из МП и ход периода; факт — на сверке (владелец 13.11.2026).
  const m = [
    ['План показов', o.plan ? grp(o.plan) : '—', o.plan ? '' : 'не CPM-план'],
    ['Сумма плана', o.plan_sum != null ? rub0(o.plan_sum) : '—', 'до НДС'],
    ['Период', o.days ? `день ${o.day} из ${o.days}` : '—', ''],
    ['Осталось', o.over ? 'период закончился' : o.left != null ? `${o.left} дн.` : '—', '', o.over ? 'var(--warning-fg)' : null],
    ['Факт', 'вносит аккаунт', flow === 'приоритезация' ? 'файлом или из сервиса площадки' : 'на итоговой сверке'],
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))', gap: '12px 14px' }}>
        {m.map(([l, v, s2, fg]) => (
          <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <span style={{ ...CAP, fontSize: 9, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l}</span>
            <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, color: fg || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{v}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s2}</span>
          </span>))}
      </div>
      {o.elapsed_pct != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ position: 'relative', flex: 1, height: 8, borderRadius: 4, background: 'var(--bg-card)', border: '1px solid var(--border-card)' }}>
            <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${o.elapsed_pct}%`, borderRadius: 4, background: 'var(--accent)' }} /></span>
          <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>прошло {pct(o.elapsed_pct)} периода</span>
        </div>
      )}
    </div>
  )
}

export function headline(now, row) {
  const s = now.slot, n = now.start_in
  if (s === 'booking' || s === 'mp_prep' || s === 'mp_sent') {
    if (n == null) return 'даты размещения не заданы'
    return n < 0 ? `${-n} дн. назад должен был стартовать` : n === 0 ? 'старт сегодня' : `${n} дн. до старта`
  }
  if (s === 'prep') return now.head?.text || 'сборка запуска'
  if (s === 'live') return row.reason || 'кампания идёт'
  if (s === 'recon') return `на стадии ${row.stage_days ?? '—'} дн. · норма 3`
  return row.reason || ''
}

export function tilesOf(now, row, deal) {
  const n = now.start_in
  const mp = (deal?.our_mps || [])[0]
  if (now.slot === 'booking') {
    return [['до старта', n == null ? '—' : n < 0 ? 'прошёл' : `${n} дн.`, now.period_from ? dm(now.period_from) : '', n != null && n < 0 ? 'var(--warning-fg)' : null],
      ['бюджет', mln(row.amount), 'клиентская сумма'], ['медиаплан', mp ? 'принят' : 'нет', mp ? `версия ${mp.version}` : '', mp ? 'var(--income-fg)' : null],
      ['бронь', row.turn?.mine ? 'не подтв.' : 'рано', 'подтверждать за 15 дн.']]
  }
  return [['возраст МП', `${row.stage_days ?? '—'} дн.`, now.slot === 'mp_sent' ? 'у клиента' : 'готовим'],
    ['старт', n == null ? '—' : n < 0 ? 'прошёл' : `через ${n} дн.`, now.period_from ? dm(now.period_from) : ''],
    ['бюджет', mln(row.amount), 'план'], ['версия МП', mp ? String(mp.version) : '—', mp ? '' : 'плана нет']]
}
