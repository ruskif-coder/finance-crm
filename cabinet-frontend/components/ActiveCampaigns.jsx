/**
 * Блок «Актуальные кампании» в кабинете паблишера.
 * Плоская таблица без группировки: строка = размещение (кампания × период).
 * Сортировка по клику на заголовок колонки, по умолчанию — новые периоды сверху.
 *
 * Зависимость только React. Токены — из дизайн-системы финмодуля.
 */
import React, { useMemo, useState } from 'react';

/* ── токены ──────────────────────────────────────────────────────────

   ЕДИНСТВЕННОЕ, ЧТО ПЕРЕПИСАНО В ЭТОМ ФАЙЛЕ ПОСЛЕ ХЕНДОФФА (кроме ключа строки ниже).
   В хендоффе палитра задана хексами; в проекте цвета живут переменными в
   `styles/globals.css`, и прибор `check-tokens` отвергает сборку с хексом в JS. Он прав:
   тёмная тема переключает переменные, а хекс остаётся светлым — блок выглядел бы
   вырезанным из другого приложения.

   Значения те же самые, что в хендоффе: переменные светлой темы совпадают с его
   палитрой один в один (сверено по `design-language.md` § «Токены»). */
export const T = {
  card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', tint: 'var(--bg-tint)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)',
  hover: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)',
  t4: 'var(--text-faint)', t5: 'var(--text-ghost)',
  accent: 'var(--accent)', accentTint: 'var(--accent-tint)',
  accentBorder: 'var(--accent-border)',
  income: 'var(--income)', incomeFg: 'var(--income-fg)', incomeTint: 'var(--income-tint)',
  incomeBorder: 'var(--income-border)',
  warning: 'var(--warning)', warnFg: 'var(--warning-fg)', warnTint: 'var(--warning-tint)',
  warnBorder: 'var(--warning-border)',
  danger: 'var(--danger)', dangerTint: 'var(--danger-tint)',
  dangerBorder: 'var(--danger-border)',
  teal: 'var(--teal)', violet: 'var(--violet)',
  shadow: 'var(--shadow-card)',
  mono: "'JetBrains Mono', ui-monospace, monospace",
  sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};

/* ── шесть статусов РК: единственный справочник состояний блока ─────── */
export const RK_STATUS = {
  'ждёт согласования': [T.accentTint, T.accent, T.accentBorder],
  'ждёт старта':       [T.subtle, T.t3, T.border],
  'в размещении':      [T.accentTint, T.accent, T.accentBorder],
  'пауза':             [T.warnTint, T.warnFg, T.warnBorder],
  'завершён':          [T.incomeTint, T.incomeFg, T.incomeBorder],
  'отказ':             [T.dangerTint, T.danger, T.dangerBorder],
};
export const STATUS_ORDER = Object.keys(RK_STATUS);

/** Маркер услуги: цвет закреплён за услугой, а не за статусом. */
export const SERVICE_DOT = { 'еФарм': T.accent, 'Альфарм-Таргет': T.teal, 'Приоритезация': T.violet };

/* ── формат и расчёты ───────────────────────────────────────────────── */
const nf = v => v.toLocaleString('ru-RU');
const rub = v => nf(v) + ' ₽';
/** Биллинг: факт показов ÷ 1000 × CPM. Считается только от факта. */
export const billing = (fact, cpm) => Math.round(fact / 1000 * cpm);
/** Период выводится из месяца флайта — пара «период ↔ срок РК» не может разойтись. */
export const periodOf = c => {
  const m = /^(\d{2})\.(\d{2})/.exec(c.flight || '');
  return m ? String(c.year) + '-' + m[2] : c.period;
};
const pctColor = v => (v >= 90 ? T.income : v >= 70 ? T.warning : T.danger);

/* ── сортировка: ключ на колонку ────────────────────────────────────── */
export const SORT_KEYS = {
  title:   c => c.brand,
  site:    c => c.site,
  service: c => c.service,
  period:  c => periodOf(c) + (c.flight || ''),
  fact:    c => c.fact,
  pct:     c => (c.plan ? c.fact / c.plan : 0),
  sum:     c => (c.fact ? billing(c.fact, c.cpm) : 0),
  erid:    c => (c.erid ? 0 : 1),
  state:   c => STATUS_ORDER.indexOf(c.status),
};

const COLS = 'minmax(190px,1.3fr) 110px minmax(104px,0.7fr) 84px 104px minmax(120px,0.8fr) 118px 100px 130px';
const HEAD = [
  ['title', 'Кампания', 'flex-start'], ['site', 'Площадка', 'flex-start'],
  ['service', 'Услуга', 'flex-start'], ['period', 'Период', 'flex-start'],
  ['fact', 'Факт показов', 'flex-end'], ['pct', '% плана', 'flex-start'],
  ['sum', 'Расчётный биллинг', 'flex-end'], ['erid', 'ЕРИД', 'flex-start'],
  ['state', 'Статус', 'center'],
];
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase' };

