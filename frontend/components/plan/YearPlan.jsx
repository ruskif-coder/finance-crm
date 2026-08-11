/**
 * Годовой план — планирование продаж по рекламодателям / брендам / месяцам.
 * Дизайн-хендофф (собственные токены T, как у конструктора МП). Данные — из реальных
 * справочников: `advertisers` [{id,name,brands:[{id,name}]}], `services` [{id,name}].
 *
 * Хранит id (advertiser_id/brand_id/service_id), имена только для отображения.
 * Карты sums/locks/products/deals ключуются индексом месяца (0..11).
 * Факт/бронь — статика из поля deals: [[bx_id, amount, closed(0|1)], ...] по месяцу,
 * заполняется по кнопке «Обновить данные о сделках» (проп onMatch).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { PortalPopover } from '../salesTableKit';

/* ── токены ─────────────────────────────────────────────────────────── */
export const T = {
  canvas: '#EBEEF6', card: '#FFFFFF', nested: '#F6F8FF', subtle: '#F6F7FB',
  planTileBg: '#F0F7F4', planTileBorder: '#D9EDE5',
  onBg: '#E6F5EF', onBorder: '#C9E8DC', lockBg: '#EAF0FF', lockBorder: '#C9D6F7',
  emptyBg: '#FFFBF3', emptyBorder: '#F2DFC0',
  border: '#E3E7F1', inner: '#EDF0F7', row: '#F2F4FA', nestedRow: '#E7EBF7', hoverBorder: '#C7D0E8',
  t1: '#1C2433', t2: '#525C70', t3: '#79839A', t4: '#A3ABBD', t5: '#C3C9D8',
  accent: '#4F6CE6', accentHover: '#3A50BE', accentTint: '#ECEFFD', accentBorder: '#D7DEFA',
  planBar: '#A9B6F2', fact: '#2FA37C', factText: '#1F7D5E',
  booked: '#C3CCEA', bookedText: '#8E9AC0', bookedGrey: '#8B93A6',
  warning: '#E89020', danger: '#C93A3E',
  shadow: '0 1px 3px rgba(28,36,51,.05), 0 4px 16px rgba(28,36,51,.04)',
  pop: '0 8px 28px rgba(28,36,51,.14)',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};

export const MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

