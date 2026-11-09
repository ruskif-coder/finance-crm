/**
 * Примитивы страницы «Премодерация» — из макета (docs/design_handoff_premoderation.zip).
 * Шрифты и карточка — из кита (salesTableKit); остальное — виды этого экрана, в ките их нет:
 * у кита Segmented без счётчиков и вида «в карточке», флажка и метки очереди нет вовсе.
 */
import React from 'react';
import { MONO, UI, card } from '@/components/salesTableKit';

export { MONO };
const SANS = UI;

export const STYLE = `
.pm-root { font-family:${SANS}; color:var(--text-primary); -webkit-font-smoothing:antialiased }
.pm-cap { font-family:${MONO}; font-size:10.5px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-cap) }
.pm-btn { display:inline-flex; align-items:center; gap:6px; height:34px; box-sizing:border-box; padding:0 14px; border:1px solid var(--border-card); background:var(--bg-card); border-radius:12px; font:600 13px ${SANS}; color:var(--text-secondary); white-space:nowrap; cursor:pointer; user-select:none }
.pm-btn:hover { border-color:var(--border-hover); color:var(--accent-fg) }
.pm-btn.p { background:var(--accent); border-color:var(--accent); color:var(--on-accent); font-weight:700 } .pm-btn.p:hover { background:var(--accent-hover); border-color:var(--accent-hover); color:var(--on-accent) }
.pm-btn.d { background:var(--danger); border-color:var(--danger); color:var(--on-accent); font-weight:700 }
.pm-btn[aria-disabled="true"] { opacity:0.45; cursor:not-allowed }
.pm-btn:focus-visible, .pm-row:focus-visible { outline:2px solid var(--accent); outline-offset:2px }
.pm-kbd { display:inline-flex; align-items:center; justify-content:center; min-width:18px; height:18px; padding:0 4px; box-sizing:border-box; border-radius:5px; border:1px solid currentColor; font:700 10px ${MONO}; opacity:0.7 }
.pm-in { font:600 13.5px ${SANS}; color:var(--text-primary); box-sizing:border-box; width:100%; height:36px; padding:0 12px; border:1px solid var(--border-card); border-radius:12px; background:var(--bg-card); outline:none }
.pm-in:focus, .pm-ta:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-tint) } .pm-in::placeholder, .pm-ta::placeholder { color:var(--text-disabled); font-weight:500 }
.pm-ta { font:600 13.5px ${SANS}; box-sizing:border-box; width:100%; padding:10px 12px; border:1px solid var(--border-card); border-radius:12px; outline:none; resize:vertical; line-height:1.45 }
.pm-row:hover { background:var(--bg-subtle) }
@keyframes pmRise { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
@keyframes pmPop { from { opacity:0; transform:scale(0.98) } to { opacity:1; transform:none } }
@media (prefers-reduced-motion: reduce) { .pm-root * { animation-duration:1ms !important; animation-delay:0s !important } }
`;

export const TONE = {
  ok: { bg: 'var(--income-tint)', fg: 'var(--income-fg)', dot: 'var(--income)', border: 'var(--income-border)' },
  warn: { bg: 'var(--warning-tint)', fg: 'var(--warning-fg)', dot: 'var(--warning)', border: 'var(--warning-border)' },
  bad: { bg: 'var(--danger-tint)', fg: 'var(--danger-fg)', dot: 'var(--danger)', border: 'var(--danger-border)' },
  info: { bg: 'var(--accent-tint)', fg: 'var(--accent-fg)', dot: 'var(--accent)', border: 'var(--accent-border)' },
  need: { bg: 'var(--bg-subtle)', fg: 'var(--text-secondary)', dot: 'var(--text-faint)', border: 'var(--border-inner)' },
};
export const Cap = ({ children, style, title }) => <span className="pm-cap" style={style} title={title}>{children}</span>;
export const Card = ({ children, style }) => <div style={{ ...card, ...style }}>{children}</div>;
export const Dot = ({ c, s = 6, style }) => <span style={{ width: s, height: s, borderRadius: 2, background: c, flex: '0 0 auto', ...style }} />;
export const Btn = ({ children, kind, disabled, onClick, style, title }) => (
  <span role="button" tabIndex={0} title={title} aria-disabled={disabled ? 'true' : undefined} className={'pm-btn' + (kind ? ' ' + kind : '')} style={style}
    onClick={disabled ? undefined : onClick} onKeyDown={e => !disabled && (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onClick && onClick())}>{children}</span>
);
export const Chip = ({ tone, children, title, style }) => { const t = TONE[tone];
  return <span title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, background: t.bg, color: t.fg, whiteSpace: 'nowrap', ...style }}><Dot c={t.dot} />{children}</span>; };
