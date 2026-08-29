/**
 * Карточка контрагента — десктоп (≥1024px).
 * Единственная зависимость — React. Стили инлайновые + один <style> для
 * шрифтов, keyframes и hover-состояний. Данные передаются пропом `data`
 * (форма — см. sampleData.js), пока бэкенда нет — используется он же.
 */
import React, { useState } from 'react';

/* ── токены ─────────────────────────────────────────────────────────── */
export const T = {
  canvas: 'var(--bg-canvas)', card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', pick: 'var(--accent-tint)', tipBg: 'var(--bg-tint)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)', hoverBorder: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)',
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)', accentTint: 'var(--accent-tint)',
  income: 'var(--income)', incomeTint: 'var(--income-tint)', expense: 'var(--bank-sovkom)',
  warning: 'var(--warning)', warningTint: 'var(--warning-tint)', warningText: 'var(--warning-text)',
  danger: 'var(--danger-fg)', dangerTint: 'var(--danger-tint)', mixed: 'var(--mixed)', mixedTint: 'var(--mixed-tint)',
  shadow: '0 1px 3px rgba(28,36,51,.05), 0 4px 16px rgba(28,36,51,.04)',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};

const card = (delay = 0) => ({
  background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow,
  borderRadius: 18, display: 'flex', flexDirection: 'column',
  animation: `riseIn .4s ${T.ease} ${delay}s both`,
});
const capTitle = {
  fontFamily: T.mono, fontSize: 11, letterSpacing: '.08em',
  textTransform: 'uppercase', fontWeight: 700, color: T.t3,
};
const colHead = {
  fontFamily: T.mono, fontSize: 10, letterSpacing: '.08em',
  textTransform: 'uppercase', color: T.t4,
};
const h2 = { fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em' };

const rub = v => v.toLocaleString('ru-RU') + ' ₽';
const mln = v => v.toFixed(2).replace('.', ',') + ' млн ₽';

/* ── мелкие блоки ───────────────────────────────────────────────────── */
const Dot = ({ color, size = 8 }) => (
  <span style={{ width: size, height: size, borderRadius: 2, background: color, flex: `0 0 ${size}px` }} />
);

const KeyRow = ({ label, value, mono, color }) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '8px 0', borderTop: `1px solid ${T.row}` }}>
    <span style={{ fontSize: 12, color: T.t3, whiteSpace: 'nowrap' }}>{label}</span>
    <span style={{
      marginLeft: 'auto', fontFamily: mono ? T.mono : T.sans, fontSize: 12, fontWeight: 600,
      color: color || (value === '—' ? T.t4 : T.t1), textAlign: 'right', lineHeight: 1.4,
    }}>{value}</span>
  </div>
);

const Chip = ({ children, bg, fg, bordered }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: 6,
    background: bg || T.card, color: fg || T.t2,
    border: bordered ? `1px solid ${T.border}` : 'none',
    borderRadius: 8, padding: '4px 10px', fontSize: bordered ? 12 : 11, fontWeight: bordered ? 600 : 700,
  }}>{children}</span>
);

const PencilIcon = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 20h4l10-10-4-4L4 16v4z" /><path d="M14.5 5.5l4 4" />
  </svg>
);
const CopyIcon = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" />
  </svg>
);
const IconBtn = ({ onClick, title, color, children }) => (
  <span className="cc-ghost" onClick={onClick} title={title} style={{
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 28, height: 28, border: `1px solid ${T.border}`, borderRadius: 9,
    color: color || T.t2, cursor: 'pointer', flex: '0 0 28px',
  }}>{children}</span>
);

/* ── пиксельные бары (язык ДДС) ─────────────────────────────────────── */
const ROWS = 10;
function cells(value, color, topDown, maxMln) {
  const filled = Math.max(value > 0 ? 1 : 0, Math.round((value / maxMln) * ROWS));
  return Array.from({ length: ROWS }, (_, i) => {
    const rank = topDown ? ROWS - i : i + 1;
    return rank <= filled ? color : T.inner;
  });
}

