import React, { useMemo, useRef, useState } from 'react'
import { productWithSurface } from '@/lib/dealTitle';
import { MONO, UI, HATCH, HATCH_RED, HATCH_GREEN } from '../salesTableKit'
import { DEAL_DOCS, docState } from '../../lib/dealDocs'
import { dm } from '@/lib/salesFormat'
import { serverDate } from '@/lib/dates'

/**
 * Канбан-доска сделок для дашборда: виды «По месяцам» и «По стадиям».
 * Дизайн — хендофф docs/дашборд нью.zip (design_handoff_deals_board).
 *
 * ОТЛИЧИЯ ОТ ХЕНДОФФА (у дизайнера не было наших данных):
 *  • стадии берём из НАШЕГО каталога (16 стадий, 3 этапа), а не из выдуманных девяти;
 *    слой денег приходит с сервера в our_stage.money_layer — здесь ничего не хардкодим;
 *  • «Оплачено» убрано: привязки платежей к сделке в системе нет;
 *  • «Документы» = Бриф · Медиаплан · ДС · Креативы — реальные сущности (lib/dealDocs);
 *  • сумма с НДС — реальная amount_with_vat, а не sum×1.22;
 *  • «Двинуть» открывает штатный диалог движения (там обязателен комментарий),
 *    а не двигает молча.
 */

const T = {
  card: 'var(--bg-card)', subtle: 'var(--bg-subtle)', tint: 'var(--bg-tint)', special: 'var(--bg-subtle)',
  border: 'var(--border-card)', inner: 'var(--border-inner)', row: 'var(--border-row)', hoverBorder: 'var(--border-hover)',
  nowBorder: 'var(--accent-border)', nowHead: 'var(--border-card)', specialBorder: 'var(--border-card)',
  t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)', t4: 'var(--text-faint)', t5: 'var(--text-disabled)',
  accent: 'var(--accent)', accentHover: 'var(--accent-hover)', accentTint: 'var(--accent-tint)',
  income: 'var(--income)', incomeTint: 'var(--income-tint)', incomeFg: 'var(--income-fg)',
  warning: 'var(--warning)', warningTint: 'var(--warning-tint)', warningFg: 'var(--warning-text)',
  gray: 'var(--bank-sovkom)',
  danger: 'var(--danger-fg)', dangerTint: 'var(--danger-tint)', dangerBorder: 'var(--danger-border)',
  pop: '0 10px 30px rgba(28,36,51,.16)',
  mono: MONO, sans: UI, ease: 'cubic-bezier(0.22,1,0.36,1)',
}

// Слой денег — ключи наши, серверные (money_layer из каталога стадий).
const LAYER = {
  'планируемые': { fill: 2, color: T.gray, label: 'Планируемые', tint: T.row, fg: T.t2 },
  'реализуемые': { fill: 4, color: T.warning, label: 'Реализуемые', tint: T.warningTint, fg: T.warningFg },
  'фактические': { fill: 6, color: T.income, label: 'Фактические', tint: T.incomeTint, fg: T.incomeFg },
}
const LAYER_ORDER = ['фактические', 'реализуемые', 'планируемые']
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const COL_W = 292, GAP = 16
const VAT = 0.22

const kk = v => Math.round(v / 1000).toLocaleString('ru-RU') + ' тыс'
const money = v => (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2).replace('.', ',') + ' млн' : kk(v))
const mln = v => (v / 1e6).toFixed(1).replace('.', ',')

// Цвет маркера услуги — стабильный хеш имени: справочник услуг растёт, руками не ведём.
const SERVICE_PALETTE = ['var(--accent)', 'var(--bank-opt)', 'var(--bank-cash)', 'var(--warning)', 'var(--income)', 'var(--bank-sovkom)', 'var(--series-pink)', 'var(--series-sky)']
const serviceDot = (name) => {
  const s = String(name || '')
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return SERVICE_PALETTE[h % SERVICE_PALETTE.length]
}

