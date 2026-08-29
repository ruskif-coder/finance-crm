/**
 * Карточка сделки — новые стадии: медиаплан, ОРД, креативы, сверка.
 * Зависимость только React. Токены — из дизайн-системы финмодуля (design_system/ds.jsx).
 *
 * Все четыре секции сворачиваются; в свёрнутом виде отдают сводку.
 * Правая колонка (документы + ответственные) — на всю высоту карточки, не внутри секций.
 *
 * Вставлено дословно из дизайн-хендоффа (docs/карточка сделки со стадиями сборки.zip,
 * code/DealCard.jsx) — задача 9. Разрешены ровно три правки (см. отчёт по задаче):
 *   1. Токены T — значения заменены на var(--*) из styles/globals.css.
 *   2. STAGES → STAGES_FALLBACK: воронка стадий приходит снаружи (deal.stages),
 *      у проекта свой каталог (STAGE_CATALOG на бэкенде), а не одиннадцать стадий хендоффа.
 *   3. Счётчик документов уже читал docs.length, не захардкожен — правка не потребовалась.
 * Плюс одна точечная правка вне этого списка — маркер «ждёт» в OrdBody читал буквальный
 * хекс #D3D9E5 мимо таблицы T; используем T.dotWait (сама переменная --dot-wait была
 * заведена в globals.css уже в этом хендоффе, но не подключена в компоненте). Остальное —
 * без изменений, включая прочие найденные хардкод-хексы (TONE, плашка годового плана,
 * белый текст на кнопках) — они перечислены в отчёте, не в коде.
 */
import React, { useState } from 'react';

/* ── токены ─────────────────────────────────────────────────────────── */
export const T = {
  canvas: 'var(--bg-canvas)', card: 'var(--bg-card)', subtle: 'var(--bg-subtle)',
  tint: 'var(--bg-tint)', dim: 'var(--bg-dim)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)',
  hoverBorder: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)', t5: 'var(--text-disabled)',
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)', accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)', accentSoft: 'var(--accent-soft)',
  income: 'var(--income)', incomeFg: 'var(--income-fg)', incomeBg: 'var(--income-bg)', incomeBorder: 'var(--income-border)',
  warning: 'var(--warning)', warningFg: 'var(--warning-text)', warningBg: 'var(--warning-bg)', warningTint: 'var(--warning-tint)', warningBorder: 'var(--warning-border)',
  danger: 'var(--danger-fg)', dangerTint: 'var(--danger-tint)', dangerBorder: 'var(--danger-border)',
  violet: 'var(--mixed)',
  dotWait: 'var(--dot-wait)',
  shadow: '0 1px 3px rgba(28,36,51,.05), 0 4px 16px rgba(28,36,51,.04)',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};
const VAT = 0.22;

/* ── воронка стадий: приходит снаружи (deal.stages) ──────────────────
   У проекта свой каталог стадий (STAGE_CATALOG на бэкенде, /sales/directories/stage-catalog);
   держать вторую копию списка во фронте значило бы завести вторую правду о воронке.
   Этот список — только запасной вариант, если deal.stages не передали. */
export const STAGES_FALLBACK = ['Медиаплан', 'Бронь', 'Сбор запуска', 'Запуск',
  'Закрытие подготовка', 'Закрытие фактическое', 'Архив'];

/* ── формат ─────────────────────────────────────────────────────────── */
const nf = v => v.toLocaleString('ru-RU');
const rub = v => nf(v) + ' ₽';

/* ── примитивы ──────────────────────────────────────────────────────── */
const capTitle = { fontFamily: T.mono, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: T.t3 };
const meta = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };

const Card = ({ delay = 0, pad = '20px 24px 18px', gap = 12, children }) => (
  <section style={{
    background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 18,
    padding: pad, display: 'flex', flexDirection: 'column', gap,
    animation: `riseIn .4s ${T.ease} ${delay}s both`,
  }}>{children}</section>
);

/** Заголовок сворачиваемой секции: каретка ▾/▸ слева от капс-подписи. */
const SecHead = ({ title, note, open, onToggle, right }) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
    <span onClick={onToggle} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9, cursor: 'pointer' }}>
      <span style={{ fontSize: 10, color: T.t4 }}>{open ? '▾' : '▸'}</span>
      <span style={capTitle}>{title}</span>
    </span>
    {note && <span style={meta}>{note}</span>}
    {right}
  </div>
);