function TurnoverChart({ months, income, expense }) {
  const [sel, setSel] = useState(null);
  // шкала = максимум ряда + 20% (иначе на малых объёмах бары пустые)
  const maxMln = Math.max(0.001, ...income, ...expense) * 1.2;
  const tip = sel == null
    ? { title: 'нажмите на столбец', inTxt: '', outTxt: '' }
    : { title: months[sel], inTxt: '+' + mln(income[sel]), outTxt: '−' + mln(expense[sel]) };

  return (
    <>
      <div style={{
        background: T.tipBg, borderRadius: 12, padding: '11px 14px', display: 'flex',
        alignItems: 'center', gap: 12, minHeight: 44, boxSizing: 'border-box',
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: T.t2 }}>{tip.title}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 16 }}>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.income }}>{tip.inTxt}</span>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.t2 }}>{tip.outTxt}</span>
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 3, alignItems: 'stretch' }}>
          {months.map((m, i) => (
            <button key={m} type="button" onClick={() => setSel(i)}
              aria-label={`${m}: приход ${mln(income[i])}, расход ${mln(expense[i])}`}
              style={{
                flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4,
                padding: '3px 0', borderRadius: 5, border: 'none', cursor: 'pointer',
                background: sel === i ? T.pick : 'transparent',
                transition: 'background-color 150ms ease',
              }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {cells(income[i], T.income, true, maxMln).map((bg, k) => (
                  <span key={k} style={{ height: 6, borderRadius: 2, background: bg }} />
                ))}
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {cells(expense[i], T.expense, false, maxMln).map((bg, k) => (
                  <span key={k} style={{ height: 6, borderRadius: 2, background: bg }} />
                ))}
              </span>
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 3, fontFamily: T.mono, fontSize: 9, color: T.t4 }}>
          {months.map((m, i) => (
            <span key={m} style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>{i % 3 === 0 ? m : ''}</span>
          ))}
        </div>
      </div>
    </>
  );
}

/* ── сетки таблиц ───────────────────────────────────────────────────── */
const CONTRACT_COLS = '1.2fr 90px 1fr 90px 90px 130px 80px';
const OPS_COLS = '88px 118px 90px 108px 108px 96px 84px 1fr 74px 74px 92px';

