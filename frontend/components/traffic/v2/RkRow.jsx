// Строка РК дашборда трафика v2 (хендофф design_handoff_traffic_expand_v2, 17.11.2026, раздел 6): карточка 50px на РК,
// раскрытая — та же строка на `--bg-tint` с границей снизу, расхлоп под ней в той же карточке. Колонки — `RK_GRID`, общий
// с шапкой колонок. Пороги тона — боевые (`pctTone`, владелец 17.11.2026), а не 0,8/0,5 из макета.
import { MONO } from '@/components/salesTableKit'
import { DASH, RunToggle, ServiceCell, StatusPill, StopBtn, num } from '@/components/traffic/dashboardKit'
import { surfaceTag } from '@/lib/dealTitle'
import CopyCode from '@/components/CopyCode'
import { chipsOf, rkTone, sysSquares, TONE_BAR, TONE_FG, ticksOf } from './rkModel'
import { dm } from '@/lib/salesFormat'

export const RK_GRID = '14px 64px minmax(240px,1.6fr) 62px 132px 112px 84px 118px 92px 84px minmax(170px,1fr) 92px 92px 176px'

const mono = { fontFamily: MONO, fontSize: 12, textAlign: 'right', whiteSpace: 'nowrap' }
const pctText = (v) => (v == null ? '' : `${Number(v).toFixed(1).replace('.', ',')} %`)

/** Шапка колонок — над всеми карточками, со сдвигом под их рамку и отступ. */
export function RkHead() {
  const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: RK_GRID, gap: 12, alignItems: 'center', padding: '0 15px 0 19px', ...cap }}>
      <span /><span>Сделка</span><span>Название РК</span><span>Услуга</span><span>Площадки</span><span>Статус РК</span>
      <span title="Е — ЕРИД креативов · W — пиксель Weborama · D — заведено в DSP · С — скрины запуска" style={{ whiteSpace: 'nowrap' }}>Е · W · D · С</span>
      <span>Период</span><span style={{ textAlign: 'right' }}>План</span><span style={{ textAlign: 'right' }}>Факт</span>
      <span title="Цвет — как идёт открутка: зелёный — по темпу, жёлтый — отстаёт, красный — недокрут. Риска — где РК должна быть по календарю. Пипсы площадок — та же шкала по каждой площадке"
        style={{ cursor: 'help', paddingLeft: 16 }}>Выполнение ⓘ</span>
      <span style={{ textAlign: 'right' }}>Прогноз</span><span style={{ textAlign: 'right' }}>Недокрут</span><span />
    </div>
  )
}

