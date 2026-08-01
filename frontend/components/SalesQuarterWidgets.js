import { grp, mln as mlnBase } from '../lib/salesFormat'

// Верхний блок дашборда сейлза «Мой квартал» — редизайн по хендоффу
// (design_handoff_sales_widgets). Один контейнер: шапка → 4 KPI с вертикальными
// разделителями → полоса «Сделки в работе» со слоями денег, легендой и сверкой.
// Тёплая нейтральная палитра + Manrope/JetBrains Mono (шрифты грузятся в <Head> страницы).

// Холодная палитра проекта — через CSS-переменные (globals.css), чтобы блок
// не выбивался из общей стилистики. Семантика (акцент/успех/предупреждение/ошибка)
// и слои денег берутся из тех же токенов, что весь дашборд.
const C = {
  text: 'var(--text-primary)', sec: 'var(--text-muted)', accent: 'var(--accent)', accentHover: 'var(--accent-hover)',
  border: 'var(--border-card)', ctrl: 'var(--border-card)', ctrlBg: 'var(--bg-card)', blockBg: 'var(--bg-card)',
  warnBg: 'var(--warning-tint)', warnText: '#8A5A12', ok: 'var(--success)', okText: 'var(--success)',
  errDot: 'var(--danger)', errText: 'var(--danger)', plan: '#CBD2E0',
  hatch: 'repeating-linear-gradient(135deg,#AFB7CA 0 3px,var(--bg-card) 3px 6px)',
}
const MONO = "'JetBrains Mono', ui-monospace, monospace"
const UI = "'Manrope', system-ui, sans-serif"

// виджеты показывают млн с 2 знаками; grp — общий
const mln = (n) => mlnBase(n, 2)

const lbl = { fontFamily: MONO, fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: C.sec }
const val = { fontFamily: MONO, fontSize: 42, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: C.text, whiteSpace: 'nowrap' }
const unit = { fontSize: 17, fontWeight: 600, color: C.sec }
const capt = { fontSize: 12, color: C.sec }
const strong = { color: C.text, fontWeight: 700, fontFamily: MONO }

// Слои денег: порядок и цвета из хендоффа. Имена — как отдаёт backend by_layer.
// Единая семантика слоёв денег (как в таблице/индикаторе): факт — зелёный,
// реализуемые — оранжевый, планируемые — серый, без группы — штриховка.
const LAYERS = [
  { name: 'фактические', display: 'фактические', bg: 'var(--income)' },
  { name: 'реализуемые', display: 'реализуемые', bg: 'var(--dot-current-dz)' },
  { name: 'планируемые', display: 'планируемые', bg: 'var(--text-faint)' },
  { name: 'Без группы', display: 'без группы', bg: C.hatch },
]