const daysAgo = (iso) => {
  if (!iso) return null
  const t = serverDate(iso).getTime()
  if (!Number.isFinite(t)) return null
  const d = Math.floor((Date.now() - t) / 86400000)
  return d <= 0 ? 'обновлено сегодня' : `обновлено ${d} дн. назад`
}

/** 6 квадратных ячеек индикатора слоя. Терминал — красная штриховка, без слоя — серая. */
function cellsFor(st) {
  // Красный штрих — только срыв. Раньше сюда попадал и «Архив успешных сделок»
  // (он тоже is_terminal), то есть успешно закрытая сделка красилась как провал.
  if (st && st.is_lost) return Array.from({ length: 6 }, () => HATCH_RED)
  if (st && st.is_terminal) return Array.from({ length: 6 }, () => HATCH_GREEN)
  const L = st && LAYER[st.money_layer]
  if (!L) return Array.from({ length: 6 }, () => HATCH)
  return Array.from({ length: 6 }, (_, i) => (i < L.fill ? L.color : T.inner))
}

/** Сделка из API → карточка доски. */
function toCard(d) {
  const st = d.our_stage
  const lost = !!(st && st.is_terminal)
  const L = st && LAYER[st.money_layer]
  const gross = d.amount_with_vat != null ? d.amount_with_vat : (d.amount || 0) * (1 + VAT)
  const sum = d.amount || 0
  const DOC_BG = [T.income, T.warning, T.inner]      // 0 готово · 1 в работе · 2 нет
  const docs = [
    { kind: 'brief', title: 'Бриф' }, { kind: 'mp', title: 'Медиаплан' },
    { kind: 'ds', title: 'Доп. соглашение' }, { kind: 'creatives', title: 'Креативы' },
  ].map(x => ({ ...x, state: docState(d, x.kind) }))
  return {
    raw: d,
    id: d.id, code: d.code || d.id, sum,
    stageId: st ? st.id : null,
    layer: lost ? null : (st ? st.money_layer : null),
    period: d.period || null,
    // Поверхность у услуг с раздельным прайсом считает сервер (row_context):
    // пустая — значит метки быть не должно, а не «не узнали».
    service: productWithSurface(d.product, d.inventory) || '—',
    stageLabel: st ? st.name : 'Без группы',
    stageBg: lost ? T.dangerTint : (L ? L.tint : T.subtle),
    stageFg: lost ? T.danger : (L ? L.fg : T.t3),
    stageDot: lost ? T.danger : (L ? L.color : T.t5),
    sumText: money(sum),
    sumFg: st && st.money_layer === 'фактические' ? T.income : (lost ? T.t4 : T.t1),
    cells: cellsFor(st),
    layerTitle: lost ? 'Провалена' : (L ? L.label : 'Без группы — требует разбора'),
    borderColor: lost ? T.dangerBorder : T.border,
    head: [d.advertiser, d.brand].filter(Boolean).join(' · ') || (d.title || '—'),
    sub: [d.agency, productWithSurface(d.product, d.inventory)].filter(Boolean).join(' · ') || '—',
    rows: [
      ['Продавец', d.sales_rep || '—'], ['Аккаунт', d.account_manager || '—'],
      ['Агентство', d.agency || '—'], ['Услуга', productWithSurface(d.product, d.inventory) || '—'],
      ['Период РК', (d.period_from || d.period_to) ? `${dm(d.period_from, '') || '…'} — ${dm(d.period_to, '') || '…'}` : '—'],
      ['Сумма с НДС', money(gross) + ' ₽'],
    ],
    docs: docs.map(x => ({ ...x, bg: DOC_BG[x.state] })),
    docsText: docs.filter(x => x.state === 0).length + ' / ' + docs.length,
    updated: daysAgo(d.date_modify || d.date_create),
  }
}

