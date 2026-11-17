// Строки таблицы площадок v2 (хендофф 8.2–8.5): шапка с сортировкой, строка группы с итогами, строка площадки.
// Первый столбец закреплён (`sticky; left: 0`), фон наследует от строки — поэтому фон задаётся СТРОКЕ, а не ячейке.
import { MONO, Z } from '@/components/salesTableKit'
import { DASH, PlaceActions, creativeCountsTitle, num } from '@/components/traffic/dashboardKit'
import PaceCell from '@/components/traffic/PaceCell'
import ExternalLaunch from '@/components/traffic/ExternalLaunch'
import { ctrTone, groupOf, volTint, volTitle } from '@/lib/sitesModel.mjs'
import { CAP_V2, CTR_STYLE, NUM, SITE_GRID, StatusDot, ctrTitle, pct1, pct2, SysCell, SysLegend } from './sitesBits'

const STICKY = { position: 'sticky', left: 0, zIndex: Z.base + 1, alignSelf: 'stretch', boxSizing: 'border-box',
  background: 'inherit', boxShadow: '1px 0 0 var(--border-inner)', display: 'flex', alignItems: 'center' }
const ROW = { display: 'grid', gridTemplateColumns: SITE_GRID, gap: 8, alignItems: 'center', padding: '0 18px 0 0' }
const CHIP = { fontFamily: MONO, flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', height: 16, padding: '0 5px',
  borderRadius: 4, fontSize: 8.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }
