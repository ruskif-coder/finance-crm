/**
 * Бриф бренда в годовом плане — часть конструктора МП без блока «медиаплан».
 * Модалка: агентство / юрлицо / гео / таргетинг (как в МП) / ответственные / free-text
 * + прогнозные показатели на услугу ЗА ГОД (полная таблица конструктора МП: суммы
 * amount/units услуги по всем месяцам → те же расчёты охват/клики/CPM/… ).
 * Данные брифа — одни на строку-бренд; пишутся в brief/service_forecast строки плана.
 */
import React, { useMemo, useState } from 'react';
import { overlayClose } from '@/lib/overlay'

// Локальные токены (не импортируем из YearPlan — иначе циклический импорт рушит сборку).
const T = {
  card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', border: 'var(--border-card)', row: 'var(--border-row)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)',
  accent: 'var(--accent)', accentTint: 'var(--accent-tint)', accentBorder: 'var(--accent-border)',
  fact: 'var(--income)', income: 'var(--income-fg)', warning: 'var(--warning)', danger: 'var(--danger-fg)',
  onBg: 'var(--income-tint)', onBorder: 'var(--income-border)',   // «месяц с услугами» — как зелёная ячейка плана
  addon: 'var(--violet-fg)', addonTint: 'var(--violet-tint)', addonBorder: 'var(--violet-border)',
  emptyBg: 'var(--warning-bg)', emptyBorder: 'var(--warning-border)', emptyText: 'var(--warning-text)', emptyNum: 'var(--text-disabled)',
  pop: '0 8px 28px rgba(28,36,51,.14)',
  mono: "'JetBrains Mono', monospace", sans: "'Manrope', system-ui, sans-serif",
  ease: 'cubic-bezier(0.22,1,0.36,1)',
};
const VAT = 0.22;

const num = v => Math.round(+v || 0).toLocaleString('ru-RU');
const dec = v => (+v || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽';
const pct = v => ((+v || 0) * 100).toFixed(2).replace('.', ',') + ' %';
const parseN = v => { const n = parseFloat(String(v ?? '').replace(/[^\d.,-]/g, '').replace(',', '.')); return Number.isFinite(n) ? n : 0; };

const MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
const TG_GROUPS = [['audience', 'Аудитория'], ['buys', 'Покупают'], ['interests', 'Интересы'], ['behavior', 'Поведение'], ['competitors', 'Конкуренты']];
const FC_HEADS = ['Частота', 'Охват', 'Показы', 'CTR', 'Клики', 'CPM', 'CPC', 'CPU', 'CR', 'Чеки', 'CPO', 'Цена', 'Доход', 'ROI', 'SOV'];
const FC_YELLOW = ['Частота', 'CTR', 'CR', 'Цена', 'SOV'];
const FC_COLS = 'minmax(140px,1.3fr) repeat(15, minmax(58px,1fr))';

const lbl = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4, marginBottom: 4 };
const colHead = { fontFamily: T.mono, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 };
const field = { width: '100%', boxSizing: 'border-box', height: 34, padding: '0 10px', border: `1px solid ${T.border}`, borderRadius: 9, fontSize: 12.5, fontWeight: 600, color: T.t1, background: 'var(--bg-card)', outline: 'none' };
const chip = { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 7, background: T.accentTint, color: T.accent, fontSize: 11, fontWeight: 600 };