const mixOf = list => {
  const total = list.reduce((a, c) => a + c.sum, 0) || 1
  return LAYER_ORDER.map(key => ({
    color: LAYER[key].color,
    width: (list.filter(c => c.layer === key).reduce((a, c) => a + c.sum, 0) / total * 100).toFixed(1) + '%',
  })).filter(m => parseFloat(m.width) > 0)
}
const tipOf = list => {
  const map = {}
  list.forEach(c => { map[c.service] = map[c.service] || { sum: 0, n: 0 }; map[c.service].sum += c.sum; map[c.service].n++ })
  return Object.keys(map).sort((a, b) => map[b].sum - map[a].sum).map(k => ({
    label: k, dot: serviceDot(k), count: map[k].n + ' шт.', sum: money(map[k].sum) + ' ₽',
  }))
}

/** Колонки «По месяцам»: 6 мес = 1 прошедший + текущий + 4; 12 мес = 3 + текущий + 8. */
export function buildMonthColumns(cards, range, now) {
  const back = range === 12 ? 3 : 1
  const keys = []
  for (let i = -back; i < range - back; i++) {
    const abs = now.y * 12 + (now.m - 1) + i
    const y = Math.floor(abs / 12), m = ((abs % 12) + 12) % 12
    keys.push({ key: `${y}-${String(m + 1).padStart(2, '0')}`, label: `${MONTHS[m]} ${String(y).slice(2)}`, isNow: i === 0, past: i < 0 })
  }
  return keys.map((k, i) => {
    const list = cards.filter(c => c.period === k.key)
    const sum = list.reduce((a, c) => a + c.sum, 0)
    const fact = list.filter(c => c.layer === 'фактические').reduce((a, c) => a + c.sum, 0)
    return {
      id: k.key, title: k.label, month: k.key,
      titleFg: k.isNow ? T.accent : (k.past ? T.t3 : T.t1),
      colBg: k.isNow ? T.tint : T.card,
      colBorder: k.isNow ? T.nowBorder : T.border,
      headBorder: k.isNow ? T.nowHead : T.row,
      sum: sum ? money(sum) + ' ₽' : '—', sumFg: sum ? T.t1 : T.t5,
      sub: sum ? 'факт ' + money(fact) : 'пусто',
      count: list.length + ' сд.', mix: mixOf(list), tip: tipOf(list),
      addLabel: k.label, delay: (Math.min(i, 6) * 0.05).toFixed(2) + 's', cards: list,
    }
  })
}

/** Колонки «По стадиям» — весь наш каталог по порядку; терминалы и «без группы» в конец. */
export function buildStageColumns(cards, stages) {
  const cols = stages.map((s, i) => {
    const special = !!s.is_terminal
    const L = LAYER[s.money_layer]
    const list = cards.filter(c => c.stageId === s.id)
    const sum = list.reduce((a, c) => a + c.sum, 0)
    return {
      id: 's' + s.id, stageId: s.id, title: s.name,
      titleFg: special ? T.danger : T.t1,
      colBg: special ? T.special : T.card,
      colBorder: special ? T.dangerBorder : T.border,
      headBorder: T.row,
      sum: sum ? money(sum) + ' ₽' : '—', sumFg: sum ? T.t1 : T.t5,
      sub: special ? 'провалена' : (L ? L.label.toLowerCase() : s.phase || ''),
      count: list.length + ' сд.', mix: mixOf(list), tip: tipOf(list),
      addLabel: s.name.toLowerCase(), delay: (Math.min(i, 6) * 0.05).toFixed(2) + 's', cards: list,
    }
  })
  // «Без группы» — сделки без нашей стадии: их нельзя терять, это разбор.
  const orphans = cards.filter(c => c.stageId == null)
  if (orphans.length) {
    const sum = orphans.reduce((a, c) => a + c.sum, 0)
    cols.push({
      id: 'none', stageId: null, title: 'Без группы', titleFg: T.t3,
      colBg: T.special, colBorder: T.specialBorder, headBorder: T.row,
      sum: sum ? money(sum) + ' ₽' : '—', sumFg: sum ? T.t1 : T.t5, sub: 'требует разбора',
      count: orphans.length + ' сд.', mix: mixOf(orphans), tip: tipOf(orphans),
      addLabel: 'без группы', delay: '0.30s', cards: orphans,
    })
  }
  return cols
}

