/**
 * Экран «Площадки × РК» — /traffic/platforms (frontend/pages/traffic/platforms.js).
 * Задача — помочь трафику найти проблемные площадки: сверху два готовых ответа (недокрут, Weborama),
 * ниже список с «полоской по РК» или матрица, справа карточка выбранной площадки.
 *
 * Пропы:
 *   data            — ответ GET /api/traffic-dashboard/platforms (см. sampleData.js)
 *   traffic         — выбранный фильтр трафика ('mine' | 'all' | 'unassigned' | id)
 *   trafficOptions  — [{ value, label }]
 *   onTraffic(v)    — смена фильтра (перезапрос)
 *   onExcel()       — GET /api/traffic-dashboard/platforms.xlsx с тем же фильтром
 *   onBack()        — «← Дашборд»
 *   onOpenRk(code)  — раскрыть РК на дашборде
 *
 * Вердикты, счётчики и медианы — с сервера. Фронт только сортирует и рисует.
 * Примитивы (кнопки, выпадашка трафика) — заменить на salesTableKit / ValuePopover.
 */
import React, { useMemo, useState } from 'react';
import { MONO, VERDICT, isProblem, C, TINT, FG, nf, pct, sgn, minus, plural, valueOf, toneOf, toneTempo, toneWr,
  stripOf, Strip, VerdictPill, Legend, Segmented, Cap, Dot, PlatformRks, platformSay, sayTone } from './reportKit';

