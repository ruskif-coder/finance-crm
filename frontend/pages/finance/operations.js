import MonthInput from '@/components/MonthInput'
import { useState, useEffect, useLayoutEffect, useRef, Fragment } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { pageAccess } from '@/lib/pageGuard'
import Navbar, { can } from '@/components/Navbar'
import { MONO, UI, MultiDrop, IconBtn, LoadError, NoAccessScreen, PortalPopover, Z, UnderlineTabs, btn, primaryBtn } from '@/components/salesTableKit'
import dynamic from 'next/dynamic'
import useIsMobile from '@/components/mobile/useIsMobile'
const OperationsMobile = dynamic(() => import('@/components/mobile/OperationsMobile'), { ssr: false, loading: () => <div style={{ padding: 24 }} /> })
import { PeriodSelect } from '@/components/PeriodSelect'
import { makeApi as api } from '@/lib/http'
import { getPermissions } from '@/lib/auth'
import { T } from '@/lib/tokens'
import { errText, isAuth, detailText } from '@/lib/loadError'
import { nowTime, fileStamp, todayMsk, monthEnd } from '@/lib/dates'
import { sanMoney, moneyNum } from '@/lib/money'
import { requiredKeys, missingFields, isBlank } from '@/lib/opRequirements'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { ChainMark, ChainPanel, ForceDeleteDialog } from '@/components/operations/OperationChain'
import PayPlanSummary, { DupTag, FilterChip } from '@/components/operations/PayPlanSummary'
import OperationPanelHost from '@/components/operations/OperationPanelHost'
import { IssueMark } from '@/components/operations/OperationIssues'
import OpsSummary, { QUICK_LABEL } from '@/components/operations/OpsSummary'
import { RegistryFooter } from '@/components/accounts/mpRegistry/controls'
import { downloadFile } from '@/lib/download'
import useLatest from '@/lib/useLatest'
import { shortAnnexNumber } from '@/lib/annexNumber'
import CreditLines from '@/components/settings/CreditLines'   // третья вкладка «Кредиты» (владелец 10.11.2026)
import { useDialogs } from '@/components/dialogs'

const STATUSES = ['ОПЛАЧЕНО', 'ПЛАН ОПЛАТ', 'ПЛАН ПОСТУПЛЕНИЙ']
const BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']
const BANK_COLOR = { 'АльфаБанк': 'var(--bank-alfa)', 'ОПТ Банк': 'var(--bank-opt)', 'Совкомбанк': 'var(--bank-sovkom)', 'Наличные': 'var(--bank-cash)' }
const VAT_OPTIONS = [0, 5, 7, 10, 20, 22]
const PAGE_SIZES = [100, 300, 500]          // хендофф «Операции · NAVY»: по умолчанию 100
// «Незаполненные» — как в реестре сделок: выбранные дыры складываются по ИЛИ,
// потому что человек ищет, что дозаполнить, а не строку без всего сразу.
const GAP_FIELDS = [
  { value: 'article', label: 'нет статьи' },
  { value: 'counterparty', label: 'нет контрагента' },
  { value: 'period', label: 'нет периода' },
  { value: 'bank', label: 'нет банка' },
]
// статус-чип: фон / текст / точка
// фон / текст / точка / рамка — по хендоффу «Операции · NAVY» (17.11.2026): оплачено — деньги, планы — нейтральные, ожидает — внимание
const STATUS_CHIP = {
  'ОПЛАЧЕНО': ['var(--money-tint)', 'var(--money-fg)', 'var(--money)', 'var(--money-border)'],
  'ПЛАН ОПЛАТ': ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--text-faint)', 'var(--border-card)'],
  'ПЛАН ПОСТУПЛЕНИЙ': ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--accent)', 'var(--border-card)'],
  'ОЖИДАЕТ': ['var(--attn-tint)', 'var(--attn-fg)', 'var(--attn)', 'var(--attn-border)'],
}
const statusChip = (s) => STATUS_CHIP[s] || ['var(--bg-subtle)', 'var(--text-secondary)', 'var(--text-faint)', 'var(--border-card)']

const fmt = (n) => (n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '')
// с копейками (для сумм выбранного): всегда 2 знака
const fmt2 = (n) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0)
const fmtDate = (d) => { if (!d) return ''; const [y, m, dd] = String(d).slice(0, 10).split('-'); return dd ? `${dd}.${m}.${y.slice(2)}` : d }
// Статус не выбирается заранее (владелец 27.11.2026: «при создании новой операции по умолчанию статус не выбран»):
// пока его нет, форма показывает «статус» и красит поле контуром, а остальные обязательные появляются по выбору —
// какие именно, решает `lib/opRequirements` (одно правило на подсветку и на проверку сохранения).
const emptyForm = () => ({ date: '', status: '', income: '', expense: '', bank: '', period: '', vat_rate: 0, article_id: '', counterparty_id: '', ds_num: '', invoice: '', invoice_date: '', description: '', document_link: '' })


const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)' }
const lbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 5, display: 'block' }
const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 11px', fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none', fontFamily: UI }
// «Обязательное не заполнено»: контур внимания на поле формы (владелец 27.11.2026). Цвет — ролью, не хексом.
// Полная рамка, а не borderColor: шорткат border у поля содержит var(), и правка одного цвета разложила бы
// его на пустые longhands — рамка отвалилась бы к браузерной серой (проверено зондом 27.11.2026).
const NEEDS = { border: '1px solid var(--warning)', boxShadow: '0 0 0 3px var(--warning-tint)' }

// сегмент-переключатель (Месяц|Квартал, ставка НДС и т.п.)
function Seg({ options, value, onChange, mono }) {
  return (
    <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3, height: 36, alignItems: 'stretch' }}>
      {options.map(o => {
        const on = String(o.value) === String(value)
        return <button key={String(o.value)} type="button" onClick={() => onChange(o.value)}
          style={{ flex: '0 0 auto', border: 'none', borderRadius: 7, padding: '0 12px', cursor: 'pointer', fontFamily: mono ? MONO : UI, fontSize: 12, fontWeight: on ? 700 : 600, background: on ? 'var(--accent-tint)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-secondary)' }}>{o.label}</button>
      })}
    </div>
  )
}

