/**
 * Части страницы «Документы для бухгалтерии». Только отображение — состояние и правила в AccountantDocs.jsx / accDocsLogic.js.
 * Шрифты и карточка — из кита (salesTableKit). Btn, Input, Chip, Pip, CopyField, FileRow — свои у экрана: в ките нет
 * компонентов с этими состояниями (фокус, «в буфере», пунктир пустого файла), а стили-объекты кита их не заменяют.
 */
import React from 'react';
import { MONO, UI as SANS, card } from '@/components/salesTableKit';
import { money } from './accDocsLogic';

export { MONO, SANS };

/* ── стили страницы (подключаются один раз) ── */
export const STYLE = `
.ad-root { font-family:${SANS}; color:var(--text-primary); -webkit-font-smoothing:antialiased }
.ad-root a { color:var(--accent); text-decoration:none } .ad-root a:hover { color:var(--accent-hover); text-decoration:underline }
.ad-cap { font-family:${MONO}; font-size:10.5px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-cap) }
.ad-btn { display:inline-flex; align-items:center; gap:6px; height:34px; box-sizing:border-box; padding:0 14px; border:1px solid var(--border-card); background:var(--bg-card); border-radius:12px; font:600 13px ${SANS}; color:var(--text-secondary); white-space:nowrap; cursor:pointer; user-select:none }
.ad-btn:hover { border-color:var(--border-hover); color:var(--accent-fg) }
.ad-btn:focus-visible, .ad-row:focus-visible, .ad-copy:focus-visible { outline:2px solid var(--accent); outline-offset:2px }
.ad-btn.p { background:var(--accent); border-color:var(--accent); color:#FFFFFF; font-weight:700 } .ad-btn.p:hover { background:var(--accent-hover); border-color:var(--accent-hover); color:#FFFFFF }
.ad-btn[aria-disabled="true"] { opacity:0.45 }
.ad-in { font:600 14px ${SANS}; color:var(--text-primary); box-sizing:border-box; width:100%; min-width:0; height:38px; padding:0 12px; border:1px solid var(--border-card); border-radius:12px; background:var(--bg-card); outline:none }
.ad-in.mono { font-family:${MONO}; font-weight:500 } .ad-in:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-tint) } .ad-in::placeholder { color:var(--text-disabled); font-weight:500 }
.ad-row:hover { background:var(--bg-subtle) }
.ad-copy { cursor:copy } .ad-copy:hover { border-color:var(--accent-border) !important }
@keyframes adRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
@keyframes adPop { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
@media (prefers-reduced-motion: reduce) { .ad-root * { animation-duration:1ms !important; animation-delay:0s !important } }
`;

/* ── примитивы ── */
export const Cap = ({ children, style }) => <span className="ad-cap" style={style}>{children}</span>;
export const Card = ({ children, style, ...p }) => <div style={{ ...card, ...style }} {...p}>{children}</div>;
export const Btn = ({ children, primary, disabled, onClick, style, title }) => (
  <span role="button" tabIndex={0} title={title} aria-disabled={disabled ? 'true' : undefined} className={'ad-btn' + (primary ? ' p' : '')} style={style}
    onClick={onClick} onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onClick && onClick())}>{children}</span>
);
export const Input = ({ mono, style, ...p }) => <input className={'ad-in' + (mono ? ' mono' : '')} style={style} {...p} />;
export const Dot = ({ c, s = 6 }) => <span style={{ width: s, height: s, borderRadius: 2, background: c, flex: '0 0 auto' }} />;
export const Clip = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>;

export const TONE = {
  ok: { bg: 'var(--income-tint)', fg: 'var(--income-fg)', dot: 'var(--income)', border: 'var(--income-border)' },
  warn: { bg: 'var(--warning-tint)', fg: 'var(--warning-fg)', dot: 'var(--warning)', border: 'var(--warning-border)' },
  bad: { bg: 'var(--danger-tint)', fg: 'var(--danger-fg)', dot: 'var(--danger)', border: 'var(--danger-border)' },
  info: { bg: 'var(--accent-tint)', fg: 'var(--accent-fg)', dot: 'var(--accent)', border: 'var(--accent-border)' },
  need: { bg: 'var(--bg-subtle)', fg: 'var(--text-secondary)', dot: 'var(--text-faint)', border: 'var(--border-inner)' },
};
export const Chip = ({ tone = 'need', children, dashed, title }) => { const t = TONE[tone];
  return <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, background: dashed ? 'var(--bg-card)' : t.bg, color: dashed ? 'var(--text-muted)' : t.fg, border: dashed ? '1px dashed var(--border-hover)' : 'none', whiteSpace: 'nowrap' }}>{!dashed && <Dot c={t.dot} />}{children}</span>; };

