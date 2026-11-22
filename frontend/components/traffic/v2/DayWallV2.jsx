/**
 * «Стена дней» v2 и строка-итог свёрнутых виджетов — хендофф «Дашборд трафика · расхлоп v2» (README 5, 5.2).
 *
 * Пропы:
 *   DayWallV2       { wall, rows, onPick, activeId? }
 *     wall      — `data.wall` GET /api/traffic-dashboard/dashboard
 *     rows      — `data.rows` того же ответа: имя («рекламодатель · бренд») и доля флайта, по id
 *     onPick(id) — клик по строке: странице прокрутить к РК и раскрыть её
 *     activeId  — раскрытая РК, строка подсвечивается
 *   WidgetsSummary  { platData, wall, rows, onOpen }
 *     platData  — `toReport()` из lib/platformsReport; null — ещё не загружено, тогда только часть стены
 *     onOpen()  — клик по карточке: развернуть виджеты
 */
import { useMemo, useState } from 'react'
import { MONO } from '../../salesTableKit'
import { DayTip, cellBucket } from '../dashboardKit'
import { Segmented, culpritsSummary, plural } from '../platforms/reportKit'
import { grp } from '@/lib/salesFormat'
import {
  buildWall, visibleRows, axisLabels, dayTitle, dayHint, pctText,
  STATE_BG, STATE_BORDER, WALL_LEGEND_V2, WALL_SHOWN,
} from './wallModel'

const COLS = '58px minmax(120px,0.8fr) minmax(300px,2fr) 122px'
const CAP = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const CARD = {
  background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18,
}
const LINK = { fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)', cursor: 'pointer' }

const Swatch = ({ state }) => (
  <span style={{ width: 8, height: 8, borderRadius: 2, boxSizing: 'border-box',
    background: STATE_BG[state], border: `1px solid ${STATE_BORDER[state]}` }} />
)

const Legend = () => (
  <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 12, fontSize: 10.5 }}>
    {WALL_LEGEND_V2.map(([t, s]) => (
      <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap' }}>
        <Swatch state={s} />{t}
      </span>
    ))}
  </span>
)

const OnlyRecent = ({ on, n, onToggle }) => (
  <span role="button" tabIndex={0} onClick={onToggle} onKeyDown={e => e.key === 'Enter' && onToggle()}
    title="Оставить РК, у которых был провал в последние три дня"
    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 9px', borderRadius: 8,
      fontSize: 11.5, whiteSpace: 'nowrap', cursor: 'pointer',
      background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
      border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
      color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontWeight: on ? 700 : 600 }}>
    провал за 3 дня<span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{n}</span>
  </span>
)

/* Итог по дням: столбик — сколько РК шли ниже темпа (красная часть — провал, жёлтая — просадка). */
const DayBars = ({ model, hov, onHov }) => (
  <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'end', paddingTop: 4 }}>
    <span style={{ ...CAP, gridColumn: 'span 2', paddingBottom: 3 }}>РК ниже темпа по дням</span>
    <span style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 34 }}>
      {model.per.map((x, i) => (
        <span key={model.dates[i]} title={dayTitle(model, i)}
          onMouseEnter={() => onHov(i)} onMouseLeave={() => onHov(h => (h === i ? -1 : h))}
          style={{ flex: '1 1 0', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%',
            gap: 1, borderRadius: 2, background: hov === i ? 'var(--bg-subtle)' : 'transparent' }}>
          <span style={{ height: `${Math.round(x.bad / model.max * 100)}%`, background: 'var(--danger)', borderRadius: '2px 2px 0 0' }} />
          <span style={{ height: `${Math.round(x.warn / model.max * 100)}%`, background: 'var(--warning)' }} />
        </span>
      ))}
    </span>
    <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-muted)', textAlign: 'right', paddingBottom: 3 }}>
      {dayHint(model, hov)}
    </span>
  </div>
)