/** Нейтральная сводка (медиаплан): значения через вертикальные разделители. */
const BriefRow = ({ items }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap', animation: `popIn .2s ${T.ease} both` }}>
    {items.map((b, i) => (
      <span key={b.label} style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingLeft: i ? 16 : 0, borderLeft: i ? `1px solid ${T.inner}` : 'none' }}>
        <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, whiteSpace: 'nowrap' }}>{b.label}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontFamily: T.mono, fontSize: b.size ?? 16, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1, color: b.fg ?? T.t1, whiteSpace: 'nowrap' }}>{b.value}</span>
          {b.tag && <span style={{ display: 'inline-flex', alignItems: 'center', background: T.warningTint, color: T.warningFg, borderRadius: 6, padding: '2px 7px', fontFamily: T.mono, fontSize: 9, fontWeight: 700 }}>{b.tag}</span>}
        </span>
      </span>
    ))}
  </div>
);

/** Сводка со статусами (ОРД, креативы, сверка): плашка + галочка/!/точка. */
const TONE = {
  ok:   { bg: T.incomeBg, border: T.incomeBorder, labelFg: '#5C9E86', valueFg: T.incomeFg, mark: '✓', markBg: '#DCF1E8', markFg: T.income },
  todo: { bg: T.warningBg, border: T.warningBorder, labelFg: '#B99358', valueFg: T.warningFg, mark: '!', markBg: T.warningTint, markFg: T.warning },
  wait: { bg: '#F8F9FC', border: '#E7EBF7', labelFg: T.t4, valueFg: T.t3, mark: '·', markBg: T.inner, markFg: T.t4 },
};
export const brief = rows => rows.map(([label, value, tone]) => ({ ...TONE[tone], label, value }));

const StatusBrief = ({ items }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap', animation: `popIn .2s ${T.ease} both` }}>
    {items.map(b => (
      <span key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', background: b.bg, border: `1px solid ${b.border}`, borderRadius: 11 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 20, height: 20, borderRadius: 6, background: b.markBg, color: b.markFg, fontSize: 11, fontWeight: 700, flex: '0 0 20px' }}>{b.mark}</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: b.labelFg }}>{b.label}</span>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: b.valueFg, whiteSpace: 'nowrap' }}>{b.value}</span>
        </span>
      </span>
    ))}
  </div>
);

const IconBtn = ({ title, children, onClick }) => (
  <span className="dc-ghost" title={title} onClick={onClick} style={{
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28,
    background: T.card, border: `1px solid ${T.border}`, color: T.t2, borderRadius: 9, cursor: 'pointer',
  }}>{children}</span>
);
const PlusIcon = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>;
const OpenIcon = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M13 5h6v6" /><path d="M19 5l-8 8" /><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" /></svg>;
const DocIcon = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>;

/* ══════════════════════════════════════════════════════════════════════
   СТРАНИЦА
   ══════════════════════════════════════════════════════════════════════ */
