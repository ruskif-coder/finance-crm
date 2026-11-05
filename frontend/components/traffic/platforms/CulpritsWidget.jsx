/**
 * Виджет «Площадки-виновники» на дашборде (frontend/components/traffic/dashboardKit.js → Culprits, PlatformRks).
 * Тот же язык, что экран «Площадки × РК»: вердикт, метка WR, полоска по РК, недокрут в показах.
 * Колонка «статус площадки» убрана — у всех одинаковая («запущен») и ничего не различает.
 *
 * Пропы:
 *   data            — тот же ответ GET /api/traffic-dashboard/platforms (фильтр трафика дашборда)
 *   onOpenReport()  — «Сводный отчёт →» → /traffic/platforms с тем же фильтром
 *   onOpenRk(code)  — раскрыть РК на дашборде
 *   limit           — сколько РК показать в раскрытии (по умолчанию 6)
 *   onExcel()       — пиктограмма «скачать» после «Сводного отчёта»: та же экселька (владелец 05.11.2026); промис — крутилка, пока готовится
 */
import React, { useMemo, useState } from 'react';
import { Cube } from '@/components/LogoLoader';
import { MONO, VERDICT, nf, minus, stripOf, Strip, VerdictPill, Legend, Segmented, Cap, PlatformRks, platformSay } from './reportKit';

const COLS = '12px 170px 200px minmax(220px,1fr) 130px 96px';

/* Сортировка по заголовкам (владелец 05.11.2026). Ключ → значение строки; больше — «хуже», поэтому по умолчанию по убыванию.
   «Картина по РК» — доля проблемных РК по выбранной мере (провал = 1, недокрут/близко = ½), без РК без данных. */
const SORTS = {
  name: { label: 'площадка', get: p => p.name, text: true },
  verdict: { label: 'вердикт', get: p => VERDICT[p.verdict].w * 2 + (p.wr_systemic ? 1 : 0) },
  strip: { label: 'картина по РК', get: (p, metric, rkByCode) => {
    const c = stripOf(p, metric, rkByCode).filter(x => x.t !== 'none');
    return c.length ? c.reduce((a, x) => a + (x.t === 'bad' ? 1 : x.t === 'warn' ? 0.5 : 0), 0) / c.length : -1;
  } },
  under: { label: 'недокрут, показы', get: p => p.stats.under_total, right: true },
  wr: { label: 'WR за порогом', get: p => (p.stats.wr_measured ? p.stats.wr_over / p.stats.wr_measured + p.stats.wr_over / 1000 : -1), right: true },
};

function SortCap({ k, sort, onSort }) {
  const on = sort.key === k, d = SORTS[k];
  return (
    <span role="button" tabIndex={0} onClick={() => onSort(k)} onKeyDown={e => e.key === 'Enter' && onSort(k)}
      title={`Сортировать: ${d.label}`} style={{ cursor: 'pointer', userSelect: 'none', textAlign: d.right ? 'right' : 'left', whiteSpace: 'nowrap' }}>
      <Cap style={{ color: on ? 'var(--accent-fg)' : undefined }}>{d.label}</Cap>
      <span style={{ fontSize: 9, marginLeft: 4, color: on ? 'var(--accent-fg)' : 'var(--text-disabled)' }}>{on ? (sort.dir < 0 ? '▼' : '▲') : '↕'}</span>
    </span>
  );
}