/** Метка в очереди. flag — синяя заливка (SSP ждёт) */
export const Pip = ({ kind, children, title }) => { const m = { flag: ['var(--accent)', 'var(--on-accent)'], bad: ['var(--danger-tint)', 'var(--danger-fg)'], warn: ['var(--warning-tint)', 'var(--warning-fg)'], info: ['var(--accent-tint)', 'var(--accent-fg)'], need: ['var(--bg-subtle)', 'var(--text-secondary)'] }[kind];
  return <span title={title} style={{ flex: '0 0 auto', whiteSpace: 'nowrap', height: 17, display: 'inline-flex', alignItems: 'center', padding: '0 5px', borderRadius: 5, fontFamily: MONO, fontSize: 10, fontWeight: 700, background: m[0], color: m[1] }}>{children}</span>; };
export const Check = ({ on, onClick, size = 18, dim, title }) => (
  <span role="checkbox" aria-checked={!!on} tabIndex={0} title={title} onClick={onClick} onKeyDown={e => e.key === ' ' && (e.preventDefault(), onClick(e))}
    style={{ width: size, height: size, borderRadius: size > 16 ? 5 : 4, boxSizing: 'border-box', border: `1.5px solid ${on ? 'var(--accent)' : 'var(--border-hover)'}`, background: on ? 'var(--accent)' : 'var(--bg-card)', color: 'var(--on-accent)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: size - 6, fontWeight: 800, cursor: 'pointer', opacity: dim ? 0.35 : 1, flex: '0 0 auto' }}>{on ? '✓' : ''}</span>
);
export const Segmented = ({ value, options, onChange, inCard }) => (
  <span style={{ display: 'inline-flex', background: inCard ? 'var(--bg-subtle)' : 'var(--bg-card)', border: `1px solid ${inCard ? 'var(--border-inner)' : 'var(--border-card)'}`, borderRadius: inCard ? 10 : 12, padding: inCard ? 2 : 3 }}>
    {options.map(([v, label, count]) => { const on = value === v;
      return <span key={v} role="button" tabIndex={0} onClick={() => onChange(v)} onKeyDown={e => e.key === 'Enter' && onChange(v)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: inCard ? 26 : 28, padding: '0 11px', borderRadius: inCard ? 8 : 9, fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer',
          background: on ? (inCard ? 'var(--bg-card)' : 'var(--accent-tint)') : 'transparent', color: on ? 'var(--accent-fg)' : 'var(--text-muted)', boxShadow: on && inCard ? 'var(--shadow-card)' : 'none' }}>
        {label}{count != null && <span style={{ fontFamily: MONO, fontSize: 11.5 }}>{count}</span>}</span>; })}
  </span>
);
/** Отметка проверки: ✓ ✗ ! – ○ */
export const CHECK_MARK = { ok: ['✓', 'var(--income-fg)', 'transparent', 'var(--text-primary)', 'var(--text-secondary)'], bad: ['✗', 'var(--danger-fg)', 'var(--danger-tint)', 'var(--danger-fg)', 'var(--danger-fg)'],
  warn: ['!', 'var(--warning-fg)', 'var(--warning-bg)', 'var(--warning-fg)', 'var(--text-secondary)'], na: ['–', 'var(--text-faint)', 'transparent', 'var(--text-primary)', 'var(--text-muted)'], off: ['○', 'var(--text-disabled)', 'transparent', 'var(--text-muted)', 'var(--text-faint)'] };