const AxisHead = ({ model }) => (
  <div style={{ ...CAP, display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', padding: '3px 0 5px',
    borderTop: '1px solid var(--border-inner)', borderBottom: '1px solid var(--border-inner)' }}>
    <span>Сделка</span><span>Рекламодатель · бренд</span>
    <span style={{ display: 'flex', gap: 2 }}>
      {axisLabels(model).map((d, i) => (
        <span key={model.dates[i]} style={{ flex: '1 1 0', textAlign: 'center', fontSize: 8, letterSpacing: 0,
          color: d.today ? 'var(--text-primary)' : 'var(--text-faint)', fontWeight: d.today ? 700 : 400 }}>{d.t}</span>
      ))}
    </span>
    <span style={{ textAlign: 'right' }}>Факт · к флайту</span>
  </div>
)

/* Клетка дня. Пустой слот — день вне флайта этой РК: не красится и без контура. */
const Cell = ({ c, dim, active, onEnter, onLeave }) => (
  <span onMouseEnter={c ? onEnter : undefined} onMouseLeave={c ? onLeave : undefined}
    style={{ flex: '1 1 0', minWidth: 3, height: 14, borderRadius: 2.5, boxSizing: 'border-box',
      background: c ? STATE_BG[c.state] : 'transparent',
      border: `1px solid ${c ? STATE_BORDER[c.state] : 'transparent'}`,
      opacity: dim ? 0.35 : 1, boxShadow: active ? '0 0 0 2px var(--accent)' : 'none' }} />
)

const rowTitle = (r) => `${r.name} · провалов ${r.counts.bad}, просадок ${r.counts.warn}, в норме ${r.counts.ok}`
  + (r.pace == null ? '' : ` · флайт ${pctText(r.pace * 100)}`)

const WallRow = ({ r, hov, tipKey, active, onPick, onTip }) => (
  <div role="button" tabIndex={0} onClick={() => onPick?.(r.id)} onKeyDown={e => e.key === 'Enter' && onPick?.(r.id)}
    style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', height: 22, borderRadius: 4,
      cursor: onPick ? 'pointer' : 'default', background: active ? 'var(--bg-subtle)' : 'transparent' }}
    onMouseOver={e => { e.currentTarget.style.background = 'var(--bg-tint)' }}
    onMouseOut={e => { e.currentTarget.style.background = active ? 'var(--bg-subtle)' : 'transparent' }}>
    <span title={rowTitle(r)} style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent-fg)' }}>{r.code}</span>
    <span title={rowTitle(r)} style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)',
      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
    <span style={{ display: 'flex', gap: 2 }}>
      {r.slots.map((c, i) => {
        const key = `${r.id}:${i}`
        return (
          <Cell key={i} c={c} dim={hov >= 0 && hov !== i} active={tipKey === key}
            onEnter={(e) => {
              const box = e.currentTarget.getBoundingClientRect()
              onTip({ key, b: cellBucket(c), label: `${r.code}${r.product ? ` · ${r.product}` : ''}`, unit: r.unit,
                x: box.left + box.width / 2, y: box.top, bottom: box.bottom })
            }}
            onLeave={() => onTip(t => (t && t.key === key ? null : t))} />
        )
      })}
    </span>
    <span style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'baseline', gap: 8 }}>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
        color: r.fact == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>{pctText(r.fact)}</span>
      <span style={{ fontFamily: MONO, fontSize: 10, width: 64, textAlign: 'right', whiteSpace: 'nowrap', color: r.lag.fg }}>
        {r.lag.text}
      </span>
    </span>
  </div>
)

const wallCaption = (m) => {
  const base = `${m.all.length} РК${m.totalRows > m.all.length ? ` из ${m.totalRows}` : ''}`
  return m.worstDay ? `${base} · хуже всего ${m.worstDay}: ${m.worstDayBelow} РК ниже темпа` : `${base} · дней ниже темпа не было`
}