const WARN_CHIP = { ...CHIP, background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', color: 'var(--warning-fg)' }
const fk = (v) => (v == null ? DASH : num(Math.round(v / 1000)))

/* ── шапка ─────────────────────────────────────────────────────────────────── */

const COLS = [
  ['name', 'Площадка · код', 'По названию'],
  ['cr', 'Креат.', 'Креативы: всего / согласовано / заведено в DSP'],
  ['weight', 'Вес, т.', 'Вес площадки, тысячи', true],
  ['share', 'Доля', 'Доля площадки в плане РК', true],
  ['plan', 'План', 'План площадки; «ФИКС» — объём задан в блоке креатива сделки', true],
  ['fact', 'Факт', '', true],
  ['clk', 'Клики', '', true],
  ['ctr', 'CTR', 'CTR площадки за период', true],
  ['exec', 'Выполнение', 'Заливка — факт от плана площадки, риска — доля прошедшего флайта РК'],
  ['under', 'Недокрут', 'Недокрут к прогнозу — тот же расчёт, что у РК', true],
  ['wr', 'Расх. WR', 'Расхождение показов с Weborama за период: (факт − WR) / факт; предел — из цели сделки', true],
  ['pace', 'Темп', 'Темп последних суток против нужного в день'],
  ['status', 'Статус', ''],
  ['sys', 'Системы', 'Состояние систем по площадке: Е · W · D · С'],
]

export const SitesHead = ({ sort, onSort, goal }) => (
  <div style={{ ...ROW, ...CAP_V2, minHeight: 28, background: 'var(--bg-card)', borderTop: '1px solid var(--border-card)',
    borderBottom: '1px solid var(--border-card)' }}>
    {COLS.map(([key, label, hint, right], i) => {
      const on = sort.key === key
      const title = (key === 'ctr' && goal ? `${hint}; цель РК — ${pct2(goal)}` : hint)
      return (
        <span key={key} onClick={() => onSort(key)} title={`${title ? `${title}. ` : ''}Клик — сортировать`}
          style={{ whiteSpace: 'nowrap', cursor: 'pointer', color: on ? 'var(--accent-fg)' : 'var(--text-cap)',
            textAlign: right ? 'right' : 'left', ...(i === 0 ? { ...STICKY, paddingLeft: 22 } : null) }}>
          {label}{on ? (sort.dir === 'asc' ? ' ▴' : ' ▾') : ''}
        </span>
      )
    })}
    <span />
  </div>
)

/* ── строка группы ─────────────────────────────────────────────────────────── */

const TOT = { ...NUM, fontSize: 10, color: 'var(--text-muted)' }

export const GroupRow = ({ g }) => {
  const t = g.totals
  return (
    <div style={{ ...ROW, minHeight: 24, background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
      <span title={g.hint} style={{ ...STICKY, paddingLeft: 22, gap: 8, whiteSpace: 'nowrap' }}>
        <span style={{ flex: '0 0 7px', width: 7, height: 7, borderRadius: 2, background: g.dot }} />
        <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          {g.title}</span>
        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{t.n}</span>
      </span>
      <span /><span />
      <span style={TOT}>{pct1(t.share * 100)}</span>
      <span style={TOT}>{num(t.plan)}</span>
      <span style={TOT}>{num(t.fact)}</span>
      <span style={TOT}>{num(t.clicks)}</span>
      <span style={TOT}>{t.ctr == null ? '' : pct2(t.ctr)}</span>
      <span />
      <span style={{ ...TOT, fontWeight: 700, color: 'var(--text-secondary)' }}>{t.under > 0 ? `−${num(t.under)}` : '0'}</span>
      <span style={TOT} title="Площадок с расхождением с Weborama за пределом из цели сделки">
        {t.wrBad ? `${t.wrBad} > ${t.wrLimit != null ? `${t.wrLimit} %` : 'предел'}` : ''}</span>
      <span /><span /><SysLegend /><span />
    </div>
  )
}

/* ── ячейки строки площадки ────────────────────────────────────────────────── */

const NameCell = ({ p, open }) => (
  <span style={{ ...STICKY, padding: '0 8px', gap: 6, minWidth: 0 }}>
    <span style={{ flex: '0 0 8px', fontSize: 7, color: 'var(--text-faint)' }}>{open ? '▴' : '▾'}</span>
    <span title={p.domain || p.publisher} style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.domain || p.publisher}</span>
    {/* Трёхбуквенный код — у всех площадок, у внешних тоже (владелец 17.11.2026) */}
    {!!p.code && <span style={{ fontFamily: MONO, flex: '0 0 auto', fontSize: 9.5, color: 'var(--text-faint)' }}>{p.code}</span>}
    {p.ext_mode === 'external' && (
      // «внешний», а не «чужой», и у правого края столбца (владелец 17.11.2026)
      <span style={{ ...WARN_CHIP, marginLeft: 'auto' }}
        title="Не наш код: площадка во внешней DSP — в нашу DSP её не завести, креатив заводится там вручную">внешний</span>
    )}
    {p.ext_mode === 'mixed' && (
      <span style={WARN_CHIP} title={`${(p.ext_surfaces || []).join('/')} — во внешней DSP, остальное — через нашу DSP`}>
        {(p.ext_surfaces || []).join('/')} вне DSP</span>
    )}
    {!!p.is_direct && (
      <span style={{ ...CHIP, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', color: 'var(--text-muted)' }}
        title="Площадка крутит сама — факт вводится руками">сама</span>
    )}
  </span>
)

const CrCell = ({ c }) => {
  if (!c) return <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{DASH}</span>
  const even = c.total === c.agreed && c.agreed === c.live
  return (
    <span title={creativeCountsTitle(c)} style={{ fontFamily: MONO, fontSize: 11, whiteSpace: 'nowrap',
      color: even ? 'var(--text-secondary)' : 'var(--warning-fg)' }}>{c.total}/{c.agreed}/{c.live}</span>
  )
}

const PlanCell = ({ p }) => (
  <span style={{ ...NUM, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 5 }}>
    <span style={{ display: 'inline-flex' }}>
      {!!p.fixed && (
        <span title="Объём задан в блоке креатива сделки — площадка получает ровно его, остаток плана РК делится по весам"
          style={{ display: 'inline-flex', alignItems: 'center', height: 14, padding: '0 4px', borderRadius: 4,
            background: 'var(--accent-tint)', fontSize: 8, fontWeight: 700, letterSpacing: '0.05em',
            color: 'var(--accent-fg)' }}>ФИКС</span>
      )}
    </span>
    <span style={{ fontWeight: 700 }}>{num(p.plan_show)}</span>
  </span>
)

const BAR_BG = { act: 'var(--income)', ok: 'var(--income)', lag: 'var(--warning)', over: 'var(--accent)' }

const ExecCell = ({ p, grp, flight }) => {
  const has = p.plan_show && p.fact_shows != null
  const pct = has ? p.fact_shows / p.plan_show * 100 : null
  const title = has ? `факт ${num(p.fact_shows)} из ${num(p.plan_show)}`
    + (flight != null ? ` · прошло ${Math.round(flight * 100)} % флайта` : '') : 'плана или факта нет'
  return (
    <span title={title} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ flex: '1 1 auto', position: 'relative', height: 6, borderRadius: 3, background: 'var(--bg-subtle)',
        border: '1px solid var(--border-inner)' }}>
        <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 3,
          width: `${has ? Math.min(100, Math.round(pct)) : 0}%`, background: BAR_BG[grp] }} />
        {flight != null && (
          <span style={{ position: 'absolute', left: `${Math.min(100, Math.max(0, flight * 100))}%`, top: -3, bottom: -3,
            width: 2, background: 'var(--text-secondary)' }} />
        )}
      </span>
      <span style={{ fontFamily: MONO, flex: '0 0 34px', fontSize: 10, textAlign: 'right', color: 'var(--text-muted)' }}>
        {has ? `${Math.round(pct)} %` : ''}</span>
    </span>
  )
}

