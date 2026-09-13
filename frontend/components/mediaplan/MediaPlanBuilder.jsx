/**
 * Конструктор медиаплана — десктоп (≥ 1024px, оптимум 1440–2560).
 * Зависимость только React. Стили инлайновые, токены — из design_system/ds.jsx.
 * Данные-справочники в CATALOG / EXTRA_CATALOG / STAFF — заменить на API.
 */
import React, { useMemo, useRef, useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { GenTitleBtn, MONO, UI } from '../salesTableKit';
import { overlayClose } from '@/lib/overlay'
import { buildTitle, separatePriceSet } from '@/lib/dealTitle'
import { isCpm, rowImp } from '@/lib/mpRow'

/* ── токены ─────────────────────────────────────────────────────────────
   Значения берём из нашей дизайн-системы (globals.css), НЕ вводим третью
   ветку палитры. T — тонкий адаптер хендоффа на наши var(--*). */
export const T = {
  canvas: 'var(--bg-canvas)', card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', tint: 'var(--bg-tint)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)', hoverBorder: 'var(--border-hover)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)',
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)', accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)',
  income: 'var(--income)', incomeTint: 'var(--income-tint)',
  warning: 'var(--warning)', warningTint: 'var(--warning-tint)', warningText: 'var(--warning-text)',
  emptyBg: 'var(--empty-bg)', emptyBorder: 'var(--empty-border)', emptyText: 'var(--empty-text)', emptyNum: 'var(--empty-num)',
  danger: 'var(--danger)', dangerTint: 'var(--danger-tint)', violet: 'var(--mixed)', violetTint: 'var(--mixed-tint)',
  shadow: 'var(--shadow-card)',
  pop: '0 8px 28px rgba(28,36,51,.14)',
  mono: MONO, sans: UI,
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};
const VAT = 0.22;

/* ── справочники (заменить на API) ──────────────────────────────────── */
export const CATALOG = [
  { position: 'Simb-ad Альфарм — Таргет', formats: ['Banners', 'Rich', 'Video'], unit: 280 },
  { position: 'Simb-ad Альфарм — Ретаргет', formats: ['Banners', 'Rich'], unit: 280 },
  { position: 'Simb-ad Аптечество — Таргет', formats: ['Banners', 'Video'], unit: 240 },
  { position: 'Simb-ad ЕАптека — Каталог', formats: ['Product card', 'Banners'], unit: 320 },
  { position: 'Simb-ad 366.ru — Главная', formats: ['Banners', 'Rich'], unit: 410 },
  { position: 'Simb-ad Кросс-сеть — Охват', formats: ['Banners', 'Video'], unit: 195 },
];
export const MODELS = ['CPM', 'CPC', 'Fix'];
/* Объём по умолчанию зависит от МОДЕЛИ, потому что колонка «Объём» означает разное:
   у CPM это показы (500 000 — обычный старт разговора), у Фикса и Пакета — ШТУКИ
   закупки. Один дефолт на всех давал 500 000 штук Polza по 80 000 ₽, то есть медиаплан
   на 40 миллиардов (владелец 08.09.2026). */
const VOL_CPM = 500000;
const VOL_UNIT = 1;
const defaultVolume = (model) => (isCpm(model) ? VOL_CPM : VOL_UNIT);
export const EXTRA_CATALOG = [
  { name: 'Sales lift отчёт', period: 'первый месяц', price: 150000 },
  { name: 'Brand lift исследование', period: 'по итогам РК', price: 180000 },
  { name: 'Медиааудит размещения', period: 'ежемесячно', price: 90000 },
  { name: 'Post-buy аналитика', period: 'по итогам РК', price: 120000 },
  { name: 'Креативная адаптация', period: 'разово', price: 60000 },
];
export const MODES = ['Полная цена', 'Скидка 50 %', 'Бонус'];
const MODE_RATE = { 'Полная цена': 1, 'Скидка 50 %': 0.5, 'Бонус': 0 };
const TG_GROUPS = [['audience', 'Аудитория'], ['buys', 'Покупают'], ['interests', 'Интересы'], ['behavior', 'Поведение'], ['competitors', 'Конкуренты']];
// Ответственные приходят из справочника «Сотрудники» (рабочие группы seller/account).
// Каждый элемент — { id, name, is_master }. Демо-значения ниже — фолбэк без API.
export const STAFF = {
  'Продавец': [{ id: -1, name: 'Андрей Мошков' }, { id: -2, name: 'Игорь Савельев' }, { id: -3, name: 'Ольга Пименова' }],
  'Аккаунт': [{ id: -4, name: 'Валерия Монич' }, { id: -5, name: 'Мария Круглова' }, { id: -6, name: 'Анна Ветрова' }],
};
// Роль в конструкторе → поле МП. Порядок = порядок строк в блоке «Ответственные».
const OWNER_FIELD = { 'Продавец': 'sales_rep_id', 'Аккаунт': 'account_manager_id', 'Трафик': 'traffic_manager_id' };
const ROLE_TINT = {
  'Продавец': [T.accentTint, T.accent],
  'Аккаунт': [T.incomeTint, T.income],
  'Трафик': [T.violetTint, T.violet],
};

/* ── формат ─────────────────────────────────────────────────────────── */
const num = v => Math.round(v).toLocaleString('ru-RU');
const dec = v => v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽';
const rub = v => Math.round(v).toLocaleString('ru-RU') + ' ₽';
const pct = v => (v * 100).toFixed(2).replace('.', ',') + ' %';
const parseN = v => {
  const n = parseFloat(String(v ?? '').replace(/\s|₽|%|\u00a0/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
};
const initials = n => n.split(' ').map(w => w[0]).join('').slice(0, 2);

/* ── сетки (одна на шапку, строки и итог) ───────────────────────────── */
const MAIN_COLS =
  '16px minmax(0,1.05fr) minmax(0,0.56fr) minmax(0,0.5fr) 40px minmax(56px,0.52fr) minmax(52px,0.48fr) minmax(34px,0.28fr) minmax(96px,1fr) minmax(96px,1fr) 20px';
const EXTRA_COLS = '16px minmax(0,1.5fr) minmax(0,0.85fr) 88px 1fr 96px 108px 108px 20px';
const FC_COLS = 'minmax(220px,1.6fr) repeat(15,minmax(64px,1fr))';
// Инвентарь строки размещения (при раздельном прайсе услуги). App → IN-App в UI.
const INV_LABEL = { web: 'Web', app: 'IN-App', cross: 'Кросс-девайс' };

/* ── примитивы ──────────────────────────────────────────────────────── */
const capTitle = { fontFamily: T.mono, fontSize: 13, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: T.t3 };
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const meta = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };

const Card = ({ delay = 0, pad = '14px 22px 12px', gap = 10, style, children }) => (
  <section style={{
    background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 18,
    padding: pad, display: 'flex', flexDirection: 'column', gap,
    animation: `riseIn .4s ${T.ease} ${delay}s both`, ...style,
  }}>{children}</section>
);

/** Поповер выбора. Закрывается по клику вне и Esc (см. useDismiss). */
// Поповер рендерится ПОРТАЛОМ в document.body (fixed от координат триггера) — физически
// вне дерева карточек, поэтому никакие стекинг-контексты/overflow/transform не мешают.
// data-pop-root на самом поповере — чтобы клик внутри не закрывал его (см. useDismiss).
const Popover = ({ open, minWidth = 240, children }) => {
  const anchor = useRef(null);   // невидимый маркер на месте использования
  const [pos, setPos] = useState(null);
  React.useLayoutEffect(() => {
    if (!open) { setPos(null); return; }
    const a = anchor.current?.parentElement;   // контейнер-триггер (data-pop-root)
    if (!a) return;
    const r = a.getBoundingClientRect();
    const left = Math.max(8, Math.min(r.left, window.innerWidth - minWidth - 12));
    setPos({ top: r.bottom + 4, left });
  }, [open]);
  return (
    <>
      <span ref={anchor} style={{ display: 'none' }} />
      {open && pos && typeof document !== 'undefined' && createPortal(
        <span data-pop-root style={{
          position: 'fixed', top: pos.top, left: pos.left, zIndex: 3000, minWidth,
          background: T.card, border: `1px solid ${T.border}`, boxShadow: T.pop, borderRadius: 12,
          padding: 6, display: 'flex', flexDirection: 'column', maxHeight: 320, overflowY: 'auto',
          animation: `popIn .18s ${T.ease} both`,
        }}>{children}</span>,
        document.body
      )}
    </>
  );
};

const Option = ({ active, label, hint, onPick }) => (
  <span className="mp-opt" onClick={onPick} style={{
    display: 'flex', alignItems: 'baseline', gap: 10, padding: '8px 10px', borderRadius: 9,
    background: active ? T.accentTint : 'transparent', cursor: 'pointer',
  }}>
    <span style={{ fontSize: 12, fontWeight: 600, color: active ? T.accent : T.t1 }}>{label}</span>
    {hint && <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9.5, color: T.t4, whiteSpace: 'nowrap' }}>{hint}</span>}
  </span>
);

const Field = ({ empty, children, onClick, caret = true }) => (
  <span className={onClick ? 'mp-field' : undefined} onClick={onClick} style={{
    display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, height: 32, boxSizing: 'border-box',
    padding: '0 10px', border: `1px solid ${empty ? T.emptyBorder : T.border}`, borderRadius: 9,
    background: empty ? T.card : T.subtle, cursor: onClick ? 'pointer' : 'default',
  }}>
    {children}
    {caret && <span style={{ marginLeft: 'auto', color: T.t4, fontSize: 10 }}>▾</span>}
  </span>
);