// Однослот с поиском в шапке (для длинных списков — Статья/Контрагент). `invalid` — обязательное ещё не выбрано:
// рамка по роли внимания, как у обычных полей (владелец 27.11.2026).
function SingleSelect({ value, onChange, options, placeholder, emptyLabel, invalid }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const selO = options.find(o => String(o.value) === String(value))
  const shown = options.filter(o => !q.trim() || String(o.label).toLowerCase().includes(q.trim().toLowerCase())).slice(0, 300)
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div onClick={() => setOpen(o => !o)} style={{ ...inp, ...(invalid ? NEEDS : null), cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: selO ? 'var(--text-primary)' : 'var(--text-faint)' }}>{selO ? selO.label : placeholder} ▾</div>
      {open && (
        <div style={{ position: 'absolute', top: '110%', left: 0, right: 0, minWidth: 210, zIndex: Z.dropdown, marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', maxHeight: 300, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: 8 }}><input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="поиск" style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-card)', fontSize: 12, outline: 'none', fontFamily: UI }} /></div>
          <div style={{ overflowY: 'auto', padding: 5 }}>
            <div onClick={() => { onChange(''); setOpen(false); setQ('') }} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12, cursor: 'pointer', color: 'var(--text-muted)' }}>{emptyLabel || '— не выбрано —'}</div>
            {shown.map(o => <div key={o.value} onClick={() => { onChange(o.value); setOpen(false); setQ('') }} style={{ padding: '6px 8px', borderRadius: 7, fontSize: 12.5, cursor: 'pointer', background: String(o.value) === String(value) ? 'var(--accent-tint)' : 'transparent', color: String(o.value) === String(value) ? 'var(--accent)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</div>)}
            {!shown.length && <div style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
          </div>
        </div>
      )}
    </div>
  )
}

// Единый набор полей формы (создание/редактирование)
// Обводка иконок. На модульном уровне, а не внутри Operations2: её использует и
// OpFields, объявленный здесь же снаружи, — из компонента он её не видит.
// Кнопки шапки и форм — кит (17.11.2026, «привести все кнопки к единому стилю»): высота 32, как у кнопок-значков рядом
const HEAD_BTN = { height: 32, padding: '0 14px', display: 'inline-flex', alignItems: 'center', boxSizing: 'border-box', whiteSpace: 'nowrap' }
const IcoStroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round', strokeLinejoin: 'round' }

const DOC_ICON = <svg width="14" height="14" viewBox="0 0 24 24" style={IcoStroke}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>

const docBtn = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 26, height: 26, borderRadius: 8, border: 'none', padding: 0, cursor: 'pointer',
  background: 'var(--accent-tint)', color: 'var(--accent)',
}

// Документы операции: ВНЕШНЯЯ ССЫЛКА И ПРИЛОЖЕННЫЕ ФАЙЛЫ РАВНОПРАВНЫ.
//
// До 22.09.2026 пиктограмма зависела только от `document_link`. Человек прикладывал
// скан — файл ложился и в базу, и на диск, — а в реестре оставался прочерк: открыть
// его отсюда было нечем, и со стороны это выглядело как «файл не прикрепился».
//
// Одна цель — открываем сразу, без лишнего щелчка. Несколько — показываем выбор:
// угадывать за человека, что ему нужнее, скан или ссылка, не из чего.
//
// Компонент объявлен на модульном уровне, а не внутри страницы: этот проект уже
// спотыкался о компоненты, рождённые заново на каждый рендер.
function DocCell({ op, open, onToggle, onOpenFile }) {
  const link = op.document_link
  const files = op.files || []
  const total = (link ? 1 : 0) + files.length
  if (!total) return <span style={{ color: 'var(--text-disabled)' }}>—</span>

  // Ссылка остаётся ссылкой: средний щелчок, «открыть в новой вкладке» и копирование
  // адреса работают только у настоящего <a>. Проверка схемы та же, что была: адрес в
  // этом поле вводят руками, и `javascript:` туда попасть не должен.
  const linkEl = (title) => (
    <a href={/^https?:\/\//i.test(link) ? link : undefined} target="_blank" rel="noreferrer"
      onClick={e => e.stopPropagation()} title={title} style={docBtn}>{DOC_ICON}</a>
  )
  if (total === 1 && link) return linkEl('Открыть документ по ссылке')
  if (total === 1) {
    const f = files[0]
    return (
      <button onClick={e => { e.stopPropagation(); onOpenFile(op.id, f) }}
        title={`Скачать «${f.name}»`} style={docBtn}>{DOC_ICON}</button>
    )
  }
  return (
    <span data-pop-root style={{ position: 'relative', display: 'inline-flex' }} onClick={e => e.stopPropagation()}>
      <button onClick={onToggle} title={`Документов: ${total}`}
        style={{ ...docBtn, width: 'auto', padding: '0 7px', gap: 4 }}>
        {DOC_ICON}<span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>{total}</span>
      </button>
      <PortalPopover open={open} minWidth={240} maxHeight={280}>
          {link && (
            <a href={/^https?:\/\//i.test(link) ? link : undefined} target="_blank" rel="noreferrer"
              style={docRow}>
              <span style={{ color: 'var(--accent)', flex: '0 0 auto' }}>{DOC_ICON}</span>
              <span style={docRowName}>Ссылка на документ</span>
            </a>
          )}
          {files.map(f => (
            <button key={f.id} onClick={() => onOpenFile(op.id, f)} style={{ ...docRow, width: '100%', border: 'none', background: 'none', textAlign: 'left', cursor: 'pointer' }}>
              <span style={{ color: 'var(--text-faint)', flex: '0 0 auto' }}>{DOC_ICON}</span>
              <span style={docRowName} title={f.name}>{f.name}</span>
            </button>
          ))}
      </PortalPopover>
    </span>
  )
}

const docRow = {
  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8,
  fontSize: 12.5, color: 'var(--text-primary)', textDecoration: 'none', fontFamily: UI,
}
const docRowName = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }

// Ячейка формы. ВЫНЕСЕНА из OpFields на модульный уровень: если объявлять её внутри
// компонента, при каждом рендере (нажатии клавиши в поле) она получает новую
// идентичность функции → React размонтирует/монтирует <Cell> с input'ом заново →
// поле теряет фокус после каждой цифры. Стабильная ссылка это устраняет.
const Cell = ({ label, opt, accent, children }) => (
  <div><span style={lbl}>{label}{opt ? <span style={{ color: accent === 'warn' ? T.warningText : 'var(--text-faint)', marginLeft: 6 }}>необяз.</span> : ''}</span>{children}</div>
)
// Метка поля для проб формы (подсветка обязательных, 27.11.2026): `data-op-field` на обёртке, чтобы зонд читал
// рамку того же элемента, что видит человек, и не зависел от порядка селектов на странице.
const Field = ({ k, children }) => <span data-op-field={k} style={{ display: 'block' }}>{children}</span>

function OpFields({ f, set, articles, counterparties, accent, mode = 'edit',
                    files = [], onAttach, onRemoveFile, busyFiles }) {
  const artOpts = articles.map(a => ({ value: a.id, label: a.name }))
  const cpOpts = counterparties.map(c => ({ value: c.id, label: c.name }))
  const cpById = Object.fromEntries(counterparties.map(c => [c.id, c]))
  // Разбор суммы — общим moneyNum, тем же, что уходит на сервер. Здесь стоял свой
  // разбор, вырезавший всё кроме цифр и точки: запятая пропадала, и «100714,71»
  // превращалось в 10 071 471 — превью НДС врало ровно в 100 раз, а в базу уходило
  // правильное значение. Расхождение двух разборов одной строки не видно глазами.
  const amt = moneyNum(f.income) || moneyNum(f.expense)
  const vatAmount = f.vat_rate > 0 && amt > 0 ? amt * f.vat_rate / (100 + f.vat_rate) : 0
  // Смена статуса (только при создании): «оплачено» — дата сегодня, банк выбирает человек (пустой подсветится);
  // «план оплат/поступлений» — дата и банк пустые (даже при переключении).
  const onStatus = (v) => {
    if (mode !== 'create') return set({ status: v })
    if (v === 'ОПЛАЧЕНО') set({ status: v, date: f.date || todayMsk(), bank: f.bank })
    else set({ status: v, date: '', bank: '' })
  }
  // Обязательные поля подсвечиваются контуром только при создании: у старых записей пустой банк или статья — норма.
  // Какие именно обязательны при выбранном статусе, решает lib/opRequirements — то же правило, что проверяет сохранение.
  const need = mode === 'create' ? new Set(requiredKeys(f.status)) : new Set()
  const warn = (k) => (need.has(k) && isBlank(f[k]) ? NEEDS : null)
  // Выбор контрагента подтягивает его статью/НДС по умолчанию — по направлению суммы
  // (поступление → доходные, списание → расходные).
  const onCounterparty = (v) => {
    const patch = { counterparty_id: v }
    const cp = cpById[+v] || cpById[v]
    if (cp) {
      const inc = moneyNum(f.income) > 0, exp = moneyNum(f.expense) > 0
      const art = inc ? cp.default_article_income_id : exp ? cp.default_article_expense_id : null
      if (art) patch.article_id = art
      const vr = inc ? cp.vat_rate_income : exp ? cp.vat_rate_expense : null
      if (vr != null) patch.vat_rate = vr
    }
    set(patch)
  }
  const sel = (val, onCh, opts, ph, extra) => (
    <select value={val} onChange={e => onCh(e.target.value)} style={{ ...inp, ...(extra || null) }}><option value="">{ph}</option>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
        <Cell label="Статус"><Field k="status">{sel(f.status, onStatus, STATUSES.map(s => ({ value: s, label: s })), 'статус', warn('status'))}</Field></Cell>
        <Cell label="Дата" opt accent={accent}><Field k="date">{<input type="date" value={f.date} onChange={e => set({ date: e.target.value })} style={{ ...inp, ...(accent === 'warn' ? { border: '1px solid var(--dot-current-dz)' } : null), ...(warn('date') || null) }} />}</Field></Cell>
        <Cell label="Поступление"><input inputMode="decimal" value={f.income ?? ''} onChange={e => set({ income: sanMoney(e.target.value) })} placeholder="0 ₽" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Списание"><input inputMode="decimal" value={f.expense ?? ''} onChange={e => set({ expense: sanMoney(e.target.value) })} placeholder="0 ₽" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Банк" opt accent={accent}><Field k="bank">{sel(f.bank, v => set({ bank: v }), BANKS.map(b => ({ value: b, label: b })), 'не указан', warn('bank'))}</Field></Cell>
        <Cell label="Период"><Field k="period"><PeriodSelect dense invalid={!!warn('period')} value={f.period} onChange={v => set({ period: v })} /></Field></Cell>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
        <Cell label="НДС">
          <div style={{ display: 'flex', gap: 6 }}>
            <select value={f.vat_rate} onChange={e => set({ vat_rate: +e.target.value })} style={{ ...inp, flex: '0 0 44%', fontFamily: MONO }}>
              {VAT_OPTIONS.map(v => <option key={v} value={v}>{v}%</option>)}
            </select>
            <input readOnly value={vatAmount ? fmt2(vatAmount) + ' ₽' : '—'} title="Сумма НДС по ставке (не редактируется)"
              style={{ ...inp, flex: 1, minWidth: 0, fontFamily: MONO, textAlign: 'right', background: 'var(--bg-subtle)', color: 'var(--text-muted)' }} />
          </div>
        </Cell>
        <Cell label="Статья"><Field k="article_id"><SingleSelect value={f.article_id} onChange={v => set({ article_id: v })} options={artOpts} placeholder="не выбрана" emptyLabel="— не выбрано —" invalid={!!warn('article_id')} /></Field></Cell>
        <Cell label="Контрагент"><Field k="counterparty_id"><SingleSelect value={f.counterparty_id} onChange={onCounterparty} options={cpOpts} placeholder="выберите или введите" emptyLabel="— не выбрано —" invalid={!!warn('counterparty_id')} /></Field></Cell>
        <Cell label="№ ДС"><input value={f.ds_num} onChange={e => set({ ds_num: e.target.value })} placeholder="—" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="№ счёта"><input value={f.invoice} onChange={e => set({ invoice: e.target.value })} placeholder="—" style={{ ...inp, fontFamily: MONO }} /></Cell>
        <Cell label="Дата счёта"><input type="date" value={f.invoice_date} onChange={e => set({ invoice_date: e.target.value })} style={inp} /></Cell>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1.7fr', gap: 14 }}>
        <Cell label="Документ">
          <div style={{ display: 'flex', gap: 6 }}>
            <input value={f.document_link} onChange={e => set({ document_link: e.target.value })} placeholder="https://…"
              title="Ссылка на документ во внешнем хранилище" style={{ ...inp, flex: 1, minWidth: 0 }} />
            {/* Сканы кладём к себе: часть первички существует только на бумаге, и
                ссылке её заменить нечем. Ссылка при этом остаётся — у операции может
                быть и то, и другое. */}
            <label title="Приложить скан документа"
              style={{ ...inp, flex: '0 0 auto', width: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6,
                       cursor: busyFiles ? 'wait' : 'pointer', whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 12,
                       fontWeight: 700, color: 'var(--accent)', borderColor: 'var(--accent)', opacity: busyFiles ? .6 : 1 }}>
              <input type="file" multiple disabled={!!busyFiles} style={{ display: 'none' }}
                onChange={e => { const list = Array.from(e.target.files || []); e.target.value = ''; if (list.length) onAttach && onAttach(list) }} />
              <svg width="13" height="13" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 5v14M5 12h14" /></svg>
              {busyFiles ? 'Загрузка…' : 'Приложить файл'}
            </label>
          </div>
          {files.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 7 }}>
              {files.map((fl, i) => (
                <div key={fl.id || ('p' + i)} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, minWidth: 0 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" style={{ ...IcoStroke, flex: '0 0 auto', color: 'var(--text-faint)' }}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
                  <span title={fl.original_name} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: fl.pending ? 'var(--text-muted)' : 'var(--text-primary)' }}>{fl.original_name}</span>
                  <span style={{ flex: '0 0 auto', fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{fl.pending ? 'после сохранения' : fmtSize(fl.size_bytes)}</span>
                  <span onClick={() => onRemoveFile && onRemoveFile(fl, i)} title="Убрать файл" className="op-ico op-ico-d"
                    style={{ flex: '0 0 auto', width: 18, height: 18, color: 'var(--text-faint)' }}>
                    <svg width="11" height="11" viewBox="0 0 24 24" style={IcoStroke}><path d="M6 6l12 12M18 6L6 18" /></svg>
                  </span>
                </div>
              ))}
            </div>
          )}
        </Cell>
        <Cell label="Описание"><input value={f.description} onChange={e => set({ description: e.target.value })} placeholder="комментарий к операции" style={inp} /></Cell>
      </div>
    </div>
  )
}

