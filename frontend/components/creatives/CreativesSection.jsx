/**
 * Блок «Креативы» в карточке сделки.
 * Комплект (креатив) → площадки внутри него. Сворачивается: раскрытый вид — карточки
 * креативов с таблицей площадок, свёрнутый — сводная таблица готовности.
 *
 * Зависимость только React. Токены — из дизайн-системы финмодуля (design_system/ds.jsx).
 * Верстка под экран 1600; правая колонка документов карточки сделки — фиксированные 280px.
 */
import React, { useState } from 'react';

/* ── токены ─────────────────────────────────────────────────────────── */
export const T = {
  card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', tint: 'var(--bg-tint)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)', hoverBorder: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)', t5: 'var(--text-disabled)',
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)', accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)',
  income: 'var(--income)', incomeFg: 'var(--income-fg)', incomeTint: 'var(--income-tint)', incomeBorder: '#CDE9DE', incomeSoft: '#9BCFBB',
  warning: 'var(--warning)', warningFg: 'var(--warning-text)', warningTint: 'var(--warning-tint)', warningBorder: 'var(--warning-border)',
  danger: 'var(--danger-fg)', dangerSoft: '#E2585C', dangerTint: '#FBEAEA', dangerBorder: 'var(--danger-border)',
  shadow: '0 1px 3px rgba(28,36,51,.05), 0 4px 16px rgba(28,36,51,.04)',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};

/** Статус площадки внутри креатива: фон · текст · рамка. */
export const SITE_STATUS = {
  'черновик':    [T.card, T.t3, T.border],
  'на проверке': [T.accentTint, T.accent, T.accentBorder],
  'принято':     [T.incomeTint, T.incomeFg, T.incomeBorder],
  'правки':      [T.dangerTint, T.danger, T.dangerBorder],
};
/** Цвет площадки в баре готовности. */
const BAR_COLOR = { 'принято': T.income, 'на проверке': T.accent, 'правки': T.dangerSoft, 'черновик': T.inner };
/** Порог: до 12 площадок — отдельные пипсы, дальше — пропорциональные сегменты. */
export const PIPS_LIMIT = 12;

/* сетки: одна на шапку, строки и итог каждой таблицы */
const BRIEF_COLS = 'minmax(150px,1.2fr) 116px 96px minmax(150px,1fr) minmax(210px,1.15fr) minmax(180px,0.9fr)';
const SITE_COLS = '18px minmax(150px,1.25fr) 26px minmax(190px,1.5fr) 128px minmax(120px,0.9fr)';

const capTitle = { fontFamily: T.mono, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: T.t3 };
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const meta = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };

/* ── производные величины комплекта ─────────────────────────────────── */
export function derive(c) {
  const total = c.sites.length;
  const ok = c.sites.filter(s => s.status === 'принято').length;
  const fix = c.sites.filter(s => s.status === 'правки').length;
  const wait = total - ok - fix;
  const pct = total ? Math.round(ok / total * 100) : 0;
  return {
    total, ok, fix, wait, pct,
    okFg: ok === total && ok ? T.income : ok ? T.warning : T.t4,
    usePips: total <= PIPS_LIMIT,
    /* сегменты в порядке ок → правки → ждём, нулевые не рисуем */
    segments: [[T.income, ok, 'согласовано'], [T.warning, fix, 'ждёт правок'], [T.inner, wait, 'ждём']]
      .filter(([, n]) => n > 0)
      .map(([bg, n, label]) => ({ bg, title: `${label} — ${n}`, width: (n / total * 100).toFixed(1) + '%' })),
    legend: [[T.income, T.incomeFg, ok, 'ок'], [T.warning, T.warningFg, fix, 'правки'], [T.t5, T.t3, wait, 'ждём']]
      .map(([dot, fg, n, label]) => ({ dot, fg: n ? fg : T.t5, text: `${n} ${label}` })),
    barTitle: `${total} площадок: согласовано ${ok}, правки ${fix}, ждём ${wait}`,
  };
}