export default function DealCard({ deal = DEMO, onChangeStage, onOpenPlan, onPickContract, onAddContract, onUpload }) {
  const [open, setOpen] = useState({ mp: true, ord: true, cr: true, rec: true });
  const toggle = k => setOpen(s => ({ ...s, [k]: !s[k] }));

  const { head, plan, mp, ord, creatives, rec, docs, owners } = deal;
  const stages = deal.stages || STAGES_FALLBACK;
  const current = head.stageIndex;

  /* деньги в шапке: единственная точка расчёта НДС */
  const money = [
    { label: 'Сумма сделки · с НДС · по медиаплану', value: rub(Math.round(mp.net * (1 + VAT))), size: 30, color: T.t1 },
    { label: 'Клиентская цена до НДС', value: rub(mp.net), size: 20, color: T.t1 },
    { label: 'НДС 22 %', value: rub(Math.round(mp.net * VAT)), size: 20, color: T.t2 },
    { label: 'Период размещения', value: mp.period, size: 20, color: T.t1 },
  ];

  return (
    <div style={{ minHeight: '100vh', boxSizing: 'border-box', padding: '26px 32px 40px', background: T.canvas, color: T.t1, fontFamily: T.sans, display: 'flex', justifyContent: 'center' }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes popIn { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
        .dc-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
        .dc-primary:hover { background:${T.accentHover} }
        .dc-row:hover { background:${T.subtle} }
      `}</style>

      <div style={{ width: '100%', maxWidth: 1180, display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* ── ШАПКА ─────────────────────────────────────────────────── */}
        <Card delay={0.07} pad="18px 24px 16px">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.accent }}>{head.id}</span>
            <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em' }}>{head.title}</span>
            <span style={meta}>{head.meta}</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 7, background: T.warningTint, color: T.warningFg, borderRadius: 9, padding: '5px 11px', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: T.warning }} />{stages[current]}
            </span>
          </div>

          {/* деньги + плашка годового плана справа */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 22, flexWrap: 'wrap', paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
            {money.map((m, i) => (
              <span key={m.label} style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingLeft: i ? 22 : 0, borderLeft: i ? `1px solid ${T.inner}` : 'none' }}>
                <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3, whiteSpace: 'nowrap' }}>{m.label}</span>
                <span style={{ fontFamily: T.mono, fontSize: m.size, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: m.color, whiteSpace: 'nowrap' }}>{m.value}</span>
              </span>
            ))}
            <span style={{
              marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 9, whiteSpace: 'nowrap',
              background: plan.linked ? T.tint : '#F8F9FC', border: `1px solid ${plan.linked ? T.accentBorder : '#E7EBF7'}`,
              borderRadius: 10, padding: '7px 10px 7px 12px',
            }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: plan.linked ? '#8F9BE8' : T.t4 }}>Годовой план</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: plan.linked ? T.t1 : T.t3 }}>
                  {plan.linked ? `${plan.name} · ${plan.note}` : 'не привязан'}
                </span>
              </span>
              <span className="dc-ghost" onClick={onOpenPlan} style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', background: T.card, border: `1px solid ${plan.linked ? T.accentBorder : T.border}`, color: T.accent, borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
                {plan.linked ? 'План →' : 'Привязать'}
              </span>
            </span>
          </div>

          {/* полоса стадий: пройденные светлые, текущая широкая и тёмная */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: '1 1 420px', minWidth: 0 }}>
              <span style={{ display: 'flex', gap: 3 }}>
                {stages.map((label, i) => (
                  <span key={label} title={`${i + 1}. ${label}${i < current ? ' — пройдено' : i === current ? ' — текущая' : ''}`}
                    style={{ flex: i === current ? 2.4 : 1, minWidth: 0, height: 8, borderRadius: 2, cursor: 'pointer',
                             background: i < current ? T.accentSoft : i === current ? T.accent : T.inner }} />
                ))}
              </span>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 9, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 }}>стадия {current + 1} из {stages.length}</span>
                <span style={{ fontSize: 12.5, fontWeight: 700 }}>{stages[current]}</span>
                <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4 }}>в стадии {head.daysInStage} дней · следующая: {stages[current + 1]}</span>
              </span>
            </span>
            <span className="dc-primary" onClick={onChangeStage} style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px', background: T.accent, color: 'var(--bg-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>Изменить стадию</span>
          </div>
        </Card>

        {/* ── ДВЕ КОЛОНКИ: секции слева, документы справа ────────────── */}
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>

            {/* МЕДИАПЛАН */}
            <Card delay={0.1}>
              <SecHead title="Медиаплан сделки" open={open.mp} onToggle={() => toggle('mp')}
                right={<span style={{ marginLeft: 'auto', ...meta }}>{mp.lines.length} строка · {rub(mp.net)} · черновик {mp.version}</span>} />
              {open.mp ? <MpBody mp={mp} /> : <BriefRow items={[
                { label: 'Услуга', value: mp.service },
                { label: 'Сумма до НДС', value: rub(mp.net), size: 18 },
                { label: 'С НДС', value: rub(Math.round(mp.net * (1 + VAT))), size: 18, fg: T.accent },
                { label: 'Показы по прогнозу', value: nf(mp.impressions), fg: T.income },
                { label: 'Период РК', value: mp.flight },
                { label: 'Версия', value: mp.version, fg: T.warningFg, tag: 'черновик' },
              ]} />}
            </Card>

            {/* ОРД */}
            <Card delay={0.14}>
              <SecHead title="ОРД" note="цепочка договоров и ЕРИД" open={open.ord} onToggle={() => toggle('ord')}
                right={<span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 9 }}>
                  <span style={{ display: 'flex', gap: 2 }}>
                    {ord.map(o => <span key={o.label} title={`${o.label} — ${o.state}`} style={{ width: 18, height: 7, borderRadius: 2, background: o.state === 'done' ? T.income : o.state === 'todo' ? T.warning : T.inner }} />)}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: ord.every(o => o.state === 'done') ? T.income : T.warning }}>
                    {ord.filter(o => o.state === 'done').length} из {ord.length}
                  </span>
                </span>} />
              {open.ord
                ? <OrdBody ord={ord} onPickContract={onPickContract} onAddContract={onAddContract} />
                : <StatusBrief items={brief(ord.map(o => [o.label, o.briefValue, o.state]))} />}
            </Card>

            {/* КРЕАТИВЫ */}
            <Card delay={0.21}>
              <SecHead title="Креативы" note={`${creatives.rows.length} комплекта · ${creatives.files} файлов · ЕРИД ${creatives.erid}`} open={open.cr} onToggle={() => toggle('cr')}
                right={<span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>дедлайн подачи {creatives.deadline}</span>
                  <span className="dc-ghost" onClick={() => onUpload?.('creatives')} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 12px', background: T.card, border: `1px solid ${T.accentBorder}`, color: T.accent, borderRadius: 9, fontSize: 11.5, fontWeight: 700, cursor: 'pointer' }}><PlusIcon />Комплект</span>
                </span>} />
              {open.cr
                ? <CreativesBody creatives={creatives} />
                : <StatusBrief items={brief([
                    ['Комплектов', String(creatives.rows.length), 'ok'],
                    ['Файлов', String(creatives.files), creatives.files ? 'ok' : 'wait'],
                    ['Принято', `${creatives.accepted} из ${creatives.rows.length}`, creatives.accepted === creatives.rows.length ? 'ok' : 'todo'],
                    ['ЕРИД', `${creatives.erid} из ${creatives.rows.length}`, creatives.erid === creatives.rows.length ? 'ok' : 'wait'],
                    ['Дедлайн', creatives.deadline, 'ok'],
                  ])} />}
            </Card>

            {/* СВЕРКА */}
            <Card delay={0.28}>
              <SecHead title="Сверка" note="план медиаплана против факта площадок" open={open.rec} onToggle={() => toggle('rec')}
                right={<span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span className="dc-ghost" style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 9, fontSize: 11.5, fontWeight: 600, color: T.t2, cursor: 'pointer' }}>Обновить факт</span>
                  <span className="dc-primary" style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', background: T.accent, color: 'var(--bg-card)', borderRadius: 9, fontSize: 11.5, fontWeight: 700, cursor: 'pointer' }}>Свести сверку</span>
                </span>} />
              {open.rec ? <RecBody rec={rec} /> : <StatusBrief items={brief([
                ['Выполнение', rec.totalPct.toFixed(0) + ' %', rec.totalPct >= 97 ? 'ok' : 'todo'],
                ['Факт показов', nf(rec.totalFact), 'ok'],
                ['К оплате', rub(rec.totalSum), 'ok'],
                ['УПД', 'не выставлен', 'todo'],
              ])} />}
            </Card>
          </div>

          {/* ── ПРАВАЯ КОЛОНКА ──────────────────────────────────────── */}
          <div style={{ flex: '0 0 clamp(230px, 25%, 320px)', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14, boxSizing: 'border-box' }}>
            <Card delay={0.14} pad="18px 18px 16px" gap={8}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={capTitle}>Документы</span>
                <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: T.accent }}>
                  {docs.filter(d => d.ready).length} из {docs.length}
                </span>
              </div>
              {docs.map(d => (
                <span key={d.label} className="dc-ghost" style={{
                  display: 'flex', alignItems: 'center', gap: 9, padding: '9px 10px', minWidth: 0, cursor: 'pointer',
                  background: d.ready ? T.card : T.dim, border: `1px solid ${d.ready ? T.border : T.inner}`, borderRadius: 11,
                }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: 7, background: d.ready ? T.accentTint : T.subtle, color: d.ready ? T.accent : T.t5, flex: '0 0 24px' }}><DocIcon /></span>
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: d.ready ? T.t1 : T.t3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.label}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.note}</span>
                  </span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 4, flex: '0 0 auto' }}>
                    {(d.tags ?? []).map(t => (
                      <span key={t} style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 7px', background: T.card, border: `1px solid ${T.accentBorder}`, color: T.accent, borderRadius: 6, fontFamily: T.mono, fontSize: 9, fontWeight: 700 }}>{t}</span>
                    ))}
                    {d.action && <span onClick={() => onUpload?.(d.label)} style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 9px', background: T.card, border: `1px solid ${T.border}`, color: T.accent, borderRadius: 7, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{d.action}</span>}
                  </span>
                </span>
              ))}
            </Card>

            <Card delay={0.21} pad="18px 18px 16px" gap={6}>
              <span style={capTitle}>Ответственные</span>
              {owners.map(o => (
                <span key={o.role} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderTop: `1px solid ${T.row}` }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, borderRadius: 10, background: o.bg, color: o.fg, fontSize: 11, fontWeight: 700, flex: '0 0 30px' }}>{o.initials}</span>
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: o.name === 'не назначен' ? T.t4 : T.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.name}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{o.role}</span>
                  </span>
                </span>
              ))}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── тело медиаплана ────────────────────────────────────────────────── */
const MP_COLS = 'minmax(120px,1.5fr) 92px 62px minmax(96px,1fr) 84px 60px minmax(96px,1.05fr) minmax(96px,1.05fr)';
const FC_COLS = '2.2fr repeat(8,1fr)';

function MpBody({ mp }) {
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ ...capTitle, fontSize: 9 }}>Параметры кампании</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 }}>старт — стоп РК</span>
          <input type="date" defaultValue={mp.start} style={dateStyle} />
          <span style={{ color: T.hoverBorder }}>→</span>
          <input type="date" defaultValue={mp.end} style={dateStyle} />
          <a href="#mp" style={{ fontSize: 12, fontWeight: 600, color: T.accent, textDecoration: 'none' }}>Открыть МП →</a>
        </span>
      </div>

      {/* 6 полей: 2 колонки × 3 строки, порядок ПО КОЛОНКАМ */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: 'repeat(3,auto)', gridAutoFlow: 'column', columnGap: 28 }}>
        {mp.params.map(([label, value]) => (
          <span key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderTop: `1px solid ${T.row}`, minWidth: 0 }}>
            <span style={{ fontSize: 12, color: T.t3, whiteSpace: 'nowrap' }}>{label}</span>
            <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, color: value === '—' ? T.t4 : T.t1, textAlign: 'right' }}>{value}</span>
          </span>
        ))}
      </div>

      <Table title="Размещение" cols={MP_COLS}
        head={['Позиция', 'Формат', 'Модель', 'Объём', 'Цена/ед.', 'Скидка', 'До НДС', 'С НДС']}
        rightAlignFrom={3}>
        {mp.lines.map(l => (
          <div key={l.position} style={{ display: 'grid', gridTemplateColumns: MP_COLS, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: `1px solid ${T.row}` }}>
            <span style={{ fontSize: 11.5, fontWeight: 600 }}>{l.position}</span>
            <span style={{ fontSize: 11, color: T.t2 }}>{l.format}</span>
            <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: T.accent }}>{l.model}</span>
            <span style={{ fontFamily: T.mono, fontSize: 11, textAlign: 'right' }}>{nf(l.volume)}</span>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t2, textAlign: 'right' }}>{l.unit.toFixed(2).replace('.', ',')} ₽</span>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t4, textAlign: 'right' }}>{l.discount} %</span>
            <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{rub(l.net)}</span>
            <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: T.accent, textAlign: 'right' }}>{rub(Math.round(l.net * (1 + VAT)))}</span>
          </div>
        ))}
      </Table>

      <Table title="Прогнозные показатели" note="гарантируются показы и CPM" cols={FC_COLS}
        head={['Строка', 'Частота', 'Охват', 'Показы', 'CTR', 'Клики', 'CPM', 'CPC', 'CPU']} rightAlignFrom={1}>
        {mp.forecast.map(f => (
          <div key={f.name} style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 9, alignItems: 'center', padding: '6px 0' }}>
            <span style={{ fontSize: 11.5, fontWeight: 600 }}>{f.name}</span>
            {[f.freq, nf(f.reach), nf(f.imp), f.ctr, nf(f.clicks), f.cpm, f.cpc, f.cpu].map((v, i) => (
              <span key={i} style={{ fontFamily: T.mono, fontSize: 11, fontWeight: i === 1 || i === 3 ? 700 : 400, textAlign: 'right', color: i === 1 || i === 3 ? T.income : i >= 5 ? T.accent : T.t1 }}>{v}</span>
            ))}
          </div>
        ))}
      </Table>
    </>
  );
}
const dateStyle = { height: 30, boxSizing: 'border-box', padding: '0 9px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 9, fontFamily: T.mono, fontSize: 11.5, fontWeight: 600, color: T.t1, outline: 'none', cursor: 'pointer' };

const Table = ({ title, note, cols, head, rightAlignFrom = 99, children }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
      <span style={{ ...capTitle, fontSize: 9 }}>{title}</span>
      {note && <span style={meta}>{note}</span>}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 9, paddingBottom: 7, borderBottom: `1px solid ${T.border}`, ...colHead }}>
      {head.map((h, i) => <span key={h} style={{ textAlign: i >= rightAlignFrom ? 'right' : 'left' }}>{h}</span>)}
    </div>
    {children}
  </div>
);

/* ── тело ОРД ───────────────────────────────────────────────────────── */
function OrdBody({ ord, onPickContract, onAddContract }) {
  return (
    <>
      {ord.map(o => {
        const l = o.label.split(' ');
        const dot = o.state === 'done' ? T.income : o.state === 'todo' ? T.warning : T.dotWait;
        const valueFg = o.state === 'done' ? T.t1 : o.state === 'todo' ? T.warningFg : T.t4;
        return (
          /* 4 колонки: маркер · лейбл в 2 строки · значение и подсказка · действия */
          <div key={o.label} style={{ display: 'grid', gridTemplateColumns: '14px 108px minmax(0,1fr) auto', gap: 12, alignItems: 'baseline', padding: '8px 0', borderTop: `1px solid ${T.row}` }}>
            <span title={o.state === 'done' ? 'готово' : o.state === 'todo' ? 'в работе' : 'ждёт'} style={{ width: 8, height: 8, borderRadius: 2, background: dot, alignSelf: 'center' }} />
            <span style={{ display: 'flex', flexDirection: 'column', fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.35 }}>
              <span>{l[0]}</span>{l.length > 1 && <span>{l.slice(1).join(' ')}</span>}
            </span>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
              <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: valueFg }}>{o.value}</span>
                {o.meta && <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4 }}>{o.meta}</span>}
                {o.fill && <FillBadge fill={o.fill} />}
              </span>
              <span style={{ fontSize: 11, color: o.state === 'lock' ? T.t4 : T.t2, lineHeight: 1.4, textWrap: 'pretty' }}>{o.hint}</span>
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flex: '0 0 auto' }}>
              {o.action && <span className="dc-primary" onClick={onPickContract} style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 13px', background: T.accent, color: 'var(--bg-card)', borderRadius: 9, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>{o.action}</span>}
              {o.canAdd && <IconBtn title="Добавить договор в реестр" onClick={onAddContract}><PlusIcon /></IconBtn>}
              {o.canOpen && <IconBtn title={o.openTitle}><OpenIcon /></IconBtn>}
            </span>
          </div>
        );
      })}
    </>
  );
}

/** Заполненность карточки договора в реестре: пиксельная шкала + призыв дозаполнить. */
const FillBadge = ({ fill }) => {
  const [ok, total, missing] = fill;
  const full = ok === total;
  const c = full ? T.income : T.warning;
  return (
    <span title={full ? 'Карточка договора в реестре заполнена полностью' : `В реестре не заполнено: ${missing} — без них ЕРИД не выпустить`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: full ? T.incomeBg : T.warningBg, color: full ? T.incomeFg : T.warningFg, border: `1px solid ${full ? T.incomeBorder : T.warningBorder}`, borderRadius: 6, padding: '2px 7px', fontFamily: T.mono, fontSize: 9, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>
      <span style={{ display: 'inline-flex', gap: 1 }}>
        {Array.from({ length: total }, (_, k) => <span key={k} style={{ width: 4, height: 7, borderRadius: 1, background: k < ok ? c : T.inner }} />)}
      </span>
      {full ? 'карточка заполнена' : `дозаполнить ${total - ok}`}
    </span>
  );
};

/* ── тело креативов ─────────────────────────────────────────────────── */
const CR_COLS = 'minmax(160px,1.35fr) minmax(140px,1.1fr) 64px 108px minmax(130px,1fr) 108px';
const CR_ST = {
  'принято':     [T.incomeBg, T.incomeFg, T.incomeBorder, 'Открыть'],
  'на проверке': [T.accentTint, T.accent, T.accentBorder, 'Напомнить'],
  'правки':      [T.dangerTint, T.danger, T.dangerBorder, 'Причина'],
  'нет файлов':  [T.subtle, T.t4, T.inner, 'Загрузить'],
};

function CreativesBody({ creatives }) {
  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 820, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: CR_COLS, gap: 12, padding: '0 8px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
            <span>Площадка</span><span>Формат</span><span style={{ textAlign: 'right' }}>Файлов</span><span>Проверка</span><span>ЕРИД</span><span style={{ textAlign: 'right' }}>Действие</span>
          </div>
          {creatives.rows.map(c => {
            const [bg, fg, border, action] = CR_ST[c.status];
            const empty = c.files === 0;
            return (
              <div key={c.site} className="dc-row" style={{ display: 'grid', gridTemplateColumns: CR_COLS, gap: 12, alignItems: 'center', padding: '9px 8px', borderRadius: 10, borderBottom: `1px solid ${T.row}`, cursor: 'pointer' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ width: 7, height: 7, borderRadius: 2, background: c.dot, flex: '0 0 7px' }} />
                  <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.site}</span>
                </span>
                <span style={{ fontSize: 11.5, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.format}</span>
                <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: c.files ? T.t1 : T.t5, textAlign: 'right' }}>{c.files || '—'}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: bg, color: fg, border: `1px solid ${border}`, borderRadius: 7, padding: '3px 0', fontSize: 10.5, fontWeight: 700 }}>{c.status}</span>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: c.erid ? T.accent : T.t5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.erid || '—'}</span>
                <span style={{ display: 'inline-flex', justifyContent: 'flex-end' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', background: empty ? T.accent : T.card, border: `1px solid ${empty ? T.accent : T.border}`, color: empty ? 'var(--bg-card)' : T.t2, borderRadius: 8, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>{action}</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {creatives.erid < creatives.rows.length && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 9, background: T.warningTint, borderRadius: 11, padding: '10px 13px' }}>
          <span style={{ width: 7, height: 7, borderRadius: 2, background: T.warning, flex: '0 0 7px' }} />
          <span style={{ fontSize: 11.5, color: T.warningFg, lineHeight: 1.4 }}>{creatives.blockNote}</span>
        </span>
      )}
    </>
  );
}

/* ── тело сверки ────────────────────────────────────────────────────── */
const REC_COLS = 'minmax(170px,1.3fr) 116px 116px 104px minmax(150px,1fr) 116px';

function RecBody({ rec }) {
  const pctColor = v => (v >= 97 ? T.income : v >= 90 ? T.warning : T.danger);
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 22, flexWrap: 'wrap', padding: '12px 0', borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}` }}>
        {rec.kpi.map((k, i) => (
          <span key={k.label} style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingLeft: i ? 22 : 0, borderLeft: i ? `1px solid ${T.inner}` : 'none' }}>
            <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 }}>{k.label}</span>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontFamily: T.mono, fontSize: 24, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: k.color, whiteSpace: 'nowrap' }}>{k.value}</span>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: T.t3 }}>{k.unit}</span>
            </span>
            <span style={{ fontSize: 11, color: T.t4 }}>{k.hint}</span>
          </span>
        ))}
      </div>

      {/* таблица слева, документы периода — колонкой справа */}
      <div style={{ display: 'flex', gap: 18, alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 0', minWidth: 0, overflowX: 'auto' }}>
          <div style={{ minWidth: 660, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'grid', gridTemplateColumns: REC_COLS, gap: 12, padding: '0 8px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
              <span>Площадка</span><span style={{ textAlign: 'right' }}>План показов</span><span style={{ textAlign: 'right' }}>Факт</span><span style={{ textAlign: 'right' }}>Δ</span><span>Выполнение</span><span style={{ textAlign: 'right' }}>К оплате</span>
            </div>
            {rec.rows.map(r => {
              const pct = r.fact / r.plan * 100;
              const delta = r.fact - r.plan;
              return (
                <div key={r.site} style={{ display: 'grid', gridTemplateColumns: REC_COLS, gap: 12, alignItems: 'center', padding: '9px 8px', borderRadius: 10, borderBottom: `1px solid ${T.row}` }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: r.dot, flex: '0 0 7px' }} />
                    <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.site}</span>
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 11.5, color: T.t2, textAlign: 'right' }}>{nf(r.plan)}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{nf(r.fact)}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: delta >= 0 ? T.income : T.danger, textAlign: 'right' }}>{(delta >= 0 ? '+' : '−') + nf(Math.abs(delta))}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ flex: '1 1 auto', minWidth: 40, display: 'block', height: 7, borderRadius: 3, background: T.inner, overflow: 'hidden' }}>
                      <span style={{ display: 'block', height: 7, width: Math.min(100, pct) + '%', borderRadius: 3, background: pctColor(pct) }} />
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: pctColor(pct), flex: '0 0 42px', textAlign: 'right' }}>{pct.toFixed(0)} %</span>
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{rub(Math.round(r.fact / 1000 * r.cpm))}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   ДЕМО-ДАННЫЕ — контракт с API
   ══════════════════════════════════════════════════════════════════════ */