const WrCell = ({ p }) => {
  const m = p.wr_mismatch
  if (!m || m.pct == null) {
    return (
      <span style={{ ...NUM, color: 'var(--text-disabled)' }}
        title={p.wr == null ? 'Данных верификатора по площадке нет' : 'Показов нет — сверять нечего'}>{DASH}</span>
    )
  }
  const fg = m.level === 'bad' ? 'var(--danger-fg)' : m.level === 'warn' ? 'var(--warning-fg)' : 'var(--text-muted)'
  const sign = m.pct > 0 ? '+' : m.pct < 0 ? '−' : ''
  const title = [`факт ${num(p.fact_shows)} · WR ${num(p.wr)}`, m.hint, m.reason].filter(Boolean).join('\n')
  return (
    <span title={title} style={{ ...NUM, color: fg, fontWeight: m.level === 'ok' ? 400 : 700 }}>
      {sign}{Math.abs(m.pct).toFixed(1).replace('.', ',')} %</span>
  )
}

const Actions = ({ p, h }) => (
  <span style={{ display: 'inline-flex', justifyContent: 'flex-end' }} onClick={e => e.stopPropagation()}>
    {p.ext_mode === 'external' ? (
      <ExternalLaunch status={p.status} canStart={p.can_start} onChange={st => h.setPlacementStatus(p, st)} />
    ) : (
      <PlaceActions status={p.status} canStart={p.can_start} uploaded={p.dsp_uploaded} why={p.start_why}
        onStart={() => h.setPlacementStatus(p, 'запущен')} onPause={() => h.setPlacementStatus(p, 'пауза')}
        onOff={() => h.setPlacementStatus(p, 'завершена')} />
    )}
  </span>
)

/* ── строка площадки ───────────────────────────────────────────────────────── */

/**
 * Клик по строке раскрывает креативы; кнопки и галочка строку не раскрывают. Пауза — строка в 60 % (8.12).
 * Фон: раскрыта — `--bg-tint`; объём площадки больше половины / всего плана РК — жёлтый / красный (27.09.2026).
 */
export const SiteRow = ({ p, open, onToggle, d, goal, mayEdit, h }) => {
  const grp = groupOf(p)
  const tone = ctrTone(p.ctr, goal)
  const bg = open ? 'var(--bg-tint)' : volTint(d.volumes, p.publisher_id) || 'var(--bg-card)'
  const under = p.under == null ? DASH : p.under > 0 ? `−${num(p.under)}` : '0'
  return (
    <div onClick={onToggle} title={volTitle(d.volumes, p.publisher_id) || (open ? 'Свернуть креативы' : 'Показать креативы площадки')}
      onMouseEnter={e => { if (!open) e.currentTarget.style.background = 'var(--bg-tint)' }}
      onMouseLeave={e => { e.currentTarget.style.background = bg }}
      style={{ ...ROW, boxSizing: 'border-box', height: 31, borderBottom: '1px solid var(--border-row)', background: bg,
        opacity: p.status === 'пауза' ? 0.6 : 1, cursor: 'pointer' }}>
      <NameCell p={p} open={open} />
      <CrCell c={p.creative_counts} />
      <span style={{ ...NUM, color: p.no_weight ? 'var(--warning-fg)' : 'var(--text-secondary)' }}
        title={p.no_weight ? 'Нет индекса в балансировщике — в раскладку не попадёт' : undefined}>
        {p.no_weight ? 'нет' : fk(p.weight)}</span>
      <span style={{ ...NUM, color: 'var(--text-secondary)' }}>{p.share ? pct1(p.share * 100) : DASH}</span>
      <PlanCell p={p} />
      <span style={{ ...NUM, fontWeight: 700, color: p.fact_shows == null ? 'var(--text-faint)' : undefined }}>
        {num(p.fact_shows)}</span>
      <span style={{ ...NUM, color: 'var(--text-secondary)' }}>{num(p.fact_clicks)}</span>
      <span title={ctrTitle(p.ctr, goal)} style={{ ...NUM, ...CTR_STYLE[tone] }}>{pct2(p.ctr)}</span>
      <ExecCell p={p} grp={grp} flight={d.pace} />
      <span style={{ ...NUM, fontWeight: 700, color: p.under == null ? 'var(--text-disabled)'
        : grp === 'lag' ? 'var(--warning-fg)' : 'var(--text-secondary)' }}
        title="Недокрут к прогнозу: план площадки − прогноз на конец флайта">{under}</span>
      <WrCell p={p} />
      <span style={{ display: 'flex', minWidth: 0, overflow: 'hidden' }}><PaceCell pace={p.pace} /></span>
      <span style={{ display: 'flex', minWidth: 0 }}>
        <StatusDot value={p.status}
          title={(d.placement_manual || []).includes(p.status) ? p.status : `${p.status} — ставит согласование креативов`} />
      </span>
      <SysCell s={p._sys} />
      {mayEdit ? <Actions p={p} h={h} /> : <span />}
    </div>
  )
}
