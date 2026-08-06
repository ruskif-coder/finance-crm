/**
 * Медиаплан — печатный документ (A4, портрет, ровно 1 лист).
 * Порт хендоффа design_handoff_mp_pdf на наши данные. Печать/PDF — window.print(),
 * геометрию задаёт @page + .page (PRINT_CSS ниже). Шрифты — самохостинг проекта
 * (Manrope + JetBrains Mono из globals.css), Google Fonts НЕ используем (режет CSP).
 */
import React, { useRef, useEffect } from 'react';

/* ── токены (печатное подмножество дизайн-системы) ──────────────────── */
export const T = {
  paper: '#FFFFFF', tint: '#F6F8FF',
  border: '#E3E7F1', row: '#F2F4FA',
  t1: '#1C2433', t2: '#525C70', t3: '#79839A', t4: '#A3ABBD',
  accent: '#4F6CE6', income: '#2FA37C',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
};
const VAT = 0.22;

/* ── формат чисел ───────────────────────────────────────────────────── */
const num = v => Math.round(v || 0).toLocaleString('ru-RU');
const rub = v => (v || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽';
const dec = v => (Number.isFinite(v) ? v : 0).toFixed(2).replace('.', ',');
const sd = (a, b) => (b ? a / b : 0);   // безопасное деление (пустой прогноз → 0, не Infinity)
// Плотные форматтеры прогноза (пустой ввод → «—», как в конструкторе; без ₽ — узкие колонки)
const fi = v => (Number.isFinite(v) && v > 0 ? num(v) : '—');
const fm = v => (Number.isFinite(v) && v > 0 ? dec(v) : '—');
const fp = v => (Number.isFinite(v) && v > 0 ? dec(v) + '%' : '—');
const froi = (rev, gross) => { if (!(gross > 0) || !rev) return '—'; const r = (rev - gross) / gross; return `${r >= 0 ? '+' : '−'}${Math.abs(r * 100).toFixed(0)}%`; };
const fk = v => (Number.isFinite(v) && v > 0 ? num(v / 1000) + 'к' : '—');   // деньги в тысячах

/* ── инвентарь (наша структура: web/IN-App/кросс-девайс) ────────────── */
const INV_LABEL = { web: 'Web', app: 'IN-App', cross: 'Кросс-девайс' };

/* ── целевые показатели (KPI приёмки) — ключ · подпись · пояснение ───── */
const GOALS_META = [
  ['freq', 'Частота', 'контактов на пользователя'],
  ['ctr', 'CTR', 'целевой клик-рейт'],
  ['cr', 'CR', 'конверсия в действие'],
  ['volume', 'Показы / клики', 'в зависимости от модели РК'],
  ['weborama', 'Расхождение с Weborama', 'допустимая погрешность'],
];

/* ── сетки: одна на шапку, строки и итог каждой таблицы ─────────────── */
const PLACEMENT_COLS = '1.55fr 0.8fr 0.75fr 0.55fr 0.95fr 0.85fr 0.55fr 1.1fr 1.1fr';
// Полный прогноз (15 метрик), вертикальный A4. Охват и Показы шире прочих —
// у них самые длинные числа (запас на ведущий знак/разделитель, иначе едет вёрстка).
// Порядок: Строка · Част · Охват · Показы · CTR · Клики · CPM · CPC · CPU · CR · Чеки · CPO · Цена · Доход · ROI · SOV
const FORECAST_COLS = '1.4fr 0.6fr 1.35fr 1.35fr 0.75fr 1.05fr 0.85fr 0.85fr 0.85fr 0.7fr 0.85fr 0.9fr 0.85fr 0.8fr 0.8fr 0.7fr';

/* ── типографика ────────────────────────────────────────────────────── */
const secTitle = { fontFamily: T.mono, fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: T.t3 };
const secMeta = { fontFamily: T.mono, fontSize: 8, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const colHead = { fontFamily: T.mono, fontSize: 8, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const totalLabel = { fontFamily: T.mono, fontSize: 7.5, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 };

const Section = ({ title, meta, children, style }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
      <span style={secTitle}>{title}</span>
      {meta && <span style={secMeta}>{meta}</span>}
    </div>
    {children}
  </div>
);

const N = ({ children, size = 9.5, color = T.t1, bold, align = 'right' }) => (
  <span style={{ fontFamily: T.mono, fontSize: size, fontWeight: bold ? 700 : 400, color, textAlign: align }}>{children}</span>
);

/* ══════════════════════════════════════════════════════════════════════
   ДОКУМЕНТ
   ══════════════════════════════════════════════════════════════════════ */
export default function MediaPlanPdf({ data = SAMPLE }) {
  const { header, placements, extras, targeting, notes, aggRules, bonusNote, params, placementMeta, goals = {} } = data;
  // Блок целевых показывается, если задан хоть один KPI; внутри — все 5, пустые → «не задано».
  const hasGoals = GOALS_META.some(([k]) => (goals[k] ?? '').toString().trim() !== '');

  // Контроль переполнения: если контент выше рабочей области A4 — ужимаем zoom'ом до 1 листа.
  // A4 = 297мм; CSS мм фиксированы (1мм = 96/25.4 px), минус верх/низ padding (30+20).
  const fitRef = useRef(null);
  useEffect(() => {
    const el = fitRef.current;
    if (!el) return;
    const AVAIL = 297 * 96 / 25.4 - 50;   // ~1072px рабочей высоты листа
    const fit = () => {
      el.style.zoom = '1';
      const s = Math.min(1, AVAIL / el.scrollHeight);
      el.style.zoom = String(s < 0.6 ? 0.6 : s);   // ниже 0.6 не жмём — иначе нечитаемо
    };
    fit();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit).catch(() => {});
  }, [data]);

  /* расчёты — единая точка правды документа (формулы совпадают с конструктором) */
  const tNet = placements.reduce((a, r) => a + r.cost, 0);
  const tVol = placements.reduce((a, r) => a + r.volume, 0);
  const tClicks = placements.reduce((a, r) => a + r.clicks, 0);
  const tReach = placements.reduce((a, r) => a + r.reach, 0);
  const tChecks = placements.reduce((a, r) => a + (r.checks || 0), 0);
  const tRevenue = placements.reduce((a, r) => a + (r.revenue || 0), 0);
  const tSov = placements.reduce((a, r) => a + (r.sov || 0), 0);
  const maxFreq = placements.length ? Math.max(...placements.map(r => r.freq || 0)) : 0;
  const extrasNet = extras.reduce((a, e) => a + e.total, 0);
  const grandNet = tNet + extrasNet;
  const tGross = tNet * (1 + VAT);
  const tRoi = tGross > 0 ? (tRevenue - tGross) / tGross : NaN;

  const kpi = [
    { label: 'Стоимость до НДС', value: rub(grandNet), hint: `${placements.length} строки размещения + доп. услуги`, color: T.t1 },
    { label: 'НДС 22 %', value: rub(grandNet * VAT), hint: 'ставка 22 %', color: T.t3 },
    { label: 'Стоимость с НДС', value: rub(grandNet * (1 + VAT)), hint: 'к оплате', color: T.accent },
    { label: 'Показы', value: num(tVol), hint: `CPM ${dec(sd(tNet, tVol) * 1000)} ₽`, color: T.income },
  ];

  return (
    <>
      <style>{PRINT_CSS}</style>

      <div className="desk">
        <section className="page">
         <div ref={fitRef} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

          {/* ── ШАПКА ───────────────────────────────────────────────── */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, paddingBottom: 11, borderBottom: `1px solid ${T.border}` }}>
            <img src={header.logo} alt="SIMB-AD" style={{ height: 26, width: 'auto', display: 'block' }} />
            <span style={{ display: 'flex', flexDirection: 'column', gap: 2, marginLeft: 'auto', textAlign: 'right' }}>
              <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em' }}>{header.title}</span>
              <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 }}>{header.subtitle}</span>
            </span>
          </div>

          {/* ── KPI ─────────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 9 }}>
            {kpi.map(k => (
              <div key={k.label} style={{ background: T.tint, borderRadius: 9, padding: '9px 11px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontFamily: T.mono, fontSize: 8, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 }}>{k.label}</span>
                <span style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.15, color: k.color }}>{k.value}</span>
                <span style={{ fontSize: 8.5, color: T.t4 }}>{k.hint}</span>
              </div>
            ))}
          </div>

          {/* ── ПАРАМЕТРЫ КАМПАНИИ ──────────────────────────────────── */}
          <Section title="Параметры кампании">
            {/* 4×2, заливка по колонкам (пары в столбик): РК+Агентство · Рекл+Бренд · Период+Старт · Место+Гео */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gridTemplateRows: 'repeat(2,auto)', gridAutoFlow: 'column', gap: '0 18px' }}>
              {params.map(([label, value, mono]) => (
                <span key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '3px 0', borderTop: `1px solid ${T.row}` }}>
                  <span style={{ fontSize: 9.5, lineHeight: 1.25, color: T.t3 }}>{label}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: mono ? T.mono : T.sans, fontSize: 9.5, lineHeight: 1.25, fontWeight: 600, textAlign: 'right' }}>{value}</span>
                </span>
              ))}
            </div>
          </Section>

          {/* ── РАЗМЕЩЕНИЕ ──────────────────────────────────────────── */}
          <Section title="Размещение" meta={placementMeta}
            style={{ gap: 6, margin: '5px 0', padding: '11px 0', borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}` }}>
            <div style={{ display: 'grid', gridTemplateColumns: PLACEMENT_COLS, gap: 8, paddingBottom: 6, borderBottom: `1px solid ${T.border}`, ...colHead }}>
              <span>Позиция</span><span>Формат</span><span>Инвентарь</span><span>Модель</span>
              <span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена/ед.</span>
              <span style={{ textAlign: 'right' }}>Скидка</span><span style={{ textAlign: 'right' }}>До НДС</span><span style={{ textAlign: 'right' }}>С НДС</span>
            </div>
            {placements.map((r, i) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: PLACEMENT_COLS, gap: 8, alignItems: 'center', padding: '3px 0', borderBottom: `1px solid ${T.row}` }}>
                <span style={{ fontSize: 9.5, fontWeight: 600, lineHeight: 1.2 }}>{r.position}</span>
                <span style={{ fontSize: 9, color: T.t2 }}>{r.format}</span>
                <span style={{ fontSize: 9, color: T.t2 }}>{INV_LABEL[r.inventory] || 'Кросс-девайс'}</span>
                <N size={9} color={T.accent} bold align="left">{r.model}</N>
                <N size={9}>{num(r.volume)}</N>
                <N size={9} color={T.t2}>{dec(r.unit)} ₽</N>
                <N size={9} color={T.t4}>{(r.discount ?? 0) * 100} %</N>
                <N size={9.5} bold>{rub(r.cost)}</N>
                <N size={9.5} bold color={T.accent}>{rub(r.cost * (1 + VAT))}</N>
              </div>
            ))}
            <div style={{ display: 'grid', gridTemplateColumns: PLACEMENT_COLS, gap: 8, alignItems: 'center', paddingTop: 5 }}>
              <span style={totalLabel}>Итого</span><span /><span /><span />
              <N size={9} bold>{num(tVol)}</N><span /><span />
              <N size={10} bold>{rub(tNet)}</N>
              <N size={10} bold color={T.accent}>{rub(tNet * (1 + VAT))}</N>
            </div>
          </Section>

          {/* ── ПРОГНОЗНЫЕ ПОКАЗАТЕЛИ (полный набор, 15 метрик) ─────── */}
          <Section title="Прогнозные показатели" meta="гарантируются показы и CPM" style={{ gap: 5 }}>
            <div style={{ display: 'grid', gridTemplateColumns: FORECAST_COLS, gap: 4, paddingBottom: 5, borderBottom: `1px solid ${T.border}`, ...colHead, fontSize: 7 }}>
              <span>Строка</span>
              {['Част.', 'Охват', 'Показы', 'CTR', 'Клики', 'CPM', 'CPC', 'CPU', 'CR', 'Чеки', 'CPO', 'Цена', 'Доход', 'ROI', 'SOV'].map(h => <span key={h} style={{ textAlign: 'right' }}>{h}</span>)}
            </div>
            {placements.map((r, i) => {
              const gross = r.cost * (1 + VAT);
              return (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: FORECAST_COLS, gap: 4, alignItems: 'center', padding: '2.5px 0', borderBottom: `1px solid ${T.row}` }}>
                  <span style={{ fontSize: 6, fontWeight: 600, lineHeight: 1.15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.position}</span>
                  <N size={6}>{fi(r.freq)}</N>
                  <N size={6}>{fi(r.reach)}</N>
                  <N size={6} bold>{fi(r.volume)}</N>
                  <N size={6}>{fp(sd(r.clicks, r.volume) * 100)}</N>
                  <N size={6} bold>{fi(r.clicks)}</N>
                  <N size={6} color={T.accent}>{fi(sd(r.cost, r.volume) * 1000)}</N>
                  <N size={6} color={T.accent}>{fi(sd(r.cost, r.clicks))}</N>
                  <N size={6} color={T.accent}>{fm(sd(r.cost, r.reach))}</N>
                  <N size={6}>{fp(sd(r.checks, r.clicks) * 100)}</N>
                  <N size={6} color={T.t2}>{fi(r.checks)}</N>
                  <N size={6} color={T.accent}>{fi(sd(r.cost, r.checks))}</N>
                  <N size={6} color={T.t2}>{fi(r.price)}</N>
                  <N size={6} color={T.income} bold>{fk(r.revenue)}</N>
                  <N size={6} bold color={(r.revenue - gross) >= 0 ? T.income : '#E5484D'}>{froi(r.revenue, gross)}</N>
                  <N size={6} color={T.t3}>{fp(r.sov)}</N>
                </div>
              );
            })}
            <div style={{ display: 'grid', gridTemplateColumns: FORECAST_COLS, gap: 4, alignItems: 'center', paddingTop: 5 }}>
              <span style={totalLabel}>Итого по МП</span>
              <N size={6} bold>{fi(maxFreq)}</N>
              <N size={6} bold>{fi(tReach)}</N>
              <N size={6} bold>{fi(tVol)}</N>
              <N size={6} bold>{fp(sd(tClicks, tVol) * 100)}</N>
              <N size={6} bold>{fi(tClicks)}</N>
              <N size={6} bold color={T.accent}>{fi(sd(tNet, tVol) * 1000)}</N>
              <N size={6} bold color={T.accent}>{fi(sd(tNet, tClicks))}</N>
              <N size={6} bold color={T.accent}>{fm(sd(tNet, tReach))}</N>
              <N size={6} bold>{fp(sd(tChecks, tClicks) * 100)}</N>
              <N size={6} bold>{fi(tChecks)}</N>
              <N size={6} bold color={T.accent}>{fi(sd(tNet, tChecks))}</N>
              <N size={6} bold color={T.t2}>{fi(sd(tRevenue, tChecks))}</N>
              <N size={6} bold color={T.income}>{fk(tRevenue)}</N>
              <N size={6} bold color={tRoi >= 0 ? T.income : '#E5484D'}>{froi(tRevenue, tGross)}</N>
              <N size={6} bold color={T.t3}>{fp(tSov)}</N>
            </div>
            <div style={{ background: T.tint, borderRadius: 9, padding: '7px 11px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 18px', marginTop: 2 }}>
              {aggRules.map(([metric, rule]) => (
                <span key={metric} style={{ fontSize: 8.5, color: T.t2, lineHeight: 1.35 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 8, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3 }}>{metric}</span> — {rule}
                </span>
              ))}
            </div>
          </Section>

          {/* ── ЦЕЛЕВЫЕ ПОКАЗАТЕЛИ (KPI приёмки) — только если заполнены ─ */}
          {hasGoals && (
            <Section title="Целевые показатели" meta="KPI, по которым принимается размещение">
              {/* равные колонки; заголовок 7px nowrap — так «Расхождение с Weborama» в одну строку без перекоса ширины */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,minmax(0,1fr))', gap: 9 }}>
                {GOALS_META.map(([k, label, hint]) => {
                  const v = (goals[k] ?? '').toString().trim();
                  return (
                    <div key={k} style={{ background: T.tint, borderRadius: 9, padding: '9px 10px', display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                      <span style={{ fontFamily: T.mono, fontSize: 7, letterSpacing: '.04em', textTransform: 'uppercase', color: T.t3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
                      <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.15, color: v ? T.t1 : T.t4 }}>{v || 'не задано'}</span>
                      <span style={{ fontSize: 8.5, color: T.t4, lineHeight: 1.25 }}>{hint}</span>
                    </div>
                  );
                })}
              </div>
            </Section>
          )}

          {/* ── ДОПОЛНИТЕЛЬНЫЕ УСЛУГИ ───────────────────────────────── */}
          {extras.length > 0 && (
            <Section title="Дополнительные услуги">
              {extras.map((e, i) => (
                <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '4px 0', borderTop: `1px solid ${T.row}` }}>
                  <span style={{ fontSize: 9.5, fontWeight: 600 }}>{e.name}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 8.5, color: T.t4 }}>{e.period}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9, color: T.t4, textDecoration: e.total < e.price ? 'line-through' : 'none' }}>{rub(e.price)}</span>
                  <N size={10} bold color={T.income}>{rub(e.total)}</N>
                </span>
              ))}
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingTop: 5 }}>
                <span style={totalLabel}>Итого доп. услуги</span>
                <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: T.income }}>{rub(extrasNet)}</span>
              </span>
              {bonusNote && <span style={{ fontSize: 8.5, color: T.t4, lineHeight: 1.4 }}>{bonusNote}</span>}
            </Section>
          )}

          {/* ── ТАРГЕТИНГ ───────────────────────────────────────────── */}
          <Section title="Таргетинг">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 22px' }}>
              {targeting.map(([group, value]) => (
                <span key={group} style={{ display: 'flex', gap: 10, padding: '3.5px 0', borderTop: `1px solid ${T.row}` }}>
                  <span style={{ flex: '0 0 70px', fontFamily: T.mono, fontSize: 8, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.45 }}>{group}</span>
                  <span style={{ fontSize: 9, color: T.t2, lineHeight: 1.35, textWrap: 'pretty' }}>{value || '—'}</span>
                </span>
              ))}
            </div>
          </Section>

          {/* ── ПРИМЕЧАНИЯ ──────────────────────────────────────────── */}
          <Section title="Примечания" style={{ paddingTop: 9, borderTop: `1px solid ${T.border}` }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '5px 18px' }}>
              {notes.map((text, i) => (
                <span key={i} style={{ display: 'flex', gap: 8 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 7.5, fontWeight: 700, color: T.t4, flex: '0 0 11px' }}>{i + 1}.</span>
                  <span style={{ fontSize: 7.5, color: T.t2, lineHeight: 1.3, textWrap: 'pretty' }}>{text}</span>
                </span>
              ))}
            </div>
          </Section>

         </div>
        </section>
      </div>
    </>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   ПЕЧАТНАЯ ГЕОМЕТРИЯ — не менять без пересчёта плотности
   (шрифты подключены глобально через styles/globals.css — @import не нужен)
   ══════════════════════════════════════════════════════════════════════ */
export const PRINT_CSS = `
.desk { background:#EBEEF6; min-height:100vh; padding:24px; display:flex; justify-content:center;
        font-family:${T.sans}; color:${T.t1}; -webkit-font-smoothing:antialiased }

.page {
  width:210mm; min-height:297mm; box-sizing:border-box;
  padding:30px 34px 20px;
  background:${T.paper};
  display:flex; flex-direction:column; gap:10px;
  box-shadow:0 4px 24px rgba(28,36,51,.12);
}

@page { size:A4 portrait; margin:0 }

@media print {
  .desk { background:none; padding:0; display:block }
  .page { width:auto; min-height:auto; height:297mm; box-shadow:none; page-break-after:avoid; overflow:hidden }
  .no-print { display:none !important }
  * { -webkit-print-color-adjust:exact; print-color-adjust:exact }
}
`;

/* ══════════════════════════════════════════════════════════════════════
   ЮРИДИЧЕСКИЙ ТЕКСТ (одинаков для всех МП, формулировки менять нельзя)
   ══════════════════════════════════════════════════════════════════════ */
export const AGG_RULES = [
  ['Охват', 'сумма по строкам, при пересечении аудиторий — с дедупликацией'],
  ['Показы / клики', 'сумма по строкам'],
  ['Частота', 'максимум по строкам, не сумма'],
  ['CTR', 'клики ÷ показы по итогу'],
  ['CPM / CPC / CPU', 'бюджет до НДС ÷ показы × 1000, ÷ клики, ÷ охват — по итогу'],
];
export const BONUS_NOTE = '* Бонусом при условии: от 500 000 ₽ до НДС на бренд в месяц при первом размещении бренда или при размещении от 1,5 млн ₽ до НДС в месяц на бренд.';
export const NOTES = [
  'При размещении по модели CPM (единица закупки — «1000 показов») гарантированы количество показов и стоимость за 1000 показов; остальные показатели прогнозные.',
  'Плановые значения основаны на данных и опыте команды; фактические результаты могут отличаться в обе стороны. Ответственность — только за ключевые параметры закупки (клики и CPC для CPC, показы и CPM для CPM).',
  'Дедлайн согласованных креативов под все форматы — не менее чем за 2 рабочих дня до старта; при нарушении срок старта не гарантируется.',
  'При изменении ключевых KPI и модели закупки после согласования медиаплан подлежит перерасчёту и повторному согласованию.',
  'KPI по CTR подтверждается при закупке по CPM и наличии всех форматов из медиаплана.',
  'Для оптимизации по постклик-показателям нужны доступы в веб-аналитику (Google Analytics, Яндекс Метрика) или ежедневные выгрузки.',
];

/* ══════════════════════════════════════════════════════════════════════
   SAMPLE — контракт данных / фолбэк
   ══════════════════════════════════════════════════════════════════════ */
export const SAMPLE = {
  header: {
    logo: '/assets/logo-mediaplan.svg',
    title: 'Медиаплан · Замбон / Анауран',
    subtitle: 'Simb-ad Альфарм / Таргет · movie360 · от 31.07.2026 · актуален 14 дней',
  },
  placementMeta: 'гео РФ · период месяц',
  params: [
    ['Агентство', 'movie360', false], ['Рекламодатель', 'Замбон', false],
    ['Бренд', 'Анауран', false], ['Название РК', 'Замбон Анауран', false],
    ['Период размещения', 'месяц', false], ['Дата старта', '31.07.2026', true],
    ['Гео', 'РФ', false], ['Место размещения', 'SIMB-AD', false],
  ],
  placements: [
    { position: 'Simb-ad Альфарм / Таргет', format: 'Banners', model: 'CPM', volume: 5357143, unit: 280, discount: 0, cost: 1500000.04, freq: 3, reach: 1785714, clicks: 64285.716 },
    { position: 'Simb-ad Альфарм / Лукалайк', format: 'Banners', model: 'CPM', volume: 2678571, unit: 280, discount: 0, cost: 750000.02, freq: 2, reach: 1071428, clicks: 32142.852 },
    { position: 'Simb-ad Альфарм / Ретаргет', format: 'Banners', model: 'CPM', volume: 1785714, unit: 280, discount: 0, cost: 500000.01, freq: 4, reach: 446428, clicks: 26785.71 },
  ],
  extras: [
    { name: 'Sales lift отчёт*', period: 'первый месяц размещения', price: 150000, total: 0 },
    { name: 'Brand lift исследование', period: 'по итогам кампании', price: 180000, total: 90000 },
  ],
  goals: { freq: '3', ctr: '1,20 %', cr: '0,35 %', volume: '2 927 400', weborama: 'до 10 %' },
  aggRules: AGG_RULES,
  bonusNote: BONUS_NOTE,
  targeting: [
    ['Аудитория', 'Ж/М 25–55 · гео РФ'],
    ['Покупают', 'ушные капли · препараты при отите'],
    ['Интересы', 'заболевания ЛОР-органов · здоровье семьи'],
    ['Поведение', 'сайты аптек · медицинские порталы'],
    ['Конкуренты', 'Отипакс · Отинум · Полидекса'],
  ],
  notes: NOTES,
};