import { card } from '@/components/salesTableKit';   // та же карточка, что в ките
const btn = { display: 'inline-flex', alignItems: 'center', height: 32, boxSizing: 'border-box', padding: '0 13px', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 12, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', cursor: 'pointer' };
const EASE = 'cubic-bezier(0.22,1,0.36,1)';
const rise = d => ({ animation: `prRise 0.4s ${EASE} ${d}s both` });
const LIST_COLS = '170px 190px minmax(300px,1fr) 80px 130px 90px 90px';

const FILTERS = [['problems', 'с проблемами', null], ['fail', 'системный провал', 'var(--danger)'], ['sysund', 'системный недокрут', 'var(--warning)'],
  ['spot', 'точечный недокрут', 'var(--warning)'], ['ok', 'в норме', 'var(--income)'], ['nodata', 'нет данных', 'var(--text-faint)'], ['wr', 'WR системно', 'var(--danger)'], ['all', 'все площадки', null]];

export default function PlatformsReport({ data, traffic, trafficOptions = [], onTraffic, onExcel, onBack, onOpenRk, initialCode = null }) {
  const [filter, setFilter] = useState('problems');
  const [metric, setMetric] = useState('tempo');
  const [kind, setKind] = useState('all');
  const [view, setView] = useState('list');
  const [selCode, setSelCode] = useState(initialCode);   // ?p=<код> — площадка из виджета (BUILD.md)

  const rkByCode = useMemo(() => Object.fromEntries(data.rks.map(r => [r.code, r])), [data.rks]);
  const plats = useMemo(() => data.platforms.slice().sort((a, b) => VERDICT[b.verdict].w - VERDICT[a.verdict].w || b.stats.under_total - a.stats.under_total), [data.platforms]);

  const counts = useMemo(() => {
    const c = { problems: plats.filter(isProblem).length, wr: plats.filter(p => p.wr_systemic).length, all: plats.length };
    Object.keys(VERDICT).forEach(k => { c[k] = plats.filter(p => p.verdict === k).length; });
    return c;
  }, [plats]);
  const eff = filter === 'problems' && !counts.problems ? 'all' : filter;   // проблем нет — сразу все
  const inKind = p => kind === 'all' || (kind === 'dsp' ? p.kind === 'DSP' : kind === 'out' ? p.kind === 'вне DSP' : p.kind === 'частично');
  const list = plats.filter(inKind).filter(p => (eff === 'all' ? true : eff === 'problems' ? isProblem(p) : eff === 'wr' ? p.wr_systemic : p.verdict === eff));
  const sel = plats.find(p => p.code === selCode) || list[0] || plats[0];
  const maxUnder = Math.max(1, ...plats.map(p => p.stats.under_total));

  /* пустые состояния */
  if (!data.rks.length) return <Shell {...{ data, traffic, trafficOptions, onTraffic, onExcel, onBack }}><Empty text="В этом фильтре трафика нет идущих РК." /></Shell>;

  /* два ответа */
  const totalUnder = plats.reduce((a, p) => a + p.stats.under_total, 0);
  const topU = plats.filter(p => p.stats.under_total).sort((a, b) => b.stats.under_total - a.stats.under_total).slice(0, 5);
  const topW = plats.filter(p => p.stats.wr_measured >= 2).sort((a, b) => b.stats.wr_over / b.stats.wr_measured - a.stats.wr_over / a.stats.wr_measured || Math.abs(b.stats.wr_median) - Math.abs(a.stats.wr_median)).slice(0, 5);
  const top5share = totalUnder ? Math.round(topU.reduce((a, p) => a + p.stats.under_total, 0) / totalUnder * 100) : 0;

  return (
    <Shell {...{ data, traffic, trafficOptions, onTraffic, onExcel, onBack }} sub={`идущие РК · ${data.rks.length} РК · ${plats.length} площадок · срез ${data.slice_date}`}>
      {data.no_fact && (
        <div style={{ padding: '10px 14px', borderRadius: 12, background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', fontSize: 12.5, color: 'var(--warning-fg)', fontWeight: 600 }}>
          Факта по идущим РК ещё нет: последний срез {data.slice_date} раньше старта РК. Темп, сутки и WR появятся с суточным срезом.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 14, ...rise(0.07) }}>
        <Answer dot="var(--warning)" title="Недокрут: где теряем показы" sub="по прогнозу к концу идущих РК" big={totalUnder ? `−${nf(totalUnder)}` : '0'} bigNote="показов"
          rows={topU.map(p => ({ p, cells: stripOf(p, 'tempo', rkByCode), value: `−${nf(p.stats.under_total)}`, fg: 'var(--text-primary)', note: `${Math.round(p.stats.under_total / totalUnder * 100)} % недокрута · ${p.stats.under_n} из ${p.stats.rated} РК` }))}
          sel={sel} onPick={setSelCode} metric="tempo"
          foot={topU.length ? `${plural(topU.length, 'площадка даёт', 'площадки дают', 'площадок дают')} ${top5share} % всего недокрута — их учитывать в весах со старта следующих запусков.` : 'Недокрута нет.'}
          actLabel="только недокрут" onAct={() => { setFilter('problems'); setMetric('tempo'); }} />
        <Answer dot="var(--danger)" title="Weborama: кто расходится раз за разом" sub="порог — из целей сделки" big={String(counts.wr)} bigFg={counts.wr ? 'var(--danger-fg)' : 'var(--income-fg)'}
          bigNote={counts.wr ? `${plural(counts.wr, 'площадка', 'площадки', 'площадок').split(' ')[1]} системно` : 'системных нет'}
          rows={topW.map(p => ({ p, cells: stripOf(p, 'wr', rkByCode), value: sgn(p.stats.wr_median), fg: p.wr_systemic ? 'var(--danger-fg)' : 'var(--text-secondary)', note: `за порогом ${p.stats.wr_over} из ${p.stats.wr_measured} РК` }))}
          sel={sel} onPick={setSelCode} metric="wr"
          foot="Системное расхождение — повод сверить код Weborama на площадке, а не разбирать каждую РК отдельно."
          actLabel="показать по WR" onAct={() => { setFilter('wr'); setMetric('wr'); }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 520px', gap: 14, alignItems: 'start', ...rise(0.14) }}>
        <div style={{ ...card, padding: '14px 18px 12px', display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {FILTERS.map(([k, label, dot]) => { const on = eff === k, zero = !counts[k]; return (
              <span key={k} role="button" tabIndex={0} onClick={() => setFilter(k)} onKeyDown={e => e.key === 'Enter' && setFilter(k)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, boxSizing: 'border-box', padding: '0 11px', borderRadius: 12, fontSize: 12, fontWeight: on ? 700 : 600, cursor: 'pointer', whiteSpace: 'nowrap',
                  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`, color: on ? 'var(--accent-fg)' : zero ? 'var(--text-faint)' : 'var(--text-secondary)' }}>
                {dot && <Dot color={dot} />}{label}<span style={{ fontFamily: MONO, fontSize: 11, color: on ? 'var(--accent-fg)' : zero ? 'var(--text-disabled)' : 'var(--text-muted)' }}>{counts[k]}</span>
              </span>); })}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', paddingBottom: 6, borderBottom: '1px solid var(--border-inner)' }}>
            <Segmented label="мера" value={metric} onChange={setMetric} options={[['tempo', 'темп'], ['day', 'сутки'], ['wr', 'WR']]} />
            <Segmented label="код" value={kind} onChange={setKind} options={[['all', 'все'], ['dsp', 'DSP'], ['out', 'вне DSP'], ['part', 'частично']]} />
            <Segmented label="вид" value={view} onChange={setView} options={[['list', 'список'], ['matrix', 'матрица']]} />
            <span style={{ marginLeft: 'auto' }}><Legend metric={metric} /></span>
          </div>
          {list.length === 0 ? <Empty text="Под фильтр площадок нет." inline /> : view === 'list'
            ? <ListView list={list} metric={metric} rkByCode={rkByCode} sel={sel} onPick={setSelCode} maxUnder={maxUnder} />
            : <MatrixView list={list} metric={metric} rks={data.rks} rkByCode={rkByCode} sel={sel} onPick={setSelCode} onOpenRk={onOpenRk} />}
        </div>
        <PlatformCard p={sel} rkByCode={rkByCode} onOpenRk={onOpenRk} />
      </div>
    </Shell>
  );
}

function Shell({ children, sub, traffic, trafficOptions, onTraffic, onExcel, onBack }) {
  return (
    <div style={{ minHeight: '100vh', boxSizing: 'border-box', padding: '22px 30px 40px', display: 'flex', justifyContent: 'center', background: 'var(--bg-canvas)', fontFamily: "'Manrope', sans-serif", color: 'var(--text-primary)' }}>
      <style>{`@keyframes prRise { from { opacity: 0; transform: translateY(12px) } to { opacity: 1; transform: none } }
        .pr-row:hover { background: var(--bg-subtle) }
        @media (prefers-reduced-motion: reduce) { .pr-root * { animation-duration: 1ms !important; animation-delay: 0s !important } }`}</style>
      <div className="pr-root" style={{ width: '100%', maxWidth: 1860, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, ...rise(0) }}>
          <span style={btn} onClick={onBack}>← Дашборд</span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em' }}>Площадки × РК</span>
            {sub && <span style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{sub}</span>}
          </span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            {/* на проде — ValuePopover */}
            <select value={traffic} onChange={e => onTraffic?.(e.target.value)} style={{ ...btn, minWidth: 170, fontFamily: 'inherit' }}>
              {trafficOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <span style={{ ...btn, background: 'var(--accent)', borderColor: 'var(--accent)', color: 'var(--on-accent)', fontWeight: 700 }} onClick={onExcel}>Скачать Excel</span>
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}

const Empty = ({ text, inline }) => (
  <div style={{ ...(inline ? {} : card), padding: '26px 20px', fontSize: 13, color: 'var(--text-muted)' }}>{text}</div>
);

function Answer({ dot, title, sub, big, bigFg = 'var(--text-primary)', bigNote, rows, sel, onPick, metric, foot, actLabel, onAct }) {
  return (
    <div style={{ ...card, padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ alignSelf: 'center' }}><Dot color={dot} size={8} /></span>
        <span style={{ fontSize: 15, fontWeight: 700 }}>{title}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: bigFg }}>{big}</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{bigNote}</span>
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {rows.length === 0 && <span style={{ padding: '8px', fontSize: 12.5, color: 'var(--text-muted)' }}>Нет площадок под этот вопрос.</span>}
        {rows.map(r => (
          <div key={r.p.code} className="pr-row" onClick={() => onPick(r.p.code)} style={{ display: 'grid', gridTemplateColumns: '150px minmax(0,1fr) 120px 150px', gap: '0 14px', alignItems: 'center', padding: '7px 8px', borderRadius: 10, cursor: 'pointer', background: r.p === sel ? 'var(--bg-tint)' : 'transparent' }}>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.p.name}</span>
            <Strip cells={r.cells} metric={metric} size={12} height={12} max={34} showSplit={false} />
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right', color: r.fg }}>{r.value}</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)', textAlign: 'right', whiteSpace: 'nowrap' }}>{r.note}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.4 }}>{foot}</span>
        <span style={{ ...btn, marginLeft: 'auto', height: 28, fontSize: 12 }} onClick={onAct}>{actLabel}</span>
      </div>
    </div>
  );
}

function ListView({ list, metric, rkByCode, sel, onPick, maxUnder }) {
  const medLabel = metric === 'wr' ? 'медиана WR' : metric === 'day' ? 'медиана суток' : 'медиана темпа';
  return (
    <div style={{ overflowX: 'auto' }}><div style={{ minWidth: 1040, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'grid', gridTemplateColumns: LIST_COLS, gap: '0 14px', padding: '0 8px 6px', borderBottom: '1px solid var(--border-inner)' }}>
        <Cap>площадка</Cap><Cap>вердикт</Cap><Cap>картина по РК · один квадрат = одна РК</Cap>
        <Cap style={{ textAlign: 'right' }}>{medLabel}</Cap><Cap style={{ textAlign: 'right' }}>недокрут, показы</Cap><Cap style={{ textAlign: 'right' }}>WR за порогом</Cap><Cap style={{ textAlign: 'right' }}>ниже плана дня</Cap>
      </div>
      {list.map(p => {
        const s = p.stats, cells = stripOf(p, metric, rkByCode);
        const medV = metric === 'wr' ? s.wr_median : metric === 'day' ? s.median_day : s.median_tempo;
        const medT = metric === 'wr' ? toneWr(medV, 10) : toneTempo(medV);
        return (
          <div key={p.code} className="pr-row" onClick={() => onPick(p.code)} style={{ display: 'grid', gridTemplateColumns: LIST_COLS, gap: '0 14px', alignItems: 'center', padding: 8, borderBottom: '1px solid var(--border-row)', borderRadius: 8, cursor: 'pointer', background: p === sel ? 'var(--bg-tint)' : 'transparent' }}>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
              <span title={p.name} style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
              <span style={{ fontFamily: MONO, fontSize: 9.5, color: p.kind === 'DSP' ? 'var(--text-muted)' : 'var(--warning-fg)' }}>{p.code} · {p.kind} · {p.pairs.length} РК</span>
            </span>
            <VerdictPill verdict={p.verdict} wr={p.wr_systemic} />
            <Strip cells={cells} metric={metric} />
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right', color: FG[medT] }}>{metric === 'wr' ? sgn(medV) : pct(medV)}</span>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end' }}>
              <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: s.under_total ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{minus(s.under_total)}</span>
              <span style={{ width: '100%', height: 4, borderRadius: 2, background: 'var(--border-inner)', display: 'flex', justifyContent: 'flex-end' }}><span style={{ width: `${Math.round(s.under_total / maxUnder * 100)}%`, height: 4, borderRadius: 2, background: 'var(--warning)' }} /></span>
            </span>
            <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right', color: p.wr_systemic ? 'var(--danger-fg)' : 'var(--text-secondary)' }}>{s.wr_measured ? `${s.wr_over} / ${s.wr_measured}` : '—'}</span>
            <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right', color: 'var(--text-secondary)' }}>{s.day_with_plan ? `${s.day_below} / ${s.day_with_plan}` : '—'}</span>
          </div>
        );
      })}
    </div></div>
  );
}

/** Матрица: колонка площадок — отдельный неподвижный блок, клетки прокручиваются (без sticky — ничего не просвечивает). */
function MatrixView({ list, metric, rks, rkByCode, sel, onPick, onOpenRk }) {
  const num = (v, m) => (v == null ? '·' : m === 'wr' ? `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)}` : String(Math.round(v * 100)));
  const note = metric === 'wr' ? 'Число — расхождение нашего счёта с Weborama, %.' : metric === 'day' ? 'Число — факт за сутки к плану дня, %.' : 'Число — темп: прогноз к плану, %.';
  const colBad = Object.fromEntries(rks.map(rk => [rk.code, list.some(p => p.pairs.some(x => x.rk === rk.code && toneOf(x, metric, rk) === 'bad'))]));
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'flex-start', borderBottom: '1px solid var(--border-row)' }}>
        <div style={{ flex: '0 0 200px', display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', boxShadow: '6px 0 8px -8px rgba(28,36,51,.25)', position: 'relative', zIndex: 1 }}>
          <span style={{ height: 58, boxSizing: 'border-box', display: 'flex', alignItems: 'flex-end', paddingBottom: 6, borderBottom: '1px solid var(--border-inner)' }}><Cap>площадка</Cap></span>
          {list.map(p => (
            <span key={p.code} className="pr-row" title={p.name} onClick={() => onPick(p.code)} style={{ height: 28, boxSizing: 'border-box', display: 'flex', alignItems: 'center', padding: '0 10px 0 4px', fontFamily: MONO, fontSize: 12, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', background: p === sel ? 'var(--bg-tint)' : 'var(--bg-card)' }}>{p.name}</span>
          ))}
        </div>
        <div style={{ flex: '1 1 auto', minWidth: 0, overflowX: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 'max-content' }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', height: 58, boxSizing: 'border-box', paddingBottom: 6, borderBottom: '1px solid var(--border-inner)' }}>
              {rks.map(rk => (
                <a key={rk.code} href={`/traffic/dashboard?open=${encodeURIComponent(rk.code)}`} onClick={e => { if (onOpenRk) { e.preventDefault(); onOpenRk(rk.code); } }} title={`${rk.code} · ${rk.title} · ${rk.start} – ${rk.end} · трафик ${rk.traffic}`}
                  style={{ flex: '0 0 40px', display: 'flex', justifyContent: 'center', alignItems: 'center', height: 52, writingMode: 'vertical-rl', transform: 'rotate(180deg)', fontFamily: MONO, fontSize: 9.5, fontWeight: 700, color: colBad[rk.code] ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{rk.code}</a>
              ))}
            </div>
            {list.map(p => {
              const byRk = Object.fromEntries(p.pairs.map(x => [x.rk, x]));
              return (
                <div key={p.code} onClick={() => onPick(p.code)} style={{ display: 'flex', alignItems: 'center', height: 28, cursor: 'pointer', background: p === sel ? 'var(--bg-tint)' : 'var(--bg-card)' }}>
                  {rks.map(rk => { const x = byRk[rk.code];
                    if (!x) return <span key={rk.code} title={`${rk.code} — площадки нет в РК`} style={{ flex: '0 0 40px' }} />;
                    const t = toneOf(x, metric, rk), v = valueOf(x, metric);
                    return (
                      <span key={rk.code} title={`${p.name} × ${rk.code} · ${rk.title}\nплан ${nf(x.plan)} · факт ${nf(x.fact)} · прогноз ${nf(x.forecast)}\nнужно в день ${nf(x.need_per_day)} · Weborama ${x.weborama == null ? '—' : nf(x.weborama)} · ${x.dsp ? 'DSP' : 'вне DSP'}`}
                        style={{ flex: '0 0 40px', display: 'flex', justifyContent: 'center' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 22, borderRadius: 6, fontFamily: MONO, fontSize: 10.5, fontWeight: 700,
                          background: t === 'none' ? 'transparent' : TINT[t], color: t === 'none' ? 'var(--text-faint)' : FG[t] }}>{num(v, metric)}</span>
                      </span>); })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{note} Пустая клетка — площадки нет в этой РК; «·» — данных ещё нет. Подробности — в подсказке клетки.</span>
    </>
  );
}

function PlatformCard({ p, rkByCode, onOpenRk }) {
  if (!p) return null;
  const s = p.stats, tone = sayTone(p);
  const box = { bad: ['var(--danger-tint)', 'var(--danger-border)'], warn: ['var(--warning-tint)', 'var(--warning-border)'], ok: ['var(--income-tint)', 'var(--income-border)'], none: ['var(--bg-subtle)', 'var(--border-inner)'] }[tone];
  const kpi = [['недокрут в РК', `${s.under_n} / ${s.rated}`, s.under_n ? 'var(--warning-fg)' : 'var(--text-primary)'], ['медиана темпа', pct(s.median_tempo), FG[toneTempo(s.median_tempo)]],
    ['недокрут, показы', minus(s.under_total), 'var(--text-primary)'], ['WR за порогом', s.wr_measured ? `${s.wr_over} / ${s.wr_measured}` : '—', p.wr_systemic ? 'var(--danger-fg)' : 'var(--text-primary)']];
  return (
    <div style={{ ...card, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12, position: 'sticky', top: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>{p.name}</span>
          <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{p.code} · {p.kind} · {p.pairs.length} РК</span>
        </span>
        <span style={{ marginLeft: 'auto' }}><VerdictPill verdict={p.verdict} wr={p.wr_systemic} /></span>
      </div>
      <div style={{ padding: '10px 12px', borderRadius: 12, background: box[0], border: `1px solid ${box[1]}`, fontSize: 12.5, lineHeight: 1.5 }}>{platformSay(p)}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 10, paddingBottom: 10, borderBottom: '1px solid var(--border-inner)' }}>
        {kpi.map(([l, v, fg]) => <span key={l} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><Cap>{l}</Cap><span style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: fg }}>{v}</span></span>)}
      </div>
      <div style={{ maxHeight: 470, overflow: 'auto' }}><PlatformRks platform={p} rkByCode={rkByCode} onOpenRk={onOpenRk} /></div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={btn} onClick={() => onOpenRk?.(p.pairs.slice().sort((a, b) => b.under - a.under)[0]?.rk)}>Открыть РК на дашборде</span>
        <span style={{ ...btn, color: 'var(--text-faint)', borderStyle: 'dashed', cursor: 'default' }} title="Меняет данные — отдельным решением">Предложить веса · следующим шагом</span>
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.4 }}>Отметка на шкале — 90 %: правее — норма, 60–90 % — недокрут, левее 60 % — провал. Сортировка — по недокруту в показах.</span>
    </div>
  );
}
