// Матрица «площадка × РК» — тело двух вкладок экрана «Согласования» (владелец 29.09.2026).
// view='appr' — светофор согласования; view='plan' — план показов и план себестоимости.
// Данные — /publisher-approvals/matrix (app/launch_prep/matrix.py).
//
// Вид — по хендоффу docs/матрица сайтов.zip (design_handoff_approvals_matrix): карточка на
// всю оставшуюся высоту, шапка и итог прилипают, площадка и итог — липкие колонки.
// Сетка — CSS-grid по шаблону реестра (правило 28.09), шапка площадки — SortHead из кита.
import { useState } from 'react'
import { MONO, SortHead } from '@/components/salesTableKit'
import { tgHref } from '@/components/publishers/kit'
import safeHref from '@/lib/safeHref'

// Цвет ячейки — токены палитры; подпись легенды — здесь же, одна на экран.
export const TONE = {
  agreed:    { label: 'согласовано', bg: 'var(--income-tint)', fg: 'var(--income-fg)', bd: 'var(--income-border)', kpi: 'var(--income)' },
  waiting:   { label: 'ждём ответа', bg: 'var(--warning-tint)', fg: 'var(--warning-text)', bd: 'var(--warning-border)', kpi: 'var(--warning-text)' },
  late:      { label: 'ждём > 2 раб. дн.', bg: 'var(--warning-bg)', fg: 'var(--dot-current-dz)', bd: 'var(--dot-current-dz)', kpi: 'var(--dot-current-dz)' },
  rework:    { label: 'на доработке', bg: 'var(--violet-tint)', fg: 'var(--violet-fg)', bd: 'var(--violet-border)', kpi: 'var(--violet-fg)' },
  refused:   { label: 'отказ', bg: 'var(--danger-tint)', fg: 'var(--danger-fg)', bd: 'var(--danger-border)', kpi: 'var(--danger-fg)' },
  unsent:    { label: 'не отправлено', bg: 'var(--bg-subtle)', fg: 'var(--text-faint)', bd: 'var(--border-card)', kpi: 'var(--text-faint)' },
  withdrawn: { label: 'отозван', bg: 'repeating-linear-gradient(45deg,var(--bg-subtle) 0 5px,var(--bg-card) 5px 10px)', fg: 'var(--text-muted)', bd: 'var(--border-card)', kpi: 'var(--text-muted)' },
}
export const counted = (tone, pend) => tone === 'agreed' || (pend && (tone === 'waiting' || tone === 'late'))