// Ячейка брифа как в таблице дашборда: лейбл + значение/«—» (клик по значению → поповер
// с поиском). onAddNew — опциональный ввод нового значения прямо в поповере (гео).
function BriefField({ label, open, onToggle, value, options, onPick, placeholder = '—', minWidth = 220, onAddNew, addPlaceholder, emptyHint }) {
  const [q, setQ] = useState('');
  const [nv, setNv] = useState('');
  const sel = options.find(o => String(o.value) === String(value));
  const shown = q.trim() ? options.filter(o => String(o.label || '').toLowerCase().includes(q.trim().toLowerCase())) : options;
  const add = () => { if (nv.trim()) { onAddNew(nv.trim()); setNv(''); } };
  return (
    <span data-pop-root style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '5px 0', borderTop: `1px solid ${T.row}`, minWidth: 0, position: 'relative', zIndex: open ? 1000 : undefined }}>
      <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.3 }}>{label}</span>
      <span className="mp-cell" onClick={onToggle} style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.3, color: sel ? T.t1 : T.t4, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sel ? sel.label : placeholder}</span>
      <Popover open={open} minWidth={minWidth}>
        {options.length > 8 && (
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск"
            style={{ width: '100%', boxSizing: 'border-box', margin: '0 0 4px', padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, outline: 'none', fontFamily: T.sans }} />
        )}
        {!!value && <Option active={false} label="— очистить —" onPick={() => onPick('')} />}
        {shown.map(o => <Option key={o.value} active={String(o.value) === String(value)} label={o.label} onPick={() => onPick(o.value)} />)}
        {!shown.length && !onAddNew && <div style={{ padding: 8, fontSize: 12, color: (!options.length && emptyHint) ? T.warningText : T.t4 }}>{(!options.length && emptyHint) ? emptyHint : 'ничего не найдено'}</div>}
        {onAddNew && (
          <div style={{ display: 'flex', gap: 5, padding: '5px 2px 2px', borderTop: `1px solid ${T.row}`, marginTop: 4 }}>
            <input value={nv} onChange={e => setNv(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') add(); }} placeholder={addPlaceholder || '+ новое'} style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, outline: 'none', fontFamily: T.sans }} />
            <span onClick={add} style={{ display: 'inline-flex', alignItems: 'center', padding: '0 10px', background: T.accent, color: 'var(--bg-card)', borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+</span>
          </div>
        )}
      </Popover>
    </span>
  );
}

// value — «сырое» число/строка; format(value) применяется только когда поле НЕ в фокусе.
// Во время ввода показываем draft (строку как есть) — поэтому курсор не прыгает за копейки.
function NumInput({ value, onChange, format, yellow, align = 'right', size = 10.5, weight = 700, placeholder }) {
  const [draft, setDraft] = useState(null);
  const empty = value === '' || value == null;
  const display = draft != null ? draft : (empty ? '' : (format ? format(value) : value));
  return (
    <input value={display} placeholder={placeholder}
      onFocus={() => setDraft(empty ? '' : String(value).replace('.', ','))}
      onChange={e => { setDraft(e.target.value); onChange(e.target.value); }}
      onBlur={() => setDraft(null)}
      className={yellow ? 'mp-yellow' : 'mp-plain'}
      style={{
        width: '100%', minWidth: 0, boxSizing: 'border-box', height: yellow ? 28 : 32,
        padding: yellow ? '0 7px' : '0 8px',
        background: yellow ? T.emptyBg : T.subtle,
        border: `1px solid ${yellow ? T.emptyBorder : T.border}`, borderRadius: yellow ? 8 : 9,
        fontFamily: T.mono, fontSize: yellow ? 11 : size, fontWeight: weight, color: T.t1,
        textAlign: align, outline: 'none',
      }} />
  );
}

const GhostAdd = ({ label, hint, warn, onClick }) => (
  <div className="mp-ghost" onClick={onClick} style={{
    display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0 2px', padding: '10px 12px',
    border: `1px dashed ${warn ? T.emptyBorder : T.accentBorder}`, borderRadius: 11,
    background: warn ? T.emptyBg : T.card, cursor: 'pointer',
  }}>
    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7, background: T.accentTint, color: T.accent }}>
      <Plus />
    </span>
    <span style={{ fontSize: 12, fontWeight: 600, color: T.accent }}>{label}</span>
    <span style={{ marginLeft: 'auto', ...meta }}>{hint}</span>
  </div>
);

const Warn = ({ children }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: T.warningTint, color: T.warningText, borderRadius: 8, padding: '4px 9px', fontSize: 10.5, fontWeight: 700 }}>
    <span style={{ width: 6, height: 6, borderRadius: 2, background: T.warning }} />{children}
  </span>
);

// Отметка «проверено» у заголовка блока. Обе (размещения + прогноз) обязательны,
// чтобы сохранить МП — чек-лист конкретного сохранения, а не свойство плана.
const VerifyBtn = ({ on, onClick, title, big }) => (
  <span onClick={onClick} title={title}
    style={{
      display: 'inline-flex', alignItems: 'center', gap: big ? 8 : 5,
      height: big ? 38 : 22, padding: big ? '0 16px' : '0 9px', borderRadius: big ? 10 : 7,
      cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
      background: on ? 'var(--income-tint)' : T.card, border: `1px solid ${on ? 'var(--income-border)' : T.border}`,
      color: on ? 'var(--income-fg)' : T.t3, fontSize: big ? 12.5 : 10, fontWeight: 800,
      letterSpacing: '.04em', textTransform: 'uppercase',
      boxShadow: on && big ? '0 1px 0 rgba(31,125,94,.08)' : 'none',
    }}>
    <svg width={big ? 15 : 11} height={big ? 15 : 11} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      {on ? <path d="M20 6L9 17l-5-5" /> : <circle cx="12" cy="12" r="8" strokeWidth="1.8" />}
    </svg>
    Проверено
  </span>
);

const Plus = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>;
const Cross = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>;
const Pencil = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20h4l10-10-4-4L4 16v4z" /><path d="M14.5 5.5l4 4" /></svg>;

const DeleteBtn = ({ onClick }) => (
  <span className="mp-del" onClick={onClick} title="Удалить строку" style={{
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 20, height: 24,
    borderRadius: 7, color: T.t4, cursor: 'pointer', transition: 'background-color 150ms ease, color 150ms ease',
  }}><Cross /></span>
);

/* ── анимация появления/удаления строк ──────────────────────────────── */
function useAnimatedRows(initial) {
  const [rows, setRows] = useState(initial);
  const [entering, setEntering] = useState({});
  const [leaving, setLeaving] = useState({});
  const seq = useRef(100);

  const add = blank => {
    const id = ++seq.current;
    setRows(r => [...r, { id, ...blank }]);
    setEntering(e => ({ ...e, [id]: true }));
    setTimeout(() => setEntering(e => { const n = { ...e }; delete n[id]; return n; }), 420);
    return id;
  };
  const remove = id => {
    setLeaving(l => ({ ...l, [id]: true }));               // 260ms — длительность rowOut
    setTimeout(() => {
      setRows(r => r.filter(x => x.id !== id));
      setLeaving(l => { const n = { ...l }; delete n[id]; return n; });
    }, 260);
  };
  const patch = (id, p) => setRows(r => r.map(x => (x.id === id ? { ...x, ...p } : x)));
  const motion = id => leaving[id]
    ? { animation: `rowOut .26s ${T.ease} both`, pointerEvents: 'none' }
    : entering[id] ? { animation: `rowIn .36s ${T.ease} both` } : {};
  return { rows, setRows, add, remove, patch, motion };
}

/* ── закрытие поповеров по клику вне / Esc ──────────────────────────── */
function useDismiss(setSel) {
  React.useEffect(() => {
    const off = e => { if (!e.target.closest('[data-pop-root]')) setSel(null); };
    const esc = e => { if (e.key === 'Escape') setSel(null); };
    document.addEventListener('mousedown', off);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc); };
  }, [setSel]);
}

/* ══════════════════════════════════════════════════════════════════════
   СТРАНИЦА
   ══════════════════════════════════════════════════════════════════════ */
/* Свод поверхностей строк в одно значение. Правило то же, что на сервере
   (app/sales/row_context.merge_inventory): 'cross' уже означает обе, и он же результат
   при встрече web с app. */
function mergeInventory(values) {
  const vals = new Set((values || []).map(v => String(v || '').trim().toLowerCase()).filter(Boolean));
  if (!vals.size) return '';
  if (vals.has('cross') || (vals.has('web') && vals.has('app'))) return 'cross';
  return [...vals][0];
}

