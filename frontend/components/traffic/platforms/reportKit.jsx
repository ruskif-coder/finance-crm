/**
 * Общий кит отчёта «Площадки × РК» и виджета «Площадки-виновники».
 * Только отображение: вердикты, счётчики и медианы приходят с сервера (backend/app/traffic/platform_report.py).
 * Стили — inline на var(--*) из RULES_TIMON_design.md §2.
 */
import React from 'react';

export { MONO } from '@/components/salesTableKit';   // один шрифт с китом (вставка хендоффа 05.11.2026)
import { MONO } from '@/components/salesTableKit';

/** Тон клетки темпа и суток — пороги ТЗ: от 90 % норма, 60–90 % недокрут, ниже 60 % провал. */
export const toneTempo = v => (v == null ? 'none' : v >= 0.9 ? 'ok' : v >= 0.6 ? 'warn' : 'bad');
/** Тон расхождения с WR — порог из целей сделки (rk.wr_threshold, %). Половина порога — «близко». */
export const toneWr = (v, thr) => (v == null ? 'none' : Math.abs(v) >= thr ? 'bad' : Math.abs(v) >= thr / 2 ? 'warn' : 'ok');

export const C    = { ok: 'var(--income)',      warn: 'var(--warning)',      bad: 'var(--danger)',      none: 'var(--border-inner)' };
export const TINT = { ok: 'var(--income-tint)', warn: 'var(--warning-tint)', bad: 'var(--danger-tint)', none: 'var(--bg-subtle)' };
export const FG   = { ok: 'var(--income-fg)',   warn: 'var(--warning-fg)',   bad: 'var(--danger-fg)',   none: 'var(--text-disabled)' };

export const VERDICT = {
  fail:   { label: 'системный провал',  tone: 'bad',  w: 5 },
  sysund: { label: 'системный недокрут', tone: 'warn', w: 4 },
  spot:   { label: 'точечный недокрут', tone: 'warn', w: 3 },
  ok:     { label: 'в норме',            tone: 'ok',   w: 1 },
  nodata: { label: 'нет данных',         tone: 'none', w: 0 },
};
export const isProblem = p => ['fail', 'sysund', 'spot'].includes(p.verdict) || p.wr_systemic;