/** Ряд слоёв над доской «По стадиям». */
export function buildLayerGroups(cards) {
  const groups = ['планируемые', 'реализуемые', 'фактические'].map(key => {
    const L = LAYER[key]
    const list = cards.filter(c => c.layer === key)
    return {
      label: L.label, bg: L.tint, fg: L.fg, border: key === 'планируемые' ? T.border : L.tint,
      sum: money(list.reduce((a, c) => a + c.sum, 0)) + ' ₽', count: list.length + ' сд.',
      cells: Array.from({ length: 6 }, (_, i) => (i < L.fill ? L.color : T.card)),
    }
  })
  const orphans = cards.filter(c => !c.layer)
  groups.push({
    label: 'Требует разбора', bg: T.special, fg: T.t3, border: T.specialBorder,
    sum: money(orphans.reduce((a, c) => a + c.sum, 0)) + ' ₽', count: orphans.length + ' сд.',
    cells: Array.from({ length: 6 }, () => HATCH),
  })
  return groups
}

const PlayIcon = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z" /></svg>
const DocIcon = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
const PencilIcon = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20h4l10-10-4-4L4 16v4z" /><path d="M14.5 5.5l4 4" /></svg>

const IconBtn = ({ title, children, onClick }) => (
  <span className="db-ghost" title={title} onClick={onClick}
    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, border: `1px solid ${T.border}`, borderRadius: 9, color: T.t2, cursor: 'pointer' }}>{children}</span>
)

function DealCard({ c, open, onToggle, canEdit, onAdvance, onOpenCard, onBrief, onEdit }) {
  return (
    <div onClick={onToggle} style={{
      background: T.card, border: `1px solid ${open ? T.nowBorder : c.borderColor}`, borderRadius: 12,
      padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8, cursor: 'pointer',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: T.accent }}>{c.code}</span>
        <span title={c.layerTitle} style={{ display: 'inline-flex', gap: 1 }}>
          {c.cells.map((bg, i) => <span key={i} style={{ width: 9, height: 8, borderRadius: 2, background: bg }} />)}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: c.sumFg }}>{c.sumText}</span>
        <span style={{ fontSize: 10, color: T.t4 }}>{open ? '▴' : '▾'}</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span title={c.head} style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.head}</span>
        <span title={c.sub} style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.04em', color: T.t4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.sub}</span>
      </div>

      <span style={{ display: 'inline-flex', alignSelf: 'flex-start', alignItems: 'center', gap: 6, background: c.stageBg, color: c.stageFg, borderRadius: 7, padding: '3px 8px', fontSize: 10.5, fontWeight: 700 }}>
        <span style={{ width: 6, height: 6, borderRadius: 2, background: c.stageDot }} />{c.stageLabel}
      </span>

      {open && (
        <div onClick={e => e.stopPropagation()}
          style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8, borderTop: `1px solid ${T.row}`, animation: `riseIn .26s ${T.ease} both` }}>
          {c.rows.map(([label, value]) => (
            <span key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{label}</span>
              <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 600, textAlign: 'right' }}>{value}</span>
            </span>
          ))}

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>Документы</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 3 }}>
              {c.docs.map(d => <span key={d.kind} title={`${d.title}: ${['готово', 'в работе', 'нет'][d.state]}`} style={{ width: 16, height: 8, borderRadius: 2, background: d.bg }} />)}
            </span>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.t4 }}>{c.docsText}</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingTop: 2 }}>
            {canEdit && (
              <span className="db-primary" onClick={onAdvance} title="Двинуть сделку по каталогу стадий"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 12px', background: T.accent, color: 'var(--bg-card)', borderRadius: 9, fontSize: 11.5, fontWeight: 700, cursor: 'pointer' }}>
                <PlayIcon />Двинуть
              </span>
            )}
            <span className="db-ghost" onClick={onOpenCard}
              style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 12px', background: T.card, border: `1px solid ${T.border}`, color: T.t2, borderRadius: 9, fontSize: 11.5, fontWeight: 700, cursor: 'pointer' }}>Карточка</span>
            <IconBtn title="Бриф" onClick={onBrief}><DocIcon /></IconBtn>
            {canEdit && <IconBtn title="Редактировать" onClick={onEdit}><PencilIcon /></IconBtn>}
          </div>
          {c.updated && <span style={{ fontFamily: T.mono, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: T.t4 }}>{c.updated}</span>}
        </div>
      )}
    </div>
  )
}