export default function CulpritsWidget({ data, onOpenReport, onOpenRk, onExcel, limit = 6 }) {
  const [metric, setMetric] = useState('tempo');
  const [busy, setBusy] = useState(false);
  const excel = async () => { if (busy || !onExcel) return; setBusy(true); try { await onExcel(); } finally { setBusy(false); } };
  const [open, setOpen] = useState(null);
  const rkByCode = useMemo(() => Object.fromEntries(data.rks.map(r => [r.code, r])), [data.rks]);
  const [sort, setSort] = useState({ key: 'under', dir: -1 });
  const onSort = k => setSort(s => (s.key === k ? { key: k, dir: -s.dir } : { key: k, dir: SORTS[k].text ? 1 : -1 }));
  const list = useMemo(() => {
    const get = SORTS[sort.key].get;
    const val = p => get(p, metric, rkByCode);
    return data.platforms.filter(p => p.stats.under_total > 0 || p.wr_systemic).sort((a, b) => {
      const x = val(a), y = val(b);
      const c = typeof x === 'string' ? x.localeCompare(y, 'ru') : x - y;
      return c * sort.dir || b.stats.under_total - a.stats.under_total;   // равные — по недокруту, как было
    });
  }, [data.platforms, sort, metric, rkByCode]);
  const maxUnder = Math.max(1, ...list.map(p => p.stats.under_total));
  const total = list.reduce((a, p) => a + p.stats.under_total, 0);
  const sys = data.platforms.filter(p => p.verdict === 'fail' || p.verdict === 'sysund').length;
  const wr = data.platforms.filter(p => p.wr_systemic).length;

  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, padding: '16px 20px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Cap style={{ fontSize: 10 }}>Площадки-виновники</Cap>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>поперёк всех видимых РК · недокрут в показах</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <Segmented value={metric} onChange={setMetric} options={[['tempo', 'темп'], ['wr', 'WR']]} />
          <span role="button" tabIndex={0} onClick={() => onOpenReport?.()} style={{ display: 'inline-flex', alignItems: 'center', height: 30, boxSizing: 'border-box', padding: '0 13px', border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer', whiteSpace: 'nowrap' }}>Сводный отчёт →</span>
          {onExcel && (
            <span role="button" tabIndex={0} onClick={excel} onKeyDown={e => e.key === 'Enter' && excel()} aria-label="Скачать Excel"
              title={busy ? 'Готовлю Excel…' : 'Скачать Excel — сводка и разбивка по площадкам'}
              style={{ display: 'inline-grid', placeItems: 'center', width: 30, height: 30, boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 12, color: 'var(--text-secondary)', cursor: busy ? 'progress' : 'pointer' }}>
              {busy ? <Cube variant="spinner" size={14} /> : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 4v11" /><path d="m7 10 5 5 5-5" /><path d="M5 20h14" />
                </svg>
              )}
            </span>
          )}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
        <span>{list.length} площадок с недокрутом или WR · всего −{nf(total)} показов · системно: {sys} · WR системно: {wr}</span>
        <span style={{ marginLeft: 'auto' }}><Legend metric={metric} /></span>
      </div>

      {list.length === 0 ? (
        <span style={{ padding: '16px 8px', fontSize: 12.5, color: 'var(--income-fg)', fontWeight: 600 }}>Площадок с недокрутом или расхождением с Weborama нет.</span>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '0 14px', padding: '6px 8px', borderBottom: '1px solid var(--border-inner)' }}>
            <span />{Object.keys(SORTS).map(k => <SortCap key={k} k={k} sort={sort} onSort={onSort} />)}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 352, overflow: 'auto' }}>
            {list.map(p => {
              const isOpen = open === p.code, s = p.stats;
              return (
                <div key={p.code} style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--border-row)' }}>
                  <div role="button" tabIndex={0} onClick={() => setOpen(isOpen ? null : p.code)} onKeyDown={e => e.key === 'Enter' && setOpen(isOpen ? null : p.code)}
                    style={{ display: 'grid', gridTemplateColumns: COLS, gap: '0 14px', alignItems: 'center', padding: 8, borderRadius: 8, cursor: 'pointer', background: isOpen ? 'var(--bg-tint)' : 'transparent' }}>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{isOpen ? '▾' : '▸'}</span>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                      <span title={p.name} style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: p.kind === 'DSP' ? 'var(--text-muted)' : 'var(--warning-fg)' }}>{p.code} · {p.kind} · {p.pairs.length} РК</span>
                    </span>
                    <VerdictPill verdict={p.verdict} wr={p.wr_systemic} />
                    <Strip cells={stripOf(p, metric, rkByCode)} metric={metric} size={8} height={12} />
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end' }}>
                      <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700 }}>{minus(s.under_total)}</span>
                      <span style={{ width: '100%', height: 4, borderRadius: 2, background: 'var(--border-inner)', display: 'flex', justifyContent: 'flex-end' }}><span style={{ width: `${Math.round(s.under_total / maxUnder * 100)}%`, height: 4, borderRadius: 2, background: 'var(--warning)' }} /></span>
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right', color: p.wr_systemic ? 'var(--danger-fg)' : 'var(--text-secondary)' }}>{s.wr_measured ? `${s.wr_over} / ${s.wr_measured}` : '—'}</span>
                  </div>
                  {isOpen && (
                    <div style={{ margin: '0 8px 10px 34px', padding: '8px 12px', background: 'var(--bg-subtle)', borderRadius: 12, display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45, padding: '2px 0 8px' }}>{platformSay(p)}</span>
                      <PlatformRks platform={p} rkByCode={rkByCode} limit={limit} onOpenRk={onOpenRk} />
                      <span style={{ paddingTop: 8, fontSize: 11.5 }}><a href={`/traffic/platforms?p=${encodeURIComponent(p.code)}`} onClick={e => { if (onOpenReport) { e.preventDefault(); onOpenReport(p.code); } }}>все {p.pairs.length} РК площадки в сводном отчёте →</a></span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