function Select({ value, onChange, options, placeholder = '—', disabled }) {
  return (
    <select value={value ?? ''} disabled={disabled} onChange={e => onChange(e.target.value === '' ? null : +e.target.value)}
      style={{ ...field, appearance: 'none', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.6 : 1 }}>
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
function NumInput({ value, onChange, disabled, placeholder }) {
  return <input value={value || ''} disabled={disabled} placeholder={placeholder || ''} onChange={e => onChange(e.target.value)}
    style={{ width: '100%', boxSizing: 'border-box', height: 26, padding: '0 6px', textAlign: 'right', border: `1px solid ${T.emptyBorder}`, background: T.emptyBg, borderRadius: 6, fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: T.t1, outline: 'none' }} />;
}

export default function BrandBrief({ open, onClose, brandLabel, advertiserId, brief = {}, forecast = {}, products = {},
  catalogs = {}, readOnly = false, isMaster = false, onChange, onAddTargeting }) {
  const { agencies = [], advCps = {}, agencyCps = {}, geoList = [], targeting = {}, sellers = [], accounts = [], svcName = {}, addonName = {}, services = [] } = catalogs;
  const svcMap = useMemo(() => Object.fromEntries((services || []).map(s => [s.id, s])), [services]);
  // цена услуги с учётом web/моб; показы = сумма ÷ цена × (CPM→1000, иначе 1)
  const lineImp = (it) => {
    const s = svcMap[it.ref_id]; if (!s) return 0;
    const price = s.separate_price ? (it.inventory === 'app' ? s.unit_price_app : s.unit_price_web) : s.unit_price;
    if (!(price > 0)) return 0;
    const mult = String(s.calc_form || '').toUpperCase() === 'CPM' ? 1000 : 1;
    return (+it.amount || 0) / price * mult;
  };
  const bf = brief || {};
  const setBrief = patch => onChange({ brief: { ...bf, ...patch } });
  const setTg = (grp, vals) => setBrief({ targeting: { ...(bf.targeting || {}), [grp]: vals } });
  const toggleTg = (grp, v) => { const cur = (bf.targeting || {})[grp] || []; setTg(grp, cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v]); };
  // юрлицо-плательщик: агентство → его юрлица, иначе → юрлица рекламодателя
  const payerOpts = bf.agency_id ? (agencyCps[bf.agency_id] || []) : (advCps[advertiserId] || []);

  const [tgOpen, setTgOpen] = useState(null);   // какая группа каталога открыта
  const [tgSearch, setTgSearch] = useState({});
  const [tgText, setTgText] = useState({});      // свободный текст (разово)
  const [tgCat, setTgCat] = useState({});        // добавить в каталог
  // Черновик ввода сезонных коэффициентов: пока печатают — держим строку как есть,
  // иначе parseFloat на каждый символ съедал бы запятую («1,» → 1) и дробь не набрать.
  // В бриф пишем число при уходе из поля.
  const [seasDraft, setSeasDraft] = useState({});
  const commitSeason = (mi, raw) => {
    const arr = (brief || {}).seasonality || [];
    const next = Array.from({ length: 12 }, (_, k) => (arr[k] != null ? arr[k] : null));
    const n = parseFloat(String(raw).replace(',', '.'));
    next[mi] = (String(raw).trim() === '' || !Number.isFinite(n) || n <= 0) ? null : n;
    setSeasDraft(d => { const c = { ...d }; delete c[mi]; return c; });
    setBrief({ seasonality: next });
  };

  // агрегация услуг за год (Σ amount + Σ units по одной услуге во всех месяцах)
  const rows = useMemo(() => {
    const agg = {};
    Object.values(products || {}).forEach(arr => (arr || []).forEach(it => {
      if (!it || it.ref_id == null) return;
      const key = `${it.type || 'service'}:${it.ref_id}`;
      if (!agg[key]) agg[key] = { key, type: it.type || 'service', ref_id: it.ref_id, amount: 0, units: 0, imp: 0 };
      agg[key].amount += +it.amount || 0; agg[key].units += +it.units || 0;
      if ((it.type || 'service') === 'service') agg[key].imp += lineImp(it);   // показы из тарификации
    }));
    return Object.values(agg);
  }, [products, svcMap]);
  const fcRows = rows.filter(r => r.type === 'service');   // прогноз — только размещения (доп услуги — фикс)
  const nm = r => (r.type === 'addon' ? (addonName[r.ref_id] || `#${r.ref_id}`) : (svcName[r.ref_id] || `#${r.ref_id}`));
  const setFc = (key, f, v) => onChange({ forecast: { ...forecast, [key]: { ...(forecast[key] || {}), [f]: v } } });

  // итоги по всем строкам прогноза
  const agg = useMemo(() => {
    let imp = 0, reach = 0, clicks = 0, checks = 0, revenue = 0, net = 0;
    fcRows.forEach(r => {
      const fc = forecast[r.key] || {};
      const _imp = Math.round(r.imp || r.units);
      const freq = parseN(fc.freq), ctr = parseN(fc.ctr) / 100, cr = parseN(fc.cr) / 100, price = parseN(fc.price);
      const _reach = freq > 0 ? _imp / freq : 0, _clicks = _imp * ctr, _checks = _clicks * cr;
      imp += _imp; reach += _reach; clicks += _clicks; checks += _checks; revenue += _checks * price; net += r.amount;
    });
    return { imp, reach, clicks, checks, revenue, net };
  }, [fcRows, forecast]);

  if (!open) return null;

  return (
    <div {...overlayClose(onClose)} style={{ position: 'fixed', inset: 0, background: 'rgba(20,26,38,.45)', zIndex: 200, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '32px 16px', overflowY: 'auto' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 'min(1800px, 96vw)', background: T.card, borderRadius: 18, boxShadow: T.pop, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '18px 24px', borderBottom: `1px solid ${T.border}` }}>
          <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: T.t1 }}>Бриф · {brandLabel || 'бренд'}</span>
          {readOnly && <span style={{ fontSize: 11, color: T.t4 }}>только просмотр</span>}
          <span onClick={onClose} title="Закрыть" style={{ marginLeft: 'auto', cursor: 'pointer', fontSize: 22, lineHeight: 1, color: T.t3, padding: '0 4px' }}>×</span>
        </div>

        <div style={{ padding: '18px 24px', display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* бриф-поля */}
          {/* пять полей в одну строку; на узком экране auto-fit переносит по мере нехватки места */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 14 }}>
            <div><div style={lbl}>Агентство</div>
              <Select value={bf.agency_id} disabled={readOnly} placeholder="прямой договор (рекламодатель)"
                options={agencies.map(a => ({ value: a.value ?? a.id, label: a.label ?? a.short_name }))}
                onChange={v => setBrief({ agency_id: v, payer_counterparty_id: null })} /></div>
            <div><div style={lbl}>Контрагент (юр.лицо-плательщик)</div>
              <Select value={bf.payer_counterparty_id} disabled={readOnly} placeholder={payerOpts.length ? (bf.agency_id ? '— юрлицо агентства' : '— юрлицо рекламодателя') : 'нет юрлиц'}
                options={payerOpts.map(c => ({ value: c.value ?? c.counterparty_id, label: c.label ?? c.name }))}
                onChange={v => setBrief({ payer_counterparty_id: v })} /></div>
            <div><div style={lbl}>Гео</div>
              <Select value={bf.geo_id} disabled={readOnly} options={geoList.map(gg => ({ value: gg.id, label: gg.name }))}
                onChange={v => setBrief({ geo_id: v })} /></div>
            <div><div style={lbl}>Ответственный сейлз (в чей дашборд)</div>
              <Select value={bf.sales_rep_id} disabled={readOnly} options={sellers.map(s => ({ value: s.id, label: s.name }))}
                onChange={v => setBrief({ sales_rep_id: v })} /></div>
            <div><div style={lbl}>Ответственный аккаунт {isMaster ? '' : '(автоматически)'}</div>
              <Select value={bf.account_manager_id} disabled={readOnly || !isMaster} options={accounts.map(s => ({ value: s.id, label: s.name }))}
                onChange={v => setBrief({ account_manager_id: v })} /></div>
          </div>


          {/* таргетинг — как в конструкторе МП */}
          <div>
            <div style={lbl}>Таргетинг</div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {TG_GROUPS.map(([g, title]) => {
                const selv = (bf.targeting || {})[g] || [];
                const cat = (targeting[g] || []).map(t => (typeof t === 'string' ? { id: t, value: t } : t)).filter(t => t && t.value != null);
                const q = (tgSearch[g] || '').trim().toLowerCase();
                const cs = q ? cat.filter(c => String(c.value).toLowerCase().includes(q)) : cat;
                const open = tgOpen === g;
                return (
                  <div key={g} style={{ display: 'flex', gap: 10, padding: '6px 0', borderTop: `1px solid ${T.row}`, alignItems: 'flex-start' }}>
                    <span style={{ flex: '0 0 96px', ...colHead, lineHeight: 1.4, paddingTop: 6 }}>{title}</span>
                    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                      {selv.map(v => <span key={v} style={chip}>{v}{!readOnly && <span onClick={() => toggleTg(g, v)} title="убрать" style={{ cursor: 'pointer', color: T.t4, fontSize: 13 }}>×</span>}</span>)}
                      {!readOnly && (
                        <span style={{ position: 'relative', display: 'inline-flex' }}>
                          <span onClick={() => setTgOpen(open ? null : g)} style={{ fontSize: 11.5, fontWeight: 600, color: T.accent, cursor: 'pointer', whiteSpace: 'nowrap' }}>+ из каталога</span>
                          {open && (
                            <>
                              <span onClick={() => setTgOpen(null)} style={{ position: 'fixed', inset: 0, zIndex: 210 }} />
                              <div onClick={e => e.stopPropagation()} style={{ position: 'absolute', top: 22, left: 0, zIndex: 220, minWidth: 240, maxHeight: 300, overflowY: 'auto', background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, boxShadow: T.pop, padding: 8 }}>
                                {cat.length >= 12 && (
                                  <input autoFocus value={tgSearch[g] || ''} onChange={e => setTgSearch(d => ({ ...d, [g]: e.target.value }))} placeholder="поиск"
                                    style={{ width: '100%', boxSizing: 'border-box', margin: '0 0 6px', padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, outline: 'none' }} />
                                )}
                                {cs.map(c => { const on = selv.includes(c.value); return (
                                  <span key={c.id} onClick={() => toggleTg(g, c.value)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, background: on ? T.accentTint : 'transparent', cursor: 'pointer' }}>
                                    <input type="checkbox" readOnly checked={on} />
                                    <span style={{ fontSize: 12, color: on ? T.accent : T.t1 }}>{c.value}</span>
                                  </span>
                                ); })}
                                {!cs.length && <div style={{ padding: '6px 8px', fontSize: 12, color: T.t4 }}>{cat.length ? 'ничего не найдено' : 'каталог пуст'}</div>}
                                {onAddTargeting && (
                                  <div style={{ display: 'flex', gap: 5, padding: '8px 2px 2px', borderTop: `1px solid ${T.row}`, marginTop: 6 }}>
                                    <input value={tgCat[g] || ''} onChange={e => setTgCat(d => ({ ...d, [g]: e.target.value }))}
                                      onKeyDown={e => { if (e.key === 'Enter') { const v = (tgCat[g] || '').trim(); if (v) { onAddTargeting(g, v); if (!selv.includes(v)) setTg(g, [...selv, v]); setTgCat(d => ({ ...d, [g]: '' })); } } }}
                                      placeholder="+ в каталог" style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, outline: 'none' }} />
                                    <span onClick={() => { const v = (tgCat[g] || '').trim(); if (v) { onAddTargeting(g, v); if (!selv.includes(v)) setTg(g, [...selv, v]); setTgCat(d => ({ ...d, [g]: '' })); } }}
                                      style={{ display: 'inline-flex', alignItems: 'center', padding: '0 10px', background: T.accent, color: 'var(--bg-card)', borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+</span>
                                  </div>
                                )}
                              </div>
                            </>
                          )}
                        </span>
                      )}
                      {!readOnly && (
                        <input value={tgText[g] || ''} onChange={e => setTgText(d => ({ ...d, [g]: e.target.value }))}
                          onKeyDown={e => { if (e.key === 'Enter') { const v = (tgText[g] || '').trim(); if (v && !selv.includes(v)) { setTg(g, [...selv, v]); setTgText(d => ({ ...d, [g]: '' })); } } }}
                          placeholder="+ текст (разово, не в каталог)" style={{ flex: '1 1 120px', minWidth: 90, height: 26, padding: '0 8px', border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 11, outline: 'none' }} />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* free-text бриф */}
          <div>
            <div style={lbl}>Текстовый бриф</div>
            <textarea value={bf.text || ''} disabled={readOnly} onChange={e => setBrief({ text: e.target.value })}
              placeholder="Задачи, ЦА, гео, форматы, KPI, ограничения…"
              style={{ width: '100%', boxSizing: 'border-box', minHeight: 84, padding: '10px 12px', border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, fontFamily: T.sans, resize: 'vertical', outline: 'none' }} />
          </div>

          {/* прогнозные показатели — полная таблица как в МП */}
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
              <span style={{ ...colHead, fontSize: 10 }}>Прогнозные показатели (за год)</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: T.emptyBg, border: `1px solid ${T.emptyBorder}`, borderRadius: 8, padding: '3px 9px', ...colHead, color: T.emptyText }}>
                <span style={{ width: 6, height: 6, borderRadius: 2, background: T.warning }} />жёлтые поля вводятся вручную
              </span>
              <span style={{ ...colHead }}>остальное считается от годовых сумм услуг</span>
              {/* Сезонные коэффициенты — в свободное место справа от заголовка; на узком
                  экране flexWrap переносит их на строку под заголовком.
                  Множатся частота/CTR/CR/SOV месяца при генерации сделок конвейером;
                  цена не множится (тариф), показы считаются из суммы и тарифа. */}
              <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <span style={{ ...colHead }} title="Поправка прогноза по месяцу при создании сделок: частота, CTR, CR, SOV. Цена не меняется. Пусто = 1">
                  сезонность
                </span>
                {MONTHS.map((mn, mi) => {
                  const has = ((products || {})[mi] || []).length > 0;   // в месяце есть услуги
                  const arr = bf.seasonality || [];
                  return (
                    <span key={mi} style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                      <span style={{ ...colHead, fontSize: 8, color: has ? T.fact : T.t4 }}>{mn}</span>
                      <input inputMode="decimal" disabled={readOnly} placeholder="1"
                        value={seasDraft[mi] !== undefined ? seasDraft[mi] : (arr[mi] != null ? String(arr[mi]).replace('.', ',') : '')}
                        title={has ? `${mn}: есть услуги — коэффициент применится` : `${mn}: услуг нет`}
                        onChange={e => {
                          // принимаем и запятую, и точку; лишние символы отсекаем
                          const v = e.target.value.replace(/[^\d.,]/g, '');
                          setSeasDraft(d => ({ ...d, [mi]: v }));
                        }}
                        onBlur={e => commitSeason(mi, e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                        style={{
                          width: 38, boxSizing: 'border-box', height: 22, padding: '0 3px', textAlign: 'center',
                          border: `1px solid ${has ? T.onBorder : T.emptyBorder}`, background: has ? T.onBg : T.emptyBg,
                          borderRadius: 5, fontFamily: T.mono, fontSize: 10, fontWeight: 700,
                          color: has ? T.income : T.t1, outline: 'none',
                        }} />
                    </span>
                  );
                })}
              </span>
            </div>
            {fcRows.length === 0
              ? <div style={{ fontSize: 12, color: T.t4, padding: '8px 0' }}>Добавьте услуги-размещения в месяцы — появится прогноз на годовой объём.</div>
              : (
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 900 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 8, padding: '0 4px 8px', borderBottom: `1px solid ${T.border}`, ...colHead }}>
                      <span>Позиция</span>
                      {FC_HEADS.map(h => <span key={h} style={{ textAlign: 'right', color: FC_YELLOW.includes(h) ? T.emptyText : T.t4 }}>{h}</span>)}
                    </div>
                    {fcRows.map(r => {
                      const fc = forecast[r.key] || {};
                      const imp = Math.round(r.imp || r.units);   // показы из тарификации (цена+модель услуги)
                      const freq = parseN(fc.freq), ctr = parseN(fc.ctr) / 100, cr = parseN(fc.cr) / 100, price = parseN(fc.price);
                      const net = r.amount, gross = Math.round(net * (1 + VAT));
                      const reach = freq > 0 ? imp / freq : 0, clicks = imp * ctr, checks = clicks * cr, revenue = checks * price;
                      const roi = gross > 0 ? (revenue - gross) / gross : NaN;
                      const ok = imp > 0;
                      const dim = ok ? undefined : T.emptyNum;
                      const money = v => (Number.isFinite(v) && v > 0 ? dec(v) : '—');
                      const int = v => (Number.isFinite(v) && v > 0 ? num(v) : '—');
                      const cell = (v, color, bold) => <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: bold ? 700 : 400, textAlign: 'right', color: dim || color }}>{v}</span>;
                      return (
                        <div key={r.key} style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 8, alignItems: 'center', padding: '6px 4px', borderBottom: `1px solid ${T.row}` }}>
                          <span style={{ fontSize: 11.5, fontWeight: 600, color: T.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${nm(r)} · год ${num(net)} ₽`}>{nm(r)}</span>
                          <NumInput value={fc.freq} disabled={readOnly} onChange={v => setFc(r.key, 'freq', v)} />
                          {cell(int(reach), T.t2)}
                          {cell(int(imp), T.t1, true)}
                          <NumInput value={fc.ctr} disabled={readOnly} onChange={v => setFc(r.key, 'ctr', v)} />
                          {cell(int(clicks), T.t1, true)}
                          {cell(money(imp > 0 ? net / imp * 1000 : 0), T.accent)}
                          {cell(money(clicks > 0 ? net / clicks : 0), T.accent)}
                          {cell(money(reach > 0 ? net / reach : 0), T.accent)}
                          <NumInput value={fc.cr} disabled={readOnly} onChange={v => setFc(r.key, 'cr', v)} />
                          {cell(int(checks), T.t2)}
                          {cell(money(checks > 0 ? net / checks : 0), T.accent)}
                          <NumInput value={fc.price} disabled={readOnly} onChange={v => setFc(r.key, 'price', v)} />
                          {cell(money(revenue), T.income, true)}
                          {cell(Number.isFinite(roi) && gross > 0 ? `${roi >= 0 ? '+' : '−'}${Math.abs(roi * 100).toFixed(0)} %` : '—', roi >= 0 ? T.income : T.danger, true)}
                          <NumInput value={fc.sov} disabled={readOnly} onChange={v => setFc(r.key, 'sov', v)} />
                        </div>
                      );
                    })}
                    {/* Итого */}
                    <div style={{ display: 'grid', gridTemplateColumns: FC_COLS, gap: 8, alignItems: 'center', padding: '10px 4px 0' }}>
                      <span style={{ ...colHead, fontWeight: 700, color: T.t3 }}>Итого за год</span>
                      {(() => {
                        const cells = [
                          [agg.reach > 0 ? num(agg.imp / agg.reach) : '—', T.t1],
                          [num(agg.reach), T.t1], [num(agg.imp), T.t1],
                          [agg.imp ? pct(agg.clicks / agg.imp) : '—', T.t1],
                          [num(agg.clicks), T.t1],
                          [agg.imp ? dec(agg.net / agg.imp * 1000) : '—', T.accent],
                          [agg.clicks ? dec(agg.net / agg.clicks) : '—', T.accent],
                          [agg.reach ? dec(agg.net / agg.reach) : '—', T.accent],
                          [agg.clicks ? pct(agg.checks / agg.clicks) : '—', T.t1],
                          [num(agg.checks), T.t1],
                          [agg.checks ? dec(agg.net / agg.checks) : '—', T.accent],
                          ['', T.t1],
                          [dec(agg.revenue), T.income],
                          [(() => { const gr = Math.round(agg.net * (1 + VAT)); return gr > 0 ? `${agg.revenue - gr >= 0 ? '+' : '−'}${Math.abs((agg.revenue - gr) / gr * 100).toFixed(0)} %` : '—'; })(), T.income],
                          ['', T.t1],
                        ];
                        return cells.map(([v, c], k) => <span key={k} style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, textAlign: 'right', color: c }}>{v}</span>);
                      })()}
                    </div>
                  </div>
                </div>
              )}
            <div style={{ marginTop: 10, fontFamily: T.mono, fontSize: 9.5, color: T.t4, lineHeight: 1.7 }}>
              ОХВАТ — показы ÷ частота · КЛИКИ — показы × CTR · ЧЕКИ — клики × CR · ДОХОД — чеки × цена<br />
              CPM / CPC / CPU / CPO — годовой бюджет до НДС ÷ показы × 1000, ÷ клики, ÷ охват, ÷ чеки · ROI — (доход − бюджет с НДС) ÷ бюджет с НДС
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '14px 24px', borderTop: `1px solid ${T.border}` }}>
          <span onClick={onClose} style={{ padding: '9px 18px', borderRadius: 10, background: T.accent, color: 'var(--bg-card)', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>Готово</span>
        </div>
      </div>
    </div>
  );
}