/** Метка в строке очереди. onGreen — строка «готово», метки на белом */
export const Pip = ({ kind, label, title, onGreen }) => {
  const m = { flag: ['var(--accent)', '#FFFFFF'], ok: ['var(--income-tint)', 'var(--income-fg)'], warn: ['var(--warning-tint)', 'var(--warning-fg)'], off: ['var(--bg-subtle)', 'var(--text-faint)'],
    'edo-off': ['var(--bg-card)', 'var(--text-disabled)'], 'edo-info': ['var(--accent-tint)', 'var(--accent-fg)'], 'edo-ok': ['var(--income-tint)', 'var(--income-fg)'], 'edo-bad': ['var(--danger-tint)', 'var(--danger-fg)'] }[kind];
  const bg = onGreen && kind !== 'flag' ? 'var(--bg-card)' : m[0];
  return <span title={title} style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5, fontFamily: MONO, fontSize: 10, fontWeight: 700, background: bg, color: m[1] }}>{label}</span>;
};

/** Значение, которое копируется по клику. state: 'last' | 'was' | '' (п.13) */
export function CopyField({ label, value, hint, state, onCopy, big = true, children, style }) {
  const last = state === 'last', was = state === 'was';
  return (
    <span role="button" tabIndex={0} className="ad-copy" title="Скопировать" onClick={onCopy} onKeyDown={e => e.key === 'Enter' && onCopy()}
      style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 12px', borderRadius: 12, minWidth: 0,
        border: `1px solid ${last ? 'var(--accent)' : was ? 'var(--border-card)' : 'var(--border-inner)'}`, background: last ? 'var(--accent-tint)' : 'var(--bg-subtle)', ...style }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>{label && <Cap>{label}</Cap>}
        <span style={{ marginLeft: 'auto', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', color: last ? 'var(--accent-fg)' : 'var(--text-faint)' }}>{last ? 'в буфере' : was ? '✓' : ''}</span></span>
      {children || <span style={{ fontFamily: big ? MONO : SANS, fontSize: big ? 15 : 13.5, fontWeight: big ? 700 : 500, lineHeight: big ? 1.35 : 1.5, overflowWrap: 'anywhere' }}>{value}</span>}
      {hint && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{hint}</span>}
    </span>
  );
}

/** Строка файла (п.7: пустая — нейтральная пунктирная) */
export function FileRow({ kind, label, file, required, note, readOnly, canAttach, onAttach, onRemove, onOpen }) {
  const has = !!file;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: 12, border: `1px ${has ? 'solid' : 'dashed'} ${has ? 'var(--border-inner)' : 'var(--border-card)'}`, background: has ? 'var(--bg-subtle)' : 'var(--bg-card)' }}>
      <span style={{ flex: '0 0 auto', minWidth: 40, height: 28, padding: '0 6px', boxSizing: 'border-box', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-inner)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 11, fontWeight: 700, color: has ? 'var(--accent-fg)' : 'var(--text-faint)' }}>{kind}</span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, flex: '1 1 auto' }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: has ? 'var(--text-primary)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{has ? (onOpen ? <a href="#" onClick={e => { e.preventDefault(); onOpen(file); }}>{file.name}</a> : file.name) : label + (required ? '' : ' · по желанию')}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{has ? `${readOnly ? 'в архиве' : 'приложено'} · ${Math.round(file.size / 1000)} КБ` : note}</span>
      </span>
      {has && !readOnly && <a href="#" onClick={e => { e.preventDefault(); onRemove(); }} style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-muted)' }}>убрать</a>}
      {(!readOnly || canAttach) && <Btn onClick={onAttach} style={{ height: 32 }}><Clip />{has ? 'заменить' : 'приложить'}</Btn>}
    </div>
  );
}

/** Поле с подписью и подсказкой снизу */
export const Field = ({ label, children, note, noteTone }) => (
  <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
    <Cap>{label}</Cap>{children}
    <span style={{ fontSize: 11.5, minHeight: 15, color: noteTone === 'warn' ? 'var(--warning-fg)' : noteTone === 'bad' ? 'var(--danger-fg)' : noteTone === 'ok' ? 'var(--income-fg)' : 'var(--text-faint)' }}>{note}</span>
  </span>
);
export const borderFor = tone => tone === 'bad' ? 'var(--danger)' : tone === 'warn' ? 'var(--warning)' : 'var(--border-card)';

/** Номер шага на карточке: ✓ когда готово (п.6) */
export const StepHead = ({ n, done, title, sub, right }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
    <span style={{ width: 24, height: 24, borderRadius: 7, background: done ? 'var(--income-tint)' : 'var(--bg-subtle)', color: done ? 'var(--income-fg)' : 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 12, fontWeight: 700 }}>{done ? '✓' : n}</span>
    <span style={{ fontSize: 15, fontWeight: 700, whiteSpace: 'nowrap' }}>{title}</span>
    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub}</span>
    {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
  </div>
);

/** Сумма-плашка для «Прошлых пакетов» и очереди */
export const Sum = ({ v, size = 13 }) => <span style={{ fontFamily: MONO, fontSize: size, fontWeight: 700, whiteSpace: 'nowrap' }}>{money(v)}</span>;