/* ── страница ───────────────────────────────────────────────────────── */
// ops* — управление таблицей операций. Пришло из хендоффа декоративным (чипы и
// заголовки колонок были простыми span без обработчиков), поэтому сортировка и фильтры
// не работали, хотя страница уже умела их грузить. Теперь состояние живёт на странице,
// а компонент только зовёт колбэки.
export default function CounterpartyCard({ data, onBack, onEdit, onEditTerms, onCopyRequisites, onOpenContracts, copied, canEdit = true,
                                           opsStatus = '', opsSortCol = 'date', opsSortDir = 'desc',
                                           onOpsStatus, onOpsSortCol, onOpsSortDir, onOpsMore, opsLoading = false }) {
  const { name, state, kind, site, brands, requisites, banks, belonging, terms,
          kpi, turnover, stats, topItems, byStatus, contracts, ops, opsTotal } = data;

  // Клик по заголовку: та же колонка — переворачиваем направление, другая — берём её.
  const headProps = {
    sortCol: opsSortCol, sortDir: opsSortDir,
    onPick: (col) => {
      if (col === opsSortCol) onOpsSortDir?.(opsSortDir === 'asc' ? 'desc' : 'asc')
      else onOpsSortCol?.(col)
    },
  };

  return (
    <div style={{
      minHeight: '100vh', boxSizing: 'border-box', padding: '26px 32px 40px',
      background: T.canvas, color: T.t1, fontFamily: T.sans,
      display: 'flex', flexDirection: 'column', gap: 16,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
        .cc-row:hover { background:${T.subtle} }
        .cc-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
        .cc-primary:hover { background:${T.accentHover} }
        .cc-link:hover { color:${T.accent} }
        .cc-scroll { overflow-x:auto }
      `}</style>

      {/* Хлебные крошки */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', animation: `riseIn .4s ${T.ease} both` }}>
        <span className="cc-link" onClick={onBack} style={{ fontSize: 13, fontWeight: 600, color: T.t3, cursor: 'pointer' }}>← Контрагенты</span>
        <span style={{ color: T.hoverBorder }}>/</span>
        <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', paddingRight: 2 }}>{name}</span>
        <Chip bg={T.incomeTint} fg={T.income}>{state}</Chip>
        <Chip bg={T.mixedTint} fg={T.mixed}>{kind}</Chip>
        {site && <span className="cc-ghost" style={{
          display: 'inline-flex', alignItems: 'center', background: T.card, border: `1px solid ${T.border}`,
          borderRadius: 8, padding: '4px 10px', fontSize: 12, fontWeight: 600, color: T.accent, cursor: 'pointer',
        }}>{site}</span>}
        {brands.map(b => <Chip key={b} bordered>{b}</Chip>)}
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>

        {/* ЛЕВАЯ КОЛОНКА 340px */}
        <div style={{ width: 340, flex: '0 0 340px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          <section style={{ ...card(0.07), padding: '20px 22px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 8 }}>
              <span style={capTitle}>Реквизиты</span>
              <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                <IconBtn onClick={onCopyRequisites} title={copied ? 'Скопировано' : 'Копировать реквизиты'} color={copied ? T.income : T.t2}><CopyIcon /></IconBtn>
                {canEdit && <IconBtn onClick={onEdit} title="Редактировать"><PencilIcon /></IconBtn>}
              </span>
            </div>
            {requisites.map(r => (
              <KeyRow key={r.label} label={r.label} value={r.value} mono={r.mono}
                      color={r.label === 'Сайт' ? T.accent : undefined} />
            ))}
            {banks.map(b => (
              <div key={b.name} style={{ display: 'flex', flexDirection: 'column', paddingTop: 14 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: T.accent, paddingBottom: 6 }}>{b.name}</span>
                {b.rows.map(r => <KeyRow key={r.label} label={r.label} value={r.value} mono />)}
              </div>
            ))}
          </section>

          <section style={{ ...card(0.14), padding: '20px 22px 16px' }}>
            <span style={{ ...capTitle, paddingBottom: 8 }}>Принадлежность</span>
            {belonging.map((g, gi) => (
              <div key={gi} style={{ display: 'flex', flexDirection: 'column', paddingTop: 6 }}>
                {g.map(r => <KeyRow key={r.label} label={r.label} value={r.value} />)}
              </div>
            ))}
          </section>

          <section style={{ ...card(0.21), padding: '20px 22px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 8 }}>
              <span style={capTitle}>Условия по умолчанию</span>
              {/* Был нарисованный, но мёртвый span: cursor:pointer без onClick. Здесь
                  задаётся ставка НДС, и «кнопка не нажимается» читалось как поломка
                  страницы, а не как ненайденная проводка. */}
              {canEdit && (
                <span style={{ marginLeft: 'auto', display: 'inline-flex' }}>
                  <IconBtn onClick={onEditTerms} title="Редактировать условия по умолчанию">
                    <PencilIcon />
                  </IconBtn>
                </span>
              )}
            </div>
            {terms.map(r => <KeyRow key={r.label} label={r.label} value={r.value} mono={r.mono} />)}
          </section>
        </div>

        {/* ПРАВАЯ КОЛОНКА */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* KPI */}
          <section style={{ ...card(0.07), padding: '2px 26px', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
            {kpi.map((k, i) => (
              <div key={k.label} style={{
                padding: `20px 22px 20px ${i === 0 ? 0 : 22}px`, display: 'flex', flexDirection: 'column', gap: 9,
                borderRight: `1px solid ${i === kpi.length - 1 ? 'transparent' : T.inner}`,
              }}>
                <span style={{ ...colHead, color: T.t3 }}>{k.label}</span>
                <span style={{ fontFamily: T.mono, fontSize: 34, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: k.color }}>{k.value}</span>
                <span style={{ fontSize: 12, color: T.t4 }}>{k.hint}</span>
              </div>
            ))}
          </section>

          {/* Оборот по месяцам */}
          <section style={{ ...card(0.14), padding: '22px 26px 20px', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={h2}>Оборот по месяцам</span>
              <span style={colHead}>весь период</span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, fontSize: 12, color: T.t3 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.income} />приход</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.expense} />расход</span>
              </span>
            </div>

            <TurnoverChart months={turnover.months} income={turnover.income} expense={turnover.expense} />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, paddingTop: 4 }}>
              {stats.map(s => (
                <div key={s.label} style={{ background: T.subtle, borderRadius: 12, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <span style={{ fontSize: 11, color: T.t3 }}>{s.label}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color: s.color }}>{s.value}</span>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 4 }}>
              <span style={{ ...colHead, color: T.t3 }}>Топ статей</span>
              {topItems.map(t => (
                <div key={t.label} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{t.label}</span>
                    <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: t.color }}>{rub(t.value)}</span>
                  </div>
                  <span style={{ height: 5, borderRadius: 2, background: T.inner, display: 'block', overflow: 'hidden' }}>
                    <span style={{ display: 'block', height: 5, width: t.width, borderRadius: 2, background: t.color }} />
                  </span>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 4 }}>
              <span style={{ ...colHead, color: T.t3 }}>По статусам</span>
              {byStatus.map(s => (
                <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: `1px solid ${T.row}` }}>
                  <Dot color={s.color} />
                  <span style={{ fontFamily: T.mono, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t2 }}>{s.label}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, color: T.t4 }}>{s.ops} оп.</span>
                  <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: s.color, minWidth: 120, textAlign: 'right' }}>{rub(s.sum)}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Договора */}
          <section style={{ ...card(0.21), padding: '20px 26px 16px', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={h2}>Договора</span>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t4 }}>{contracts.length}</span>
              <span className="cc-link" onClick={onOpenContracts} style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: T.accent, cursor: 'pointer' }}>В реестр →</span>
            </div>
            <div className="cc-scroll">
              <div style={{
                minWidth: 700, display: 'grid', gridTemplateColumns: CONTRACT_COLS, gap: 14,
                padding: '0 4px 9px', borderBottom: `1px solid ${T.border}`, ...colHead,
              }}>
                <span>№ договора</span><span>Дата</span><span>Формат</span><span>Пролонг.</span>
                <span>Срок опл.</span><span>Окончание</span><span>Документ</span>
              </div>
              {contracts.map(c => (
                <div key={c.number} className="cc-row" style={{
                  minWidth: 700, display: 'grid', gridTemplateColumns: CONTRACT_COLS, gap: 14,
                  alignItems: 'center', padding: '10px 4px', borderRadius: 10,
                }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>{c.number}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, color: T.t2 }}>{c.date}</span>
                  <span style={{ fontSize: 12, color: T.t2 }}>{c.format}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, color: T.t4 }}>{c.prolongation}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, color: T.t2 }}>{c.payTerm}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ fontFamily: T.mono, fontSize: 12, color: T.t2 }}>{c.endsAt}</span>
                    {c.expired && <span style={{ background: T.dangerTint, color: T.danger, borderRadius: 6, padding: '2px 7px', fontSize: 10, fontWeight: 700 }}>истёк</span>}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, color: T.t4 }}>{c.document}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Операции */}
          <section style={{ ...card(0.28), padding: '20px 26px 16px', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ ...h2, paddingRight: 4 }}>Операции</span>
              {/* Нативный select вместо декоративного чипа: он открывается везде,
                  не требует портала и не обрежется скроллом таблицы. Внешний вид —
                  тот же чип из хендоффа. */}
              <OpsPick value={opsStatus} onChange={onOpsStatus} options={[
                { value: '', label: 'Все статусы' },
                { value: 'ОПЛАЧЕНО', label: 'Оплачено' },
                { value: 'ПЛАН ПОСТУПЛЕНИЙ', label: 'План поступлений' },
                { value: 'ПЛАН ОПЛАТ', label: 'План оплат' },
              ]} />
              <OpsPick value={opsSortCol} onChange={onOpsSortCol} options={OPS_SORTABLE} />
              <OpsPick value={opsSortDir} onChange={onOpsSortDir} options={[
                { value: 'desc', label: '↓ По убыванию' },
                { value: 'asc', label: '↑ По возрастанию' },
              ]} />
              {opsLoading && <span style={{ fontSize: 11, color: T.t4 }}>загрузка…</span>}
              <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{opsTotal} записей</span>
            </div>

            <div className="cc-scroll">
              <div style={{ minWidth: 1080, display: 'flex', flexDirection: 'column' }}>
                <div style={{
                  display: 'grid', gridTemplateColumns: OPS_COLS, gap: 12, padding: '0 6px 9px',
                  borderBottom: `1px solid ${T.border}`, ...colHead,
                }}>
                  {/* Клик по заголовку = смена колонки сортировки, повторный клик —
                      направления. Сортируются только те колонки, что умеет бэкенд
                      (sort_map в counterparties.py); остальные — обычный текст. */}
                  <OpsHead col="date" label="Дата" {...headProps} />
                  <OpsHead col="status" label="Статус" {...headProps} />
                  <span style={{ textAlign: 'right' }}>ДЗ</span>
                  <OpsHead col="income" label="Приход" right {...headProps} />
                  <OpsHead col="expense" label="Расход" right {...headProps} />
                  <span>Банк</span>
                  <OpsHead col="period" label="Период" {...headProps} />
                  <OpsHead col="article" label="Статья" {...headProps} />
                  <span>№ ДС</span>
                  <span>№ счёта</span><span>Дата счёта</span>
                </div>
                {ops.map((o, i) => (
                  <div key={i} className="cc-row" style={{
                    display: 'grid', gridTemplateColumns: OPS_COLS, gap: 12, alignItems: 'center',
                    padding: '10px 6px', borderRadius: 10, borderBottom: `1px solid ${T.row}`,
                  }}>
                    <span style={{ fontFamily: T.mono, fontSize: 12, color: T.t2 }}>{o.date}</span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                      <Dot color={o.statusColor} size={7} />
                      <span style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', fontWeight: 700, color: o.statusColor }}>{o.status}</span>
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 12, color: T.accent, textAlign: 'right' }}>{o.dz ?? '—'}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.income, textAlign: 'right' }}>{o.income == null ? '—' : rub(o.income)}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.t2, textAlign: 'right' }}>{o.expense == null ? '—' : rub(o.expense)}</span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                      <Dot color={o.bankColor} size={7} />
                      <span style={{ fontSize: 12, color: T.t2 }}>{o.bank}</span>
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3 }}>{o.period}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, letterSpacing: '.04em', color: T.t3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.item}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3 }}>{o.ds}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3 }}>{o.account}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3 }}>{o.accountDate}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 2px 2px' }}>
              {ops.length < opsTotal && (
                <span className="cc-ghost" onClick={() => !opsLoading && onOpsMore?.()} style={{
                  display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px',
                  border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12, fontWeight: 600,
                  color: T.accent, cursor: opsLoading ? 'default' : 'pointer', opacity: opsLoading ? 0.5 : 1,
                }}>{opsLoading ? 'Загрузка…' : 'Показать ещё'}</span>
              )}
              <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, color: T.t4 }}>{ops.length} из {opsTotal}</span>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}


// Колонки, которые умеет сортировать бэкенд (sort_map в routers/counterparties.py).
// Список общий для чипа сортировки и кликабельных заголовков — чтобы предложить
// сортировку по колонке, которой сервер не знает, было невозможно.
const OPS_SORTABLE = [
  { value: 'date', label: 'Дата' },
  { value: 'status', label: 'Статус' },
  { value: 'income', label: 'Приход' },
  { value: 'expense', label: 'Расход' },
  { value: 'period', label: 'Период' },
  { value: 'article', label: 'Статья' },
];

// Чип-выпадашка: нативный select, обёрнутый в оформление хендоффа.
function OpsPick({ value, onChange, options }) {
  return (
    <span className="cc-ghost" style={{
      display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 8px 0 12px',
      border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12, fontWeight: 600,
      color: T.t1, background: T.card, cursor: 'pointer',
    }}>
      <select value={value} onChange={e => onChange?.(e.target.value)}
        style={{ appearance: 'none', border: 'none', background: 'transparent', outline: 'none',
          font: 'inherit', color: 'inherit', cursor: 'pointer', paddingRight: 4 }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <span style={{ color: T.t4, fontSize: 10 }}>▾</span>
    </span>
  );
}

// Заголовок сортируемой колонки: активная подсвечена и показывает направление.
function OpsHead({ col, label, right, sortCol, sortDir, onPick }) {
  const on = sortCol === col;
  return (
    <span onClick={() => onPick?.(col)} title="Сортировать"
      style={{ cursor: 'pointer', textAlign: right ? 'right' : 'left', color: on ? T.accent : undefined,
        userSelect: 'none' }}>
      {label}{on ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
    </span>
  );
}