/* ══════════════════════════════════════════════════════════════════════
   БЛОК
   ══════════════════════════════════════════════════════════════════════ */
/* `title` добавлен к контракту хендоффа: этот же компонент рисует таблицы на экране
   «Кампании», где над каждой стоит месяц со своим итогом, и второй заголовок внутри
   означал бы «Актуальные кампании» под подписью «сентябрь 2026». `null` прячет шапку.
   Вторая копия таблицы ради заголовка разошлась бы с первой на первой же правке. */
export default function ActiveCampaigns({ campaigns = DEMO, onOpen,
  title = 'Актуальные кампании' }) {
  /* по умолчанию новые периоды сверху */
  const [sort, setSort] = useState({ key: 'period', dir: -1 });

  const rows = useMemo(() => {
    const f = SORT_KEYS[sort.key] || SORT_KEYS.period;
    return campaigns.slice().sort((a, b) => {
      const x = f(a), y = f(b);
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }, [campaigns, sort]);

  const total = useMemo(() => {
    const plan = rows.reduce((a, c) => a + c.plan, 0);
    const fact = rows.reduce((a, c) => a + c.fact, 0);
    const sum = rows.reduce((a, c) => a + (c.fact ? billing(c.fact, c.cpm) : 0), 0);
    const erid = rows.filter(c => c.erid).length;
    return { fact, sum, pct: plan ? Math.round(fact / plan * 100) : 0, erid };
  }, [rows]);

  const click = key => setSort(s => ({ key, dir: s.key === key ? -s.dir : 1 }));

  return (
    <section style={{
      background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 18,
      padding: '20px 24px 16px', display: 'flex', flexDirection: 'column', gap: 12,
      fontFamily: T.sans, color: T.t1, animation: `riseIn .4s ${T.ease} .21s both`,
    }}>
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important } }
        .ac-row:hover { background:${T.subtle} }
        .ac-head:hover { color:${T.accent} }
      `}</style>

      {!!title && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em' }}>{title}</span>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 1180, display: 'flex', flexDirection: 'column' }}>

          {/* шапка: каждая колонка сортирует */}
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, padding: '0 6px 9px', borderBottom: `1px solid ${T.border}`, ...colHead, color: T.t4 }}>
            {HEAD.map(([key, label, justify]) => {
              const on = sort.key === key;
              return (
                <span key={key} className="ac-head" onClick={() => click(key)}
                  title={`Сортировать по «${label}»${on ? (sort.dir > 0 ? ' — по возрастанию' : ' — по убыванию') : ''}`}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5, justifyContent: justify, color: on ? T.accent : T.t4, cursor: 'pointer', userSelect: 'none' }}>
                  {label}
                  <span style={{ fontSize: 8, color: T.accent }}>{on ? (sort.dir > 0 ? '▲' : '▼') : ''}</span>
                </span>
              );
            })}
          </div>

          {rows.map(c => {
            const period = periodOf(c);
            const pct = c.plan ? c.fact / c.plan * 100 : 0;
            const [stBg, stFg, stBorder] = RK_STATUS[c.status];
            return (
              /* КЛЮЧ ДОПОЛНЕН площадкой, поверхностью и флайтом — единственная правка
                 вставленного компонента, и вот почему. В макете у площадки один сайт, и
                 пары «бренд + период» хватало. В системе учётка может видеть несколько
                 площадок (служебный доступ видит все 41), и тогда одна пара встречается
                 десятками: React считает такие строки одной, и при сортировке они
                 перемешиваются на глазах. Ключ обязан быть уникален по строке. */
              <div key={[c.site, c.brand, period, c.surface, c.flight].join('|')}
                className="ac-row" onClick={() => onOpen?.(c)}
                style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center', padding: '9px 6px', borderRadius: 10, borderBottom: `1px solid ${T.row}`, minWidth: 0, cursor: 'pointer' }}>

                {/* 1. кампания: рекламодатель · бренд, второй строкой поверхность и флайт */}
                <span style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 8, minWidth: 0 }}>
                  <span style={{ width: 7, height: 7, borderRadius: 2, background: SERVICE_DOT[c.service] || T.t5, flex: '0 0 7px', marginTop: 4 }} />
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.brand}</span>
                    {/* Только срок РК. Поверхность переехала под УСЛУГУ — так она
                        показана на остальных наших дашбордах (`ServiceChip`: «еФарм
                        WEB»), и это не вкусовщина: web и app — это разновидность
                        УСЛУГИ, а не свойство кампании. Пока она стояла у имени, одна и
                        та же услуга на двух поверхностях читалась как две разные
                        кампании. */}
                    <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.04em', color: T.t4, whiteSpace: 'nowrap' }}>{c.flight}</span>
                  </span>
                </span>

                <span style={{ fontSize: 12.5, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.site}</span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 12, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.service}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 }}>{c.surface}</span>
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3, whiteSpace: 'nowrap' }}>{period}</span>
                <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, textAlign: 'right' }}>{c.fact ? nf(c.fact) : '—'}</span>

                {/* 6. % плана: полоса + число, порог цвета 90 / 70 */}
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ flex: '1 1 auto', minWidth: 34, display: 'block', height: 6, borderRadius: 3, background: T.inner, overflow: 'hidden' }}>
                    <span style={{ display: 'block', height: 6, width: Math.min(100, pct) + '%', borderRadius: 3, background: pctColor(pct) }} />
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: 700, color: pctColor(pct), flex: '0 0 34px', textAlign: 'right' }}>
                    {c.plan && c.fact ? Math.round(pct) + '%' : '—'}
                  </span>
                </span>

                <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {c.fact ? rub(billing(c.fact, c.cpm)) : '—'}
                </span>

                {/* 8. ЕРИД: номер либо «не выпущен» */}
                <span title={c.erid ? 'ЕРИД выпущен нашей стороной' : 'ЕРИД появится после сборки цепочки ОРД'}
                  style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: c.erid ? 700 : 400, color: c.erid ? T.accent : T.t5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.erid || 'не выпущен'}
                </span>

                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: stBg, color: stFg, border: `1px solid ${stBorder}`, borderRadius: 7, padding: '4px 0', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {c.status}
                </span>
              </div>
            );
          })}

          {/* итог по видимым строкам */}
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center', padding: '13px 6px 0' }}>
            <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого</span>
            <span /><span /><span />
            <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{nf(total.fact)}</span>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3 }}>{total.pct} % по показам</span>
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{rub(total.sum)}</span>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>{total.erid} из {rows.length} ЕРИД</span>
            <span />
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
        <span style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '.04em', color: T.t4 }}>суммы до НДС · сверка по факту закрытия периода</span>
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   ДЕМО-ДАННЫЕ — контракт с API
   ══════════════════════════════════════════════════════════════════════ */
const c = (brand, service, year, surface, flight, plan, fact, cpm, status, erid = '') =>
  ({ brand, service, year, period: year + '-01', surface, flight, plan, fact, cpm, status, erid, site: 'Maksavit.ru' });

export const DEMO = [
  c('Woerwag · Мильгамма', 'еФарм', 2026, 'web', '01.10 — 31.10', 620000, 0, 450, 'ждёт согласования'),
  c('Sanofi · Но-шпа', 'еФарм', 2026, 'app', '05.10 — 31.10', 410000, 0, 420, 'ждёт согласования'),
  c('BINNO · Венапрокт', 'Альфарм-Таргет', 2026, 'web', '01.12 — 31.12', 260000, 0, 380, 'ждёт старта'),
  c('AB-BIOTICS · Бифистим', 'еФарм', 2026, 'web', '05.09 — 30.09', 540000, 318400, 450, 'в размещении', 'Kra251bQm'),
  c('Замбон · Анауран', 'Альфарм-Таргет', 2026, 'web', '12.09 — 30.09', 300000, 96200, 380, 'в размещении', 'Kra263kWs'),
  c('Ферон · Виферон', 'еФарм', 2026, 'app', '01.09 — 25.09', 360000, 214800, 420, 'в размещении', 'Kra271dFy'),
  c("Dr. Reddy's · Найз", 'Приоритезация', 2026, 'web', '08.09 — 30.09', 180000, 41300, 520, 'пауза', 'Kra266mZc'),
  c('Belle you · Кросс-сеть', 'Альфарм-Таргет', 2026, 'web', '01.09 — 30.09', 200000, 0, 380, 'отказ'),
  c('Sanofi · Маалокс', 'еФарм', 2026, 'web', '01.08 — 31.08', 720000, 706400, 450, 'завершён', 'Kra174pLd'),
  c('BINNO · Кагоцел', 'Альфарм-Таргет', 2026, 'web', '01.08 — 31.08', 480000, 492100, 380, 'завершён', 'Kra198xTf'),
  c('Ферон · Виферон', 'еФарм', 2026, 'app', '01.08 — 25.08', 360000, 351800, 420, 'завершён', 'Kra240nHv'),
];