const fmtSize = (n) => !n ? '' : n < 1024 ? n + ' Б' : n < 1024 * 1024 ? Math.round(n / 1024) + ' КБ'
  : (n / 1024 / 1024).toFixed(1).replace('.', ',') + ' МБ'

// колонки таблицы (сетка из хендоффа)
// Четвёртый элемент — ключ сортировки на сервере (см. _sort_map в operations.py).
// Он есть у каждой колонки, кроме «Действий»: там сортировать нечего. «ДЗ» сортируется
// по сроку оплаты — метка (просрочка/текущая/план) это и есть возраст долга.
// Хендофф «Операции · NAVY» (17.11.2026): одна «Сумма» со знаком вместо «Поступления» и «Списания»; «Контрагент» — сразу за ней
// (единственная перестановка); левая группа до «Контрагента» включительно закреплена при прокрутке вбок (`STICKY`).
const COLS = [
  ['sel', '16px', ''], ['date', '74px', 'Дата', 'date'], ['status', '136px', 'Статус', 'status'], ['dz', '26px', 'ДЗ', 'dz'],
  ['amount', '118px', 'Сумма', 'amount'], ['counterparty', '260px', 'Контрагент', 'counterparty'],
  ['bank', '110px', 'Банк', 'bank'], ['period', '80px', 'Период', 'period'], ['article', '120px', 'Статья', 'article'],
  ['vat', '48px', 'НДС', 'vat_rate'], ['vat_amount', '92px', 'НДС сумма', 'vat_fact'], ['ds_num', '104px', '№ ДС', 'ds_num'], ['invoice', '96px', '№ счёта', 'invoice'],
  ['invoice_date', '82px', 'Дата счёта', 'invoice_date'], ['doc', '40px', 'Док', 'doc'], ['description', 'minmax(180px,1fr)', 'Описание', 'description'], ['actions', '88px', 'Действия'],
]
const STICKY = ['sel', 'date', 'status', 'dz', 'amount', 'counterparty']
const GAP = 10
const ROW_PAD = 8
const RIGHT = new Set(['amount', 'vat', 'vat_amount'])
const CENTER = new Set(['dz'])     // метка ДЗ по центру: у левого края ореол точки срезался overflow ячейки (18.11.2026)
const justify = (k) => (RIGHT.has(k) ? 'flex-end' : CENTER.has(k) ? 'center' : 'flex-start')
// Клик по строке открывает боковую панель операции (владелец 09.11.2026); эти ячейки живут своими кликами
const NO_PANEL = new Set(['sel', 'doc', 'actions'])
const PAD_LEFT = { counterparty: 6, ds_num: 14 }       // колонка после прижатой вправо суммы — отступ и у шапки, и у ячейки

/** ДЗ планового поступления (хендофф «Операции · NAVY»): в срок — пустое кольцо, срок прошёл (в пределах GRACE_DAYS) — точка
 *  внимания с ореолом, просрочка — точка провала с ореолом. Правила — receivables.py; подсказка — по сроку с сервера. */
const DZ_LOOK = { future: ['var(--ok)', false], current: ['var(--attn)', true], overdue: ['var(--bad)', true] }
function DzMark({ status, due }) {
  const look = DZ_LOOK[status]
  if (!look) return <span style={{ color: 'var(--text-disabled)' }}>—</span>
  const d = due ? new Date(`${String(due).slice(0, 10)}T00:00:00`) : null
  const days = d ? Math.round((d - new Date(new Date().toDateString())) / 86400000) : null
  const dd = due ? `${String(due).slice(8, 10)}.${String(due).slice(5, 7)}` : ''
  const tip = days == null ? '' : status === 'future' ? `в срок · до ${dd} · ${days} дн`
    : status === 'current' ? `срок был ${dd} · ${-days} дн назад, до просрочки ${30 + days} дн` : `просрочено ${-days} дн · срок был ${dd}`
  const [c, filled] = look
  return <span title={tip} style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', boxSizing: 'border-box',
    background: filled ? c : 'transparent', border: `1.5px solid ${c}`, boxShadow: filled ? `0 0 0 3px color-mix(in srgb, ${c} 22%, transparent)` : 'none' }} />
}