/* ── бар готовности ─────────────────────────────────────────────────── */
const ReadinessBar = ({ c, d }) => (
  <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
    <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
      {d.usePips ? (
        <span style={{ flex: '1 1 auto', minWidth: 40, display: 'flex', gap: 2 }}>
          {c.sites.map(s => (
            <span key={s.site} title={`${s.site} — ${s.status}`} style={{ flex: 1, minWidth: 0, height: 8, borderRadius: 2, background: BAR_COLOR[s.status] }} />
          ))}
        </span>
      ) : (
        <span title={d.barTitle} style={{ flex: '1 1 auto', minWidth: 40, display: 'flex', gap: 2 }}>
          {d.segments.map(g => <span key={g.title} title={g.title} style={{ width: g.width, height: 8, borderRadius: 2, background: g.bg }} />)}
        </span>
      )}
      <span style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: 700, color: d.okFg, flex: '0 0 34px', textAlign: 'right' }}>{d.pct} %</span>
    </span>
    <span style={{ display: 'flex', gap: 10, fontFamily: T.mono, fontSize: 9, letterSpacing: '.04em', whiteSpace: 'nowrap' }}>
      {d.legend.map(l => (
        <span key={l.text} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: l.fg }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: l.dot }} />{l.text}
        </span>
      ))}
    </span>
  </span>
);

const MarkBadge = ({ c }) => (c.erid ? (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.incomeTint, color: T.incomeFg, borderRadius: 7, padding: '4px 10px', fontFamily: T.mono, fontSize: 9, fontWeight: 700, letterSpacing: '.06em', whiteSpace: 'nowrap' }}>
    Маркирован <span style={{ color: T.incomeSoft }}>|</span> ERID {c.erid}
  </span>
) : (
  <span style={{ display: 'inline-flex', alignItems: 'center', background: T.subtle, color: T.t3, borderRadius: 7, padding: '4px 10px', fontFamily: T.mono, fontSize: 9, fontWeight: 700, letterSpacing: '.06em', whiteSpace: 'nowrap' }}>Черновик</span>
));

const PlusIcon = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>;
const CrossIcon = ({ size = 11 }) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>;

/* ══════════════════════════════════════════════════════════════════════
   БЛОК
   ══════════════════════════════════════════════════════════════════════ */

/* ── свёрнутый вид, вынесен из секции ────────────────────────────────────
   ЕДИНСТВЕННАЯ правка хендоффа: разметка сводной таблицы вынесена из тела секции в
   отдельный экспорт, без изменения хотя бы одного стиля. Понадобилось это потому, что
   в нашей карточке сворачиванием управляет общий компонент `components/deal/Section`,
   а он ждёт УЗЕЛ для свёрнутого состояния, а не секцию со своим состоянием внутри. */