export const DEMO = {
  head: { id: '6JT5U9', title: 'BEIERSDORF · Eucerin', meta: 'ОККАМ · еФарм · 2026-05', stageIndex: 2, daysInStage: 6 },
  plan: { linked: true, name: 'BEIERSDORF · 2026', note: 'тестовый план · мес. 5' },
  mp: {
    net: 500000, version: 'v1', service: 'еФарм', period: '2026-05', flight: '01.05 — 31.05',
    start: '2026-05-01', end: '2026-05-31', impressions: 1111111111,
    params: [
      ['Агентство', 'OKKAM'], ['Рекламодатель', 'BEIERSDORF'], ['Бренд', 'Eucerin'],
      ['Контрагент', 'САЙТСИНГ ООО'], ['Период размещения', 'месяц · 2026-05'], ['Гео', '—'],
    ],
    lines: [{ position: 'еФарм', format: 'Banners', model: 'CPM', volume: 1111111111, unit: 450, discount: 0, net: 500000 }],
    forecast: [{ name: 'еФарм', freq: '2', reach: 555556, imp: 1111111111, ctr: '2,00 %', clicks: 22222, cpm: '450,00 ₽', cpc: '22,50 ₽', cpu: '0,90 ₽' }],
  },
  /* ОРД: четыре звена цепочки; fill — заполненность карточки договора в реестре */
  ord: [
    { label: 'Плательщик', state: 'done', value: 'САЙТСИНГ ООО', briefValue: 'САЙТСИНГ ООО',
      hint: 'сопоставлен со справочником контрагентов', canOpen: true, openTitle: 'Открыть карточку контрагента' },
    { label: 'Доходный договор', state: 'done', value: 'РМ-01-08-23', briefValue: 'РМ-01-08-23',
      meta: 'от 2023-08-01', hint: 'единственный договор плательщика с отметкой ОРД, от 01.08.2023',
      fill: [3, 5, 'ИНН плательщика, дата подписания'], canAdd: true, canOpen: true, openTitle: 'Открыть договор в реестре' },
    { label: 'Изначальный договор', state: 'todo', value: 'не выбран', briefValue: 'выбрать из 7',
      meta: '7 вариантов', hint: 'под РМ-01-08-23 подходящих договоров 7, прошлых сборок не было',
      fill: [0, 5, 'договор не выбран'], action: 'Выбрать из 7', canAdd: true, canOpen: true, openTitle: 'Показать подходящие договоры' },
    { label: 'Креативы и ЕРИД', state: 'lock', value: 'ждёт цепочку', briefValue: 'не выпущен',
      hint: 'откроется, когда договорная обвязка сойдётся' },
  ],
  creatives: {
    deadline: '28.04.2026', files: 6, accepted: 1, erid: 1,
    blockNote: 'ЕРИД выпускается только после сборки цепочки ОРД — сейчас не выбран изначальный договор. Дедлайн подачи креативов 28.04, за 3 рабочих дня до старта.',
    rows: [
      { site: 'еФарм · главная', format: '1080×607, 2 макета', files: 2, status: 'принято', erid: 'ERID-2Vf n1x8Bq', dot: 'var(--accent)' },
      { site: 'еФарм · каталог', format: '640×360, 1 макет', files: 1, status: 'на проверке', erid: '', dot: 'var(--accent)' },
      { site: 'Аптечество · APP', format: '1080×1080, 3 макета', files: 3, status: 'правки', erid: '', dot: 'var(--warning)' },
      { site: '366.ru · главная', format: 'не загружено', files: 0, status: 'нет файлов', erid: '', dot: 'var(--income)' },
    ],
  },
  rec: {
    totalFact: 1079600, totalPct: 98.1, totalSum: 478905,
    rows: [
      { site: 'еФарм · главная', plan: 720000, fact: 706400, cpm: 450, dot: 'var(--accent)' },
      { site: 'еФарм · каталог', plan: 291111, fact: 268900, cpm: 450, dot: 'var(--accent)' },
      { site: 'Аптечество · APP', plan: 100000, fact: 104300, cpm: 380, dot: 'var(--warning)' },
    ],
    kpi: [
      { label: 'Выполнение плана', value: '98', unit: '%', hint: 'по показам', color: 'var(--income)' },
      { label: 'К оплате по факту', value: '0,48', unit: 'млн ₽', hint: 'до НДС', color: 'var(--text-primary)' },
      { label: 'Отклонение от МП', value: '−21', unit: 'тыс ₽', hint: 'план 500 000 ₽', color: 'var(--danger-fg)' },
      { label: 'Недокрут', value: '2', unit: '%', hint: '1 площадка ниже 95 %', color: 'var(--warning)' },
    ],
  },
  docs: [
    { label: 'Медиаплан', note: 'v1 · черновик', ready: true, tags: ['PDF', 'XLS'] },
    { label: 'Договор', note: 'из Битрикса — нет', ready: false },
    { label: 'МП (Битрикс)', note: 'из Битрикса — нет', ready: false },
    { label: 'Доп. соглашение', note: 'не загружен', ready: false, action: 'Загрузить' },
    { label: 'Креативы', note: 'не загружены', ready: false, action: 'Загрузить' },
    { label: 'Счёт', note: 'не выставлен', ready: false, action: 'Создать' },
    { label: 'УПД', note: 'не выставлен', ready: false, action: 'Создать' },
    { label: 'Отчёт', note: 'не загружен', ready: false, action: 'Загрузить' },
    { label: 'Акт', note: 'не загружен', ready: false, action: 'Загрузить' },
  ],
  owners: [
    { name: 'Лидген S.', role: 'продавец', initials: 'ЛS', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
    { name: 'Ксения Ж.', role: 'аккаунт', initials: 'КЖ', bg: 'var(--income-tint)', fg: 'var(--income-fg)' },
    { name: 'не назначен', role: 'трафик', initials: '—', bg: 'var(--bg-subtle)', fg: 'var(--text-disabled)' },
  ],
};