export default function Operations2() {
  const { confirm, alert } = useDialogs()
  const router = useRouter()
  /* Прямая ссылка открывала экран и у того, кому раздел не открыт: меню пункт прячет,
     адрес — нет. Дальше каждый экран вёл себя по-своему, и «нет доступа» читалось как
     «сломалось». Решение о доступе принимает карта навигации — см. lib/pageGuard. */
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])
  const access = pageAccess(router.pathname, mounted)
  // Точечная ссылка на операцию — /finance/operations?op=<id>. Приходит из импорта
  // документов Диадока, где иначе на операцию сослаться нечем: у реестра нет ни
  // карточки строки, ни собственного адреса у операции.
  const focusOp = router.query.op ? String(router.query.op) : null
  // Вкладка «План оплат» (`?tab=plan`) — тот же реестр, ограниченный операциями, которые
  // человек сам отметил «В план» (решение владельца 02.11.2026: вкладка внутри операций,
  // функционал целиком тот же). В адресе — чтобы обновление страницы не сбрасывало вкладку.
  const payPlan = router.query.tab === 'plan'
  const creditTab = router.query.tab === 'credit'   // настройка кредитных линий (владелец 10.11.2026: «3 вкладкой в операциях»)
  const [perms, setPerms] = useState({})
  const canEdit = can(perms, 'operations', 'edit')
  // Кнопки — по тому праву, которое спросит сервер (аудит 23.09.2026, 6.L1): создание и
  // удаление гейтились правом правки, и человек без них видел кнопки, отвечавшие 403.
  const canCreate = can(perms, 'operations', 'create')
  const canDelete = can(perms, 'operations', 'delete')
  const canImport = can(perms, 'import')
  const canCredit = can(perms, 'settings_balances')   // право кредитных линий — то же, что у стартовых остатков
  const isMobile = useIsMobile()
  const [ops, setOps] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  // Сбой загрузки. Пустая таблица от сбоя и пустая от фильтра — разные вещи.
  const [err, setErr] = useState('')
  // Материнская с частичными оплатами удаляется только принудительно, с паролем: сервер
  // отвечает 409, и здесь открывается подтверждение. { id, message } или null.
  const [forceDel, setForceDel] = useState(null)
  const [bulkPwd, setBulkPwd] = useState(null)   // массовое удаление цепочки ждёт пароль
  const [articles, setArticles] = useState([])
  const [counterparties, setCounterparties] = useState([])
  const [periodOptions, setPeriodOptions] = useState([])
  const [updatedAt, setUpdatedAt] = useState('')

  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(100)
  const [quick, setQuick] = useState(null)            // плитка итогов: in | out | over | empty
  const [summary, setSummary] = useState(null)
  const [sortCol, setSortCol] = useState('date')
  const [sortDir, setSortDir] = useState('desc')

  const [dateFrom, setDateFrom] = useState(''); const [dateTo, setDateTo] = useState('')
  const [fStatus, setFStatus] = useState([]); const [fBank, setFBank] = useState([]); const [fArticle, setFArticle] = useState([]); const [fCp, setFCp] = useState([]); const [fPeriod, setFPeriod] = useState([]); const [fOpType, setFOpType] = useState([]); const [fGaps, setFGaps] = useState([])

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState(emptyForm())
  const [editing, setEditing] = useState(null)        // { id, ...form }
  const [sel, setSel] = useState({})                  // { id: true }
  // Сводка плана оплат и выбранный в ней блок (хендофф 02.11.2026): блок несёт ids своих строк — таблица
  // показывает ровно их. Один активный фильтр; смена вкладки его снимает.
  const [planSum, setPlanSum] = useState(null)
  const [planF, setPlanF] = useState(null)
  const setTab = (t) => {
    setSel({}); setPage(0); setPlanF(null)
    router.replace({ pathname: router.pathname, query: t === 'plan' || t === 'credit' ? { tab: t } : {} }, undefined, { shallow: true })
  }
  const [bulk, setBulk] = useState({ status: '', date: '', period: '', bank: '', vat_rate: '', article_id: '', counterparty_id: '' })
  const [editFiles, setEditFiles] = useState([])   // сканы открытой на правку операции
  const [newFiles, setNewFiles] = useState([])     // выбранные в форме создания, ещё не отправленные
  const [filesBusy, setFilesBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  // Высота шапки меряется, а не задаётся числом: у шапки две строки, и их набор
  // зависит от прав пользователя — закреплённая панель массовой правки иначе то
  // наезжала бы на меню, то висела бы с зазором.
  const [navH, setNavH] = useState(60)
  const lastSelIdx = useRef(null)   // якорь для shift-выбора диапазона
  const [hidden, setHidden] = useState(new Set())   // скрытые колонки
  const [colPicker, setColPicker] = useState(false)
  // Какая строка показывает выбор документа. Одна на таблицу: два открытых списка
  // одновременно не нужны, а хранение в самой строке потребовало бы состояния на
  // каждую из сотни.
  const [docMenu, setDocMenu] = useState(null)
  // Закрытие списка документов — щелчком мимо. Признак «мимо» один на проект:
  // `closest('[data-pop-root]')`. Сама панель рисуется порталом в body, поэтому
  // проверять вложенность в строку таблицы бесполезно — её там нет.
  useEffect(() => {
    if (docMenu === null) return undefined
    const onDown = (e) => {
      if (!e.target.closest || !e.target.closest('[data-pop-root]')) setDocMenu(null)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [docMenu])
  // Своя прокрутка таблицы (хендофф, раздел 3): карточка занимает оставшуюся высоту окна, прокручивается таблица, а не страница
  const scrollRef = useRef(null)
  const [tableH, setTableH] = useState(480)
  useLayoutEffect(() => {
    const fit = () => { const el = scrollRef.current; if (el) setTableH(Math.max(320, window.innerHeight - el.getBoundingClientRect().top - 52 - 28)) }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  })
  const toggleCol = (k) => setHidden(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); localStorage.setItem('ops2_hidden', JSON.stringify([...n])); return n })
  const visibleCols = COLS.filter(([k]) => !hidden.has(k))
  const gridT = visibleCols.map(c => c[1]).join(' ')
  const stickLeft = {}
  { let x = ROW_PAD; for (const [k, w] of visibleCols) { if (!STICKY.includes(k)) break; stickLeft[k] = x; x += parseInt(w, 10) + GAP } }
  const lastStick = visibleCols.filter(([k]) => k in stickLeft).slice(-1)[0]?.[0]
  const stick = (k, bg) => (k in stickLeft ? { position: 'sticky', left: stickLeft[k], zIndex: 1, background: bg,
    // фон ячейки закрывает и зазор справа — под закреплённой группой не просвечивает прокрученное; у последней — разделитель
    boxShadow: k === lastStick ? '1px 0 0 0 var(--border-card)' : `${GAP}px 0 0 0 ${bg}` } : null)

  const tok = () => localStorage.getItem('token')

  useEffect(() => {
    if (!tok()) { router.push('/login'); return }
    try { setPerms(getPermissions()) } catch (e) {}
    try { const h = JSON.parse(localStorage.getItem('ops2_hidden')); if (Array.isArray(h)) setHidden(new Set(h.flatMap(k => (k === 'income' || k === 'expense' ? (h.includes('income') && h.includes('expense') ? ['amount'] : []) : [k])))) } catch (e) { /* нет настройки — все колонки */ }
    // Справочники формы. Один `.catch(() => {})` на оба обнулял ОБА списка при
    // падении любого: выпадашки пустели, и это читалось как «в базе ничего нет».
    Promise.all([api(tok()).get('/articles/'), api(tok()).get('/counterparties/?limit=1000')])
      .then(([a, c]) => { setArticles(a.data?.items || a.data || []); setCounterparties(c.data?.items || c.data || []) })
      .catch(e => { if (!isAuth(e)) setErr('Справочники статей и контрагентов не загрузились — выпадающие списки пусты не потому, что данных нет') })
    api(tok()).get('/operations/periods').then(r => setPeriodOptions(r.data?.periods || [])).catch(() => {})
    const measure = () => { const el = document.querySelector('[data-navbar]'); if (el) setNavH(el.getBoundingClientRect().height) }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  // Возврат на экран = перечитать. Реестр операций правят с других экранов и другие
  // люди; без этого список показывал состояние на момент открытия вкладки
  // (lib/useRefreshOnReturn, замер 13.09.2026 — финмодуль был пропущен целиком).
  useRefreshOnReturn(() => { if (tok()) loadOps({ quiet: true }) })

  // Номер запроса: ответ, пришедший после более нового, отбрасывается. Иначе при быстрой
  // смене фильтров старый ответ ложился поверх свежего, и под новым фильтром висел
  // список старого (аудит 23.09.2026, 6.M4).
  const latest = useLatest()
  const loadOps = async ({ quiet = false } = {}) => {
    const fresh = latest()
    // Фоновая перечитка — тихая: «Загрузка…» вместо таблицы сбрасывала прокрутку и
    // раскрытые строки (аудит, 6.M6).
    if (!quiet) setLoading(true)
    setErr('')
    try {
      const params = new URLSearchParams({ skip: page * pageSize, limit: pageSize, sort_col: sortCol, sort_dir: sortDir })
      fStatus.forEach(s => params.append('status', s)); fBank.forEach(b => params.append('bank', b))
      fOpType.forEach(t => params.append('op_type', t))
      fArticle.forEach(id => params.append('article_id', id)); fCp.forEach(id => params.append('counterparty_id', id))
      fPeriod.forEach(p => params.append('period', p)); fGaps.forEach(g => params.append('gaps', g))
      if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo)
      // ?op=<id> — точечная ссылка на операцию (из импорта документов Диадока).
      // Пока она в адресе, остальные фильтры не важны: показывается ровно эта строка.
      if (focusOp) params.append('ids', focusOp)
      if (payPlan) params.append('pay_plan', 'true')
      if (payPlan && planF) planF.ids.forEach(id => params.append('ids', id))
      // итоги — по тем же фильтрам, без плитки (числа плиток не прыгают, когда одна нажата); список — с плиткой
      const sumParams = new URLSearchParams(params); ['skip', 'limit', 'sort_col', 'sort_dir', 'ids'].forEach(k => sumParams.delete(k))
      if (!focusOp) api(tok()).get(`/operations/summary?${sumParams}`).then(r => { if (fresh()) setSummary(r.data) }).catch(() => { if (fresh()) setSummary(null) })
      if (quick) params.append('quick', quick)
      if (payPlan) api(tok()).get('/operations/pay-plan/summary').then(r => { if (fresh()) setPlanSum(r.data) }).catch(() => {})
      const res = await api(tok()).get(`/operations/?${params}`)
      if (!fresh()) return
      setOps(res.data?.items || []); setTotal(res.data?.total || 0)
      // Время последней загрузки данных (обновляется при любом изменении — add/edit/delete
      // зовут loadOps). Считаем на клиенте, не при рендере — без SSR-рассинхрона.
      setUpdatedAt(nowTime())
    } catch (e) {
      // Реестр операций — журнал денег. «Ничего не нашлось» и «не смогли спросить»
      // на нём выглядят одинаково пустой таблицей, и различать их обязан экран.
      if (fresh() && !isAuth(e)) setErr(errText(e))
    }
    finally { if (fresh()) setLoading(false) }
  }
  // Смена ЛЮБОГО фильтра возвращает на первую страницу и снимает выделение. Раньше это
  // делал только фильтр «Незаполненные»: на третьей странице выбранный статус с сорока
  // строками запрашивал skip=600 и показывал пустую таблицу при «40 записей», а
  // выделение переживало фильтр и «Удалить» задевало невидимые строки (6.M1, 6.M2).
  const filtersKey = JSON.stringify([fStatus, fBank, fArticle, fCp, fPeriod, fOpType, fGaps, dateFrom, dateTo, planF && [planF.kind, planF.value], quick])
  const lastFilters = useRef(filtersKey)
  useEffect(() => {
    if (!tok()) return
    if (lastFilters.current !== filtersKey) {
      lastFilters.current = filtersKey
      setSel({})
      if (page !== 0) { setPage(0); return }      // загрузку сделает прогон с page = 0
    }
    loadOps()
  }, [page, pageSize, sortCol, sortDir, filtersKey, focusOp, payPlan])

  // Тип операции фильтрует сервер (op_type), строки приходят уже отобранными.
  const rows = ops
  // Боковая панель операции: открыта по клику на строку, ↑/↓ — соседи на текущей странице
  const [panelId, setPanelId] = useState(null)
  const openPanel = (e, id) => {
    if (e.target.closest('[data-noexp], input, button, a, select, textarea')) return
    if (String(window.getSelection?.() || '')) return          // выделяли текст в строке, а не открывали
    setPanelId(id)
  }
  const panelAt = rows.findIndex(o => o.id === panelId)

  const onSort = (k) => { if (!k) return; if (sortCol === k) setSortDir(d => d === 'desc' ? 'asc' : 'desc'); else { setSortCol(k); setSortDir('desc') }; setPage(0) }
  const resetFilters = () => { setDateFrom(''); setDateTo(''); setFStatus([]); setFBank([]); setFArticle([]); setFCp([]); setFPeriod([]); setFOpType([]); setFGaps([]); setQuick(null); setPage(0) }

  // Приведение формы к типам бэкенда: пустые строки в id/датах → null, иначе
  // pydantic (Optional[int]/Optional[date]) отвергает '' → 422 «ошибка сохранения».
  const cleanOp = (f) => ({
    date: f.date || null, status: f.status, income: moneyNum(f.income), expense: moneyNum(f.expense),
    bank: f.bank || null, period: f.period || null, vat_rate: +f.vat_rate || 0,
    article_id: f.article_id ? +f.article_id : null, counterparty_id: f.counterparty_id ? +f.counterparty_id : null,
    ds_num: f.ds_num || '', invoice: f.invoice || '', invoice_date: f.invoice_date || null,
    description: f.description || '', document_link: f.document_link || '',
  })

  const saveCreate = async () => {
    const f = createForm
    // Проверка и подсветка — одно правило (lib/opRequirements): список полей не дублируется здесь словами.
    const miss = missingFields(f)
    if (miss.length) { alert('Заполните обязательные поля: ' + miss.map(m => m.label).join(', ')); return }
    setSaving(true)
    try {
      const res = await api(tok()).post('/operations/', cleanOp(createForm))
      const newId = res.data?.id
      if (newId && newFiles.length) await attachToExisting(newId, newFiles)
      setCreateForm(emptyForm()); setNewFiles([]); setCreateOpen(false); loadOps()
    }
    catch (e) { alert(detailText(e, 'Не удалось создать')) } finally { setSaving(false) }
  }
  const downloadTemplate = async () => {
    try {
      const res = await api(tok()).get('/operations/import/template', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url; a.download = 'shablon_operaciy.xlsx'; a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось скачать шаблон') }
  }
  const downloadExport = async () => {
    try {
      const params = new URLSearchParams({ sort_col: sortCol, sort_dir: sortDir })
      fStatus.forEach(s => params.append('status', s)); fBank.forEach(b => params.append('bank', b))
      fArticle.forEach(id => params.append('article_id', id)); fCp.forEach(id => params.append('counterparty_id', id))
      fPeriod.forEach(p => params.append('period', p)); fGaps.forEach(g => params.append('gaps', g))
      fOpType.forEach(t => params.append('op_type', t))
      if (dateFrom) params.append('date_from', dateFrom); if (dateTo) params.append('date_to', dateTo)
      if (payPlan) params.append('pay_plan', 'true')
      if (quick) params.append('quick', quick)            // плитка итогов — файл совпадает с экраном
      const res = await api(tok()).get(`/operations/export?${params}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a'); a.href = url
      a.download = `${payPlan ? 'plan_oplat' : 'operacii'}_${fileStamp()}.xlsx`
      a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert('Не удалось выгрузить') }
  }
  // Форма правки раскрывается прямо под своей строкой, поэтому никуда не скроллим:
  // строка уже перед глазами, а прыжок к форме наверху таблицы терял место в списке.
  const openEdit = (op) => {
    setEditFiles([]); loadOpFiles(op.id)
    setEditing({ id: op.id, date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || '', expense: op.expense || '', bank: op.bank || '', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
  }
  const saveEdit = async () => {
    setSaving(true)
    try { await api(tok()).put(`/operations/${editing.id}`, cleanOp(editing)); setEditing(null); setEditFiles([]); loadOps() }
    catch (e) { alert(detailText(e, 'Не удалось сохранить')) } finally { setSaving(false) }
  }

  // Приложенные сканы. В правке операция уже существует — файл уходит на сервер сразу.
  // В создании id ещё нет, поэтому выбранные файлы ждут в памяти браузера и уезжают
  // сразу после того, как POST вернёт номер новой операции. Промежуточное хранилище
  // на сервере при таком порядке не нужно.
  // Открыть приложенный файл из реестра. Через lib/download — там единственное в
  // проекте правило имени файла; свой <a download> здесь снова терял бы расширение.
  const openOpFile = async (opId, f) => {
    setDocMenu(null)
    await downloadFile(`/operations/${opId}/files/${f.id}`, f.name, (msg) => setErr(msg))
  }

  const loadOpFiles = async (id) => {
    try { const r = await api(tok()).get(`/operations/${id}/files`); setEditFiles(r.data || []) }
    catch (e) { setEditFiles([]) }
  }
  const attachToExisting = async (id, list) => {
    setFilesBusy(true)
    try {
      for (const file of list) {
        const fd = new FormData(); fd.append('file', file)
        await api(tok()).post(`/operations/${id}/files`, fd)
      }
      await loadOpFiles(id)
    } catch (e) {
      alert(detailText(e, 'Не удалось приложить файл'))
      await loadOpFiles(id)
    } finally { setFilesBusy(false) }
  }
  const removeFromExisting = async (id, fl) => {
    if (!(await confirm(`Убрать файл «${fl.original_name}»?`))) return
    try { await api(tok()).delete(`/operations/${id}/files/${fl.id}`); await loadOpFiles(id) }
    catch (e) { alert(detailText(e, 'Не удалось удалить файл')) }
  }
  // Список для формы создания: File-объекты браузера приводим к той же форме,
  // что приходит с сервера, чтобы компонент формы не различал два случая.
  const pendingAsFiles = newFiles.map(file => ({ original_name: file.name, size_bytes: file.size, pending: true }))
  // Копирование: не создаём дубль сразу, а открываем форму «Новая операция» с данными
  // копируемой — пользователь правит и подтверждает (POST на «Добавить операцию»).
  const dupOp = (op) => {
    setEditing(null)
    setCreateForm({ date: op.date || '', status: op.status || 'ОПЛАЧЕНО', income: op.income || '', expense: op.expense || '', bank: op.bank || 'АльфаБанк', period: op.period || '', vat_rate: op.vat_rate || 0, article_id: op.article_id || '', counterparty_id: op.counterparty_id || '', ds_num: op.ds_num || '', invoice: op.invoice || '', invoice_date: op.invoice_date || '', description: op.description || '', document_link: op.document_link || '' })
    setCreateOpen(true)
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  }
  // мобильные CRUD-хендлеры (форма в OperationsMobile)
  const mobileSave = async (body, id) => {
    const b = cleanOp(body)
    try { if (id) await api(tok()).put(`/operations/${id}`, b); else await api(tok()).post('/operations/', b); loadOps(); return true }
    catch (e) { alert(detailText(e, 'Не удалось сохранить')); return false }
  }
  // 409 — у операции есть частичные оплаты: удалить можно только принудительно, с
  // паролем. Остальные отказы показываем текстом сервера, а не общим «не удалось».
  const deleteOne = async (id) => {
    try { await api(tok()).delete(`/operations/${id}`); loadOps() }
    catch (e) {
      if (e?.response?.status === 409) setForceDel({ id, message: detailText(e, '') })
      else alert(detailText(e, 'Не удалось удалить'))
    }
  }
  const mobileDelete = (id) => deleteOne(id)
  const delOp = async (id) => { if (!(await confirm('Удалить операцию?'))) return; deleteOne(id) }

  const selIds = Object.keys(sel).filter(k => sel[k]).map(Number)
  const selRows = rows.filter(o => sel[o.id])
  // выбор с Shift: диапазон от последнего кликнутого до текущего (в пределах страницы)
  const toggleSel = (o, shiftKey) => {
    const idx = rows.findIndex(r => r.id === o.id)
    if (shiftKey && lastSelIdx.current != null && lastSelIdx.current >= 0 && lastSelIdx.current < rows.length) {
      const [a, b] = [lastSelIdx.current, idx].sort((x, y) => x - y)
      const target = !sel[o.id]
      setSel(s => { const n = { ...s }; rows.slice(a, b + 1).forEach(r => { n[r.id] = target }); return n })
    } else {
      setSel(s => ({ ...s, [o.id]: !s[o.id] }))
    }
    lastSelIdx.current = idx
  }
  const selIncome = selRows.reduce((s, o) => s + (o.income || 0), 0)
  const selExpense = selRows.reduce((s, o) => s + (o.expense || 0), 0)
  const applyBulk = async () => {
    const body = { ids: selIds }
    Object.entries(bulk).forEach(([k, v]) => { if (v !== '') body[k] = k === 'vat_rate' ? +v : v })
    if (Object.keys(body).length <= 1) { alert('Заполните хотя бы одно поле'); return }
    setSaving(true)
    try { await api(tok()).patch('/operations/bulk', body); setSel({}); setBulk({ status: '', date: '', period: '', bank: '', vat_rate: '', article_id: '', counterparty_id: '' }); loadOps() }
    catch (e) { alert(detailText(e, 'Не удалось применить')) } finally { setSaving(false) }
  }
  // Цепочка в выделении — сервер отвечает 428 и просит пароль; окно пароля повторяет
  // тот же запрос с ним (решение владельца 23.09.2026).
  const bulkDelete = (ids, password) => api(tok()).delete('/operations/bulk', { data: { ids, password } })
  const delBulk = async () => {
    if (!(await confirm(`Удалить ${selIds.length} операций?`))) return
    setSaving(true)
    try { await bulkDelete(selIds); setSel({}); loadOps() }
    catch (e) {
      const d = e?.response?.data?.detail  // detail-ok: объект need_password + typeof === 'string'
      if (e?.response?.status === 428 && d?.need_password) setBulkPwd({ ids: selIds, message: d.message })
      else alert((typeof d === 'string' && d) || 'Не удалось удалить')
    } finally { setSaving(false) }
  }

  // План оплат: встают только неоплаченные списания — что пропущено, говорим вслух.
  const toPlan = async () => {
    setSaving(true)
    try {
      const { data } = await api(tok()).post('/operations/pay-plan', { ids: selIds })
      if (data.skipped) alert(`В план: ${data.added}. Пропущено: ${data.skipped} — в план встают только неоплаченные списания (статус «ПЛАН ОПЛАТ»).`)
      setSel({}); loadOps()
    } catch (e) { alert(detailText(e, 'Не удалось поставить в план')) } finally { setSaving(false) }
  }
  const outOfPlan = async () => {
    setSaving(true)
    try { await api(tok()).delete('/operations/pay-plan', { data: { ids: selIds } }); setSel({}); loadOps() }
    catch (e) { alert(detailText(e, 'Не удалось убрать из плана')) } finally { setSaving(false) }
  }
  const title = `${payPlan ? 'План оплат' : 'Операции'} · Финансы | SIMB-AD ERP`

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const cpName = Object.fromEntries(counterparties.map(c => [c.id, c.name]))
  const artName = Object.fromEntries(articles.map(a => [a.id, a.name]))
  const opt = (arr, get = x => x) => arr.map(get)

  const allOnPage = rows.length > 0 && rows.every(o => sel[o.id])
  const someOnPage = rows.some(o => sel[o.id])

  const chev = (d) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={d} /></svg>

  const cell = (o, key) => {
    switch (key) {
      case 'sel': return <input type="checkbox" checked={!!sel[o.id]} onClick={e => toggleSel(o, e.shiftKey)} onChange={() => {}} title="Shift — выбрать диапазон" style={{ width: 14, height: 14, cursor: 'pointer' }} />
      case 'date': return <span style={{ fontFamily: MONO }}>{fmtDate(o.date) || '—'}</span>
      case 'status': { const [bg, fg, dot, bd] = statusChip(o.status); return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: bg, color: fg, border: `1px solid ${bd}`, borderRadius: 8, padding: '2px 8px', fontFamily: MONO, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', whiteSpace: 'nowrap' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: dot }} />{o.status}{!payPlan && o.pay_plan && <span title="В плане оплат" style={{ marginLeft: 4, color: 'var(--accent)' }}>· в плане</span>}</span> }
      case 'dz': return <DzMark status={o.receivable_status} due={o.receivable_due} />
      case 'amount': return o.income ? <span title={`поступление ${fmt2(o.income)} ₽`} style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--money-fg)' }}>+{fmt(o.income)}</span>
        : o.expense ? <span title={`списание ${fmt2(o.expense)} ₽`} style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--text-primary)' }}>−{fmt(o.expense)}</span>
        : <span style={{ color: 'var(--text-disabled)' }}>—</span>
      case 'bank': return o.bank ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)' }}><span style={{ width: 8, height: 8, borderRadius: 2, background: BANK_COLOR[o.bank] || 'var(--text-faint)' }} />{o.bank}</span> : <span style={{ color: 'var(--text-disabled)' }}>—</span>
      case 'period': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.period || '—'}</span>
      case 'article': return <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{artName[o.article_id] || o.article || '—'}</span>
      case 'counterparty': {
        // Стрелка ведёт в карточку контрагента и только в новой вкладке: реестр операций
        // открыт с фильтрами и прокруткой, и уводить с него — терять рабочее место.
        // stopPropagation обязателен — иначе клик по ссылке заодно откроет строку на правку
        // (тот же приём, что у иконки документа ниже).
        const cpn = cpName[o.counterparty_id] || o.counterparty || '—'
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, minWidth: 0, maxWidth: '100%', fontWeight: 700 }}>
            {o.counterparty_id ? (
              <a href={`/directory/counterparties/${o.counterparty_id}`} target="_blank" rel="noreferrer"
                 onClick={e => e.stopPropagation()} title="Карточка контрагента — в новой вкладке"
                 className="op-ico" style={{ width: 18, height: 18, flex: '0 0 auto', color: 'var(--text-faint)' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" style={IcoStroke}><path d="M7 17 17 7" /><path d="M9 7h8v8" /></svg>
              </a>
            ) : null}
            {o.no_counterparty
              // контрагент-заглушка «ПЛАН» или пусто — «без контрагента»; такие операции в плитке «Незаполненные» (хендофф NAVY)
              ? <span title="Нет контрагента — операция в «Незаполненных»" style={{ fontWeight: 600, fontStyle: 'italic', color: 'var(--attn-fg)' }}>без контрагента</span>
              : <span title={cpn} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: payPlan && planSum?.stub_ids?.includes(o.id) ? 'var(--danger-fg)' : undefined }}>{cpn}</span>}
            {payPlan && <DupTag tag={planSum?.tags?.[o.id]} />}
            {/* проблемы операции (20.11.2026) — в широкой колонке: в статусе значок обрезался */}
            <IssueMark issues={o.issues} />
          </span>
        )
      }
      case 'vat': return <span style={{ fontFamily: MONO }}>{o.vat_rate ? o.vat_rate + '%' : <span style={{ color: 'var(--text-disabled)' }}>—</span>}</span>
      case 'vat_amount': return o.vat_fact ? <span title={fmt2(o.vat_fact) + ' ₽'} style={{ fontFamily: MONO }}>{fmt(o.vat_fact)}</span> : <span style={{ color: 'var(--text-disabled)' }}>—</span>
      // отступ слева: правый край «НДС сумма» иначе упирается в номер ДС (владелец 09.11.2026: «всё сливается»)
      case 'ds_num': return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0, paddingLeft: PAD_LEFT.ds_num }}>
        <span style={{ fontFamily: MONO, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={o.ds_num || ''}>{shortAnnexNumber(o.ds_num) || '—'}</span>
        <ChainMark op={o} />
      </span>
      case 'invoice': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{o.invoice || '—'}</span>
      case 'invoice_date': return <span style={{ fontFamily: MONO, color: 'var(--text-secondary)' }}>{fmtDate(o.invoice_date) || '—'}</span>
      case 'doc': return <DocCell op={o} open={docMenu === o.id}
        onToggle={() => setDocMenu(m => m === o.id ? null : o.id)}
        onOpenFile={openOpFile} />
      case 'description': return <span title={o.description} style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.description || '—'}</span>
      case 'actions': return (canEdit || canCreate || canDelete) ? <span style={{ display: 'inline-flex', gap: 4 }}>
        {canCreate && <span onClick={() => dupOp(o)} title="Дублировать" className="op-ico" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg></span>}
        {canEdit && <span onClick={() => openEdit(o)} title="Редактировать" className="op-ico op-ico-w" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></span>}
        {canDelete && <span onClick={() => delOp(o.id)} title="Удалить" className="op-ico op-ico-d" style={{ color: 'var(--text-muted)' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M6 6l12 12M18 6L6 18" /></svg></span>}
      </span> : null
      default: return null
    }
  }

  const HeadCard = ({ title, right, iconBg, iconFg, iconPath, onClose }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 24px', borderBottom: '1px solid var(--border-inner)' }}>
      <span style={{ width: 28, height: 28, borderRadius: 9, background: iconBg, color: iconFg, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={IcoStroke}>{iconPath}</svg></span>
      <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', flex: 1 }}>{title}</span>
      {right}
      <span onClick={onClose} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1, padding: 4 }}>✕</span>
    </div>
  )

  // Отказ рисуем ДО загрузки И ДО ветки мобилки: пустая таблица читается как «ничего
  // не нашлось». Порядок был обратный, и с телефона гард не срабатывал вовсе — человек
  // без права видел мобильный реестр с надписью «Нет операций по фильтрам», то есть
  // ровно то ложное утверждение, которое убирали с десктопа (найдено 11.09.2026).
  if (access === 'denied') return (
    <NoAccessScreen title="Операции: нет доступа" what="Операции"
      nav={<><Head><title>{title}</title></Head><Navbar /></>} />
  )

  // ── Мобильная версия (< 1024px) ──
  if (isMobile) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed', fontFamily: UI }}>
        <Head><title>{title}</title></Head>
        <Navbar active="operations" />
        <OperationsMobile
          total={total} rows={rows} loading={loading} articles={articles} counterparties={counterparties} canEdit={canEdit} canCreate={canCreate} canDelete={canDelete}
          dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
          fStatus={fStatus} setFStatus={setFStatus} fBank={fBank} setFBank={setFBank}
          fArticle={fArticle} setFArticle={setFArticle} fCp={fCp} setFCp={setFCp} fOpType={fOpType} setFOpType={setFOpType}
          fPeriod={fPeriod} setFPeriod={setFPeriod} periodOptions={periodOptions}
          resetFilters={resetFilters} pageSize={pageSize} setPageSize={setPageSize}
          onSave={mobileSave} onDelete={mobileDelete} downloadExport={downloadExport} emptyForm={emptyForm} />
        {forceDel && <ForceDeleteDialog opId={forceDel.id} message={forceDel.message}
          onClose={() => setForceDel(null)} onDone={() => { setForceDel(null); loadOps() }} />}
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--page-bg) fixed', fontFamily: UI }}>
      <Head>
        <title>{title}</title>
      </Head>
      <Navbar active="operations" />
      {forceDel && <ForceDeleteDialog opId={forceDel.id} message={forceDel.message}
        onClose={() => setForceDel(null)} onDone={() => { setForceDel(null); loadOps() }} />}
      {bulkPwd && <ForceDeleteDialog message={bulkPwd.message}
        title={`Удалить ${bulkPwd.ids.length} операций?`} confirmLabel="Удалить с цепочкой"
        submit={pwd => bulkDelete(bulkPwd.ids, pwd)}
        onClose={() => setBulkPwd(null)} onDone={() => { setBulkPwd(null); setSel({}); loadOps() }} />}
      <style>{`
        
        .op-row:hover { --op-row: var(--bg-subtle) !important; }
        .op-ico { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:7px; cursor:pointer; }
        .op-ico:hover { background: var(--accent-tint); color: var(--accent) !important; }
        .op-ico-w:hover { background: var(--warning-tint); color: var(--warning-text) !important; }
        .op-ico-d:hover { background: var(--danger-tint); color: var(--danger-fg) !important; }
        
      `}</style>

      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Шапка */}
        {/* заголовок, счётчик и вкладки — одной строкой (владелец 17.11.2026: «сэкономим место») */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em', margin: 0, color: 'var(--text-primary)' }}>Операции</h1>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{new Intl.NumberFormat('ru-RU').format(total)} записей{updatedAt ? ` · обновлено ${updatedAt}` : ''}</span>
            <span style={{ marginLeft: 10 }}>
              <UnderlineTabs line={false} value={creditTab ? 'credit' : payPlan ? 'plan' : 'all'} onChange={setTab}
                tabs={[{ key: 'all', label: 'Операции' }, { key: 'plan', label: 'План оплат' }].concat(canCredit ? [{ key: 'credit', label: 'Кредиты' }] : [])} />
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {canCreate && <button onClick={() => setCreateOpen(o => !o)} style={{ ...primaryBtn, ...HEAD_BTN }}>+ Новая операция</button>}
            {canCreate && <button onClick={downloadTemplate} style={{ ...btn(false), ...HEAD_BTN }}>Шаблон</button>}
            {canImport && <IconBtn title="Импорт из файла" onClick={() => router.push('/finance/import')}><svg width="17" height="17" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 15V3" /><path d="M7 8l5-5 5 5" /><path d="M5 21h14" /></svg></IconBtn>}
            <IconBtn title="Выгрузить в Excel (с учётом фильтров)" onClick={downloadExport}><svg width="17" height="17" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg></IconBtn>
          </div>
        </div>
        {creditTab ? <CreditLines /> : <>
        {payPlan && <PayPlanSummary data={planSum} filter={planF} onFilter={setPlanF} />}
        {!focusOp && <OpsSummary s={summary} quick={quick} onQuick={q => { setQuick(q); setPage(0) }} />}

        {/* Форма создания */}
        {createOpen && canCreate && (
          <div style={{ ...CARD, position: 'relative', zIndex: 30, border: '1px solid var(--accent-border)', boxShadow: '0 1px 3px rgba(28,36,51,.05), 0 8px 28px rgba(79,108,230,.10)', animation: 'm-rise var(--dur-slow) var(--ease-out) both' }}>
            <HeadCard title="Новая операция" iconBg="var(--accent-tint)" iconFg="var(--accent)" iconPath={<><path d="M12 5v14" /><path d="M5 12h14" /></>} onClose={() => setCreateOpen(false)} />
            <div style={{ padding: '20px 24px' }}><OpFields f={createForm} set={p => setCreateForm(s => ({ ...s, ...p }))} articles={articles} counterparties={counterparties} mode="create"
              files={pendingAsFiles} busyFiles={filesBusy}
              onAttach={list => setNewFiles(prev => [...prev, ...list])}
              onRemoveFile={(fl, i) => setNewFiles(prev => prev.filter((_, k) => k !== i))} /></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px', background: 'var(--bg-subtle)', borderTop: '1px solid var(--border-inner)' }}>
              <button onClick={saveCreate} disabled={saving} style={{ ...primaryBtn, ...HEAD_BTN }}>Добавить операцию</button>
              <button onClick={() => setCreateOpen(false)} style={{ ...btn(false), ...HEAD_BTN }}>Отмена</button>
              <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-faint)' }}>обязательны статус, период, статья и контрагент · у «Оплачено» — ещё дата и банк · НДС считается по ставке</span>
            </div>
          </div>
        )}

        {/* Карточка таблицы */}
        <div style={{ ...CARD, padding: '18px 24px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {/* строка фильтров */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--border-card)', borderRadius: 10, padding: '7px 10px', fontFamily: MONO, fontSize: 11, color: 'var(--text-muted)' }}>
              <MonthInput clearable value={dateFrom.slice(0, 7)} onChange={e => setDateFrom(e.target.value ? e.target.value + '-01' : '')} style={{ border: 'none', outline: 'none', fontFamily: MONO, fontSize: 11, width: 92, background: 'transparent' }} />
              <span style={{ color: 'var(--text-disabled)' }}>—</span>
              <MonthInput clearable value={dateTo.slice(0, 7)} onChange={e => setDateTo(e.target.value ? monthEnd(e.target.value) : '')} style={{ border: 'none', outline: 'none', fontFamily: MONO, fontSize: 11, width: 92, background: 'transparent' }} />
            </span>
            <MultiDrop label="Статус" options={STATUSES.map(s => ({ value: s, label: s }))} selected={fStatus} onChange={setFStatus} />
            <MultiDrop label="Банк" options={BANKS.map(b => ({ value: b, label: b }))} selected={fBank} onChange={setFBank} />
            <MultiDrop label="Статья" options={articles.map(a => ({ value: a.id, label: a.name, tone: a.type === 'income' ? 'income' : undefined }))} selected={fArticle} onChange={setFArticle} />
            <MultiDrop label="Контрагент" options={counterparties.map(c => ({ value: c.id, label: c.name }))} selected={fCp} onChange={setFCp} />
            <MultiDrop label="Период" options={periodOptions.map(p => ({ value: p, label: p }))} selected={fPeriod} onChange={setFPeriod} />
            <MultiDrop label="Тип операции" options={[{ value: 'income', label: 'Поступления' }, { value: 'expense', label: 'Списания' }]} selected={fOpType} onChange={setFOpType} />
            <MultiDrop label="Незаполненные" options={GAP_FIELDS} selected={fGaps} onChange={v => { setFGaps(v); setPage(0) }} />
            {!!quick && (
              <span role="button" tabIndex={0} onClick={() => { setQuick(null); setPage(0) }} onKeyDown={e => e.key === 'Enter' && setQuick(null)} title="Снять фильтр плитки"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 11px', borderRadius: 10, cursor: 'pointer', fontSize: 12.5, fontWeight: 700,
                  background: 'var(--signal-tint)', border: '1px solid var(--signal-border)', color: 'var(--signal-text)' }}>{QUICK_LABEL[quick]} ✕</span>
            )}
            {focusOp && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 11px', borderRadius: 20, background: 'var(--accent-tint)', color: 'var(--accent)', fontSize: 12 }}>
                Показана одна операция #{focusOp}
                <span onClick={() => router.push('/finance/operations')}
                  style={{ cursor: 'pointer', textDecoration: 'underline' }}>показать все</span>
              </div>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, position: 'relative' }}>
              <IconBtn title="Сбросить фильтры" onClick={resetFilters}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></IconBtn>
              <IconBtn title="Настройка колонок" active={colPicker} onClick={() => setColPicker(o => !o)}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></svg></IconBtn>
              {colPicker && (<>
                <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setColPicker(false)} />
                <div style={{ position: 'absolute', right: 0, top: '120%', zIndex: 40, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 10, minWidth: 200, maxHeight: 340, overflowY: 'auto' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Колонки</div>
                  {COLS.filter(([k]) => k !== 'sel' && k !== 'actions').map(([k, , label]) => (
                    <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 2px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={!hidden.has(k)} onChange={() => toggleCol(k)} /> {label || k}
                    </label>
                  ))}
                </div>
              </>)}
            </div>
          </div>

          {/* Массовая правка — всплывашкой, закреплённой под шапкой: выделять строки
              можно в любом месте списка, и панель не уезжает вместе с ним. В потоке
              страницы она оставалась у начала таблицы, то есть за экраном. */}
          {canEdit && selIds.length > 0 && (
              <div style={{ position: 'fixed', top: navH + 10, left: 24, right: 24, zIndex: 45, boxShadow: 'var(--shadow-float)', background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', borderRadius: 14, padding: '16px 18px', display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap', animation: 'm-rise var(--dur-base) var(--ease-out) both' }}>
                <div style={{ minWidth: 150, borderRight: '1px solid var(--accent-border)', paddingRight: 14 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-fg)', marginBottom: 6 }}>Выбрано: {selIds.length}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, color: 'var(--income)' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)' }} />+{fmt2(selIncome)} ₽</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, color: 'var(--text-primary)' }}><span style={{ width: 6, height: 6, borderRadius: 2, background: T.expense }} />−{fmt2(selExpense)} ₽</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO, fontSize: 12, fontWeight: 700, marginTop: 4, paddingTop: 4, borderTop: '1px solid var(--accent-border)', color: (selIncome - selExpense) >= 0 ? 'var(--income)' : T.danger }}><span style={{ width: 6, height: 6, borderRadius: 2, background: (selIncome - selExpense) >= 0 ? 'var(--income)' : T.danger }} />{(selIncome - selExpense) >= 0 ? '+' : '−'}{fmt2(Math.abs(selIncome - selExpense))} ₽</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', width: 148, flexShrink: 0 }}>
                  <span style={lbl}>Дата</span>
                  <input type="date" value={bulk.date} onChange={e => setBulk(b => ({ ...b, date: e.target.value }))} style={{ ...inp, width: '100%' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', width: 300, flexShrink: 0 }}>
                  <span style={lbl}>Период</span>
                  <PeriodSelect dense value={bulk.period} onChange={v => setBulk(b => ({ ...b, period: v }))} />
                </div>
                {[['Статус', 'status', STATUSES.map(s => ({ value: s, label: s })), 150], ['Банк', 'bank', BANKS.map(b => ({ value: b, label: b })), 140], ['НДС', 'vat_rate', VAT_OPTIONS.map(v => ({ value: v, label: v + '%' })), 112], ['Статья', 'article_id', articles.map(a => ({ value: a.id, label: a.name })), 160], ['Контрагент', 'counterparty_id', counterparties.map(c => ({ value: c.id, label: c.name })), 190]].map(([label, k, opts, w]) => (
                  <div key={k} style={{ display: 'flex', flexDirection: 'column', width: w, flexShrink: 0 }}>
                    <span style={lbl}>{label}</span>
                    {(k === 'article_id' || k === 'counterparty_id')
                      ? <SingleSelect value={bulk[k]} onChange={v => setBulk(b => ({ ...b, [k]: v }))} options={opts} placeholder="не менять" emptyLabel="не менять" />
                      : <select value={bulk[k]} onChange={e => setBulk(b => ({ ...b, [k]: e.target.value }))} style={{ ...inp, width: '100%' }}><option value="">не менять</option>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>}
                  </div>
                ))}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                  {payPlan
                    ? <button onClick={outOfPlan} disabled={saving} style={{ ...btn(false), ...HEAD_BTN, height: 38 }}>Убрать из плана</button>
                    : <button onClick={toPlan} disabled={saving} title="Поставить в план оплат" style={{ ...btn(false), ...HEAD_BTN, height: 38 }}>В план</button>}
                  <button onClick={applyBulk} disabled={saving} style={{ ...primaryBtn, ...HEAD_BTN, height: 38 }}>Применить к {selIds.length}</button>
                  {canDelete && <button onClick={delBulk} disabled={saving} title={`Удалить ${selIds.length}`} aria-label="Удалить" style={{ width: 38, height: 38, flexShrink: 0, background: 'var(--bg-card)', border: '1px solid var(--danger-border)', color: T.danger, borderRadius: 10, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 14h10l1-14" /></svg></button>}
                  <button onClick={() => setSel({})} title="Снять выделение" aria-label="Снять выделение" style={{ width: 38, height: 38, flexShrink: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', color: 'var(--text-secondary)', borderRadius: 10, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="16" height="16" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M18 6L6 18" /><path d="M6 6l12 12" /></svg></button>
                </div>
              </div>
          )}

          {/* показано + пагинация */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
            <span>Показано <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{total ? page * pageSize + 1 : 0}–{Math.min((page + 1) * pageSize, total)}</b> из <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{new Intl.NumberFormat('ru-RU').format(total)}</b>{payPlan && planF && planSum ? <> · в плане <b style={{ color: 'var(--text-primary)', fontFamily: MONO }}>{planSum.count}</b></> : null}</span>
            {payPlan && <FilterChip filter={planF} onClear={() => setPlanF(null)} />}
            <span style={{ display: 'inline-flex', gap: 14 }}>
              {[['оплачено', 'var(--money)'], ['план', 'var(--text-faint)'], ['ожидает · срок прошёл', 'var(--attn)'], ['просрочено', 'var(--bad)']].map(([l, c]) => <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}</span>)}
            </span>
          </div>

          {/* таблица */}
          <div ref={scrollRef} style={{ overflow: 'auto', height: tableH, margin: '10px -24px 0', borderTop: '1px solid var(--border-inner)' }}>
            <div style={{ minWidth: 1880 }}>
              <div style={{ position: 'sticky', top: 0, zIndex: 3, display: 'grid', gridTemplateColumns: gridT, gap: GAP, alignItems: 'center', height: 38, padding: `0 ${ROW_PAD}px`, background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)', fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                {visibleCols.map(([k, w, label, sc]) => k === 'sel'
                  ? <span key={k} style={{ ...stick(k, 'var(--bg-card)'), height: '100%', display: 'flex', alignItems: 'center' }}><input type="checkbox" ref={el => { if (el) el.indeterminate = someOnPage && !allOnPage }} checked={allOnPage} onChange={e => setSel(e.target.checked ? Object.fromEntries(rows.map(o => [o.id, true])) : {})} style={{ width: 14, height: 14, cursor: 'pointer' }} /></span>
                  : <span key={k} onClick={() => onSort(sc)} style={{ ...stick(k, 'var(--bg-card)'), height: '100%', display: 'flex', alignItems: 'center', justifyContent: justify(k), paddingLeft: PAD_LEFT[k], cursor: sc ? 'pointer' : 'default', color: sortCol === sc ? 'var(--accent)' : undefined }}>{label}{sortCol === sc ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}</span>)}
              </div>
              {/* «Нет операций по выбранным фильтрам» — утверждение о ДАННЫХ. На сбое
                  загрузки оно неверно, и подменять им причину нельзя: человек начнёт
                  менять фильтры вместо того, чтобы повторить запрос. */}
              {loading ? <div style={{ padding: 30, color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
                : err ? <div style={{ padding: 20 }}>
                    <LoadError text={err} onRetry={() => loadOps()} /></div>
                : rows.length === 0 ? <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Нет операций по выбранным фильтрам</div>
                  : rows.map(o => (
                    <Fragment key={o.id}>
                      {/* фон строки — переменной --op-row: ею же красятся закреплённые ячейки (и при наведении — .op-row:hover) */}
                      <div className="op-row" onClick={e => openPanel(e, o.id)} style={{ '--op-row': panelId === o.id || sel[o.id] ? 'var(--accent-tint)' : (editing?.id === o.id ? 'var(--warning-tint)' : 'var(--bg-card)'), display: 'grid', gridTemplateColumns: gridT, gap: GAP, alignItems: 'center', padding: `7px ${ROW_PAD}px`, borderBottom: '1px solid var(--border-row)', fontSize: 14.4, color: 'var(--text-primary)', cursor: 'pointer', background: 'var(--op-row)' }}>
                        {visibleCols.map(([k]) => <span key={k} data-noexp={NO_PANEL.has(k) ? '' : undefined} style={{ ...stick(k, 'var(--op-row)'), alignSelf: 'stretch', display: 'flex', alignItems: 'center', justifyContent: justify(k), overflow: 'hidden', paddingLeft: PAD_LEFT[k] }}>{cell(o, k)}</span>)}
                      </div>
                      {/* Правка раскрывается под своей строкой — форма стоит там, где
                          пользователь только что кликнул, и список не теряет место. */}
                      {editing?.id === o.id && canEdit && (
                        <div style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 14, padding: '18px 20px', margin: '2px 0 10px', animation: 'm-rise var(--dur-base) var(--ease-out) both' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                            <span style={{ width: 28, height: 28, borderRadius: 9, background: 'var(--warning-tint)', color: T.warningText, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="15" height="15" viewBox="0 0 24 24" style={IcoStroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></span>
                            <span style={{ fontSize: 15, fontWeight: 700, flex: 1 }}>Редактирование #{editing.id}</span>
                            <span onClick={() => setEditing(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18 }}>✕</span>
                          </div>
                          <OpFields f={editing} set={p => setEditing(s => ({ ...s, ...p }))} articles={articles} counterparties={counterparties} accent="warn"
                            files={editFiles} busyFiles={filesBusy}
                            onAttach={list => attachToExisting(editing.id, list)}
                            onRemoveFile={fl => removeFromExisting(editing.id, fl)} />
                          {/* Цепочка частичных оплат и «Частичная оплата» у плановой. Строится по
                              СОХРАНЁННОЙ операции (o), а не по черновику формы: делит сервер, и
                              делит то, что лежит в базе. */}
                          <ChainPanel op={o} canEdit={canEdit} banks={BANKS}
                            onChanged={() => { setEditing(null); loadOps() }} />
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14 }}>
                            <span style={{ fontSize: 12, color: 'var(--text-faint)', flex: 1 }}>поля, отмеченные «необяз.», можно оставить пустыми</span>
                            <button onClick={saveEdit} disabled={saving} style={{ ...primaryBtn, ...HEAD_BTN }}>Сохранить изменения</button>
                            <button onClick={() => setEditing(null)} style={{ ...btn(false), ...HEAD_BTN }}>Отмена</button>
                          </div>
                        </div>
                      )}
                    </Fragment>
                  ))}
            </div>
          </div>

          {/* подвал — страницы (хендофф «Операции · NAVY», раздел 3): всегда виден, смена размера — на первую страницу */}
          <div style={{ margin: '0 -24px -14px' }}>
            <RegistryFooter view={{ page, pages: totalPages, total, from: total ? page * pageSize + 1 : 0, to: Math.min((page + 1) * pageSize, total) }}
              size={pageSize} sizes={PAGE_SIZES} onSize={n => { setPageSize(n); setPage(0) }} onPage={setPage} />
          </div>
        </div>
        </>}
      </div>
      {panelId != null && <OperationPanelHost opId={panelId} onClose={() => setPanelId(null)} onOpen={setPanelId}
        hasPrev={panelAt > 0} hasNext={panelAt >= 0 && panelAt < rows.length - 1}
        onPrev={() => panelAt > 0 && setPanelId(rows[panelAt - 1].id)}
        onNext={() => panelAt >= 0 && panelAt < rows.length - 1 && setPanelId(rows[panelAt + 1].id)}
        onRefreshRegistry={() => { setPanelId(null); loadOps() }} onIssuesChanged={() => loadOps()} />}
    </div>
  )
}