/* ── форматы ── */
export const nf = v => Math.round(v).toLocaleString('ru-RU');
export const pct = v => (v == null ? '—' : `${Math.round(v * 100)} %`);
export const sgn = v => { if (v == null) return '—'; const r = Math.round(v); return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r)} %`; };
export const minus = v => (v ? `−${nf(v)}` : '—');
export const plural = (n, a, b, c) => { const x = n % 100, y = n % 10; return `${n} ${x > 10 && x < 20 ? c : y > 1 && y < 5 ? b : y === 1 ? a : c}`; };

/** Значение пары по мере: tempo | day | wr */
export const valueOf = (x, metric) => (metric === 'tempo' ? x.tempo : metric === 'day' ? x.day : x.wr);
export const toneOf = (x, metric, rk) => (metric === 'wr' ? toneWr(x.wr, rk.wr_threshold) : toneTempo(valueOf(x, metric)));

/** Полоска по РК: один квадрат на РК, худшие слева. */
const RANK = { bad: 0, warn: 1, ok: 2, none: 3 };
export function stripOf(platform, metric, rkByCode) {
  return platform.pairs
    .map(x => { const rk = rkByCode[x.rk]; const t = toneOf(x, metric, rk); return { x, rk, t }; })
    .sort((a, b) => RANK[a.t] - RANK[b.t]);
}
export function stripSplit(cells, metric) {
  const n = { bad: 0, warn: 0, ok: 0, none: 0 }; cells.forEach(c => { n[c.t] += 1; });
  return [n.bad && `${n.bad} провал`, n.warn && `${n.warn} ${metric === 'wr' ? 'близко к порогу' : 'недокрут'}`, `${n.ok} норма`, n.none && `${n.none} без данных`].filter(Boolean).join(' · ');
}
const cellTitle = (c, metric) => `${c.rk.code} · ${c.rk.title}\n${metric === 'wr' ? `расхождение с WR ${sgn(c.x.wr)} (порог ±${c.rk.wr_threshold} %)` : `${metric === 'tempo' ? 'темп' : 'сутки'} ${pct(valueOf(c.x, metric))}`}${c.x.under ? ` · недокрут ${nf(c.x.under)}` : ''}`;

/* ── мелкие компоненты ── */
export const Cap = ({ children, style }) => (
  <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-cap)', ...style }}>{children}</span>
);
export const Dot = ({ color, size = 7 }) => <span style={{ width: size, height: size, borderRadius: 2, background: color, flex: `0 0 ${size}px`, display: 'inline-block' }} />;

export function VerdictPill({ verdict, wr }) {
  const v = VERDICT[verdict]; const none = v.tone === 'none';
  return (
    <span style={{ display: 'flex', gap: 5, alignItems: 'center', flexWrap: 'wrap' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', borderRadius: 8, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
        background: TINT[v.tone], color: none ? 'var(--text-muted)' : FG[v.tone] }}>
        <Dot color={none ? 'var(--text-faint)' : C[v.tone]} size={6} />{v.label}
      </span>
      {wr && <span title="WR расходится системно" style={{ padding: '2px 6px', borderRadius: 6, fontFamily: MONO, fontSize: 9.5, fontWeight: 700, background: 'var(--danger-tint)', color: 'var(--danger-fg)' }}>WR</span>}
    </span>
  );
}

/** Полоска по РК. size — ширина квадрата, max — сколько квадратов показать. */
export function Strip({ cells, metric, size = 10, height = 14, max, showSplit = true }) {
  const shown = max ? cells.slice(0, max) : cells;
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
      <span style={{ display: 'flex', gap: 2, height, overflow: 'hidden' }}>
        {shown.map((c, i) => <span key={i} title={cellTitle(c, metric)} style={{ flex: `0 0 ${size}px`, borderRadius: 2, background: C[c.t] }} />)}
      </span>
      {showSplit && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{stripSplit(cells, metric)}</span>}
    </span>
  );
}

export function Legend({ metric }) {
  const items = metric === 'wr'
    ? [['ok', 'до половины порога'], ['warn', 'близко к порогу'], ['bad', 'за порогом сделки'], ['none', 'нет замера']]
    : [['ok', 'от 90 %'], ['warn', '60–90 %'], ['bad', 'ниже 60 %'], ['none', 'нет данных']];
  return (
    <span style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
      {items.map(([t, l]) => <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: 2, background: C[t] }} />{l}</span>)}
    </span>
  );
}

export function Segmented({ label, value, options, onChange }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {label && <Cap>{label}</Cap>}
      <span style={{ display: 'inline-flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 10, padding: 2 }}>
        {options.map(([v, l]) => { const on = v === value; return (
          <span key={v} role="button" tabIndex={0} onClick={() => onChange(v)} onKeyDown={e => e.key === 'Enter' && onChange(v)}
            style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 10px', borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: 'pointer',
              background: on ? 'var(--bg-card)' : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-muted)', boxShadow: on ? 'var(--shadow-card)' : 'none' }}>{l}</span>); })}
      </span>
    </span>
  );
}

/** Шкала темпа: полоса до 120 %, отметка на 90 %. */
export function TempoBar({ value }) {
  const t = toneTempo(value);
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
      <span style={{ flex: '1 1 auto', height: 6, borderRadius: 2, background: 'var(--border-inner)', position: 'relative' }}>
        <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: value == null ? 0 : `${Math.min(100, Math.round(value / 1.2 * 100))}%`, borderRadius: 2, background: C[t] }} />
        <span style={{ position: 'absolute', left: '75%', top: -3, bottom: -3, width: 1, background: 'var(--text-faint)' }} title="90 % — граница нормы" />
      </span>
      <span style={{ flex: '0 0 40px', fontFamily: MONO, fontSize: 11.5, fontWeight: 700, textAlign: 'right', color: FG[t] }}>{pct(value)}</span>
    </span>
  );
}

/** Таблица РК площадки (карточка отчёта и раскрытие виджета). Сортировка — по недокруту. */
export function PlatformRks({ platform, rkByCode, limit, onOpenRk }) {
  const cols = '72px minmax(0,1fr) 64px 84px 60px';
  const rows = platform.pairs.slice().sort((a, b) => b.under - a.under).slice(0, limit || undefined);
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: '0 10px', padding: '0 4px 6px', borderBottom: '1px solid var(--border-inner)' }}>
        <Cap>РК</Cap><Cap>темп · прогноз к плану</Cap><Cap style={{ textAlign: 'right' }}>сутки</Cap><Cap style={{ textAlign: 'right' }}>недокрут</Cap><Cap style={{ textAlign: 'right' }}>WR</Cap>
      </div>
      {rows.map(x => { const rk = rkByCode[x.rk]; return (
        <div key={x.rk} style={{ display: 'grid', gridTemplateColumns: cols, gap: '0 10px', alignItems: 'center', padding: '6px 4px', borderBottom: '1px solid var(--border-row)' }}>
          <a href={`/traffic/dashboard?open=${encodeURIComponent(rk.code)}`} onClick={e => { if (onOpenRk) { e.preventDefault(); onOpenRk(rk.code); } }} title={`${rk.title} · ${rk.start} – ${rk.end} · трафик ${rk.traffic}`}
            style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>{rk.code}</a>
          <TempoBar value={x.tempo} />
          <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', color: FG[toneTempo(x.day)] }}>{pct(x.day)}</span>
          <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', color: x.under ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{minus(x.under)}</span>
          <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', color: FG[toneWr(x.wr, rk.wr_threshold)] }}>{sgn(x.wr)}</span>
        </div>); })}
    </div>
  );
}

/** Вывод словами по площадке — в карточке и в раскрытии виджета. */
export function platformSay(p) {
  const s = p.stats;
  if (p.verdict === 'nodata') return 'Факта по идущим РК ещё нет — темп, сутки и WR появятся с суточным срезом.';
  if (p.verdict === 'ok' && !p.wr_systemic) return 'Площадка идёт в темпе во всех своих РК — вмешательство не нужно.';
  return [
    s.under_n ? `Недокрут в ${s.under_n} из ${s.rated} РК${s.fail_n ? `, провал в ${s.fail_n}` : ''}, медиана темпа ${pct(s.median_tempo)}, теряем ${nf(s.under_total)} показов. ${p.verdict === 'spot' ? 'Проблема точечная — смотреть конкретные РК.' : 'Проблема системная — снизить вес площадки со старта следующих запусков.'}` : '',
    p.wr_systemic ? `Weborama расходится системно: за порогом ${s.wr_over} из ${s.wr_measured} РК, медиана ${sgn(s.wr_median)} — сверить код Weborama на площадке.` : '',
  ].filter(Boolean).join(' ');
}
export const sayTone = p => (p.verdict === 'fail' || p.wr_systemic ? 'bad' : p.verdict === 'ok' ? 'ok' : p.verdict === 'nodata' ? 'none' : 'warn');