function BoardColumn({ col, openId, setOpenId, tipId, setTipId, canEdit, handlers }) {
  return (
    <div style={{
      width: COL_W, flex: `0 0 ${COL_W}px`, boxSizing: 'border-box', background: col.colBg,
      border: `1px solid ${col.colBorder}`, borderRadius: 16, padding: '12px 12px 14px',
      display: 'flex', flexDirection: 'column', gap: 10, animation: `riseIn .4s ${T.ease} ${col.delay} both`,
    }}>
      <div onMouseEnter={() => setTipId(col.id)} onMouseLeave={() => setTipId(null)}
        style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 7, paddingBottom: 10, borderBottom: `1px solid ${col.headBorder}` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span title={col.title} style={{ fontSize: 13.5, fontWeight: 700, color: col.titleFg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{col.title}</span>
          <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9.5, color: T.t4, whiteSpace: 'nowrap' }}>{col.count}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em', color: col.sumFg }}>{col.sum}</span>
          <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9, color: T.t4 }}>{col.sub}</span>
        </div>
        <span style={{ display: 'flex', gap: 2, height: 5 }}>
          {col.mix.map((m, i) => <span key={i} style={{ width: m.width, borderRadius: 3, background: m.color }} />)}
        </span>

        {tipId === col.id && col.tip.length > 0 && (
          <span style={{
            position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 40, minWidth: 200,
            background: T.card, border: `1px solid ${T.border}`, boxShadow: T.pop, borderRadius: 12,
            padding: '9px 11px', display: 'flex', flexDirection: 'column', gap: 5, animation: `popIn .16s ${T.ease} both`,
          }}>
            <span style={{ fontFamily: T.mono, fontSize: 8.5, letterSpacing: '.08em', textTransform: 'uppercase', color: T.t4 }}>По услугам</span>
            {col.tip.map(t => (
              <span key={t.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 7, height: 7, borderRadius: 2, background: t.dot, flex: '0 0 7px' }} />
                <span style={{ fontSize: 11.5, color: T.t2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.label}</span>
                <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9.5, color: T.t4, whiteSpace: 'nowrap' }}>{t.count}</span>
                <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{t.sum}</span>
              </span>
            ))}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {col.cards.map(c => (
          <DealCard key={c.id} c={c} canEdit={canEdit}
            open={openId === c.id}
            onToggle={() => setOpenId(openId === c.id ? null : c.id)}
            onAdvance={e => { e.stopPropagation(); handlers.onAdvance && handlers.onAdvance(c.raw) }}
            onOpenCard={e => { e.stopPropagation(); handlers.onOpenCard && handlers.onOpenCard(c.raw) }}
            onBrief={e => { e.stopPropagation(); handlers.onBrief && handlers.onBrief(c.raw) }}
            onEdit={e => { e.stopPropagation(); handlers.onEdit && handlers.onEdit(c.raw) }} />
        ))}
        {canEdit && handlers.onAdd && (
          <div className="db-ghostadd" onClick={() => handlers.onAdd(col)}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '9px 10px', border: `1px dashed ${T.nowBorder}`, borderRadius: 12, color: T.accent, fontSize: 11.5, fontWeight: 600, cursor: 'pointer' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            Сделка в {col.addLabel}
          </div>
        )}
      </div>
    </div>
  )
}

/** Тумблер видов — экспортируем, чтобы страница поставила его в свой ряд управления. */
export const BoardTabs = ({ items, value, onChange, mono }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', padding: 3, height: 34, boxSizing: 'border-box', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10 }}>
    {items.map(([v, label]) => {
      const on = v === value
      return (
        <span key={v} onClick={() => onChange(v)} style={{
          display: 'inline-flex', alignItems: 'center', height: 26, padding: mono ? '0 11px' : '0 12px',
          borderRadius: 8, background: on ? T.accentTint : 'transparent', color: on ? T.accent : T.t2,
          fontFamily: mono ? T.mono : T.sans, fontSize: mono ? 11.5 : 12.5, fontWeight: on ? 700 : 600,
          whiteSpace: 'nowrap', cursor: 'pointer', transition: 'background-color 150ms ease, color 150ms ease',
        }}>{label}</span>
      )
    })}
  </span>
)