/* ── формат ─────────────────────────────────────────────────────────── */
const num = v => Math.round(v).toLocaleString('ru-RU');
const mln = v => (v / 1e6).toFixed(1).replace('.', ',');
const kk = v => (!v ? '—' : v >= 1e6 ? (v / 1e6).toFixed(1).replace('.', ',') + 'м' : Math.round(v / 1e3) + 'к');
const parseN = v => {
  const n = parseFloat(String(v ?? '').replace(/[^\d.,-]/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
};
export const pctColor = p => (p >= 80 ? T.fact : p >= 50 ? T.warning : T.danger);
const stop = e => e && e.stopPropagation && e.stopPropagation();

/* ── расчёты (единственная точка правды) ────────────────────────────── */
export const monthValue = (b, i) => {
  if (!b.on[i]) return 0;
  if (b.sums[i] != null) return b.sums[i];
  const lockedSum = Object.keys(b.locks).reduce((a, k) => a + (b.on[k] && b.sums[k] != null ? b.sums[k] : 0), 0);
  const free = b.on.reduce((a, v, k) => a + (v && !b.locks[k] ? 1 : 0), 0);
  return free > 0 ? Math.max(0, b.plan - lockedSum) / free : 0;
};
export const factOf = (b, i) => (b.deals[i] || []).reduce((a, d) => a + (d[2] ? d[1] : 0), 0);
export const bookedOf = (b, i) => (b.deals[i] || []).reduce((a, d) => a + (d[2] ? 0 : d[1]), 0);
const sumMonths = (b, fn) => MONTHS.reduce((a, _, i) => a + fn(b, i), 0);

/* ── сетки ──────────────────────────────────────────────────────────── */
const PLAN_COLS = `minmax(340px,1.7fr) 120px repeat(12, minmax(80px,1fr)) 66px`;
const PROG_COLS = '1.5fr 108px 108px 1fr 88px 74px';

/* ── типографика ────────────────────────────────────────────────────── */
const capTitle = { fontFamily: T.mono, fontSize: 13, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: T.t3 };
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const meta = { fontFamily: T.mono, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };

const Card = ({ delay = 0, pad = '20px 24px 16px', gap = 12, style, className, children }) => (
  <section className={className} style={{
    background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 18,
    padding: pad, display: 'flex', flexDirection: 'column', gap,
    animation: `riseIn .4s ${T.ease} ${delay}s both`, ...style,
  }}>{children}</section>
);

const Dot = ({ color, size = 8 }) => (
  <span style={{ width: size, height: size, borderRadius: 2, background: color, flex: `0 0 ${size}px` }} />
);

// Портальная выпадашка из общего кита — не обрезается overflow'ом таблицы и не уходит
// под соседние карточки (раньше был локальный position:absolute → клип).
const Popover = ({ children, minWidth = 200 }) => (
  <PortalPopover open minWidth={minWidth} maxHeight={260} style={{ boxShadow: T.pop, animation: `popIn .18s ${T.ease} both` }}>{children}</PortalPopover>
);

const Option = ({ active, label, onPick }) => (
  <span className="yp-opt" onClick={onPick} style={{
    padding: '7px 10px', borderRadius: 9, background: active ? T.accentTint : 'transparent',
    color: active ? T.accent : T.t1, fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
  }}>{label}</span>
);

/** Двухсегментный бар: факт (цвет по проценту) + бронь (#C3CCEA). */
const ProgressBar = ({ plan, fact, booked, height = 8, bg = T.inner, delay = 0 }) => {
  const pct = plan ? (fact / plan) * 100 : 0;
  const factW = Math.min(100, pct);
  const bookedW = plan ? Math.max(0, Math.min(100 - factW, (booked / plan) * 100)) : 0;
  return (
    <span style={{ flex: '1 1 auto', minWidth: 40, display: 'flex', gap: 2, height, borderRadius: 3, background: bg, overflow: 'hidden' }}>
      <span style={{ height, width: factW + '%', borderRadius: 3, background: pctColor(pct), transformOrigin: 'left', animation: `barGrow .55s ${T.ease} ${delay}s both` }} />
      <span title="бронь" style={{ height, width: bookedW + '%', borderRadius: 3, background: T.booked, transformOrigin: 'left', animation: `barGrow .55s ${T.ease} ${delay}s both` }} />
    </span>
  );
};

const IconBtn = ({ title, onClick, children, size = 32, disabled }) => (
  <span className="yp-ghost" title={title} onClick={disabled ? undefined : onClick} style={{
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size,
    border: `1px solid ${T.border}`, borderRadius: 9, color: T.t2, cursor: disabled ? 'default' : 'pointer',
    flex: `0 0 ${size}px`, opacity: disabled ? 0.5 : 1,
  }}>{children}</span>
);

const Plus = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>;
const Pencil = () => <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20h4l10-10-4-4L4 16v4z" /><path d="M14.5 5.5l4 4" /></svg>;
const Refresh = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" /></svg>;
const Spread = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12h18" /><path d="M7 8l-4 4 4 4" /><path d="M17 8l4 4-4 4" /></svg>;
const Copy = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" /></svg>;
const Lock = ({ locked }) => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <rect x="5" y="11" width="14" height="9" rx="2.5" />
    <path d={locked ? 'M8 11V8a4 4 0 0 1 8 0v3' : 'M8 11V8a4 4 0 0 1 7.5-2'} />
  </svg>
);

const blankBrand = id => ({ id, brand: '', brand_id: null, plan: 0, on: Array(12).fill(0), sums: {}, locks: {}, products: {}, deals: {} });

/* ══════════════════════════════════════════════════════════════════════
   СТРАНИЦА
   ══════════════════════════════════════════════════════════════════════ */
export default function YearPlan({
  year, years = [], onYear,
  groups: initial = [], advertisers = [], services = [],
  onSave, onMatch, saving = false, matching = false, savedAt = '', readOnly = false,
  reps = [], repValue = null, onRep = () => {}, ownRepId = null, isMaster = false,
  mode = 'edit', allData = [], onVerifyPassword,
}) {
  const [groups, setGroups] = useState(initial);
  const [pendingDel, setPendingDel] = useState(null);   // { kind:'group'|'brand', gid, bid, label }
  const [pwd, setPwd] = useState('');
  const [pwErr, setPwErr] = useState('');
  const [pwBusy, setPwBusy] = useState(false);
  const [sel, setSel] = useState(null);       // открытый поповер
  const [edit, setEdit] = useState(null);     // редактируемая ячейка суммы `${brandId}_${month}`
  const [openProg, setOpenProg] = useState(null);
  const [yearOpen, setYearOpen] = useState(false);
  const [repOpen, setRepOpen] = useState(false);
  const allMode = mode === 'all';
  const repLabel = allMode ? 'Все сейлзы'
    : (repValue != null && repValue === ownRepId) ? 'Мой план'
    : (reps.find(r => r.id === repValue)?.name || 'Мой план');
  const seq = useRef(100000);

  useEffect(() => { setGroups(initial); }, [initial]);

  const advById = useMemo(() => Object.fromEntries(advertisers.map(a => [a.id, a])), [advertisers]);
  const svcName = useMemo(() => Object.fromEntries(services.map(s => [s.id, s.name])), [services]);

  useEffect(() => {
    const off = e => { if (!e.target.closest('[data-pop-root]')) { setSel(null); setYearOpen(false); setRepOpen(false); } };
    const esc = e => { if (e.key === 'Escape') { setSel(null); setEdit(null); setYearOpen(false); setRepOpen(false); } };
    document.addEventListener('mousedown', off);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc); };
  }, []);

  const patchBrand = (gid, bid, p) => setGroups(gs => gs.map(g => (g.id !== gid ? g : {
    ...g, brands: g.brands.map(b => (b.id === bid ? { ...b, ...p } : b)),
  })));
  const toggleSel = key => setSel(s => (s === key ? null : key));

  /* итоги */
  const totals = useMemo(() => {
    const filled = groups.filter(g => g.adv_id);
    const allBrands = groups.flatMap(g => g.brands);
    const plan = allBrands.reduce((a, b) => a + b.plan, 0);
    const fact = allBrands.reduce((a, b) => a + sumMonths(b, factOf), 0);
    const booked = allBrands.reduce((a, b) => a + sumMonths(b, bookedOf), 0);
    return {
      plan, fact, booked,
      pct: plan ? (fact / plan) * 100 : 0,
      counter: `${filled.length} рекламодателей · ${filled.reduce((a, g) => a + g.brands.filter(b => b.brand_id).length, 0)} брендов`,
    };
  }, [groups]);

  const monthTotals = MONTHS.map((_, i) => {
    const all = groups.flatMap(g => g.brands);
    return {
      plan: all.reduce((a, b) => a + monthValue(b, i), 0),
      fact: all.reduce((a, b) => a + factOf(b, i), 0),
    };
  });
  const maxMonth = Math.max(1, ...monthTotals.map(m => m.plan));
  const anyClosed = groups.some(g => !g.open);

  const kpi = [
    { label: 'План года', value: mln(totals.plan), unit: 'млн ₽', color: T.t1, hint: totals.counter },
    { label: 'Факт', value: mln(totals.fact), unit: 'млн ₽', color: T.fact, hint: 'закрытые сделки' },
    { label: 'Бронь', value: mln(totals.booked), unit: 'млн ₽', color: T.bookedGrey, hint: 'сделки в работе' },
    { label: 'Выполнение', value: totals.pct.toFixed(0), unit: '%', color: pctColor(totals.pct), hint: `остаток ${mln(Math.max(0, totals.plan - totals.fact))} млн ₽` },
  ];

  /* распределение остатка по незакреплённым месяцам */
  const distribute = (gid, b) => {
    const lockedSum = Object.keys(b.locks).reduce((a, k) => a + (b.on[k] && b.sums[k] != null ? b.sums[k] : 0), 0);
    const freeIdx = b.on.map((v, i) => (v && !b.locks[i] ? i : -1)).filter(i => i >= 0);
    if (!freeIdx.length) return;
    const per = Math.max(0, b.plan - lockedSum) / freeIdx.length;
    const sums = { ...b.sums };
    freeIdx.forEach(i => { sums[i] = per; });
    patchBrand(gid, b.id, { sums });
  };

  const addGroup = () => setGroups(gs => [...gs, { id: ++seq.current, adv: '', adv_id: null, open: true, brands: [blankBrand(++seq.current)] }]);
  // копия настроек года бренда: те же план/месяцы/суммы/закрепления/продукты, но с пустым
  // (активным) выбором бренда и без привязанных сделок — вставляется сразу под исходным
  const copyBrand = (gid, b) => setGroups(gs => gs.map(g => (g.id !== gid ? g : {
    ...g,
    brands: g.brands.flatMap(x => (x.id !== b.id ? [x] : [x, {
      ...x, id: ++seq.current, brand: '', brand_id: null, deals: {},
      on: x.on.slice(), sums: { ...x.sums }, locks: { ...x.locks }, products: { ...x.products },
    }])),
  })));
  const doMatch = async () => {
    if (!onMatch) return;
    const pairs = groups.filter(g => g.adv_id).flatMap(g => g.brands.map(b => [g.adv_id, b.brand_id]));
    const matched = await onMatch(pairs);
    if (!matched) return;
    // вмерживаем deals по (advertiser_id, brand_id); brand_id=null → в первую строку без бренда
    setGroups(gs => gs.map(g => (g.adv_id == null ? g : {
      ...g,
      brands: g.brands.map(b => {
        const m = matched.find(x => x.advertiser_id === g.adv_id && x.brand_id === b.brand_id);
        return m ? { ...b, deals: m.deals || {} } : { ...b, deals: {} };
      }),
    })));
  };
  const save = () => onSave && onSave(groups);

  // удаление строки плана — под подтверждение повторным вводом пароля
  const askDelete = (payload) => { setPwd(''); setPwErr(''); setPendingDel(payload); };
  const confirmDelete = async () => {
    if (!pendingDel) return;
    setPwBusy(true); setPwErr('');
    try {
      const ok = onVerifyPassword ? await onVerifyPassword(pwd) : true;
      if (!ok) { setPwErr('Неверный пароль'); setPwBusy(false); return; }
    } catch { setPwErr('Неверный пароль'); setPwBusy(false); return; }
    const d = pendingDel;
    if (d.kind === 'group') setGroups(gs => gs.filter(x => x.id !== d.gid));
    else setGroups(gs => gs.map(x => (x.id === d.gid ? { ...x, brands: x.brands.filter(y => y.id !== d.bid) } : x)));
    setPwBusy(false); setPendingDel(null); setPwd('');
  };

  return (
    <>
      <style>{CSS}</style>

      {pendingDel && (
        <div onClick={() => !pwBusy && setPendingDel(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(28,36,51,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div onClick={stop} style={{ width: 400, maxWidth: '100%', background: T.card, borderRadius: 16, boxShadow: T.pop, padding: '22px 22px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>Удалить из плана</span>
            <span style={{ fontSize: 13, color: T.t2, lineHeight: 1.5 }}>
              {pendingDel.label} будет удалён{pendingDel.kind === 'group' ? ' со всеми брендами' : ''}. Подтвердите действие вводом пароля.
            </span>
            <input type="password" autoFocus value={pwd} disabled={pwBusy} placeholder="Ваш пароль"
              onChange={e => { setPwd(e.target.value); setPwErr(''); }}
              onKeyDown={e => { if (e.key === 'Enter' && pwd) confirmDelete(); }}
              style={{ height: 38, padding: '0 12px', borderRadius: 10, border: `1px solid ${pwErr ? T.danger : T.border}`, fontSize: 14, outline: 'none', fontFamily: T.sans }} />
            {pwErr && <span style={{ fontSize: 12, color: T.danger }}>{pwErr}</span>}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 2 }}>
              <span className="yp-ghost" onClick={() => !pwBusy && setPendingDel(null)}
                style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 15px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 13, fontWeight: 600, color: T.t2, cursor: 'pointer' }}>Отмена</span>
              <span onClick={pwBusy || !pwd ? undefined : confirmDelete}
                style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 16px', background: T.danger, color: '#FFF', borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: pwBusy || !pwd ? 'default' : 'pointer', opacity: pwBusy || !pwd ? 0.55 : 1 }}>
                {pwBusy ? 'Проверка…' : 'Удалить'}
              </span>
            </div>
          </div>
        </div>
      )}

      <div style={{ boxSizing: 'border-box', padding: '26px 32px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* шапка */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', animation: `riseIn .4s ${T.ease} both` }}>
          <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.025em' }}>Годовой план</span>
          <span data-pop-root style={{ position: 'relative' }}>
            <span className="yp-ghost" onClick={() => setYearOpen(o => !o)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 30, padding: '0 12px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontFamily: T.mono, fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
              {year} <span style={{ color: T.t4, fontSize: 10 }}>▾</span>
            </span>
            {yearOpen && (
              <Popover minWidth={120}>
                {Array.from(new Set([year, ...years, year - 1, year + 1])).sort((a, b) => b - a).map(y => (
                  <Option key={y} active={y === year} label={String(y)} onPick={() => { setYearOpen(false); onYear && onYear(y); }} />
                ))}
              </Popover>
            )}
          </span>
          {isMaster && (
            <span data-pop-root style={{ position: 'relative' }}>
              <span className="yp-ghost" onClick={() => setRepOpen(o => !o)} title="Чей план смотреть"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 30, padding: '0 12px', background: allMode ? T.accentTint : T.card, border: `1px solid ${allMode ? T.accentBorder : T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 700, color: allMode ? T.accent : T.t1, cursor: 'pointer' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /></svg>
                </span>
                {repLabel} <span style={{ color: T.t4, fontSize: 10 }}>▾</span>
              </span>
              {repOpen && (
                <PortalPopover open minWidth={230} style={{ boxShadow: T.pop }}>
                  <Option active={allMode} label="Показать все" onPick={() => { setRepOpen(false); onRep('all'); }} />
                  {ownRepId != null && <Option active={!allMode && repValue === ownRepId} label="Мой план" onPick={() => { setRepOpen(false); onRep(ownRepId); }} />}
                  <span style={{ height: 1, background: T.inner, margin: '4px 6px' }} />
                  {reps.map(r => <Option key={r.id} active={!allMode && repValue === r.id} label={r.name} onPick={() => { setRepOpen(false); onRep(r.id); }} />)}
                </PortalPopover>
              )}
            </span>
          )}
          <span style={meta}>{totals.counter}{savedAt ? ` · сохранено ${savedAt}` : ''}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            {!allMode && (
            <span className="yp-ghost" onClick={() => setGroups(gs => gs.map(g => ({ ...g, open: anyClosed })))}
              style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 13px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: T.t2, cursor: 'pointer' }}>
              {anyClosed ? 'Развернуть все' : 'Свернуть все'}
            </span>
            )}
            {!readOnly && (
              <span className="yp-ghost" onClick={matching ? undefined : doMatch}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 13px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: T.t2, cursor: matching ? 'default' : 'pointer', opacity: matching ? 0.6 : 1 }}>
                <Refresh />{matching ? 'Обновляю…' : 'Обновить данные о сделках'}
              </span>
            )}
            {!readOnly && (
              <span className="yp-primary" onClick={saving ? undefined : save}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 32, padding: '0 16px', background: T.accent, color: '#FFF', borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1 }}>
                {saving ? 'Сохраняю…' : 'Сохранить'}
              </span>
            )}
            {!readOnly && (
              <span className="yp-primary" onClick={addGroup}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 32, padding: '0 14px', background: T.accent, color: '#FFF', borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>
                <Plus />Рекламодатель
              </span>
            )}
          </span>
        </div>

        {allMode && <AllSummary year={year} data={allData} />}

        {!allMode && <>
        {/* верхний ряд: до 1920 — 2 этажа, после — в один ряд */}
        <div className="yp-toprow">

        {/* KPI — всегда 4 в ряд */}
        <Card delay={0.07} pad="2px 22px" gap={0} style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', alignContent: 'center' }}>
          {kpi.map((k, i) => (
            <div key={k.label} style={{ padding: '16px 18px 16px 0', marginRight: 18, display: 'flex', flexDirection: 'column', gap: 8, borderRight: `1px solid ${i === 3 ? 'transparent' : T.inner}` }}>
              <span style={{ ...meta, color: T.t3 }}>{k.label}</span>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                <span style={{ fontFamily: T.mono, fontSize: 34, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: k.color }}>{k.value}</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: T.t3 }}>{k.unit}</span>
              </span>
              <span style={{ fontSize: 11.5, color: T.t4 }}>{k.hint}</span>
            </div>
          ))}
        </Card>

        {/* план и факт по месяцам */}
        <Card delay={0.14}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em' }}>План и факт по месяцам</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 12, fontSize: 11.5, color: T.t3 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.fact} />факт</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.planBar} />план</span>
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, minHeight: 110 }}>
            {monthTotals.map((m, i) => {
              const ROWS = 10;
              const planCells = Math.round((m.plan / maxMonth) * ROWS);
              const factCells = Math.round((m.fact / maxMonth) * ROWS);
              return (
                <span key={i} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 1, justifyContent: 'flex-end' }}>
                    {Array.from({ length: ROWS }, (_, k) => {
                      const rank = ROWS - k;
                      return <span key={k} style={{ height: 7, borderRadius: 2, background: rank <= factCells ? T.fact : rank <= planCells ? T.planBar : T.inner }} />;
                    })}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4 }}>{i % 2 === 0 ? MONTHS[i] : ''}</span>
                </span>
              );
            })}
          </div>
        </Card>

        </div>

        {/* главная таблица */}
        <Card delay={0.21} pad="20px 24px 14px" gap={4}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span style={capTitle}>План по рекламодателям</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', background: T.nested, color: T.accent, borderRadius: 8, padding: '4px 9px', fontSize: 10.5, fontWeight: 700 }}>
              клик по строке — детализация по брендам
            </span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 13, fontSize: 11, color: T.t3, flexWrap: 'wrap' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.fact} />период в плане</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.t5} />сделка в брони</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.accent} />сумма закреплена</span>
            </span>
          </div>

          <div style={{ overflow: 'auto hidden', paddingBottom: 14 }}>
            <div style={{ minWidth: 1180, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'grid', gridTemplateColumns: PLAN_COLS, gap: 6, padding: '0 8px 9px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
                <span>Рекламодатель / бренд</span>
                <span style={{ textAlign: 'right' }}>Годовой план, ₽</span>
                {MONTHS.map(m => <span key={m} style={{ textAlign: 'center' }}>{m}</span>)}
                <span />
              </div>

              {groups.length === 0 && (
                <div style={{ padding: '26px 8px', color: T.t4, fontSize: 13 }}>Плана на {year} ещё нет — добавьте рекламодателя.</div>
              )}

              {groups.map(g => {
                const plan = g.brands.reduce((a, b) => a + b.plan, 0);
                const emptyAdv = !g.adv_id;
                return (
                  <div key={g.id} style={{ display: 'flex', flexDirection: 'column' }}>
                    {/* строка рекламодателя */}
                    <div onClick={() => setGroups(gs => gs.map(x => (x.id === g.id ? { ...x, open: !x.open } : x)))}
                      className="yp-row" style={{
                        display: 'grid', gridTemplateColumns: PLAN_COLS, gap: 6, alignItems: 'center',
                        padding: '9px 8px', borderRadius: 10, borderBottom: `1px solid ${T.row}`,
                        background: emptyAdv ? T.emptyBg : (g.open ? T.nested : 'transparent'), cursor: 'pointer',
                      }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, borderRadius: 6, background: T.accentTint, color: T.accent, fontSize: 8, flex: '0 0 18px' }}>{g.open ? '▲' : '▼'}</span>
                        <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                          <span onClick={e => { stop(e); if (!readOnly) toggleSel('g' + g.id); }} style={{ display: 'inline-block', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'middle', fontSize: 13, fontWeight: 700, color: emptyAdv ? T.warning : T.t1, cursor: readOnly ? 'default' : 'pointer', whiteSpace: 'nowrap' }}>
                            {g.adv || 'выберите рекламодателя'} {!readOnly && <span style={{ color: T.t4, fontSize: 9 }}>▾</span>}
                          </span>
                          {sel === ('g' + g.id) && (
                            <Popover minWidth={260}>
                              {advertisers.map(a => (
                                <Option key={a.id} active={a.id === g.adv_id} label={a.name}
                                  onPick={() => {
                                    setGroups(gs => gs.map(x => (x.id === g.id ? {
                                      ...x, adv: a.name, adv_id: a.id,
                                      // сброс брендов при смене рекламодателя — списки брендов разные
                                      brands: x.brands.map(b => ({ ...b, brand: '', brand_id: null })),
                                    } : x)));
                                    setSel(null);
                                  }} />
                              ))}
                            </Popover>
                          )}
                        </span>
                        <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4, whiteSpace: 'nowrap' }}>{g.brands.length} бренд.</span>
                      </span>
                      <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, textAlign: 'right' }}>{plan ? num(plan) : '—'}</span>
                      {MONTHS.map((m, i) => {
                        const p = g.brands.reduce((a, b) => a + monthValue(b, i), 0);
                        const f = g.brands.reduce((a, b) => a + factOf(b, i), 0);
                        const bk = g.brands.reduce((a, b) => a + bookedOf(b, i), 0);
                        return (
                          <span key={m} title={`${m} · план ${p ? num(p) + ' ₽' : '—'}${f ? ' · факт ' + num(f) + ' ₽' : ''}${bk ? ' · бронь ' + num(bk) + ' ₽' : ''}`}
                            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: '5px 4px', borderRadius: 9, background: p ? T.planTileBg : T.subtle, border: `1px solid ${p ? T.planTileBorder : T.inner}` }}>
                            <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: p ? T.t1 : T.t5 }}>{p ? kk(p) : '—'}</span>
                            {(f || bk) > 0 && <span style={{ fontFamily: T.mono, fontSize: 9, color: f ? T.fact : T.bookedGrey }}>{f ? kk(f) : 'бронь ' + kk(bk)}</span>}
                          </span>
                        );
                      })}
                      <span style={{ display: 'flex', justifyContent: 'center' }}>
                        {!readOnly && (
                          <IconBtn size={26} title="Удалить рекламодателя из плана"
                            onClick={() => { stop(); askDelete({ kind: 'group', gid: g.id, label: g.adv ? `Рекламодатель «${g.adv}»` : 'Рекламодатель' }); }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" /></svg>
                          </IconBtn>
                        )}
                      </span>
                    </div>

                    {/* бренды */}
                    {g.open && (
                      <div style={{ display: 'flex', flexDirection: 'column', background: T.nested, borderRadius: 12, margin: '3px 0 8px', padding: '4px 8px', animation: `rowIn .24s ${T.ease} both` }}>
                        {g.brands.map(b => {
                          const brandList = (advById[g.adv_id] && advById[g.adv_id].brands) || [];
                          // сумма закреплённых месяцев; если она больше годового плана — план не сходится
                          const lockedSum = Object.keys(b.locks).reduce((a, k) => a + (b.on[k] && b.sums[k] != null ? b.sums[k] : 0), 0);
                          const overLocked = Object.keys(b.locks).length > 0 && lockedSum > (b.plan || 0);
                          // сводка по сметченным сделкам бренда (все месяцы)
                          const allDeals = Object.values(b.deals || {}).reduce((a, arr) => a.concat(arr), []);
                          const dCount = allDeals.length;
                          const dFact = allDeals.reduce((a, d) => a + (d[2] ? d[1] : 0), 0);
                          const dBooked = allDeals.reduce((a, d) => a + (d[2] ? 0 : d[1]), 0);
                          const brandLocked = !!b.brand_id;   // после выбора бренд фиксируется (копия — для нового)
                          return (
                            <div key={b.id} title={overLocked ? `Закреплено ${num(lockedSum)} ₽ — больше годового плана` : undefined}
                              style={{ display: 'grid', gridTemplateColumns: PLAN_COLS, gap: 6, alignItems: 'center', padding: '7px 0', borderTop: `1px solid ${T.nestedRow}`, background: overLocked ? '#FCEBEC' : undefined, borderRadius: overLocked ? 8 : undefined }}>
                              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, paddingLeft: 27 }}>
                                <span data-pop-root style={{ position: 'relative', minWidth: 0, flex: '0 1 auto' }}>
                                  <span className={readOnly || brandLocked ? undefined : 'yp-field'} title={brandLocked ? 'Бренд зафиксирован. Для нового — кнопка «копировать» в конце строки' : undefined}
                                    onClick={() => { if (!readOnly && !brandLocked) toggleSel('b' + b.id); }} style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 10px', maxWidth: 190, boxSizing: 'border-box',
                                    background: brandLocked ? T.subtle : T.card, border: `1px solid ${b.brand_id ? T.border : T.emptyBorder}`, borderRadius: 9,
                                    fontSize: 12, fontWeight: 600, color: b.brand_id ? T.t1 : T.warning, cursor: (readOnly || brandLocked) ? 'default' : 'pointer', whiteSpace: 'nowrap',
                                  }}><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{b.brand || 'выберите бренд'}</span>{!readOnly && !brandLocked && <span style={{ color: T.t4, fontSize: 9, flex: '0 0 auto' }}>▾</span>}</span>
                                  {sel === ('b' + b.id) && (
                                    <Popover minWidth={200}>
                                      {brandList.length
                                        ? brandList.map(x => (
                                          <Option key={x.id} active={x.id === b.brand_id} label={x.name}
                                            onPick={() => { patchBrand(g.id, b.id, { brand: x.name, brand_id: x.id }); setSel(null); }} />
                                        ))
                                        : <Option active={false} label="— выберите рекламодателя" onPick={() => setSel(null)} />}
                                    </Popover>
                                  )}
                                </span>
                                {dCount > 0 && (
                                  <span title={`Сметчено сделок: ${dCount} · факт ${num(dFact)} ₽ · бронь ${num(dBooked)} ₽`}
                                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', borderRadius: 7, background: dBooked > 0 ? '#F0F2F7' : T.onBg, color: dBooked > 0 ? T.t3 : T.factText, fontFamily: T.mono, fontSize: 9.5, fontWeight: 700, whiteSpace: 'nowrap', flex: '0 0 auto' }}>
                                    <Dot color={dFact > 0 ? T.fact : T.bookedGrey} size={6} />{dCount} сд · {kk(dFact + dBooked)}
                                  </span>
                                )}
                              </span>

                              <span style={{ display: 'flex', alignItems: 'center', gap: 4, height: 28, padding: '0 4px 0 8px', background: T.card, border: `1px solid ${overLocked ? T.danger : T.border}`, borderRadius: 9 }}>
                                <input value={b.plan ? num(b.plan) : ''} placeholder="" disabled={readOnly} onChange={e => patchBrand(g.id, b.id, { plan: parseN(e.target.value) })}
                                  style={{ width: '100%', minWidth: 0, border: 'none', background: 'transparent', outline: 'none', fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, textAlign: 'right', color: overLocked ? T.danger : T.t1 }} />
                                {!readOnly && (
                                  <span className="yp-ghost" title="Распределить остаток плана по незакреплённым месяцам" onClick={() => distribute(g.id, b)}
                                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 20, height: 20, borderRadius: 6, color: T.accent, cursor: 'pointer', flex: '0 0 20px' }}><Spread /></span>
                                )}
                              </span>

                              {b.on.map((onRaw, i) => {
                                const on = !!onRaw;   // b.on[i] — число 0/1; {0 && …} отрендерил бы литерал «0»
                                const locked = !!b.locks[i];
                                const value = monthValue(b, i);
                                const editing = edit === `${b.id}_${i}`;
                                const items = b.products[i] || [];
                                const deals = b.deals[i] || [];
                                const popKey = `p${b.id}_${i}`;
                                return (
                                  <span key={i} style={{ position: 'relative', zIndex: sel === popKey ? 40 : 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    {deals.length > 0 && (
                                      <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                                        {deals.map(d => (
                                          <span key={d[0]} title={`${d[0]} · ${num(d[1])} ₽ · ${d[2] ? 'закрыта' : 'бронь'}`}
                                            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '1px 4px', borderRadius: 5, background: d[2] ? T.onBg : '#F0F2F7', color: d[2] ? T.factText : T.t3, fontFamily: T.mono, fontSize: 8.5, fontWeight: 700 }}>
                                            {d[0]} · {kk(d[1])}
                                          </span>
                                        ))}
                                      </span>
                                    )}
                                    <span onClick={() => {
                                      if (readOnly) return;
                                      const on2 = b.on.slice(); on2[i] = on ? 0 : 1;
                                      const p = { ...b.products }, s = { ...b.sums }, l = { ...b.locks };
                                      if (on) { delete p[i]; delete s[i]; delete l[i]; }
                                      patchBrand(g.id, b.id, { on: on2, products: p, sums: s, locks: l });
                                    }}
                                      title={`${MONTHS[i]}${on ? ' · ' + num(value) + ' ₽' + (locked ? ' (закреплено)' : '') : ' · не планируется'}`}
                                      style={{
                                        position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
                                        minHeight: 42, padding: '5px 4px', borderRadius: 9, cursor: readOnly ? 'default' : 'pointer',
                                        background: on ? (locked ? T.lockBg : T.onBg) : T.subtle,
                                        border: `1px solid ${on ? (locked ? T.lockBorder : T.onBorder) : T.inner}`,
                                      }}>
                                      {on && !editing && (
                                        <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: locked ? T.accentHover : T.factText }}>{kk(value)}</span>
                                      )}
                                      {on && editing && (
                                        <input autoFocus defaultValue={b.sums[i] != null ? num(b.sums[i]) : (value ? num(value) : '')}
                                          onClick={stop} onBlur={e => { const v = parseN(e.target.value); const s = { ...b.sums }; if (v) s[i] = v; else delete s[i]; patchBrand(g.id, b.id, { sums: s }); setEdit(null); }}
                                          onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                                          style={{ width: '100%', minWidth: 0, boxSizing: 'border-box', height: 20, padding: '0 4px', border: `1px solid ${T.accent}`, borderRadius: 6, background: 'rgba(255,255,255,.85)', fontFamily: T.mono, fontSize: 11, fontWeight: 700, textAlign: 'center', outline: 'none' }} />
                                      )}
                                      {on && !readOnly && (
                                        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                          <span title="Изменить сумму" onClick={e => { stop(e); setEdit(`${b.id}_${i}`); setSel(null); }}
                                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16, borderRadius: 5, background: 'rgba(255,255,255,.55)', color: locked ? T.accent : '#4F9C82' }}><Pencil /></span>
                                          <span title={locked ? 'Снять закрепление суммы' : 'Закрепить сумму месяца'}
                                            onClick={e => {
                                              stop(e);
                                              const l = { ...b.locks }, s = { ...b.sums };
                                              if (locked) delete l[i]; else { l[i] = 1; if (s[i] == null) s[i] = value; }
                                              patchBrand(g.id, b.id, { locks: l, sums: s });
                                            }}
                                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16, borderRadius: 5, background: locked ? T.accent : 'rgba(255,255,255,.55)', color: locked ? '#FFF' : '#4F9C82' }}><Lock locked={locked} /></span>
                                          <span data-pop-root style={{ position: 'relative' }}>
                                            <span title="Продукты месяца" onClick={e => { stop(e); toggleSel(popKey); }}
                                              style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 16, height: 16, padding: '0 4px', borderRadius: 5, background: items.length ? 'rgba(255,255,255,.7)' : 'transparent', color: items.length ? T.factText : '#4F9C82', fontFamily: T.mono, fontSize: 8.5, fontWeight: 700 }}>
                                              {items.length || '+ прод.'}
                                            </span>
                                            {sel === popKey && (
                                              <Popover minWidth={200}>
                                                <span style={{ ...colHead, padding: '4px 10px 6px' }}>{MONTHS[i]} · продукты</span>
                                                {services.map(pr => {
                                                  const active = items.includes(pr.id);
                                                  return (
                                                    <Option key={pr.id} active={active} label={pr.name} onPick={() => {
                                                      const next = active ? items.filter(x => x !== pr.id) : [...items, pr.id];
                                                      const p = { ...b.products };
                                                      if (next.length) p[i] = next; else delete p[i];
                                                      patchBrand(g.id, b.id, { products: p });
                                                    }} />
                                                  );
                                                })}
                                              </Popover>
                                            )}
                                          </span>
                                        </span>
                                      )}
                                    </span>
                                    {on && items.length > 0 && (
                                      <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                                        {items.map(id => (
                                          <span key={id} title={svcName[id]}
                                            style={{ padding: '1px 5px', borderRadius: 5, background: T.accentTint, color: T.accent, fontSize: 8.5, fontWeight: 700, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {svcName[id] || `#${id}`}
                                          </span>
                                        ))}
                                      </span>
                                    )}
                                  </span>
                                );
                              })}
                              <span style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 4 }}>
                                {!readOnly && (
                                  <IconBtn size={26} title="Копировать настройки года (новый бренд)"
                                    onClick={() => copyBrand(g.id, b)}><Copy /></IconBtn>
                                )}
                                {!readOnly && (
                                  <IconBtn size={26} title="Удалить бренд из плана"
                                    onClick={() => askDelete({ kind: 'brand', gid: g.id, bid: b.id, label: b.brand ? `Бренд «${b.brand}»` : 'Бренд' })}>
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" /></svg>
                                  </IconBtn>
                                )}
                              </span>
                            </div>
                          );
                        })}

                        {!readOnly && (
                          <div className="yp-ghost-add" onClick={() => setGroups(gs => gs.map(x => (x.id === g.id ? {
                            ...x, brands: [...x.brands, blankBrand(++seq.current)],
                          } : x)))}
                            style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0 4px', padding: '10px 12px', border: `1px dashed ${T.accentBorder}`, borderRadius: 11, cursor: 'pointer' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7, background: T.accentTint, color: T.accent }}><Plus /></span>
                            <span style={{ fontSize: 12, fontWeight: 600, color: T.accent }}>Добавить бренд</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {!readOnly && (
                <div className="yp-ghost-add" onClick={addGroup}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '8px 0 2px', padding: '10px 12px', border: `1px dashed ${T.accentBorder}`, borderRadius: 11, cursor: 'pointer' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7, background: T.accentTint, color: T.accent }}><Plus /></span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.accent }}>Добавить рекламодателя</span>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: PLAN_COLS, gap: 6, alignItems: 'center', padding: '12px 8px 6px' }}>
                <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого план</span>
                <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{num(totals.plan)} ₽</span>
                {monthTotals.map((m, i) => (
                  <span key={i} style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, textAlign: 'center', color: m.plan ? T.t1 : T.t5 }}>{m.plan ? kk(m.plan) : '—'}</span>
                ))}
                <span />
              </div>
            </div>
          </div>
        </Card>

        {/* выполнение плана */}
        <Card delay={0.28} pad="20px 24px 16px">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em' }}>Выполнение плана</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, fontSize: 11.5, color: T.t3 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ display: 'inline-flex', gap: 1 }}><Dot color={T.danger} /><Dot color={T.warning} /><Dot color={T.fact} /></span>
                факт · цвет по выполнению
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.booked} />бронь</span>
            </span>
            <span style={meta}>по рекламодателям · факт из закрытых сделок</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, padding: '0 4px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
            <span>Рекламодатель / бренд</span><span style={{ textAlign: 'right' }}>План</span>
            <span style={{ textAlign: 'right' }}>Факт</span><span>Выполнение</span>
            <span style={{ textAlign: 'right' }}>Бронь</span><span style={{ textAlign: 'right' }}>Δ</span>
          </div>

          {groups.filter(g => g.adv_id).map((g, gi) => {
            const plan = g.brands.reduce((a, b) => a + b.plan, 0);
            const fact = g.brands.reduce((a, b) => a + sumMonths(b, factOf), 0);
            const booked = g.brands.reduce((a, b) => a + sumMonths(b, bookedOf), 0);
            const pct = plan ? (fact / plan) * 100 : 0;
            const gap = fact + booked - plan;
            const open = openProg === g.id;
            return (
              <div key={g.id} style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="yp-row" onClick={() => setOpenProg(open ? null : g.id)}
                  style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, alignItems: 'center', padding: '7px 4px', borderRadius: 9, borderBottom: `1px solid ${T.row}`, background: open ? T.nested : 'transparent', cursor: 'pointer' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, borderRadius: 6, background: T.accentTint, color: T.accent, fontSize: 8, flex: '0 0 18px' }}>{open ? '▲' : '▼'}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{g.adv}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4, whiteSpace: 'nowrap' }}>{g.brands.length} бренд.</span>
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, textAlign: 'right' }}>{kk(plan)} ₽</span>
                  <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: T.fact, textAlign: 'right' }}>{kk(fact)} ₽</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                    <ProgressBar plan={plan} fact={fact} booked={booked} delay={gi * 0.05} />
                    <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, flex: '0 0 46px' }}>
                      <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: pctColor(pct) }}>{pct.toFixed(0)} %</span>
                      {booked > 0 && plan > 0 && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.bookedText }}>+{((booked / plan) * 100).toFixed(0)} %</span>}
                    </span>
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3, textAlign: 'right' }}>{booked ? kk(booked) + ' ₽' : '—'}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: gap >= 0 ? T.fact : T.danger, textAlign: 'right' }}>{(gap >= 0 ? '+' : '−') + kk(Math.abs(gap))}</span>
                </div>

                {open && (
                  <div style={{ display: 'flex', flexDirection: 'column', background: T.nested, borderRadius: 12, margin: '3px 0 8px', padding: '4px 8px', animation: `rowIn .24s ${T.ease} both` }}>
                    {g.brands.map(b => {
                      const bf = sumMonths(b, factOf), bb = sumMonths(b, bookedOf);
                      const bp = b.plan ? (bf / b.plan) * 100 : 0;
                      const bgap = bf + bb - b.plan;
                      return (
                        <div key={b.id} style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, alignItems: 'center', padding: '6px 0', borderTop: `1px solid ${T.nestedRow}` }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, paddingLeft: 27 }}>
                            <Dot color={pctColor(bp)} size={7} />
                            <span style={{ fontSize: 12, fontWeight: 600, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.brand || '—'}</span>
                            <span style={{ fontFamily: T.mono, fontSize: 9, color: T.t4, whiteSpace: 'nowrap' }}>{b.on.reduce((a, v) => a + v, 0)} мес.</span>
                          </span>
                          <span style={{ fontFamily: T.mono, fontSize: 11.5, textAlign: 'right' }}>{kk(b.plan)} ₽</span>
                          <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: T.fact, textAlign: 'right' }}>{kk(bf)} ₽</span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                            <ProgressBar plan={b.plan} fact={bf} booked={bb} height={6} bg="#E1E7F7" />
                            <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: pctColor(bp), flex: '0 0 42px', textAlign: 'right' }}>{bp.toFixed(0)} %</span>
                          </span>
                          <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.t3, textAlign: 'right' }}>{bb ? kk(bb) + ' ₽' : '—'}</span>
                          <span style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: 700, color: bgap >= 0 ? T.fact : T.danger, textAlign: 'right' }}>{(bgap >= 0 ? '+' : '−') + kk(Math.abs(bgap))}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          <div style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, alignItems: 'center', padding: '12px 4px 0' }}>
            <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого</span>
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{num(totals.plan)} ₽</span>
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.fact, textAlign: 'right' }}>{num(totals.fact)} ₽</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <ProgressBar plan={totals.plan} fact={totals.fact} booked={totals.booked} />
              <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, flex: '0 0 46px' }}>
                <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: pctColor(totals.pct) }}>{totals.pct.toFixed(0)} %</span>
                {totals.booked > 0 && totals.plan > 0 && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.bookedText }}>+{((totals.booked / totals.plan) * 100).toFixed(0)} %</span>}
              </span>
            </span>
            <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: T.t3, textAlign: 'right' }}>{kk(totals.booked)} ₽</span>
            <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: (totals.fact + totals.booked - totals.plan) >= 0 ? T.fact : T.danger, textAlign: 'right' }}>
              {((totals.fact + totals.booked - totals.plan) >= 0 ? '+' : '−') + kk(Math.abs(totals.fact + totals.booked - totals.plan))}
            </span>
          </div>
        </Card>
        </>}
      </div>
    </>
  );
}