function Bar({ r, tone }) {
  const pct = r.done_pct
  const fl = r.pace == null ? null : Math.min(100, r.pace * 100)
  return (
    <span title={pct == null ? 'факта ещё нет' : `выполнено ${pctText(pct)}${fl == null ? '' : ` при флайте ${Math.round(fl)} %`}`}
      style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '0 10px 0 16px' }}>
      <span style={{ position: 'relative', height: 6, borderRadius: 3, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)' }}>
        <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, Math.max(0, pct || 0))}%`, borderRadius: 3, background: TONE_BAR[tone] }} />
        {fl != null && <span style={{ position: 'absolute', left: `${fl}%`, top: -3, bottom: -3, width: 2, background: 'var(--text-secondary)' }} />}
      </span>
      <span style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 9.5 }}>
        <span style={{ fontWeight: 700, color: TONE_FG[tone] }}>{pctText(pct)}</span>
        <span style={{ color: 'var(--text-faint)' }}>{fl == null ? '' : `флайт ${Math.round(fl)} %`}</span>
      </span>
    </span>
  )
}

function Left({ r }) {
  const text = r.days_to_start
    ? (r.days_to_start === 1 ? 'старт завтра' : `до старта ${r.days_to_start} дн`)
    : r.days_left == null ? DASH : r.flight_over ? 'флайт закончен' : `${r.days_left} дн осталось`
  return <span style={{ fontSize: 10, whiteSpace: 'nowrap', color: r.days_to_start ? 'var(--accent-fg)' : 'var(--text-faint)' }}>{text}</span>
}

/**
 * props: r — строка реестра; open — раскрыта ли; mayEdit, mayReport; onToggle(); onStart(); onPause(); onStop().
 */
export default function RkRow({ r, open, mayEdit, mayReport, onToggle, onStart, onPause, onStop }) {
  const tone = rkTone(r)
  const ticks = ticksOf(r)
  const running = r.status === 'запущена'
  const startable = r.status !== 'окончена' && r.status !== 'архив'
  const block = r.dsp_block
  return (
    <div id={`rk-row-${r.id}`} onClick={onToggle} title={`${open ? 'Свернуть РК' : 'Развернуть РК'} · трафик: ${r.traffic || 'не назначен'}`}
      style={{ display: 'grid', gridTemplateColumns: RK_GRID, gap: 12, alignItems: 'center', boxSizing: 'border-box', height: 50,
        padding: '0 14px 0 18px', cursor: 'pointer', background: open ? 'var(--bg-tint)' : 'var(--bg-card)',
        borderBottom: `1px solid ${open ? 'var(--border-card)' : 'transparent'}` }}>
      <span style={{ fontSize: 8, color: 'var(--text-faint)' }}>{open ? '▴' : '▾'}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}
        onClick={e => e.stopPropagation()}>
        <span style={{ flex: '0 0 6px', width: 6, height: 6, borderRadius: 2, background: tone === 'none' ? 'transparent' : TONE_BAR[tone] }} />
        <CopyCode text={r.deal_code} />
      </span>
      <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span title={r.deal_title} style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.deal_title}</span>
        <span style={{ display: 'flex', gap: 5, overflow: 'hidden' }}>
          {chipsOf(r, tone).map(c => (
            <span key={c.t} title={c.hint} style={{ display: 'inline-flex', alignItems: 'center', height: 16, padding: '0 6px', borderRadius: 5,
              background: c.danger ? 'var(--danger-tint)' : 'var(--warning-tint)', border: `1px solid ${c.danger ? 'var(--danger-border)' : 'var(--warning-border)'}`,
              fontSize: 10, fontWeight: 600, color: c.danger ? 'var(--danger-fg)' : 'var(--warning-fg)', whiteSpace: 'nowrap' }}>{c.t}</span>
          ))}
        </span>
      </span>
      <ServiceCell product={r.product} color={r.product_color} surface={surfaceTag(r.inventory)} />
      <span title={`крутят ${r.placements_on || 0} из ${r.placements || 0}${ticks.lag ? ` · отстают ${ticks.lag}` : ''}`}
        style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ display: 'inline-flex', gap: 2 }}>
          {ticks.colors.map((c, i) => <span key={i} style={{ width: 4, height: 13, borderRadius: 1, background: c }} />)}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{r.placements_on || 0} / {r.placements || 0}</span>
      </span>
      <span><StatusPill value={r.status} w={104} /></span>
      <span style={{ display: 'inline-flex', gap: 3 }}>
        {sysSquares(r).map(m => (
          <span key={m.l} title={m.t} style={{ fontFamily: MONO, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18,
            boxSizing: 'border-box', borderRadius: 5, background: m.bg, border: `1px solid ${m.border}`, fontSize: 9, fontWeight: 700, color: m.fg }}>{m.l}</span>
        ))}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{dm(r.date_start)} … {dm(r.date_end)}</span>
        <Left r={r} />
      </span>
      <span style={{ ...mono, fontWeight: 700 }}>{r.plan_show ? num(r.plan_show) : <span style={{ color: 'var(--warning-fg)' }}>нет МП</span>}</span>
      <span style={{ ...mono, fontWeight: 700, color: r.fact_shows == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>{num(r.fact_shows)}</span>
      <Bar r={r} tone={tone} />
      <span style={{ ...mono, color: r.forecast == null ? 'var(--text-faint)' : 'var(--text-secondary)' }}>{num(r.forecast)}</span>
      <span style={{ ...mono, fontWeight: 700, color: r.under ? TONE_FG[tone === 'ok' ? 'warn' : tone] : 'var(--text-faint)' }}>
        {r.under == null ? DASH : r.under ? `−${num(r.under)}` : '0'}</span>
      <span style={{ display: 'inline-flex', justifyContent: 'flex-end', alignItems: 'center', gap: 6 }} onClick={e => e.stopPropagation()}>
        {mayReport && (
          <a href={`/traffic/campaign/${encodeURIComponent(r.deal_code || '')}`} className="tp-icon" title="Отчёт по РК: срезы, площадки, выводы"
            style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', boxSizing: 'border-box', background: 'var(--bg-card)',
              border: '1px solid var(--border-card)', borderRadius: 8, fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)',
              whiteSpace: 'nowrap', textDecoration: 'none' }}>Отчёт по РК</a>
        )}
        {mayEdit && (
          <>
            <RunToggle running={running} disabled={!!block || (!running && !startable)}
              title={block || (running ? 'Поставить РК на паузу' : r.launch_hint ? `Запуск заперт: ${r.launch_hint}` : 'Запустить РК')}
              onClick={() => (running ? onPause() : onStart())} />
            <StopBtn disabled={!!block} title={block || 'Остановить РК'} label="Стоп РК" onClick={onStop} />
          </>
        )}
      </span>
    </div>
  )
}