export default function DealsBoard({ deals = [], view = 'months', range = 6, stages = [], canEdit = false, ...handlers }) {
  const [openId, setOpenId] = useState(null)
  const [tipId, setTipId] = useState(null)
  const boardRef = useRef(null)
  const groupsRef = useRef(null)

  const now = useMemo(() => { const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() + 1 } }, [])
  const cards = useMemo(() => deals.map(toCard), [deals])
  const columns = useMemo(
    () => (view === 'stages' ? buildStageColumns(cards, stages) : buildMonthColumns(cards, range, now)),
    [cards, view, range, stages, now])
  const groups = useMemo(() => (view === 'stages' ? buildLayerGroups(cards) : []), [cards, view])
  const boardWidth = columns.length * COL_W + Math.max(0, columns.length - 1) * GAP

  // Ряд слоёв и доска скроллятся синхронно в обе стороны.
  const syncFrom = src => () => {
    const a = boardRef.current, b = groupsRef.current
    if (!a || !b) return
    if (src === 'board') b.scrollLeft = a.scrollLeft; else a.scrollLeft = b.scrollLeft
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, fontFamily: T.sans, color: T.t1 }}>
      <style>{`
        @keyframes riseIn { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:none } }
        @keyframes popIn { from { opacity:0; transform:translateY(-4px) } to { opacity:1; transform:none } }
        @media (prefers-reduced-motion: reduce) { .db-anim * { animation-duration:1ms !important; animation-delay:0s !important } }
        .db-ghost:hover { border-color:${T.hoverBorder}; color:${T.accent} }
        .db-primary:hover { background:${T.accentHover} }
        .db-ghostadd:hover { border-color:${T.accent}; background:${T.tint} }
      `}</style>

      {view === 'stages' && (
        <div ref={groupsRef} onScroll={syncFrom('groups')} style={{ overflow: 'auto hidden', padding: '0 4px', scrollbarWidth: 'none' }}>
          <div style={{ display: 'flex', gap: GAP, minWidth: boardWidth }}>
            {groups.map(g => (
              // Плашки тянутся на всю ширину доски: колонок у нас 17, а не 9 как в
              // макете, — при фиксированных 600px ряд обрывался и хвост доски (этап ДО)
              // оставался без шапки. Минимум 600px сохраняем.
              <div key={g.label} style={{
                flex: '1 1 600px', minWidth: 0, boxSizing: 'border-box', background: g.bg,
                border: `1px solid ${g.border}`, borderRadius: 14, padding: '10px 14px',
                display: 'flex', alignItems: 'center', gap: 12,
              }}>
                <span style={{ display: 'inline-flex', gap: 1 }}>
                  {g.cells.map((bg, i) => <span key={i} style={{ width: 9, height: 9, borderRadius: 2, background: bg }} />)}
                </span>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: g.fg }}>{g.label}</span>
                <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 9.5, color: T.t4 }}>{g.count}</span>
                <span style={{ fontFamily: T.mono, fontSize: 12.5, fontWeight: 700, color: g.fg }}>{g.sum}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div ref={boardRef} onScroll={syncFrom('board')} className="db-anim" style={{ overflow: 'auto hidden', padding: '0 4px 16px' }}>
        <div style={{ display: 'flex', gap: GAP, alignItems: 'flex-start', minWidth: boardWidth }}>
          {columns.map(col => (
            <BoardColumn key={col.id} col={col} openId={openId} setOpenId={setOpenId}
              tipId={tipId} setTipId={setTipId} canEdit={canEdit} handlers={handlers} />
          ))}
        </div>
      </div>
    </div>
  )
}