/* ── сводка «Показать все» — read-only, группировка по сейлзам ────────── */
function AllSummary({ year, data = [] }) {
  const [open, setOpen] = useState(null);
  const tot = data.reduce((a, r) => ({ plan: a.plan + r.plan, fact: a.fact + r.fact, booked: a.booked + r.booked }), { plan: 0, fact: 0, booked: 0 });
  const pct = tot.plan ? (tot.fact / tot.plan) * 100 : 0;
  const months = MONTHS.map((_, i) => data.reduce((a, r) => a + ((r.months && r.months[i]) || 0), 0));
  const maxMonth = Math.max(1, ...months);
  const kpi = [
    { label: 'План года', value: mln(tot.plan), unit: 'млн ₽', color: T.t1, hint: `${data.length} сейлзов` },
    { label: 'Факт', value: mln(tot.fact), unit: 'млн ₽', color: T.fact, hint: 'закрытые сделки' },
    { label: 'Бронь', value: mln(tot.booked), unit: 'млн ₽', color: T.bookedGrey, hint: 'сделки в работе' },
    { label: 'Выполнение', value: pct.toFixed(0), unit: '%', color: pctColor(pct), hint: `остаток ${mln(Math.max(0, tot.plan - tot.fact))} млн ₽` },
  ];
  return (
    <>
      <div className="yp-toprow">
        <Card delay={0.07} pad="2px 22px" gap={0} style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', alignContent: 'center' }}>
          {kpi.map((k, i) => (
            <div key={k.label} style={{ padding: '16px 18px 16px 0', marginRight: 18, display: 'flex', flexDirection: 'column', gap: 8, borderRight: `1px solid ${i === 3 ? 'transparent' : T.inner}` }}>
              <span style={{ ...meta, color: T.t3 }}>{k.label}</span>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                <span style={{ fontFamily: T.mono, fontSize: 34, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: k.color }}>{k.value}</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: T.t3 }}>{k.unit}</span>
              </span>
              <span style={{ fontSize: 11.5, color: T.t4 }}>{k.hint}</span>
            </div>
          ))}
        </Card>
        <Card delay={0.14}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em' }}>План по месяцам · все сейлзы</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, minHeight: 110 }}>
            {months.map((m, i) => {
              const ROWS = 10; const planCells = Math.round((m / maxMonth) * ROWS);
              return (
                <span key={i} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 1, justifyContent: 'flex-end' }}>
                    {Array.from({ length: ROWS }, (_, k) => { const rank = ROWS - k; return <span key={k} style={{ height: 7, borderRadius: 2, background: rank <= planCells ? T.planBar : T.inner }} />; })}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4 }}>{i % 2 === 0 ? MONTHS[i] : ''}</span>
                </span>
              );
            })}
          </div>
        </Card>
      </div>

      <Card delay={0.21} pad="20px 24px 16px">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.02em' }}>Годовой план по сейлзам</span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, fontSize: 11.5, color: T.t3 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ display: 'inline-flex', gap: 1 }}><Dot color={T.danger} /><Dot color={T.warning} /><Dot color={T.fact} /></span>
              факт · цвет по выполнению
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Dot color={T.booked} />бронь</span>
          </span>
          <span style={meta}>{year} · клик по строке — детализация по рекламодателям</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, padding: '0 4px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
          <span>Сейлз / рекламодатель</span><span style={{ textAlign: 'right' }}>План</span>
          <span style={{ textAlign: 'right' }}>Факт</span><span>Выполнение</span>
          <span style={{ textAlign: 'right' }}>Бронь</span><span style={{ textAlign: 'right' }}>Δ</span>
        </div>

        {data.length === 0 && <div style={{ padding: '24px 4px', color: T.t4, fontSize: 13 }}>Планов на {year} ещё нет.</div>}

        {data.map((r, ri) => {
          const p = r.plan ? (r.fact / r.plan) * 100 : 0;
          const gap = r.fact + r.booked - r.plan;
          const isOpen = open === (r.rep_id ?? `x${ri}`);
          const key = r.rep_id ?? `x${ri}`;
          return (
            <div key={key} style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="yp-row" onClick={() => setOpen(isOpen ? null : key)}
                style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, alignItems: 'center', padding: '8px 4px', borderRadius: 9, borderBottom: `1px solid ${T.row}`, background: isOpen ? T.nested : 'transparent', cursor: 'pointer' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, borderRadius: 6, background: T.accentTint, color: T.accent, fontSize: 8, flex: '0 0 18px' }}>{isOpen ? '▲' : '▼'}</span>
                  <span style={{ fontSize: 13.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.rep_name}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.t4, whiteSpace: 'nowrap' }}>{r.advertisers.length} рекл.</span>
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{kk(r.plan)} ₽</span>
                <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: T.fact, textAlign: 'right' }}>{kk(r.fact)} ₽</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                  <ProgressBar plan={r.plan} fact={r.fact} booked={r.booked} delay={ri * 0.04} />
                  <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, flex: '0 0 46px' }}>
                    <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: pctColor(p) }}>{p.toFixed(0)} %</span>
                    {r.booked > 0 && r.plan > 0 && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.bookedText }}>+{((r.booked / r.plan) * 100).toFixed(0)} %</span>}
                  </span>
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t3, textAlign: 'right' }}>{r.booked ? kk(r.booked) + ' ₽' : '—'}</span>
                <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: gap >= 0 ? T.fact : T.danger, textAlign: 'right' }}>{(gap >= 0 ? '+' : '−') + kk(Math.abs(gap))}</span>
              </div>
              {isOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', background: T.nested, borderRadius: 12, margin: '3px 0 8px', padding: '4px 8px', animation: `rowIn .24s ${T.ease} both` }}>
                  {r.advertisers.map((a, ai) => {
                    const ap = a.plan ? (a.fact / a.plan) * 100 : 0;
                    const agap = a.fact + a.booked - a.plan;
                    return (
                      <div key={ai} style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, alignItems: 'center', padding: '6px 0', borderTop: `1px solid ${T.nestedRow}` }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, paddingLeft: 27 }}>
                          <Dot color={pctColor(ap)} size={7} />
                          <span style={{ fontSize: 12, fontWeight: 600, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                        </span>
                        <span style={{ fontFamily: T.mono, fontSize: 11.5, textAlign: 'right' }}>{kk(a.plan)} ₽</span>
                        <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: T.fact, textAlign: 'right' }}>{kk(a.fact)} ₽</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                          <ProgressBar plan={a.plan} fact={a.fact} booked={a.booked} height={6} bg="#E1E7F7" />
                          <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: pctColor(ap), flex: '0 0 42px', textAlign: 'right' }}>{ap.toFixed(0)} %</span>
                        </span>
                        <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.t3, textAlign: 'right' }}>{a.booked ? kk(a.booked) + ' ₽' : '—'}</span>
                        <span style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: 700, color: agap >= 0 ? T.fact : T.danger, textAlign: 'right' }}>{(agap >= 0 ? '+' : '−') + kk(Math.abs(agap))}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        <div style={{ display: 'grid', gridTemplateColumns: PROG_COLS, gap: 12, alignItems: 'center', padding: '12px 4px 0' }}>
          <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого</span>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{num(tot.plan)} ₽</span>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.fact, textAlign: 'right' }}>{num(tot.fact)} ₽</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <ProgressBar plan={tot.plan} fact={tot.fact} booked={tot.booked} />
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: pctColor(pct), flex: '0 0 46px', textAlign: 'right' }}>{pct.toFixed(0)} %</span>
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: T.t3, textAlign: 'right' }}>{kk(tot.booked)} ₽</span>
          <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: (tot.fact + tot.booked - tot.plan) >= 0 ? T.fact : T.danger, textAlign: 'right' }}>
            {((tot.fact + tot.booked - tot.plan) >= 0 ? '+' : '−') + kk(Math.abs(tot.fact + tot.booked - tot.plan))}
          </span>
        </div>
      </Card>
    </>
  );
}

/* ── глобальные стили ───────────────────────────────────────────────── */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
@keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
@keyframes rowIn  { from { opacity:0; transform:translateY(-6px) } to { opacity:1; transform:none } }
@keyframes popIn  { from { opacity:0; transform:translateY(-4px) } to { opacity:1; transform:none } }
@keyframes barGrow { from { transform:scaleX(0) } to { transform:scaleX(1) } }
@media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
.yp-row:hover { background:${T.nested} }
.yp-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
.yp-field:hover { border-color:${T.hoverBorder} }
.yp-opt:hover { background:${T.subtle} }
.yp-primary:hover { filter:brightness(0.94) }
.yp-link:hover { color:${T.accentHover} }
.yp-ghost-add:hover { border-color:${T.accent}; background:${T.nested} }
/* верхний ряд: до 1920 — 2 этажа (KPI сверху, график снизу), после — в один ряд */
.yp-toprow { display:grid; grid-template-columns:1fr; gap:16px; align-items:stretch }
@media (min-width:1921px) {
  .yp-toprow { grid-template-columns:minmax(0,1fr) minmax(0,1.15fr) }
}
`;