export function CreativesBrief({ creatives = [], onPreview }) {
  const items = creatives.map(c => ({ c, d: derive(c) }));
  const sumTotal = items.reduce((a, x) => a + x.d.total, 0);
  const sumOk = items.reduce((a, x) => a + x.d.ok, 0);
  const marked = creatives.filter(c => !!c.erid).length;

  return (
    <div style={{ fontFamily: T.sans, color: T.t1 }}>
      <style>{`
        @keyframes popIn { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
        .cs-row:hover { background:${T.subtle} }
        .cs-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
      `}</style>

        <div style={{ display: 'flex', flexDirection: 'column', animation: `popIn .2s ${T.ease} both` }}>
          <div style={{ display: 'grid', gridTemplateColumns: BRIEF_COLS, gap: 14, padding: '0 4px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
            <span>Креатив</span><span>Тип</span><span style={{ textAlign: 'right' }}>Согласовано</span>
            <span>Готовность площадок</span><span>Материалы</span><span style={{ textAlign: 'right' }}>Маркировка</span>
          </div>

          {items.map(({ c, d }) => (
            <div key={c.num} className="cs-row" style={{ display: 'grid', gridTemplateColumns: BRIEF_COLS, gap: 14, alignItems: 'center', padding: '9px 4px', borderBottom: `1px solid ${T.row}`, minWidth: 0 }}>
              <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
                <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: T.accent, flex: '0 0 24px' }}>{c.num}</span>
                <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
              </span>

              <span style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.tech}</span>

              <span style={{ display: 'inline-flex', alignItems: 'baseline', justifyContent: 'flex-end', gap: 4, whiteSpace: 'nowrap' }}>
                <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em', color: d.okFg }}>{d.ok}</span>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t4 }}>из {d.total}</span>
              </span>

              <ReadinessBar c={c} d={d} />

              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.file}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 9, color: T.t4, whiteSpace: 'nowrap' }}>{c.size}</span>
                </span>
                {/* Вторая правка хендоффа, названная владельцем явно: «есть скриншоты»
                    в свёрнутой сводке. Значок в идиоме соседнего «ТТ» — факт наличия
                    доказательств, без разбивки по площадкам. */}
                {!!c.shots && (
                  <span title={`Скриншоты размещения: ${c.shots}`} style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 8px', background: T.incomeTint, color: T.incomeFg, border: `1px solid ${T.incomeBorder}`, borderRadius: 8, fontFamily: T.mono, fontSize: 9.5, fontWeight: 700, whiteSpace: 'nowrap', flex: '0 0 auto' }}>скрины · {c.shots}</span>
                )}
                <span className="cs-ghost" onClick={() => onPreview?.(c)} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 10px', background: T.card, border: `1px solid ${T.border}`, color: T.t2, borderRadius: 8, fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer', flex: '0 0 auto' }}>предпросмотр</span>
              </span>

              <span style={{ display: 'inline-flex', justifyContent: 'flex-end', minWidth: 0 }}><MarkBadge c={c} /></span>
            </div>
          ))}

          {/* итог: согласовано площадок по всем креативам + маркировка */}
          <div style={{ display: 'grid', gridTemplateColumns: BRIEF_COLS, gap: 14, alignItems: 'center', padding: '11px 4px 0' }}>
            <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого</span>
            <span />
            <span style={{ display: 'inline-flex', alignItems: 'baseline', justifyContent: 'flex-end', gap: 4, whiteSpace: 'nowrap' }}>
              <span style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em', color: sumOk === sumTotal && sumOk ? T.income : sumOk ? T.warning : T.t4 }}>{sumOk}</span>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t4 }}>из {sumTotal}</span>
            </span>
            <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.t3 }}>площадок согласовано по всем креативам</span>
            <span />
            <span style={{ display: 'inline-flex', justifyContent: 'flex-end', fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: marked === creatives.length ? T.income : T.warning, whiteSpace: 'nowrap' }}>
              {marked} из {creatives.length} маркировано
            </span>
          </div>
        </div>
    </div>
  );
}