export default function MediaPlanBuilder({ brief, catalog = CATALOG, extraCatalog = EXTRA_CATALOG, staff = STAFF, models = MODELS, modes = MODES,
  advertisers = [], agencies = [], brandsByAdv = {}, advCps = {}, agencyCps = {}, geoList = [], targetingCatalog = {},
  bound = false, initial, backLabel = 'Реестр медиапланов', onBack, versions = [], onOpenVersion,
  onAddTargeting, onAddGeo, onCreateBrand, onSave, onExportXlsx, onPreviewPdf, onEditBrief, onLinkDeal, onCreateDeal,
  dealBrief, onDealBriefSave, onDealBriefSync, ownCompany }) {
  const init = initial || {};
  /* Раздельный прайс приходит в каталоге услуг (`separate`) — тем же признаком, по
     которому конструктор показывает две цены. Для имени он решает, дописывать ли
     WEB/APP к услуге. */
  const separateSvc = useMemo(
    () => separatePriceSet((catalog || []).map(c => ({ name: c.position, separate_price: c.separate }))),
    [catalog]);
  const [verOpen, setVerOpen] = useState(false);   // дропдаун истории версий
  // Чек-лист перед сохранением: обе отметки «проверено» (размещения + прогноз).
  // Не свойство плана, а подтверждение конкретного сохранения — сбрасывается после него.
  const [okMain, setOkMain] = useState(false);
  const [okFc, setOkFc] = useState(false);
  const verified = okMain && okFc;
  // Комментарий о причинах изменений при отправке на согласование (необязательный).
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState('');
  const doSaveRef = useRef(null);   // ссылка на save() из блока кнопок — зовём из модалки
  // Новый МП — пустой (одна незаполненная строка); сохранённый — префилл из initial.
  const main = useAnimatedRows((init.rows && init.rows.length)
    ? init.rows.map((r, i) => ({ id: i + 1, position: r.position || '', format: r.format || '', model: r.model || 'CPM', inventory: r.inventory || 'cross', volume: r.volume || 0, unit: r.unit_price || 0, discount: r.discount || 0 }))
    : [{ id: 1, position: '', format: '', model: 'CPM', inventory: 'cross', volume: 0, unit: 0, discount: 0 }]);
  const extras = useAnimatedRows((init.extras || []).map((e, i) => ({ id: i + 1, name: e.name || '', period: e.period || '', mode: e.mode || 'Полная цена', price: e.price || 0, total: e.total || 0 })));
  const [fc, setFc] = useState(() => { const o = {}; (init.rows || []).forEach((r, i) => { o[i + 1] = r.forecast || {}; }); return o; });
  const [goals, setGoals] = useState(init.goals || { freq: '', ctr: '', cr: '', volume: '', weborama: '' });
  // owners: роль → id сотрудника (или null). Префилл из сохранённого МП по ids —
  // синхронно из init, не завися от того, успел ли загрузиться справочник staff.
  const [owners, setOwners] = useState(() => {
    const o = {};
    for (const role of Object.keys(OWNER_FIELD)) o[role] = init[OWNER_FIELD[role]] || null;
    return o;
  });
  // Редактируемый бриф (in-memory в песочнице; при привязке к сделке будет префилл)
  const [bf, setBf] = useState({
    advertiser_id: init.advertiser_id || '', brand_id: init.brand_id || '',
    agency_id: init.agency_id || '', payer_id: init.payer_counterparty_id || '',
    period: init.period || '', geo_id: init.geo_id || '',
    date_from: (init.date_from || '').slice(0, 10), date_to: (init.date_to || '').slice(0, 10),
    title: init.title || '',   // '' = собирается авто; непустое = ручное (правится/дописывается)
    targeting: init.targeting || { audience: [], buys: [], interests: [], behavior: [], competitors: [] },
  });
  // Free-text бриф связанной сделки (виджет открывается по иконке в шапке брифа)
  const [briefPanel, setBriefPanel] = useState(false);
  const [briefText, setBriefText] = useState('');
  const [briefBusy, setBriefBusy] = useState(false);
  useEffect(() => { setBriefText(dealBrief?.brief || ''); }, [dealBrief?.brief]);
  const briefHasDeal = !!dealBrief?.has_deal;
  const briefHas = !!(dealBrief?.brief || '').trim();
  const [titleEdit, setTitleEdit] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [periodConfirm, setPeriodConfirm] = useState(null);   // {ym} — подтверждение смены дат при заполненных данных
  const monthBounds = (ym) => { if (!/^\d{4}-\d{2}$/.test(ym || '')) return [null, null]; const [y, m] = ym.split('-').map(Number); const last = new Date(y, m, 0).getDate(); return [`${ym}-01`, `${ym}-${String(last).padStart(2, '0')}`]; };
  const applyPeriod = (ym, withDates) => { const [f, t] = monthBounds(ym); setBf(s => ({ ...s, period: ym, ...(withDates ? { date_from: f, date_to: t } : {}) })); };
  // выбор периода в шапке → авто-даты месяца; если даты уже стоят — спросить (поп-ап)
  const onPeriodChange = (ym) => { if (ym && ym !== bf.period && (bf.date_from || bf.date_to)) setPeriodConfirm(ym); else applyPeriod(ym, true); };
  /* Авто-название и эффективное (ручное перекрывает авто) — ОДНО выражение на весь
     конструктор, и общий модуль внутри (lib/dealTitle.js).

     До 03.09.2026 здесь было ДВЕ сборки: эта — та, что уходит на СОХРАНЕНИЕ, — и
     вторая в шапке брифа, для показа. Первый заход свёл к общему модулю только
     вторую, и получилось хуже, чем было: шапка показывала новое имя, а в базу
     уезжало старое, собранное здесь (« · », без услуги). Владелец поймал это на
     сделке ZCBPLS: план назывался по-новому, а сохранилось по-старому.

     Услуга и поверхность — из строк размещения: своего поля под них у плана нет. */
  const _lblT = (opts, v) => (opts.find(o => String(o.value) === String(v)) || {}).label;
  const autoTitle = useMemo(() => {
    const svcRows = main.rows.filter(r => (r.position || '').trim());
    const names = [...new Set(svcRows.map(r => r.position.trim()))];
    const svcName = names.length === 1 ? names[0] : '';
    return buildTitle({
      advertiser: _lblT(advertisers, bf.advertiser_id),
      brand: _lblT(brandsByAdv[bf.advertiser_id] || [], bf.brand_id),
      agency: _lblT(agencies, bf.agency_id),
      product: svcName,
      inventory: mergeInventory(svcRows.filter(r => r.position.trim() === svcName).map(r => r.inventory)),
      period: bf.period, separate: separateSvc,
    }) || 'Новый медиаплан';
  }, [main.rows, advertisers, agencies, brandsByAdv, bf.advertiser_id, bf.brand_id,
      bf.agency_id, bf.period, separateSvc]);
  const effectiveTitle = (bf.title || '').trim() ? bf.title : autoTitle;
  const [tgDraft, setTgDraft] = useState({});   // «+ текст» — разовое значение (не в каталог)
  const [tgCat, setTgCat] = useState({});       // «+ в каталог» — новое значение в общий каталог
  const [tgSearch, setTgSearch] = useState({}); // поиск по каталогу группы
  const [geoAdd, setGeoAdd] = useState('');
  const [periodEdit, setPeriodEdit] = useState(false);
  const toggleTg = (g, v) => setBf(s => { const cur = s.targeting[g] || []; return { ...s, targeting: { ...s.targeting, [g]: cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v] } }; });
  // свободный текст — только в этот МП, НЕ в каталог
  const addTg = (g) => { const v = (tgDraft[g] || '').trim(); if (!v) return; setBf(s => ({ ...s, targeting: { ...s.targeting, [g]: [...new Set([...(s.targeting[g] || []), v])] } })); setTgDraft(d => ({ ...d, [g]: '' })); };
  // новое значение в ОБЩИЙ каталог (сохраняется) + сразу выбирается в этом МП
  const addTgToCatalog = async (g) => { const v = (tgCat[g] || '').trim(); if (!v) return; if (onAddTargeting) await onAddTargeting(g, v); setBf(s => ({ ...s, targeting: { ...s.targeting, [g]: [...new Set([...(s.targeting[g] || []), v])] } })); setTgCat(d => ({ ...d, [g]: '' })); };
  const addGeo = async () => { const v = geoAdd.trim(); if (!v) return; const id = onAddGeo ? await onAddGeo(v) : null; setBf(s => ({ ...s, geo_id: id ?? s.geo_id })); setGeoAdd(''); };
  // Free-text таргетинга коммитится по Enter/«+»; если не нажали — досбираем черновики при сохранении (иначе текст терялся).
  const mergeTgDrafts = () => { const out = { ...bf.targeting }; TG_GROUPS.forEach(([g]) => { const v = (tgDraft[g] || '').trim(); if (v) out[g] = [...new Set([...(out[g] || []), v])]; }); return out; };
  const [sel, setSel] = useState(null);       // {kind,id,field} — открытый поповер
  const [ownerOpen, setOwnerOpen] = useState(null);
  useDismiss(setSel);

  const isOpen = (kind, id, field) => sel && sel.kind === kind && sel.id === id && sel.field === field;
  const toggle = (kind, id, field) => setSel(s => (s && s.kind === kind && s.id === id && s.field === field ? null : { kind, id, field }));
  const setFcField = (id, field, value) => setFc(s => ({ ...s, [id]: { ...(s[id] || {}), [field]: value } }));

  /* расчёты */
  const calc = useMemo(() => {
    // Формула зависит от модели: CPM — за 1000 (объём/1000×цена), иначе — кол-во×цена (Fix/CPC).
    const net = r => Math.round(r.volume * r.unit * (1 - r.discount) / (r.model === 'CPM' ? 1000 : 1));
    const filled = main.rows.filter(r => r.position && r.volume && r.unit);
    const tNet = filled.reduce((a, r) => a + net(r), 0);
    const tVol = filled.reduce((a, r) => a + r.volume, 0);
    const extrasNet = extras.rows.reduce((a, e) => a + e.total, 0);
    const agg = { reach: 0, imp: 0, clicks: 0, checks: 0, revenue: 0, gross: 0, sov: 0, freq: 0 };
    main.rows.forEach(r => {
      const f = fc[r.id] || {};
      if (!(r.position && r.volume && r.unit)) return;
      const freq = parseN(f.freq), ctr = parseN(f.ctr) / 100, cr = parseN(f.cr) / 100, price = parseN(f.price);
      // Показы, а не объём: у Фикса и Пакета в объёме штуки закупки (см. lib/mpRow).
      const imp = rowImp(r.model, r.volume, f), clicks = imp * ctr, checks = clicks * cr;
      agg.reach += freq > 0 ? imp / freq : 0;
      agg.imp += imp; agg.clicks += clicks; agg.checks += checks;
      agg.revenue += checks * price; agg.gross += Math.round(net(r) * (1 + VAT));
      agg.sov += parseN(f.sov); agg.freq = Math.max(agg.freq, freq);
    });
    return { net, filled, tNet, tVol, extrasNet, agg, grandNet: tNet + extrasNet };
  }, [main.rows, extras.rows, fc]);

  const emptyMain = main.rows.length - calc.filled.length;
  const emptyExtra = extras.rows.filter(e => !e.name).length;
  const plural = n => (n === 1 ? 'строка не заполнена' : n < 5 ? 'строки не заполнены' : 'строк не заполнено');

  const summary = [
    { label: 'Размещение до НДС', value: rub(calc.tNet), color: T.t1 },
    { label: 'Доп. услуги', value: rub(calc.extrasNet), color: T.income },
    { label: 'НДС 22 %', value: rub(calc.grandNet * VAT), color: T.t2 },
    { label: 'Строк в плане', value: `${calc.filled.length} из ${main.rows.length}`, color: emptyMain ? T.warning : T.t1 },
    { label: 'Прогноз показов', value: num(calc.agg.imp), color: T.accent },
  ];

  const GOALS = [
    ['freq', 'Частота', 'напр. 3', 'контактов на пользователя'],
    ['ctr', 'CTR', 'напр. 1,20 %', 'целевой клик-рейт'],
    ['cr', 'CR', 'напр. 0,35 %', 'конверсия в целевое действие'],
    ['volume', 'Показы / клики', 'напр. 2 927 400', 'в зависимости от модели РК'],
    ['weborama', 'Расхождение с Weborama', 'напр. до 10 %', 'допустимая погрешность'],
  ];
  const FC_RULES = [
    ['Охват', 'показы ÷ частота'],
    ['Клики', 'показы × CTR'],
    ['CPM / CPC / CPU / CPO', 'бюджет до НДС ÷ показы × 1000, ÷ клики, ÷ охват, ÷ чеки'],
    ['Чеки', 'клики × CR'],
    ['Доход', 'чеки × средняя цена'],
    ['ROI', '(доход − бюджет с НДС) ÷ бюджет с НДС'],
  ];

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
        body { margin:0; background:${T.canvas}; color:${T.t1}; font-family:${T.sans}; -webkit-font-smoothing:antialiased }
        a { color:${T.accent}; text-decoration:none } a:hover { color:${T.accentHover}; text-decoration:underline }
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes popIn { from { opacity:0; transform:translateY(-4px) } to { opacity:1; transform:none } }
        @keyframes pulseEmpty { 0%,100% { border-color:${T.emptyBorder} } 50% { border-color:${T.warning} } }
        @keyframes rowIn { from { opacity:0; transform:translateY(-6px) scaleY(.85); max-height:0 } to { opacity:1; transform:none; max-height:60px } }
        @keyframes rowOut { from { opacity:1; transform:none; max-height:60px }
                            to { opacity:0; transform:translateX(24px); max-height:0; margin:0; padding-top:0; padding-bottom:0 } }
        @media (prefers-reduced-motion: reduce) { * { animation-duration:1ms !important; animation-delay:0s !important } }
        .mp-field:hover { border-color:${T.hoverBorder} }
        .mp-cell:hover { text-decoration:underline; text-decoration-style:dotted; text-underline-offset:3px; color:${T.accent} }
        .mp-opt:hover { background:${T.subtle} }
        .mp-ghost:hover { border-color:${T.accent}; background:${T.tint} }
        .mp-del:hover { background:${T.dangerTint}; color:${T.danger} }
        .mp-primary:hover { background:${T.accentHover} }
        .mp-outline:hover { background:${T.accentTint} }
        .mp-yellow:focus { border-color:${T.warning} }
        .mp-plain:focus { border-color:${T.accent}; background:${T.card} }
        .mp-scroll { overflow-x:auto }
        #mp-small { display:none }
        @media (max-width: 900px) { #mp-small { display:flex } #mp-desktop { display:none } }
      `}</style>

      {/* заглушка для узких экранов */}
      <div id="mp-small" style={{
        minHeight: '100vh', boxSizing: 'border-box', padding: '32px 22px', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: 14,
      }}>
        <span style={{ fontSize: 52, lineHeight: 1 }}>🖥️</span>
        <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>Это не для маленьких экранов</span>
        <span style={{ maxWidth: 300, fontSize: 13, color: T.t3, lineHeight: 1.5 }}>
          Конструктор медиаплана работает на широком экране — откройте его с компьютера.
        </span>
      </div>

      <div id="mp-desktop" style={{ minHeight: '100vh', boxSizing: 'border-box', padding: '26px 32px 40px', display: 'flex', justifyContent: 'center' }}>
        {/* Комментарий о причинах изменений. Спрашивается ТОЛЬКО когда план уже отдан
            клиенту (init.sealed) и сохранение родит новую версию: там объяснение нужно,
            а на правках черновика оно было бы лишним кликом. Поле необязательное. */}
        {noteOpen && (
          <div {...overlayClose(() => setNoteOpen(false))} style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(20,22,28,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div onClick={e => e.stopPropagation()} style={{ width: 460, maxWidth: '92vw', background: T.card, borderRadius: 16, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 12, boxShadow: '0 16px 48px rgba(20,22,28,.3)' }}>
              <span style={{ fontSize: 16, fontWeight: 700 }}>Новая версия медиаплана</span>
              <span style={{ fontSize: 12.5, color: T.t3 }}>Предыдущую версию клиент уже видел, поэтому она сохраняется как есть. Оставьте комментарий о причинах изменений — он попадёт в историю. Поле необязательное.</span>
              <textarea autoFocus value={noteText} onChange={e => setNoteText(e.target.value)} rows={4} placeholder="Причины изменений…"
                style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: 10, border: `1px solid ${T.border}`, fontSize: 13, fontFamily: T.sans, outline: 'none', resize: 'vertical' }} />
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <span onClick={() => setNoteOpen(false)} style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 14px', border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: T.t2, cursor: 'pointer' }}>Отмена</span>
                <span onClick={() => { const n = noteText.trim(); setNoteOpen(false); doSaveRef.current && doSaveRef.current(n); }}
                  style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 16px', background: T.accent, color: 'var(--bg-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>ОК, сохранить</span>
              </div>
            </div>
          </div>
        )}
        <div style={{ width: '100%', maxWidth: 1760, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* хлебные крошки + действия */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', animation: `riseIn .4s ${T.ease} both`, position: 'relative', zIndex: verOpen ? 5000 : undefined }}>
            <span onClick={onBack} style={{ fontSize: 13, fontWeight: 600, color: T.t3, cursor: onBack ? 'pointer' : 'default' }}>← {backLabel}</span>
            <span style={{ color: T.hoverBorder }}>/</span>
            <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em' }}>Конструктор медиаплана</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: T.warningTint, color: T.warningText, borderRadius: 9, padding: '5px 11px', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: T.warning }} />
              {init.sealed ? 'Отдан клиенту' : 'Черновик'}{init.version ? ` v${init.version}` : ''}
            </span>
            {versions.length > 1 && (
              <span style={{ position: 'relative' }}>
                <span onClick={() => setVerOpen(o => !o)} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 12, fontWeight: 600, color: T.t2, border: `1px solid ${T.border}`, borderRadius: 9, padding: '5px 10px', background: T.card }}>🕑 Версии ({versions.length}) ▾</span>
                {verOpen && (
                  <div style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 1000, minWidth: 250, background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, boxShadow: '0 12px 32px rgba(20,22,28,.16)', padding: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {versions.map(v => {
                      const cur = v.id === init.id;
                      return (
                        <span key={v.id} onClick={() => { if (!cur && onOpenVersion) onOpenVersion(v.id); setVerOpen(false); }}
                          style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '7px 9px', borderRadius: 8, cursor: cur ? 'default' : 'pointer', background: cur ? T.accentTint : 'transparent' }}>
                          <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: cur ? T.accent : T.t1 }}>v{v.version}</span>
                          <span style={{ fontSize: 11.5, color: T.t3 }}>{v.updated_at ? new Date(v.updated_at).toLocaleDateString('ru-RU') : ''}</span>
                          <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 11, color: T.t2 }}>{v.amount_gross ? Math.round(v.amount_gross).toLocaleString('ru-RU') + ' ₽' : '—'}</span>
                          {cur && <span style={{ fontSize: 10, color: T.accent, fontWeight: 700 }}>• текущая</span>}
                        </span>
                      );
                    })}
                  </div>
                )}
              </span>
            )}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
              <span className="mp-outline" onClick={onPreviewPdf} style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 13px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: T.t2, cursor: 'pointer' }}>PDF</span>
              {onExportXlsx && <span className="mp-outline" onClick={onExportXlsx} style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 13px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: T.t2, cursor: 'pointer' }}>Excel</span>}
              {(() => {
                // Кнопка ОДНА. Что произойдёт — правка текущей версии или рождение
                // новой — решает сервер по тому, отдан ли план клиенту; фронт лишь
                // называет это вслух и у отданного плана спрашивает причину изменений.
                // Раньше кнопок было пять («Сохранить черновик», «На согласование»,
                // «Согласовать», «Отклонить», «В архив»), и человек выбирал ими не
                // действие, а состояние плана — параллельное стадии его сделки.
                const okToSave = !emptyMain && calc.filled.length > 0 && verified;
                const hint = !verified ? 'Отметьте обе таблицы как проверенные'
                  : (calc.filled.length ? 'Заполните все строки' : 'Добавьте хотя бы одну строку размещения');
                const btn = (bg, color, bd) => ({ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px', background: bg, border: bd || 'none', color, borderRadius: 10, fontSize: 12.5, fontWeight: 700, cursor: 'pointer' });
                const save = (note) => onSave?.({ brief: { ...bf, title: effectiveTitle, targeting: mergeTgDrafts() }, main: main.rows, extras: extras.rows, fc, goals, owners, verified: true, change_note: note || '' });
                doSaveRef.current = save;   // чтобы модалка комментария могла отправить
                return (
                  <span className={okToSave ? 'mp-primary' : undefined}
                    onClick={() => { if (!okToSave) return; if (init.sealed) { setNoteText(''); setNoteOpen(true); } else save(); }}
                    title={okToSave ? undefined : hint}
                    style={{ ...btn(okToSave ? T.accent : 'var(--bank-sovkom)', 'var(--bg-card)'), cursor: okToSave ? 'pointer' : 'default' }}>
                    {init.sealed ? 'Сохранить новой версией' : 'Сохранить'}
                  </span>
                );
              })()}
            </span>
          </div>

          {/* ── БРИФ + СДЕЛКА ─────────────────────────────────────────── */}
          <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', flexWrap: 'wrap' }}>
            <Card delay={0.07} style={{ flex: '1 1 0', minWidth: 0 }}>
              {(() => {
                const brOpts = brandsByAdv[bf.advertiser_id] || [];
                const payerOpts = bf.agency_id ? (agencyCps[bf.agency_id] || []) : (advCps[bf.advertiser_id] || []);
                const L = (opts, v) => (opts.find(o => String(o.value) === String(v)) || {}).label;
                /* Имя НЕ собирается здесь заново: и показ, и сохранение берут одно
                   выражение `autoTitle` / `effectiveTitle` (объявлено выше). Вторая
                   сборка ровно здесь и разъехалась с той, что пишется в базу. */
                const displayTitle = effectiveTitle;   // ручное имя перекрывает авто
                const selSt = { width: '100%', boxSizing: 'border-box', height: 32, padding: '0 8px', background: T.subtle, border: `1px solid ${T.border}`, borderRadius: 9, fontFamily: T.sans, fontSize: 12, color: T.t1, outline: 'none', cursor: 'pointer' };
                const lbl = { fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, marginBottom: 3, display: 'block' };
                const chip = { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, padding: '2px 7px', borderRadius: 6, background: T.accentTint, color: T.accent };
                return (<>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                    {titleEdit ? (
                      <input autoFocus value={titleDraft} onChange={e => setTitleDraft(e.target.value)}
                        onBlur={() => { setBf(s => ({ ...s, title: titleDraft })); setTitleEdit(false); }}
                        onKeyDown={e => { if (e.key === 'Enter') { setBf(s => ({ ...s, title: titleDraft })); setTitleEdit(false); } else if (e.key === 'Escape') setTitleEdit(false); }}
                        style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', border: `1px solid ${T.accent}`, borderRadius: 8, padding: '2px 8px', outline: 'none', fontFamily: T.sans, color: T.t1, minWidth: 320, maxWidth: '100%', boxSizing: 'border-box' }} />
                    ) : (
                      <span className="mp-cell" onClick={() => { setTitleDraft(bf.title || autoTitle); setTitleEdit(true); }} title="Клик — редактировать (можно дописать своё)" style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', cursor: 'pointer' }}>{displayTitle}</span>
                    )}
                    <span style={meta}>бриф · черновик</span>
                    {/* Та же кнопка, что в реестрах и на карточке (salesTableKit.GenTitleBtn):
                        действие одно — собрать имя по шаблону, — и выглядеть должно
                        одинаково. Здесь она снимает ручное имя, и авто-сборка берёт своё. */}
                    {(bf.title || '').trim() && !titleEdit && (
                      <GenTitleBtn size={22} title="Собрать название по шаблону"
                        onClick={() => setBf(s => ({ ...s, title: '' }))} />
                    )}
                    <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: briefHas ? T.accent : T.t3 }}>{briefHas ? 'бриф есть' : 'брифа нет'}</span>
                      <button type="button" onClick={() => setBriefPanel(o => !o)} title="Бриф сделки"
                        style={{ width: 34, height: 34, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${briefHas ? T.accent : T.border}`, background: briefHas ? T.accentTint : T.card, borderRadius: 9, color: briefHas ? T.accent : T.t3, cursor: 'pointer' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M9 12h6" /><path d="M9 16h4" /></svg>
                      </button>
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: 22, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    {/* Параметры РК — слева, 2 колонки × 3 строки (колоночный порядок) */}
                    <div style={{ flex: '0 0 30%', minWidth: 240, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gridTemplateRows: 'repeat(3,auto)', gridAutoFlow: 'column', columnGap: 16 }}>
                      <BriefField label="Рекламодатель" open={isOpen('brief', 0, 'adv')} onToggle={() => toggle('brief', 0, 'adv')} value={bf.advertiser_id} options={advertisers} onPick={v => { setBf(s => ({ ...s, advertiser_id: v, brand_id: '', payer_id: '' })); setSel(null); }} />
                      <BriefField label="Бренд" open={isOpen('brief', 0, 'brand')} onToggle={() => bf.advertiser_id && toggle('brief', 0, 'brand')} value={bf.brand_id} options={brOpts} placeholder={bf.advertiser_id ? '—' : 'сначала рекламодатель'} onPick={v => { setBf(s => ({ ...s, brand_id: v })); setSel(null); }}
                        onAddNew={(bf.advertiser_id && onCreateBrand) ? (async (name) => { const id = await onCreateBrand(bf.advertiser_id, name); if (id) { setBf(s => ({ ...s, brand_id: id })); setSel(null); } }) : undefined} addPlaceholder="+ новый бренд" />
                      <BriefField label="Агентство" open={isOpen('brief', 0, 'ag')} onToggle={() => toggle('brief', 0, 'ag')} value={bf.agency_id} options={agencies} onPick={v => { setBf(s => ({ ...s, agency_id: v, payer_id: '' })); setSel(null); }} />
                      <BriefField label="Контрагент (юр.лицо)" open={isOpen('brief', 0, 'payer')} onToggle={() => toggle('brief', 0, 'payer')} value={bf.payer_id} options={payerOpts} placeholder={payerOpts.length ? '—' : 'нет юрлиц'} emptyHint="Привяжите юр лицо в справочнике" onPick={v => { setBf(s => ({ ...s, payer_id: v })); setSel(null); }} />
                      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '5px 0', borderTop: `1px solid ${T.row}`, minWidth: 0 }}>
                        <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.3 }}>Период размещения</span>
                        {periodEdit
                          ? <input type="month" autoFocus value={bf.period} onChange={e => onPeriodChange(e.target.value)} onBlur={() => setPeriodEdit(false)} style={{ boxSizing: 'border-box', height: 26, padding: '0 6px', background: T.subtle, border: `1px solid ${T.border}`, borderRadius: 8, fontFamily: T.mono, fontSize: 12.5, color: T.t1, outline: 'none' }} />
                          : <span className="mp-cell" onClick={() => setPeriodEdit(true)} style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600, lineHeight: 1.3, color: bf.period ? T.t1 : T.t4, cursor: 'pointer' }}>{bf.period || '—'}</span>}
                      </span>
                      <BriefField label="Гео" open={isOpen('brief', 0, 'geo')} onToggle={() => toggle('brief', 0, 'geo')} value={bf.geo_id} options={geoList.map(g => ({ value: g.id, label: g.name }))} minWidth={180} onPick={v => { setBf(s => ({ ...s, geo_id: v })); setSel(null); }} onAddNew={async (name) => { const id = onAddGeo ? await onAddGeo(name) : null; setBf(s => ({ ...s, geo_id: id ?? s.geo_id })); setSel(null); }} addPlaceholder="+ гео" />
                    </div>
                      {/* Плашка материнского годового плана — если МП прикреплён к сделке,
                          рождённой конвейером плана. Тот же смысл, что в раскрытии сделки. */}
                      {init.year_plan && (
                        <span style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10, background: T.subtle, border: `1px solid ${T.border}`, borderRadius: 10, padding: '8px 10px' }}>
                          <span style={{ minWidth: 0, flex: 1 }}>
                            <span style={{ display: 'block', fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3 }}>Годовой план</span>
                            <span style={{ display: 'block', fontSize: 12, fontWeight: 700, color: T.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                              title={[init.year_plan.title, init.year_plan.comment].filter(Boolean).join(' · ')}>
                              {init.year_plan.title || `План ${init.year_plan.year || ''}`}
                              {init.year_plan.comment ? <span style={{ fontWeight: 600, color: T.t2 }}> · {init.year_plan.comment}</span> : null}
                              {init.year_plan.month != null ? <span style={{ fontFamily: T.mono, fontWeight: 600, color: T.t3 }}> · мес. {init.year_plan.month + 1}</span> : null}
                            </span>
                          </span>
                          <a href={`/sales/year-plan?year=${init.year_plan.year}${init.year_plan.rep_id ? `&rep=${init.year_plan.rep_id}` : ''}`}
                            target="_blank" rel="noreferrer" title="Открыть годовой план в новой вкладке"
                            style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', borderRadius: 8, background: T.accentTint, border: `1px solid ${T.accentBorder}`, color: T.accent, fontSize: 11, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap', flex: '0 0 auto' }}>
                            Открыть план →
                          </a>
                        </span>
                      )}
                    </div>

                    {/* Таргетинг — справа: чипы из каталога (пикер) + свободный текст */}
                    <div style={{ flex: 1, minWidth: 260, display: 'flex', flexDirection: 'column', gap: 2 }}>
                      {TG_GROUPS.map(([g, label]) => {
                        const selv = bf.targeting[g] || []; const cat = targetingCatalog[g] || [];
                        const cs = (tgSearch[g] || '').trim() ? cat.filter(c => String(c.value).toLowerCase().includes(tgSearch[g].trim().toLowerCase())) : cat;
                        return (
                          <div key={g} style={{ display: 'flex', gap: 10, padding: '5px 0', borderTop: `1px solid ${T.row}`, alignItems: 'flex-start' }}>
                            <span style={{ flex: '0 0 84px', fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.4, paddingTop: 5 }}>{label}</span>
                            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
                              {selv.map(v => <span key={v} style={chip}>{v}<span onClick={() => toggleTg(g, v)} title="убрать" style={{ cursor: 'pointer', color: T.t4, fontSize: 12 }}>×</span></span>)}
                              <span data-pop-root style={{ position: 'relative', display: 'inline-flex', zIndex: isOpen('tg', 0, g) ? 1000 : undefined }}>
                                <span className="mp-cell" onClick={() => toggle('tg', 0, g)} style={{ fontSize: 11, color: T.accent, cursor: 'pointer', whiteSpace: 'nowrap' }}>+ из каталога</span>
                                <Popover open={isOpen('tg', 0, g)} minWidth={230}>
                                  {cat.length >= 15 && (
                                    <input autoFocus value={tgSearch[g] || ''} onChange={e => setTgSearch(d => ({ ...d, [g]: e.target.value }))} placeholder="поиск"
                                      style={{ width: '100%', boxSizing: 'border-box', margin: '0 0 4px', padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, outline: 'none', fontFamily: T.sans }} />
                                  )}
                                  {cs.map(c => { const on = selv.includes(c.value); return (
                                    <span key={c.id} className="mp-opt" onClick={() => toggleTg(g, c.value)} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '6px 8px', borderRadius: 8, background: on ? T.accentTint : 'transparent', cursor: 'pointer' }}>
                                      <input type="checkbox" readOnly checked={on} />
                                      <span style={{ fontSize: 12, color: on ? T.accent : T.t1 }}>{c.value}</span>
                                    </span>
                                  ); })}
                                  {!cs.length && <div style={{ padding: '6px 8px', fontSize: 12, color: T.t4 }}>{cat.length ? 'ничего не найдено' : 'каталог пуст'}</div>}
                                  <div style={{ display: 'flex', gap: 5, padding: '6px 2px 2px', borderTop: `1px solid ${T.row}`, marginTop: 4 }}>
                                    <input value={tgCat[g] || ''} onChange={e => setTgCat(d => ({ ...d, [g]: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter') addTgToCatalog(g); }} placeholder="+ в каталог" style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, outline: 'none', fontFamily: T.sans }} />
                                    <span onClick={() => addTgToCatalog(g)} title="Добавить в каталог" style={{ display: 'inline-flex', alignItems: 'center', padding: '0 10px', background: T.accent, color: 'var(--bg-card)', borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+</span>
                                  </div>
                                </Popover>
                              </span>
                              <input value={tgDraft[g] || ''} onChange={e => setTgDraft(d => ({ ...d, [g]: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter') addTg(g); }} placeholder="+ текст (разово, не в каталог)" style={{ ...selSt, flex: '1 1 110px', minWidth: 80, width: 'auto', height: 26, fontSize: 11, padding: '0 8px' }} />
                              {(tgDraft[g] || '').trim() && <span onClick={() => addTg(g)} title="Добавить текст" style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 9px', background: T.accent, color: 'var(--bg-card)', borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+</span>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>);
              })()}
            </Card>

            {/* Сделка — 20 % */}
            <Card delay={0.1} pad="14px 12px 12px" gap={8} style={{ flex: '0 0 clamp(180px, 20%, 250px)', minWidth: 0 }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {bound ? (
                  <span className="mp-outline" onClick={onLinkDeal} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '8px 6px', background: T.card, color: T.accent, border: `1px solid ${T.accentBorder}`, borderRadius: 10, fontSize: 11.5, fontWeight: 700, lineHeight: 1.3, cursor: 'pointer' }}>Сохранить медиаплан</span>
                ) : (<>
                  <span style={{ display: 'flex', gap: 8 }}>
                    <span className="mp-outline" onClick={onLinkDeal} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '7px 6px', background: T.card, color: T.accent, border: `1px solid ${T.accentBorder}`, borderRadius: 10, fontSize: 11.5, fontWeight: 700, lineHeight: 1.3, cursor: 'pointer' }}>Привязать к сделке</span>
                    <span className="mp-primary" onClick={onCreateDeal} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '7px 6px', background: T.accent, color: 'var(--bg-card)', borderRadius: 10, fontSize: 11.5, fontWeight: 700, lineHeight: 1.3, cursor: 'pointer' }}>Создать сделку</span>
                  </span>
                  <span style={{ fontSize: 10, color: T.t4, lineHeight: 1.4 }}>Без привязки суммы не попадают в ДДС и дебиторку.</span>
                </>)}
              </span>

              <span style={{ position: 'relative', zIndex: 20, display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 8, borderTop: `1px solid ${T.border}` }}>
                <span style={{ ...capTitle, fontSize: 10 }}>Ответственные</span>
                {Object.keys(staff).map(role => {
                  const list = staff[role] || [];
                  const selId = owners[role];
                  const selRep = list.find(r => r.id === selId);
                  const name = selRep?.name;
                  const [bg, fg] = ROLE_TINT[role] || [T.accentTint, T.accent];
                  const open = ownerOpen === role;
                  return (
                    <span key={role} data-pop-root style={{ position: 'relative', zIndex: open ? 1000 : 1, display: 'flex', flexDirection: 'column' }}>
                      {name ? (
                        <span className="mp-opt" onClick={() => setOwnerOpen(open ? null : role)} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 6px 4px 0', borderRadius: 10, cursor: 'pointer' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, background: bg, color: fg, fontSize: 12, fontWeight: 700, flex: '0 0 32px' }}>{initials(name)}</span>
                          <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}{selRep?.is_master ? ' ★' : ''}</span>
                            <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{role}</span>
                          </span>
                          <DeleteBtn onClick={e => { e.stopPropagation(); setOwners(o => ({ ...o, [role]: null })); setOwnerOpen(null); }} />
                        </span>
                      ) : (
                        <span className="mp-opt" onClick={() => setOwnerOpen(open ? null : role)} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 6px 4px 0', borderRadius: 10, cursor: 'pointer' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, border: `1px dashed ${T.accentBorder}`, background: T.accentTint, color: T.accent, flex: '0 0 32px' }}><Plus /></span>
                          <span style={{ fontSize: 12, fontWeight: 600, color: T.accent }}>Добавить</span>
                          <span style={{ marginLeft: 'auto', ...meta }}>{role}</span>
                        </span>
                      )}
                      {open && (
                        <Popover open minWidth={200}>
                          {list.length ? list.map(r => (
                            <span key={r.id} className="mp-opt" onClick={() => { setOwners(o => ({ ...o, [role]: r.id })); setOwnerOpen(null); }}
                              style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 9px', borderRadius: 9, background: r.id === selId ? T.accentTint : 'transparent', cursor: 'pointer' }}>
                              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 8, background: bg, color: fg, fontSize: 10.5, fontWeight: 700 }}>{initials(r.name)}</span>
                              <span style={{ fontSize: 12, fontWeight: 600, color: r.id === selId ? T.accent : T.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}{r.is_master ? ' ★' : ''}</span>
                            </span>
                          )) : <span style={{ padding: '7px 9px', fontSize: 12, color: T.t4 }}>Нет сотрудников</span>}
                        </Popover>
                      )}
                    </span>
                  );
                })}
              </span>

              {/* От какого юрлица оказываем услуги. Сегодня оно одно и приходит из
                  справочника, выбора нет — но названо явно, потому что оно задаёт
                  ставку НДС по нашим услугам, и здесь появится выбор, когда юрлиц
                  станет несколько. */}
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 8, borderTop: `1px solid ${T.border}` }}>
                <span style={{ ...capTitle, fontSize: 10 }}>Услуги от</span>
                <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: T.t1, lineHeight: 1.3 }}>
                  {ownCompany?.name || 'юрлицо не определено'}
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase',
                  color: ownCompany?.vat_rate_income ? T.t4 : T.warningText }}>
                  {ownCompany?.vat_rate_income
                    ? `НДС ${ownCompany.vat_rate_income} %`
                    : 'ставка НДС не задана'}
                </span>
              </span>
            </Card>
          </div>

          {/* ── БРИФ СДЕЛКИ (free-text, раскрывается иконкой в шапке брифа) ── */}
          {briefPanel && (
            <Card delay={0.05} pad="16px 22px 16px" gap={10}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={capTitle}>Бриф сделки</span>
                {!briefHasDeal && <span style={{ fontSize: 12, color: T.t3 }}>привяжите сделку, чтобы сохранять и синхронизировать бриф</span>}
                {dealBrief?.is_local && <span style={{ fontSize: 11, color: T.t4 }}>локальная сделка — без Битрикса</span>}
                <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
                  <button type="button" disabled={!briefHasDeal || dealBrief?.is_local || briefBusy}
                    onClick={async () => { setBriefBusy(true); try { await onDealBriefSync?.(); } finally { setBriefBusy(false); } }}
                    style={{ padding: '7px 12px', borderRadius: 9, border: `1px solid ${T.border}`, background: T.card, color: (!briefHasDeal || dealBrief?.is_local) ? T.t4 : T.accent, fontSize: 12, fontWeight: 700, cursor: (!briefHasDeal || dealBrief?.is_local) ? 'default' : 'pointer', opacity: (!briefHasDeal || dealBrief?.is_local) ? 0.5 : 1 }}>
                    ⟳ С Битрикса
                  </button>
                  <button type="button" disabled={!briefHasDeal || briefBusy}
                    onClick={async () => { setBriefBusy(true); try { await onDealBriefSave?.(briefText); } finally { setBriefBusy(false); } }}
                    style={{ padding: '7px 14px', borderRadius: 9, border: 'none', background: T.accent, color: 'var(--bg-card)', fontSize: 12, fontWeight: 700, cursor: (!briefHasDeal || briefBusy) ? 'default' : 'pointer', opacity: (!briefHasDeal || briefBusy) ? 0.5 : 1 }}>
                    {briefBusy ? 'Сохранение…' : 'Сохранить'}
                  </button>
                </span>
              </div>
              <textarea value={briefText} onChange={e => setBriefText(e.target.value)}
                placeholder={briefHasDeal ? 'Задачи, ЦА, гео, форматы, KPI, бюджет…' : 'Бриф сохранится в сделку после привязки'}
                style={{ width: '100%', boxSizing: 'border-box', minHeight: 130, resize: 'vertical', padding: '11px 13px', border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 13.5, lineHeight: 1.5, fontFamily: T.sans, color: T.t1, background: T.card, outline: 'none' }} />
            </Card>
          )}

          {/* ── МЕДИАПЛАН + ДОП. УСЛУГИ + ЦЕЛЕВЫЕ ────────────────────── */}
          <Card delay={0.14} pad="20px 26px 18px" gap={14}>
            <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>

              {/* левая часть — 80 % */}
              <div style={{ flex: '1 1 calc(80% - 20px)', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={capTitle}>Медиаплан</span>
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>{main.rows.length}</span>
                  {emptyMain > 0 && <Warn>{emptyMain} {plural(emptyMain)}</Warn>}
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ ...meta, color: T.t3 }}>Старт — стоп РК</span>
                    <input type="date" value={bf.date_from || ''} onChange={e => setBf(s => ({ ...s, date_from: e.target.value }))} style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 9, fontFamily: T.mono, fontSize: 11.5, fontWeight: 600, color: T.t1, outline: 'none', cursor: 'pointer' }} />
                    <span style={{ color: T.hoverBorder }}>→</span>
                    <input type="date" value={bf.date_to || ''} onChange={e => setBf(s => ({ ...s, date_to: e.target.value }))} style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 9, fontFamily: T.mono, fontSize: 11.5, fontWeight: 600, color: T.t1, outline: 'none', cursor: 'pointer' }} />
                  </span>
                </div>

                <div className="mp-scroll">
                  <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: MAIN_COLS, gap: 4, padding: '0 8px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
                      <span /><span>Позиция</span><span>Формат</span><span>Инвентарь</span><span>Модель</span>
                      <span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена</span><span style={{ textAlign: 'right' }}>Скид.</span>
                      <span style={{ textAlign: 'right' }}>Бюджет до НДС</span><span style={{ textAlign: 'right' }}>Бюджет с НДС</span><span />
                    </div>

                    {main.rows.map((r, i) => {
                      const empty = !r.position || !r.format || !r.volume || !r.unit;
                      const net = calc.net(r);
                      const cat = catalog.find(c => c.position === r.position);
                      const mo = main.motion(r.id);
                      return (
                        <div key={r.id} style={{
                          display: 'grid', gridTemplateColumns: MAIN_COLS, gap: 4, alignItems: 'center',
                          padding: '8px 6px', margin: '2px 0', borderRadius: 11,
                          border: `1px solid ${empty ? T.emptyBorder : 'transparent'}`,
                          background: empty ? T.emptyBg : T.card,
                          animation: mo.animation || (empty ? `pulseEmpty 2.4s ease-in-out infinite` : undefined),
                          pointerEvents: mo.pointerEvents,
                        }}>
                          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>{i + 1}</span>

                          {/* Позиция */}
                          <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                            <Field empty={empty} onClick={() => toggle('main', r.id, 'position')}>
                              <span style={{ fontSize: 12, fontWeight: 600, color: r.position ? T.t1 : T.emptyText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {r.position || 'выберите услугу'}
                              </span>
                            </Field>
                            <Popover open={isOpen('main', r.id, 'position')} minWidth={280}>
                              {catalog.map(c => (
                                <Option key={c.position} active={c.position === r.position} label={c.position}
                                  hint={c.separate ? `Web ${(c.unitWeb || 0).toLocaleString('ru-RU')} / IN-App ${(c.unitApp || 0).toLocaleString('ru-RU')} ₽` : `${c.unit.toLocaleString('ru-RU')} ₽ / ${c.formats[0]}`}
                                  onPick={() => {
                                    const model = c.model || r.model || 'CPM';
                                    main.patch(r.id, { position: c.position, format: r.format && c.formats.includes(r.format) ? r.format : c.formats[0], model, inventory: c.separate ? 'web' : 'cross', unit: c.separate ? (c.unitWeb || 0) : c.unit, volume: r.volume || defaultVolume(model) });
                                    setSel(null);
                                  }} />
                              ))}
                            </Popover>
                          </span>

                          {/* Формат */}
                          <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                            <Field empty={empty} onClick={() => toggle('main', r.id, 'format')}>
                              <span style={{ fontSize: 11.5, color: r.format ? T.t2 : T.emptyText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.format || 'формат'}</span>
                            </Field>
                            <Popover open={isOpen('main', r.id, 'format')} minWidth={160}>
                              {(cat ? cat.formats : ['Banners', 'Rich', 'Video']).map(f => (
                                <Option key={f} active={f === r.format} label={f} onPick={() => { main.patch(r.id, { format: f }); setSel(null); }} />
                              ))}
                            </Popover>
                          </span>

                          {/* Инвентарь — выбор web/IN-App при раздельном прайсе, иначе Кросс-девайс */}
                          <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                            {cat && cat.separate ? (
                              <>
                                <Field empty={empty} onClick={() => toggle('main', r.id, 'inv')}>
                                  <span style={{ fontSize: 11.5, color: r.inventory ? T.t2 : T.emptyText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{INV_LABEL[r.inventory] || 'Web'}</span>
                                </Field>
                                <Popover open={isOpen('main', r.id, 'inv')} minWidth={150}>
                                  <Option active={r.inventory === 'web'} label="Web" hint={`${(cat.unitWeb || 0).toLocaleString('ru-RU')} ₽`} onPick={() => { main.patch(r.id, { inventory: 'web', unit: cat.unitWeb || 0 }); setSel(null); }} />
                                  <Option active={r.inventory === 'app'} label="IN-App" hint={`${(cat.unitApp || 0).toLocaleString('ru-RU')} ₽`} onPick={() => { main.patch(r.id, { inventory: 'app', unit: cat.unitApp || 0 }); setSel(null); }} />
                                </Popover>
                              </>
                            ) : (
                              <span title="Единый прайс — без деления на web / IN-App" style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 4px', fontSize: 11, color: T.t4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Кросс-девайс</span>
                            )}
                          </span>

                          {/* Модель */}
                          <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                            <span onClick={() => toggle('main', r.id, 'model')} style={{
                              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: 32,
                              boxSizing: 'border-box', padding: '0 8px', borderRadius: 9,
                              background: empty ? T.warningTint : T.accentTint, color: empty ? T.emptyText : T.accent,
                              fontFamily: T.mono, fontSize: 11, fontWeight: 700, cursor: 'pointer',
                            }}>{r.model}</span>
                            <Popover open={isOpen('main', r.id, 'model')} minWidth={120}>
                              {/* Смена модели меняет СМЫСЛ объёма (показы ↔ штуки ↔ клики).
                                  Введённое человеком не трогаем, но НЕТРОНУТЫЙ дефолт
                                  переводим — иначе 500 000 показов молча становятся
                                  500 000 штук по 80 000 ₽. */}
                              {models.map(m => <Option key={m} active={m === r.model} label={m} onPick={() => {
                                const untouched = r.volume === defaultVolume(r.model);
                                main.patch(r.id, untouched ? { model: m, volume: defaultVolume(m) } : { model: m });
                                setSel(null);
                              }} />)}
                            </Popover>
                          </span>

                          {/* Объём / Цена / Скидка */}
                          <NumInput value={r.volume || ''} format={num} placeholder="0" onChange={v => main.patch(r.id, { volume: parseN(v) })} />
                          <NumInput value={r.unit || ''} format={dec} placeholder="0,00" onChange={v => main.patch(r.id, { unit: parseN(v) })} weight={600} />
                          <NumInput value={r.discount * 100} format={v => `${Math.round(v)} %`} onChange={v => main.patch(r.id, { discount: Math.max(0, Math.min(1, parseN(v) / 100)) })} weight={600} />

                          {/* Бюджет до НДС — вводимый, пересчитывает объём (защита от деления на 0 при скидке 100%) */}
                          <NumInput value={net || ''} format={dec} placeholder="0,00"
                            onChange={v => { const val = parseN(v); if (r.unit > 0 && r.discount < 1) main.patch(r.id, { volume: Math.round(val / (1 - r.discount) / r.unit * (r.model === 'CPM' ? 1000 : 1)) }); }} />

                          <span style={{ fontFamily: T.mono, fontSize: 10.5, fontWeight: 700, color: net ? T.accent : T.t4, textAlign: 'right', whiteSpace: 'nowrap' }}>
                            {net ? dec(Math.round(net * (1 + VAT))) : '—'}
                          </span>

                          <DeleteBtn onClick={() => main.remove(r.id)} />
                        </div>
                      );
                    })}

                    <GhostAdd warn={emptyMain > 0}
                      label={emptyMain ? 'Добавить ещё строку' : 'Добавить строку размещения'}
                      hint="клик по строке или ⌘+↵"
                      onClick={() => { const id = main.add({ position: '', format: '', model: 'CPM', inventory: 'cross', volume: 0, unit: 0, discount: 0 }); setFc(s => ({ ...s, [id]: { freq: '', ctr: '', cr: '', price: '', sov: '' } })); }} />

                    <div style={{ display: 'grid', gridTemplateColumns: MAIN_COLS, gap: 4, alignItems: 'center', padding: '12px 8px 0' }}>
                      <span />
                      <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого размещение</span>
                      <span /><span /><span />
                      <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{num(calc.tVol)}</span>
                      <span /><span />
                      <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{dec(calc.tNet)}</span>
                      <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.accent, textAlign: 'right' }}>{dec(Math.round(calc.tNet * (1 + VAT)))}</span>
                      <span />
                    </div>
                  </div>
                </div>

                {/* Доп. услуги — под медиапланом */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingTop: 14, borderTop: `1px solid ${T.border}` }}>
                  <span style={capTitle}>Доп. услуги</span>
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>{extras.rows.length}</span>
                  {emptyExtra > 0 && <Warn>{emptyExtra} {plural(emptyExtra)}</Warn>}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: EXTRA_COLS, gap: 4, padding: '0 6px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
                    <span /><span>Услуга</span><span>Период</span><span style={{ textAlign: 'center' }}>Условие</span><span />
                    <span style={{ textAlign: 'right' }}>Цена</span><span style={{ textAlign: 'right' }}>Итого</span>
                    <span style={{ textAlign: 'right' }}>С НДС</span><span />
                  </div>

                  {extras.rows.map((e, i) => {
                    const empty = !e.name;
                    const mo = extras.motion(e.id);
                    const modeBg = e.mode === 'Бонус' ? T.incomeTint : e.mode === 'Полная цена' ? T.subtle : T.accentTint;
                    const modeFg = e.mode === 'Бонус' ? T.income : e.mode === 'Полная цена' ? T.t2 : T.accent;
                    return (
                      <div key={e.id} style={{
                        display: 'grid', gridTemplateColumns: EXTRA_COLS, gap: 4, alignItems: 'center', minWidth: 0,
                        boxSizing: 'border-box', padding: '8px 6px', margin: '2px 0', borderRadius: 11,
                        border: `1px solid ${empty ? T.emptyBorder : T.inner}`, background: empty ? T.emptyBg : T.card,
                        animation: mo.animation || (empty ? 'pulseEmpty 2.4s ease-in-out infinite' : undefined),
                        pointerEvents: mo.pointerEvents,
                      }}>
                        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>{i + 1}</span>

                        <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                          <Field empty={empty} onClick={() => toggle('extras', e.id, 'name')}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: e.name ? T.t1 : T.emptyText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {e.name || 'выберите доп. услугу'}
                            </span>
                          </Field>
                          <Popover open={isOpen('extras', e.id, 'name')} minWidth={300}>
                            {extraCatalog.map(c => (
                              <Option key={c.name} active={c.name === e.name} label={c.name}
                                hint={`${c.price.toLocaleString('ru-RU')} ₽ · ${c.period}`}
                                onPick={() => { extras.patch(e.id, { name: c.name, period: c.period, price: c.price, total: Math.round(c.price * MODE_RATE[e.mode]) }); setSel(null); }} />
                            ))}
                          </Popover>
                        </span>

                        <Field empty={empty} caret={false}>
                          <span style={{ fontFamily: T.mono, fontSize: 10, color: e.period ? T.t2 : T.emptyText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.period || 'период'}</span>
                        </Field>

                        <span data-pop-root style={{ position: 'relative', minWidth: 0 }}>
                          <span onClick={() => toggle('extras', e.id, 'mode')} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: 32, boxSizing: 'border-box', padding: '0 8px', borderRadius: 9, background: modeBg, color: modeFg, fontSize: 10.5, fontWeight: 700, cursor: 'pointer' }}>{e.mode}</span>
                          <Popover open={isOpen('extras', e.id, 'mode')} minWidth={150}>
                            {modes.map(m => <Option key={m} active={m === e.mode} label={m} onPick={() => { extras.patch(e.id, { mode: m, total: Math.round(e.price * MODE_RATE[m]) }); setSel(null); }} />)}
                          </Popover>
                        </span>

                        <span />
                        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.t4, textAlign: 'right', whiteSpace: 'nowrap', textDecoration: e.total < e.price ? 'line-through' : 'none' }}>{dec(e.price)}</span>
                        <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: e.total ? T.t1 : T.income, textAlign: 'right', whiteSpace: 'nowrap' }}>{dec(e.total)}</span>
                        {/* цена с НДС — от «Итого» (что реально в счёте), а не от прайса */}
                        <span style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: T.accent, textAlign: 'right', whiteSpace: 'nowrap' }}>{dec(Math.round((e.total || 0) * (1 + VAT)))}</span>
                        <DeleteBtn onClick={() => extras.remove(e.id)} />
                      </div>
                    );
                  })}

                  <GhostAdd label="Добавить" hint="sales · brand lift"
                    onClick={() => extras.add({ name: '', period: '', mode: 'Скидка 50 %', price: 0, total: 0 })} />

                  <span style={{ display: 'grid', gridTemplateColumns: EXTRA_COLS, gap: 4, alignItems: 'baseline', padding: '10px 6px 0' }}>
                    <span />
                    <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого доп.</span>
                    <span /><span /><span /><span />
                    <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: T.income, textAlign: 'right' }}>{rub(calc.extrasNet)}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: T.accent, textAlign: 'right' }}>{rub(Math.round(calc.extrasNet * (1 + VAT)))}</span>
                    <span />
                  </span>
                </div>
              </div>

              {/* правая часть — целевые показатели, 20 %, вертикально */}
              <div style={{ flex: '1 1 calc(20% - 20px)', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10, paddingLeft: 20, borderLeft: `1px solid ${T.inner}`, boxSizing: 'border-box' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span style={capTitle}>Целевые показатели</span>
                  <span style={meta}>KPI приёмки размещения</span>
                </div>
                {GOALS.map(([key, label, ph, hint]) => (
                  <span key={key} style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0, paddingTop: 8, borderTop: `1px solid ${T.row}` }}>
                    <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.3 }}>{label}</span>
                    <input value={goals[key]} placeholder={ph} onChange={e => setGoals(g => ({ ...g, [key]: e.target.value }))}
                      className="mp-plain"
                      style={{ width: '100%', boxSizing: 'border-box', height: 34, padding: '0 11px', background: T.subtle, border: `1px solid ${T.border}`, borderRadius: 9, fontFamily: T.mono, fontSize: 12.5, fontWeight: 600, color: T.t1, outline: 'none' }} />
                    <span style={{ fontSize: 9.5, color: T.t4, lineHeight: 1.35 }}>{hint}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* итоговая строка — на всю ширину карточки; в конце отметка «проверено» */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.35fr repeat(5,minmax(0,1fr)) auto', alignItems: 'end', marginTop: 16, paddingTop: 18, borderTop: `1px solid ${T.border}` }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingRight: 16, minWidth: 0 }}>
                <span style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t3 }}>Итого с НДС</span>
                <span style={{ fontFamily: T.mono, fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, whiteSpace: 'nowrap' }}>{rub(calc.grandNet * (1 + VAT))}</span>
              </span>
              {summary.map(s => (
                <span key={s.label} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '0 8px 2px 12px', borderLeft: `1px solid ${T.inner}`, minWidth: 0 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3, lineHeight: 1.3 }}>{s.label}</span>
                  <span style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1, color: s.color, whiteSpace: 'nowrap' }}>{s.value}</span>
                </span>
              ))}
              <span style={{ paddingLeft: 16, borderLeft: `1px solid ${T.inner}`, display: 'flex', alignItems: 'flex-end' }}>
                <VerifyBtn big on={okMain} onClick={() => setOkMain(v => !v)}
                  title="Отметьте, что блок размещений проверен — без этого сохранение недоступно" />
              </span>
            </div>

            {emptyMain > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 9, background: T.warningTint, borderRadius: 11, padding: '10px 14px' }}>
                <span style={{ width: 7, height: 7, borderRadius: 2, background: T.warning, flex: '0 0 7px' }} />
                <span style={{ fontSize: 11.5, color: T.warningText, lineHeight: 1.4 }}>
                  Пока есть незаполненные строки, план нельзя отправить на согласование — заполните или удалите их.
                </span>
              </span>
            )}
          </Card>

          {/* ── ПРОГНОЗНЫЕ ПОКАЗАТЕЛИ ────────────────────────────────── */}
          <Card delay={0.21} pad="20px 24px 16px" gap={8}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ ...capTitle, fontSize: 10 }}>Прогнозные показатели</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: T.emptyBg, border: `1px solid ${T.emptyBorder}`, borderRadius: 8, padding: '3px 9px', fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.emptyText }}>
                <span style={{ width: 6, height: 6, borderRadius: 2, background: T.warning }} />жёлтые поля вводятся вручную
              </span>
              <span style={meta}>остальное считается от медиаплана</span>
            </div>

            <div className="mp-scroll">
              <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 10, padding: '0 4px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
                  <span>Позиция</span>
                  {['Частота', 'Охват', 'Показы', 'CTR', 'Клики', 'CPM', 'CPC', 'CPU', 'CR', 'Чеки', 'CPO', 'Цена', 'Доход', 'ROI', 'SOV'].map(h => (
                    <span key={h} style={{ textAlign: 'right', color: ['Частота', 'CTR', 'CR', 'Цена', 'SOV'].includes(h) ? T.emptyText : T.t4 }}>{h}</span>
                  ))}
                </div>

                {main.rows.map(r => {
                  const f = fc[r.id] || {};
                  const ok = !!(r.position && r.volume && r.unit);
                  const freq = parseN(f.freq), ctr = parseN(f.ctr) / 100, cr = parseN(f.cr) / 100, price = parseN(f.price);
                  const imp = rowImp(r.model, r.volume, f), net = calc.net(r), gross = Math.round(net * (1 + VAT));
                  const reach = freq > 0 ? imp / freq : 0, clicks = imp * ctr, checks = clicks * cr, revenue = checks * price;
                  const roi = gross > 0 ? (revenue - gross) / gross : NaN;
                  const dim = ok ? undefined : T.emptyNum;
                  const money = v => (Number.isFinite(v) && v > 0 ? dec(v) : '—');
                  const int = v => (Number.isFinite(v) && v > 0 ? num(v) : '—');
                  const cell = (v, color, bold) => <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: bold ? 700 : 400, textAlign: 'right', color: dim || color }}>{v}</span>;
                  return (
                    <div key={r.id} style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 10, alignItems: 'center', padding: '6px 4px', borderBottom: `1px solid ${T.row}` }}>
                      <span style={{ fontSize: 11.5, fontWeight: 600, color: ok ? T.t1 : T.emptyText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.position || 'строка не заполнена'}
                      </span>
                      <NumInput yellow value={f.freq || ''} onChange={v => setFcField(r.id, 'freq', v)} />
                      {cell(int(reach), T.t2)}
                      {/* У CPM показы = объём и гарантированы договором, править их
                          отдельно значило бы разрешить им разойтись с суммой. У Фикса и
                          Пакета объём это штуки, а предоплаченный объём показов знает
                          только аккаунт — поле жёлтое (владелец 08.09.2026). */}
                      {isCpm(r.model)
                        ? cell(int(imp), T.t1, true)
                        : <NumInput yellow value={f.imp || ''} onChange={v => setFcField(r.id, 'imp', v)} />}
                      <NumInput yellow value={f.ctr || ''} onChange={v => setFcField(r.id, 'ctr', v)} />
                      {cell(int(clicks), T.t1, true)}
                      {cell(money(imp > 0 ? net / imp * 1000 : 0), T.accent)}
                      {cell(money(clicks > 0 ? net / clicks : 0), T.accent)}
                      {cell(money(reach > 0 ? net / reach : 0), T.accent)}
                      <NumInput yellow value={f.cr || ''} onChange={v => setFcField(r.id, 'cr', v)} />
                      {cell(int(checks), T.t2)}
                      {cell(money(checks > 0 ? net / checks : 0), T.accent)}
                      <NumInput yellow value={f.price || ''} onChange={v => setFcField(r.id, 'price', v)} />
                      {cell(money(revenue), T.income, true)}
                      {cell(Number.isFinite(roi) && gross > 0 ? `${roi >= 0 ? '+' : '−'}${Math.abs(roi * 100).toFixed(0)} %` : '—', roi >= 0 ? T.income : T.danger, true)}
                      <NumInput yellow value={f.sov || ''} onChange={v => setFcField(r.id, 'sov', v)} />
                    </div>
                  );
                })}

                {/* Итого по МП */}
                <div style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 10, alignItems: 'center', padding: '10px 4px 0' }}>
                  <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого по МП</span>
                  {[
                    [calc.agg.freq ? String(calc.agg.freq).replace('.', ',') : '—', T.t1],
                    [num(calc.agg.reach), T.t1], [num(calc.agg.imp), T.t1],
                    [calc.agg.imp ? pct(calc.agg.clicks / calc.agg.imp) : '—', T.t1],
                    [num(calc.agg.clicks), T.t1],
                    [calc.agg.imp ? dec(calc.tNet / calc.agg.imp * 1000) : '—', T.accent],
                    [calc.agg.clicks ? dec(calc.tNet / calc.agg.clicks) : '—', T.accent],
                    [calc.agg.reach ? dec(calc.tNet / calc.agg.reach) : '—', T.accent],
                    [calc.agg.clicks ? pct(calc.agg.checks / calc.agg.clicks) : '—', T.t1],
                    [num(calc.agg.checks), T.t1],
                    [calc.agg.checks ? dec(calc.tNet / calc.agg.checks) : '—', T.accent],
                    ['', T.t1],
                    [dec(calc.agg.revenue), T.income],
                    [calc.agg.gross ? `${calc.agg.revenue >= calc.agg.gross ? '+' : '−'}${Math.abs((calc.agg.revenue - calc.agg.gross) / calc.agg.gross * 100).toFixed(0)} %` : '—', calc.agg.revenue >= calc.agg.gross ? T.income : T.danger],
                    [calc.agg.sov ? `${calc.agg.sov.toFixed(0)} %` : '—', T.t1],
                  ].map(([v, c], k) => (
                    <span key={k} style={{ fontFamily: T.mono, fontSize: 11.5, fontWeight: 700, color: c, textAlign: 'right' }}>{v}</span>
                  ))}
                </div>
              </div>
            </div>

            {/* легенда формул — ВНЕ скролл-контейнера; справа отметка «проверено» */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '2px 20px', alignItems: 'center', background: T.tint, borderRadius: 10, padding: '9px 12px', marginTop: 4 }}>
              {FC_RULES.map(([metric, rule], i) => (
                <span key={metric} style={{ fontSize: 10, color: T.t2, lineHeight: 1.4, gridColumn: (i % 2) + 1 }}>
                  <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t3 }}>{metric}</span> — {rule}
                </span>
              ))}
              <span style={{ gridColumn: 3, gridRow: `1 / span ${Math.ceil(FC_RULES.length / 2)}`, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingLeft: 16 }}>
                <VerifyBtn big on={okFc} onClick={() => setOkFc(v => !v)}
                  title="Отметьте, что прогноз проверен — без этого сохранение недоступно" />
              </span>
            </div>
          </Card>
        </div>
      </div>

      {periodConfirm && (
        <div {...overlayClose(() => setPeriodConfirm(null))} style={{ position: 'fixed', inset: 0, background: T.overlay || 'rgba(28,36,51,.45)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ background: T.card, border: `1px solid ${T.border}`, boxShadow: T.shadow, borderRadius: 16, padding: '22px 24px', maxWidth: 420, width: '100%', fontFamily: T.sans }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, color: T.t1 }}>Сменить период?</div>
            <div style={{ fontSize: 13, color: T.t2, lineHeight: 1.5, marginBottom: 20 }}>Со сменой периода изменятся даты старта и конца РК по умолчанию. Продолжить?</div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <span onClick={() => { setBf(s => ({ ...s, period: periodConfirm })); setPeriodConfirm(null); }} style={{ padding: '8px 16px', borderRadius: 9, border: `1px solid ${T.border}`, background: T.card, color: T.t1, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Нет, оставить даты</span>
              <span onClick={() => { applyPeriod(periodConfirm, true); setPeriodConfirm(null); }} style={{ padding: '8px 16px', borderRadius: 9, border: 'none', background: T.accent, color: 'var(--bg-card)', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>Да, обновить</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