// `fill` — карточка занимает высоту ячейки и растёт вниз при «ещё N РК ▾», без прокрутки внутри (владелец 17.11.2026, вечер);
// утреннее решение «строки прокручиваются внутри» снято. Было: (17.11.2026).
export function DayWallV2({ wall, rows, onPick, activeId, fill = false }) {
  const model = useMemo(() => buildWall(wall, rows), [wall, rows])
  const [sort, setSort] = useState('worst')
  const [onlyRecent, setOnlyRecent] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [hov, setHov] = useState(-1)
  const [tip, setTip] = useState(null)
  const { rows: list, full } = visibleRows(model, { sort, onlyRecent, expanded })

  return (
    <div style={{ ...CARD, flex: '1 1 0', minWidth: 0, padding: '14px 18px 12px', display: 'flex', flexDirection: 'column', gap: 8,
      ...(fill ? { height: '100%', boxSizing: 'border-box' } : null) }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 800 }}>Стена дней</span>
        <span style={CAP}>день против нужного темпа</span>
        <span style={{ marginLeft: 'auto' }}>
          <Segmented value={sort} onChange={setSort} options={[['worst', 'хуже сначала'], ['code', 'по коду']]} />
        </span>
        <OnlyRecent on={onlyRecent} n={model.recentCount} onToggle={() => setOnlyRecent(v => !v)} />
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 11.5, color: 'var(--text-muted)' }}>
        <span>{wallCaption(model)}</span>
        <Legend />
      </span>
      {model.all.length ? (
        <>
          <DayBars model={model} hov={hov} onHov={setHov} />
          <AxisHead model={model} />
          <div style={{ display: 'flex', flexDirection: 'column', ...(fill ? { flex: '1 1 auto' } : null) }}>
            {list.map(r => (
              <WallRow key={r.id} r={r} hov={hov} tipKey={tip?.key} active={r.id === activeId} onPick={onPick} onTip={setTip} />
            ))}
            {!list.length && (
              <span style={{ padding: '10px 0', fontSize: 12, color: 'var(--text-faint)' }}>
                Провалов за последние три дня нет.
              </span>
            )}
          </div>
          {full > WALL_SHOWN && (
            <span role="button" tabIndex={0} onClick={() => setExpanded(v => !v)}
              onKeyDown={e => e.key === 'Enter' && setExpanded(v => !v)} style={{ ...LINK, paddingTop: 2 }}>
              {expanded ? `свернуть до ${WALL_SHOWN} худших ▴` : `ещё ${full - WALL_SHOWN} РК — ближе к темпу ▾`}
            </span>
          )}
        </>
      ) : (
        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
          Пока нечего показывать: ни у одной РК нет ни флайта, ни плана.
        </span>
      )}
      {tip && <DayTip {...tip} />}
    </div>
  )
}

const SumCap = ({ children }) => (
  <span style={{ ...CAP, fontWeight: 700, color: 'var(--text-primary)' }}>{children}</span>
)
const B = ({ children }) => <b style={{ fontFamily: MONO }}>{children}</b>

const wallSummary = (m) => {
  if (!m.all.length) return 'нет РК с флайтом'
  const worst = m.worstRk ? ` · худшая ${m.worstRk.code} ${pctText(m.worstRk.fact)}` : ''
  const day = m.worstDay ? ` · хуже всего ${m.worstDay}` : ''
  return `${m.recentCount} РК с провалом за 3 дня${worst}${day}`
}

export function WidgetsSummary({ platData, wall, rows, onOpen }) {
  const model = useMemo(() => buildWall(wall, rows), [wall, rows])
  const cul = platData ? culpritsSummary(platData) : null
  return (
    // NAVY (17.11.2026): свёрнутые виджеты — тёмной строкой, как сами виджеты; в прежних темах атрибут ничего не меняет
    <div role="button" tabIndex={0} onClick={() => onOpen?.()} onKeyDown={e => e.key === 'Enter' && onOpen?.()}
      title="Развернуть виджеты" data-tone="dark" className="tp-widgets-sum"
      style={{ ...CARD, display: 'flex', alignItems: 'center', gap: 22, padding: '9px 18px', cursor: 'pointer' }}>
      {cul && (
        <>
          <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8, whiteSpace: 'nowrap' }}>
            <SumCap>Площадки-виновники</SumCap>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {plural(cul.count, 'площадка', 'площадки', 'площадок')} с недокрутом или WR · <B>{cul.under ? `−${grp(cul.under)}` : '0'}</B> показов · системно <B>{cul.systemic}</B>
            </span>
          </span>
          <span style={{ width: 1, height: 18, background: 'var(--border-inner)' }} />
        </>
      )}
      <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8, whiteSpace: 'nowrap', minWidth: 0 }}>
        <SumCap>Стена дней</SumCap>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{wallSummary(model)}</span>
      </span>
      <span style={{ marginLeft: 'auto', ...LINK, whiteSpace: 'nowrap' }}>развернуть ▾</span>
    </div>
  )
}