export default function SalesQuarterWidgets({
  data, summary, lastSyncAt,
  quarter, setQuarter, quarters,
  repId, setRepId, reps, canViewOthers,
  onCreate, onCreateAgency, onCreateAdvertiser,
}) {
  const p = data?.params || {}
  const closedPct = data?.closed?.amount ? Math.round((data.closed.our_sum / data.closed.amount) * 100) : null

  const totals = summary?.totals
  const byLayer = summary?.by_layer || []
  const layerAmt = (name) => (byLayer.find(b => b.name === name)?.amount) || 0
  const layerDeals = (name) => (byLayer.find(b => b.name === name)?.deals) || 0
  const portfolioAmt = totals?.amount || 0
  const width = (name) => (portfolioAmt > 0 ? (layerAmt(name) / portfolioAmt) * 100 : 0)

  const syncTime = lastSyncAt ? new Date(lastSyncAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : null
  const recon = totals ? totals.reconciles : true

  const selBox = {
    border: `1px solid ${C.ctrl}`, background: C.ctrlBg, borderRadius: 10, padding: '8px 12px',
    fontFamily: UI, fontSize: 13, fontWeight: 600, color: C.text, cursor: 'pointer',
    appearance: 'auto',
  }

  return (
    <div style={{ fontFamily: UI }}>
      <style>{`
        .qw-kpi { display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid ${C.border}; border-bottom:1px solid ${C.border}; }
        .qw-cell { display:flex; flex-direction:column; gap:16px; }
        .qw-portfolio { display:flex; align-items:center; gap:36px; }
        @media (max-width:1200px){
          .qw-kpi { grid-template-columns:repeat(2,1fr); }
          .qw-cell { padding:22px !important; }
          .qw-portfolio { flex-direction:column; align-items:stretch; gap:16px; }
        }
        .qw-btn { transition:background-color 120ms ease, border-color 120ms ease; }
        .qw-btn:hover { background:${C.accentHover} !important; }
        .qw-sel:hover { border-color:var(--text-faint) !important; }
      `}</style>

      <div style={{ background: C.blockBg, border: `1px solid ${C.border}`, borderRadius: 28,
        padding: '34px 36px 30px', display: 'flex', flexDirection: 'column', gap: 26 }}>

        {/* ── Шапка ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
            <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', color: C.text }}>Мой квартал</span>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.sec }}>
              {(data?.rep || '—') + ' / ' + (data?.quarter || '')}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {syncTime && <div style={{ fontFamily: MONO, fontSize: 12, color: C.sec, marginRight: 8 }}>обновлено {syncTime}</div>}
            {canViewOthers && (
              <select className="qw-sel" value={repId} onChange={e => setRepId(e.target.value)} style={selBox}>
                <option value="">— я / сотрудник —</option>
                {(reps || []).map(r => <option key={r.id} value={r.id}>{r.is_head ? '★ ' : ''}{r.name}{r.is_head ? ' · мастер-сейлз' : ''}{r.linked ? '' : ' (без юзера)'}</option>)}
              </select>
            )}
            <select className="qw-sel" value={quarter} onChange={e => setQuarter(e.target.value)} style={selBox}>
              <option value="">Текущий квартал</option>
              {(quarters || []).map(q => <option key={q} value={q}>{q.replace('-', ' ')}</option>)}
              <option value="all">Показать все</option>
            </select>
            {onCreateAgency && (
              <button className="qw-btn" onClick={onCreateAgency}
                style={{ background: 'var(--bg-card)', color: C.accent, border: `1px solid ${C.accent}`, borderRadius: 10, padding: '10px 16px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>+ Агентство</button>
            )}
            {onCreateAdvertiser && (
              <button className="qw-btn" onClick={onCreateAdvertiser}
                style={{ background: 'var(--bg-card)', color: C.accent, border: `1px solid ${C.accent}`, borderRadius: 10, padding: '10px 16px', fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>+ Рекламодатель</button>
            )}
            {onCreate && (
              <button className="qw-btn" onClick={onCreate}
                style={{ background: C.accent, color: '#fff', border: 'none', borderRadius: 10, padding: '10px 16px',
                  fontFamily: MONO, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>+ Сделка</button>
            )}
          </div>
        </div>

        {/* ── Сетка KPI ── */}
        <div className="qw-kpi">
          {/* 1. Бонус за квартал */}
          <div className="qw-cell" style={{ padding: '26px 26px 26px 0', borderRight: `1px solid ${C.border}` }}>
            <div style={lbl}>Бонус за квартал</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
              <span style={val}>{grp(data?.forming_bonus)}</span>
              <span style={unit}>₽</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              {data?.booking?.bonus > 0 && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: C.warnBg,
                  color: C.warnText, borderRadius: 6, padding: '4px 8px', fontSize: 12, fontWeight: 700 }}>
                  +{grp(data.booking.bonus)} на бронях
                </span>
              )}
              <span style={capt}>{Math.round((p.bonus_rate || 0) * 100)}% после −{Math.round((p.agency_sk || 0) * 100)}% СК</span>
            </div>
          </div>

          {/* 2. Доведено до результата */}
          <div className="qw-cell" style={{ padding: 26, borderRight: `1px solid ${C.border}` }}>
            <div style={lbl}>Доведено до результата</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
              <span style={val}>{mln(data?.closed?.amount)}</span>
              <span style={unit}>млн ₽</span>
            </div>
            <div style={capt}>наша сумма <span style={strong}>{grp(data?.closed?.our_sum)} ₽</span>{closedPct != null ? ` · ${closedPct}%` : ''}</div>
          </div>

          {/* 3. Брони */}
          <div className="qw-cell" style={{ padding: 26, borderRight: `1px solid ${C.border}` }}>
            <div style={lbl}>Брони</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
              <span style={val}>{mln(data?.booking?.amount)}</span>
              <span style={unit}>млн ₽</span>
            </div>
            <div style={capt}>наша <span style={strong}>{grp(data?.booking?.our_sum)} ₽</span> · бонус <span style={strong}>{grp(data?.booking?.bonus)}</span></div>
          </div>

          {/* 4. Активная песочница */}
          <div className="qw-cell" style={{ padding: '26px 0 26px 26px' }}>
            <div style={lbl}>Активная песочница</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={val}>{data?.sandbox?.count ?? '—'}</span>
              <span style={{ ...unit, fontSize: 16 }}>МП</span>
            </div>
            <div style={capt}>сумма <span style={strong}>{mln(data?.sandbox?.amount)} млн ₽</span> · 1-я воронка</div>
          </div>
        </div>

        {/* ── Полоса «Сделки в работе» ── */}
        <div className="qw-portfolio">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 190 }}>
            <div style={lbl}>Сделки в работе</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
              <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: C.text }}>{mln(portfolioAmt)}</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: C.sec }}>млн ₽ / {totals?.deals ?? 0} шт</span>
            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 2, height: 10 }}>
              {LAYERS.map(L => {
                const w = width(L.name)
                if (w <= 0) return null
                return <div key={L.name} title={`${L.display}: ${mln(layerAmt(L.name))} млн · ${layerDeals(L.name)}`}
                  style={{ width: `${w}%`, background: L.bg }} />
              })}
            </div>
            <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', fontSize: 12, color: C.sec }}>
              {LAYERS.map(L => (
                <span key={L.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ width: 8, height: 8, background: L.bg }} />
                  {L.display} <span style={strong}>{mln(layerAmt(L.name))} млн · {layerDeals(L.name)}</span>
                </span>
              ))}
            </div>
          </div>

          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap',
            color: recon ? C.okText : C.errText }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: recon ? C.ok : C.errDot }} />
            {recon ? 'сверка сходится' : 'сверка расходится'}
          </div>
        </div>
      </div>
    </div>
  )
}