export default function CreativesSection({
  creatives = DEMO, service = 'еФарм', deadline = '28.04.2026', blockNote = DEFAULT_BLOCK_NOTE,
  onPreview, onAddCreative, onAddSites, onRemoveCreative, onCheckCreative, onRequestSpec, onRemoveSite,
}) {
  const [open, setOpen] = useState(true);
  const items = creatives.map(c => ({ c, d: derive(c) }));

  const sumTotal = items.reduce((a, x) => a + x.d.total, 0);
  const sumOk = items.reduce((a, x) => a + x.d.ok, 0);
  const marked = creatives.filter(c => !!c.erid).length;

  return (
    <section style={{
      background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 18,
      padding: '20px 24px 18px', display: 'flex', flexDirection: 'column', gap: 12,
      fontFamily: T.sans, color: T.t1, animation: `riseIn .4s ${T.ease} .21s both`,
    }}>
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes popIn { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
        .cs-row:hover { background:${T.subtle} }
        .cs-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
        .cs-primary:hover { background:${T.accentHover} }
        .cs-warn:hover { background:${T.warningTint} }
        .cs-del:hover { background:${T.dangerTint}; color:${T.danger} }
        .cs-dash:hover { border-color:${T.accent}; background:${T.tint} }
      `}</style>

      {/* шапка секции */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span onClick={() => setOpen(o => !o)} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9, cursor: 'pointer' }}>
          <span style={{ fontSize: 10, color: T.t4 }}>{open ? '▾' : '▸'}</span>
          <span style={capTitle}>Креативы</span>
        </span>
        <span style={meta}>услуга: {service} · из медиаплана</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>дедлайн подачи {deadline}</span>
          <span style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, letterSpacing: '.06em', color: T.t3, whiteSpace: 'nowrap' }}>{creatives.length} в работе</span>
        </span>
      </div>

      {/* ── СВЁРНУТЫЙ: сводная таблица готовности ─────────────────────── */}
      {!open && <CreativesBrief creatives={creatives} onPreview={onPreview} />}

      {/* ── РАСКРЫТЫЙ: карточка на креатив ──────────────────────────── */}
      {open && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {items.map(({ c, d }) => (
              <div key={c.num} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: '14px 16px 12px', display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>Креатив {c.num}</span>
                  <span style={{ fontSize: 14, fontWeight: 600, color: T.accent }}>{c.name}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4, whiteSpace: 'nowrap' }}>{c.tags}</span>
                  <span style={{ marginLeft: 'auto', flex: '0 0 auto' }}><MarkBadge c={c} /></span>
                </div>

                {/* архив креатива */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', minWidth: 0 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, flex: '0 0 44px' }}>архив</span>
                  <a href="#file" style={{ fontSize: 12.5, fontWeight: 600, color: T.accent, textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.file}</a>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
                    <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4, whiteSpace: 'nowrap' }}>{c.size}</span>
                    <span className="cs-ghost" onClick={() => onPreview?.(c)} style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 10px', background: T.card, border: `1px solid ${T.border}`, color: T.t2, borderRadius: 8, fontSize: 10.5, fontWeight: 600, cursor: 'pointer' }}>предпросмотр</span>
                    <span className="cs-del" title="Убрать архив" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 6, color: T.dangerSoft, cursor: 'pointer' }}><CrossIcon /></span>
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, paddingTop: 2 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3 }}>площадки</span>
                  <span style={{ fontFamily: T.mono, fontSize: 9, color: T.t4 }}>·</span>
                  <span style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: d.total ? T.warning : T.t5 }}>{d.total}</span>
                </div>

                {/* таблица площадок креатива */}
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: SITE_COLS, gap: 12, padding: '0 4px 7px', borderBottom: `1px solid ${T.inner}`, ...colHead }}>
                    <span /><span>Площадка</span><span>ТТ</span><span>Посадочная страница</span>
                    <span style={{ textAlign: 'center' }}>Статус</span><span>ЕРИД</span>
                  </div>
                  {c.sites.map(s => {
                    const [stBg, stFg, stBorder] = SITE_STATUS[s.status];
                    return (
                      <div key={s.site} className="cs-row" style={{ display: 'grid', gridTemplateColumns: SITE_COLS, gap: 12, alignItems: 'center', padding: '7px 4px', borderBottom: `1px solid ${T.row}`, minWidth: 0 }}>
                        <span className="cs-del" title="Убрать площадку" onClick={() => onRemoveSite?.(c, s)} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, borderRadius: 5, color: T.t5, cursor: 'pointer' }}><CrossIcon size={10} /></span>
                        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 7, minWidth: 0 }}>
                          <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.site}</span>
                          <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{s.surface}</span>
                        </span>
                        <span title={s.hasSpec ? 'Технические требования получены' : 'Технических требований нет'}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 18, borderRadius: 5, background: s.hasSpec ? T.accentTint : T.subtle, color: s.hasSpec ? T.accent : T.t5, fontFamily: T.mono, fontSize: 9, fontWeight: 700, cursor: 'pointer' }}>ТТ</span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                          <span style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: s.url ? T.t2 : T.t5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.url || 'ссылки нет'}</span>
                          {!s.url && <span className="cs-ghost" onClick={() => onRequestSpec?.(c, s)} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', background: T.card, border: `1px solid ${T.border}`, color: T.t2, borderRadius: 7, fontSize: 10.5, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer', flex: '0 0 auto' }}>запросить</span>}
                        </span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: stBg, color: stFg, border: `1px solid ${stBorder}`, borderRadius: 7, padding: '3px 0', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{s.status}</span>
                        <span style={{ fontFamily: T.mono, fontSize: 10.5, color: s.erid ? T.accent : T.t5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.erid || '—'}</span>
                      </div>
                    );
                  })}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingTop: 4 }}>
                  <span className="cs-ghost" onClick={() => onAddSites?.(c)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 12px', background: T.card, border: `1px solid ${T.accentBorder}`, color: T.accent, borderRadius: 9, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}><PlusIcon />Площадки</span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
                    <span className="cs-warn" onClick={() => onRemoveCreative?.(c)} style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 13px', background: T.card, border: `1px solid ${T.warningBorder}`, color: T.warningFg, borderRadius: 9, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>Удалить креатив</span>
                    <span className="cs-primary" onClick={() => onCheckCreative?.(c)} style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 14px', background: T.accent, color: 'var(--bg-card)', borderRadius: 9, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>Проверить креатив</span>
                  </span>
                </div>
              </div>
            ))}

            <span className="cs-dash" onClick={onAddCreative} style={{ display: 'inline-flex', alignSelf: 'flex-start', alignItems: 'center', gap: 8, height: 32, padding: '0 13px', border: `1px dashed ${T.accentBorder}`, borderRadius: 10, fontSize: 12, fontWeight: 600, color: T.accent, cursor: 'pointer' }}><PlusIcon />Прикрепить креатив</span>
          </div>

          {marked < creatives.length && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 9, background: T.warningTint, borderRadius: 11, padding: '10px 13px' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: T.warning, flex: '0 0 7px' }} />
              <span style={{ fontSize: 11.5, color: T.warningFg, lineHeight: 1.4 }}>{blockNote}</span>
            </span>
          )}
        </>
      )}
    </section>
  );
}

export const DEFAULT_BLOCK_NOTE =
  'ЕРИД выпускается только после сборки цепочки ОРД — сейчас не выбран изначальный договор. ' +
  'Дедлайн подачи креативов 28.04, за 3 рабочих дня до старта.';

/* ══════════════════════════════════════════════════════════════════════
   ДЕМО-ДАННЫЕ — контракт с API
   ══════════════════════════════════════════════════════════════════════ */
const site = (s, status = 'черновик', extra = {}) => ({ site: s, surface: 'web', hasSpec: false, url: '', erid: '', status, ...extra });

export const DEMO = [
  {
    num: '№1', name: 'Ебала большая', tags: 'общий · banner html5', tech: 'banner html5',
    file: 'html_Solosorb_dcp.zip', size: '611 КБ', erid: 'KRA245VRG',
    sites: [
      site('366.ru', 'принято', { hasSpec: true, url: 'solosorb.ru/promo', erid: 'KRA245VRG' }),
      site('24farmacia.ru', 'принято', { hasSpec: true, url: 'solosorb.ru/promo', erid: 'KRA245VRG' }),
      site('aptechestvo.ru', 'на проверке', { hasSpec: true, url: 'solosorb.ru/promo' }),
      site('009.рф'), site('ASNA.ru'), site('120на80.рф'), site('003ms.ru'), site('superapteka.ru'),
    ],
  },
  {
    num: '№2', name: 'Ебала маленькая', tags: 'общий · параллельный · banner html5', tech: 'banner html5',
    file: 'html_Solosorb_dcp (2).zip', size: '611 КБ', erid: '',
    sites: [
      site('366.ru', 'правки', { hasSpec: true }),
      site('24farmacia.ru'), site('aptechestvo.ru'), site('009.рф'),
      site('ASNA.ru'), site('120на80.рф'), site('003ms.ru'),
    ],
  },
  {
    num: '№3', name: 'Не Ебала', tags: 'общий · параллельный · banner html5', tech: 'banner html5',
    file: 'html_Solosorb_adfox.zip', size: '611 КБ', erid: '',
    sites: [site('stoletov.ru'), site('zdesapteka.ru'), site('polza.ru')],
  },
];