const nf = new Intl.NumberFormat('ru-RU')
export const short = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(2).replace('.', ',')} млн`
  : v >= 1e3 ? `${Math.round(v / 1e3)} тыс` : nf.format(Math.round(v || 0)))

/** Итоги строки/колонки — одно правило на строки, подвал и KPI страницы. */
export function totalsOf(cells, pend) {
  const t = { g: 0, n: 0, s: 0, m: 0 }
  cells.forEach(c => {
    if (!c) return
    t.n++
    if (c.tone === 'agreed') t.g++
    if (c.plan_show && counted(c.tone, pend)) { t.s += c.plan_show; t.m += c.plan_cost || 0 }
  })
  return t
}

const PUB_W = 230
const TOT_W = 98
const LINE = '1px solid var(--border-row)'
const stick = (left, z = 2, bg = 'var(--bg-card)') => ({ position: 'sticky', left, zIndex: z, background: bg })
const TG_PATH = 'M21.5 3.5 2.8 10.7c-1.3.5-1.2 1.2-.2 1.5l4.8 1.5 1.8 5.6c.2.6.1.9.8.9.5 0 .7-.2 1-.5l2.4-2.3 4.9 3.6c.9.5 1.5.2 1.8-.8l3.2-15.1c.3-1.3-.5-1.9-1.8-1.1zM8 13.4l10.4-6.6c.5-.3.9-.1.5.2l-8.9 8-.3 3.7L8 13.4z'

// Значок группы: есть ссылка — в фирменном цвете мессенджера, нет — серый и неактивный.
function Chat({ href, kind }) {
  const label = kind === 'tg' ? 'Группа в Telegram' : 'Группа в MAX'
  const box = { display: 'inline-flex', width: 18, height: 18, borderRadius: 5, alignItems: 'center',
    justifyContent: 'center', fontFamily: MONO, fontSize: 9, fontWeight: 700, flex: '0 0 auto', textDecoration: 'none' }
  const glyph = (fill) => (kind === 'tg'
    ? <svg width="11" height="11" viewBox="0 0 24 24" style={{ fill }}><path d={TG_PATH} /></svg> : 'M')
  return href
    ? <a href={href} target="_blank" rel="noreferrer" title={label} onClick={e => e.stopPropagation()}
        style={{ ...box, background: kind === 'tg' ? 'var(--brand-tg)' : 'var(--brand-max)', color: 'var(--on-accent)' }}>{glyph('var(--on-accent)')}</a>
    : <span title={`${label}: ссылки нет`} style={{ ...box, background: 'var(--border-inner)', color: 'var(--text-faint)' }}>{glyph('var(--text-faint)')}</span>
}

function tipOf(c, pub, deal, lateDays, extra = []) {
  const state = c.tone === 'waiting' || c.tone === 'late'
    ? `Ждём ответа ${c.days ? `${c.days} раб. дн.` : '— отправлено сегодня'}${c.tone === 'late' ? ` (дольше ${lateDays})` : ''} · согласовано ${c.agreed} из ${c.sent}`
    : c.tone === 'agreed' ? `Согласовано · ${[...new Set(c.states)].join(', ')}` : TONE[c.tone].label
  return { head: `${pub.name} × ${deal.brand} (${deal.code})`, lines: [state,
    `Комплектов: ${c.pairs}, отправлено ${c.sent}${c.withdrawn ? `, отозвано ${c.withdrawn}` : ''}`,
    `Услуга: ${[...new Set(c.services)].join(', ') || '—'}`, `Аккаунт: ${deal.account || '—'}`, ...extra] }
}

function Light({ c }) {
  const t = TONE[c.tone]
  const txt = c.tone === 'late' ? `${c.days} дн` : c.tone === 'refused' ? 'отказ' : c.tone === 'rework' ? 'правки'
    : c.tone === 'withdrawn' ? 'отозв' : c.tone === 'unsent' ? '—' : `${c.agreed}/${c.sent}`
  return (
    <div className="mx-dot" style={{ width: 62, height: 28, margin: 'auto', borderRadius: 8, display: 'flex',
      alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 10.5, fontWeight: 700,
      background: t.bg, color: t.fg, boxShadow: `inset 0 0 0 1px ${t.bd}` }}>{txt}</div>
  )
}

function PlanCell({ c, pend }) {
  if (!c.plan_show) {
    return <div style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', opacity: .6, textAlign: 'center' }}>нет плана</div>
  }
  const inTotal = counted(c.tone, pend)
  const ok = c.tone === 'agreed'
  const wait = c.tone === 'waiting' || c.tone === 'late'
  return (
    <div className="mx-dot" style={{ padding: '4px 6px', borderRadius: 8, lineHeight: 1.25, textAlign: 'center',
      background: ok ? TONE.agreed.bg : wait ? TONE.waiting.bg : 'transparent',
      boxShadow: ok ? `inset 0 0 0 1px ${TONE.agreed.bd}` : wait ? `inset 0 0 0 1px ${TONE.waiting.bd}` : 'none',
      color: ok || wait ? 'var(--text-primary)' : 'var(--text-faint)', opacity: inTotal || wait ? 1 : 0.6 }}>
      <b style={{ display: 'block', fontFamily: MONO, fontSize: 11 }}>{short(c.plan_show)}</b>
      <span style={{ fontFamily: MONO, fontSize: 10, color: c.plan_cost == null ? 'var(--danger-fg)' : 'var(--text-muted)' }}>
        {c.plan_cost == null ? 'нет CPM' : `${short(c.plan_cost)} ₽`}</span>
    </div>
  )
}

const Tot = ({ plan, t }) => (plan
  ? <div style={{ lineHeight: 1.25, textAlign: 'center' }}><b style={{ display: 'block' }}>{short(t.s)}</b>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400 }}>{short(t.m)} ₽</span></div>
  : `${t.g}/${t.n}`)
const totCell = { fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', padding: 6,
  display: 'flex', alignItems: 'center', justifyContent: 'center', alignSelf: 'stretch' }

export default function ApprovalsMatrix({ view, deals, pubs, cell, lateDays, pend, sort, onSort }) {
  const [tip, setTip] = useState(null)
  const plan = view === 'plan'
  const colW = plan ? 98 : 80
  const GRID = `${PUB_W}px ${TOT_W}px repeat(${deals.length}, ${colW}px)`
  const row = { display: 'grid', gridTemplateColumns: GRID }
  const colTot = deals.map(d => totalsOf(pubs.map(p => cell[`${d.id}:${p.id}`]), pend))
  const all = totalsOf(deals.flatMap(d => pubs.map(p => cell[`${d.id}:${p.id}`])), pend)
  const show = (e, t) => setTip({ x: Math.min(e.clientX + 14, window.innerWidth - 316), y: e.clientY + 14, ...t })
  const openDeal = (d) => window.open(`/sales/deals/${d.id}#sec-creatives`, '_blank', 'noopener')

  return (
    <>
      <style>{'.mx-row:hover>div{background:var(--accent-wash)!important}.mx-dot{transition:transform .12s}.mx-dot:hover{transform:scale(1.06)}'}</style>
      <div style={{ width: 'max-content', minWidth: '100%' }}>
        <div style={{ ...row, position: 'sticky', top: 0, zIndex: 3, background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-card)' }}>
          <div style={{ ...stick(0, 4, 'var(--bg-subtle)'), padding: '9px 4px 0', display: 'flex', alignItems: 'flex-end', borderRight: LINE }}>
            <SortHead label="Площадка \ РК" active={sort.key === 'name'} dir={sort.dir} onClick={() => onSort('name')} />
          </div>
          <div style={{ ...stick(PUB_W, 4, 'var(--bg-subtle)'), padding: '9px 0 0', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', borderRight: '1px solid var(--border-card)' }}>
            <SortHead label={plan ? 'Итого' : 'Согл.'} active={sort.key === 'total'} dir={sort.dir} onClick={() => onSort('total')} />
          </div>
          {deals.map(d => (
            <div key={d.id} title={`${d.brand} · ${d.advertiser || ''} · ${d.account || ''}`}
              style={{ padding: '9px 6px', textAlign: 'center', minWidth: 0, borderRight: LINE, alignSelf: 'end' }}>
              <div style={{ fontWeight: 700, fontSize: 11.5, lineHeight: 1.25, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{d.brand}</div>
              <a href={`/sales/deals/${d.id}`} target="_blank" rel="noreferrer"
                style={{ display: 'block', paddingTop: 2, fontFamily: MONO, fontSize: 9.5, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none' }}>{d.code}</a>
            </div>
          ))}
        </div>

        {pubs.map(p => {
          const cells = deals.map(d => cell[`${d.id}:${p.id}`])
          return (
            <div key={p.id} className="mx-row" style={{ ...row, minHeight: 37 }}>
              <div style={{ ...stick(0), display: 'flex', alignItems: 'center', gap: 4, padding: '7px 12px', minWidth: 0, borderBottom: LINE, borderRight: LINE }}>
                <Chat href={safeHref(p.max)} kind="max" />
                <Chat href={safeHref(tgHref(p.tg))} kind="tg" />
                <span title={p.name} style={{ marginLeft: 6, fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
              </div>
              <div style={{ ...stick(PUB_W, 2, 'var(--bg-subtle)'), ...totCell, borderBottom: LINE, borderRight: '1px solid var(--border-card)' }}>
                <Tot plan={plan} t={totalsOf(cells, pend)} />
              </div>
              {deals.map((d, i) => {
                const c = cells[i]
                const base = { padding: 4, borderBottom: LINE, borderRight: LINE, display: 'flex', alignItems: 'center', justifyContent: 'center' }
                if (!c) return <div key={d.id} style={base} />
                const extra = plan ? (c.plan_show
                  ? [`План: ${nf.format(c.plan_show)} показов`, c.plan_cost == null ? 'CPM площадки в реестре не заполнен'
                    : `Себестоимость: ${nf.format(Math.round(c.plan_cost))} ₽ (CPM ${p.cpm} ₽ до НДС)`,
                    ...(counted(c.tone, pend) ? [] : ['В итог не входит'])]
                  : ['Плана у площадки в РК нет (доля не назначена)']) : []
                const t = tipOf(c, p, d, lateDays, extra)
                return (
                  <div key={d.id} style={{ ...base, cursor: 'pointer' }} onClick={() => openDeal(d)}
                    onMouseMove={e => show(e, t)} onMouseLeave={() => setTip(null)}>
                    {plan ? <PlanCell c={c} pend={pend} /> : <Light c={c} />}
                  </div>
                )
              })}
            </div>
          )
        })}

        <div style={{ ...row, position: 'sticky', bottom: 0, zIndex: 3, background: 'var(--bg-subtle)', borderTop: '1px solid var(--border-card)' }}>
          <div style={{ ...stick(0, 4, 'var(--bg-subtle)'), padding: '8px 12px', fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', borderRight: LINE }}>
            {plan ? 'Итого по РК' : 'Согласовано'}
          </div>
          <div style={{ ...stick(PUB_W, 4, 'var(--bg-subtle)'), ...totCell, borderRight: '1px solid var(--border-card)' }}>
            {plan ? <Tot plan t={all} /> : ''}
          </div>
          {colTot.map((t, i) => <div key={deals[i].id} style={{ ...totCell, borderRight: LINE }}><Tot plan={plan} t={t} /></div>)}
        </div>
      </div>

      {tip && (
        <div style={{ position: 'fixed', left: tip.x, top: tip.y, zIndex: 9, pointerEvents: 'none', maxWidth: 300,
          background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-card)',
          boxShadow: '0 10px 30px rgba(28,36,51,.16)', padding: '10px 12px', borderRadius: 12, fontSize: 12, lineHeight: 1.55 }}>
          <b>{tip.head}</b>
          {tip.lines.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      )}
    </>
  )
}
