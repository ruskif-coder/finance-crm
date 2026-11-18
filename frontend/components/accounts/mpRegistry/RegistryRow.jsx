/**
 * Строка реестра медиапланов v2 и её расхлоп (хендофф design_handoff_mp_registry, 17.11.2026).
 *
 * Первая колонка (стрелка, ID, замок, название, «нужна виза») липкая слева. Клик по строке раскрывает план только для
 * чтения — тем же компонентом, что «Медиаплан сделки» на карточке (`MpReadView`). Клик по ячейке шапки плана — правка
 * через `ValuePopover`, как на проде; если план отдан клиенту или зафиксирован — ячейка не открывается, а замок у ID
 * объясняет почему (раньше человек узнавал об этом из `alert` с 409 уже после выбора значения).
 */
import { useState } from 'react'
import { GenTitleBtn, MONO, UI } from '@/components/salesTableKit'
import MpReadView from '@/components/mediaplan/MpReadView'
import { fmtFull } from '@/lib/salesFormat'
import { fmtDate, fmtDateOfMoment, fmtDateTime, fmtDayOfMoment, fmtTime, todayMsk } from '@/lib/dates'
import { dayKind, shortMoney, shortName, SURFACE_HINT, SURFACE_LABEL, toneOf } from '@/lib/mpRegistryModel.mjs'
import { Chevron } from './controls'

/** Колонки — дословно из хендоффа §2; минимальная ширина таблицы 1850px (на 1920 без прокрутки вбок). */
export const GRID = 'minmax(280px,1.5fr) 150px 90px minmax(110px,1fr) minmax(110px,1fr) 80px 110px 84px 84px minmax(140px,1.1fr) 170px 112px 196px'
export const TABLE_MIN_W = 1850

const clip = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const CLOSED_HINT = 'Правка из реестра закрыта — см. замок у ID'
const VISA_HINT = 'План создан системой и не проверен. Откройте его, отметьте «проверено» у размещений и прогноза и сохраните.'

export function lockHint(it, canEditLocked) {
  if (it.lock === 'sent') return 'Отдан клиенту. Правка из реестра переписала бы эту версию — откройте план в конструкторе, сохранение создаст новую версию.'
  if (it.lock === 'fixed') {
    return canEditLocked
      ? `Зафиксирован: сделка на стадии «${it.deal_stage || '—'}». Вы можете править как администратор или мастер-аккаунт — правка попадёт в журнал.`
      : `Зафиксирован: сделка на стадии «${it.deal_stage || '—'}». Править может администратор или мастер-аккаунт — в конструкторе, правка попадёт в журнал.`
  }
  return ''
}

const LockIcon = ({ title, color }) => (
  <span title={title} style={{ display: 'inline-flex', color }}>
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2" /><rect x="3" y="7" width="10" height="7" rx="2" /></svg>
  </span>
)

/** «сегодня 11:05» · «вчера 18:44» · «12.11» — по Москве. */
function updatedLabel(at) {
  if (!at) return { text: '—', today: false }
  const [dd, mm, yyyy] = fmtDateOfMoment(at, '').split('.')
  const kind = dayKind(`${yyyy}-${mm}-${dd}`, todayMsk())
  if (kind === 'today') return { text: `сегодня ${fmtTime(at)}`, today: true }
  if (kind === 'yesterday') return { text: `вчера ${fmtTime(at)}`, today: false }
  return { text: fmtDayOfMoment(at), today: false }
}

/** Ячейка шапки плана: открыта — клик даёт пикер; закрыта — подсказка про замок. Клик не раскрывает строку. */
const EditCell = ({ open, onPick, mono, children }) => (
  <span onClick={open ? (e) => { e.stopPropagation(); onPick(e) } : undefined} title={open ? 'Клик — изменить' : CLOSED_HINT}
    style={{ ...clip, display: 'block', boxSizing: 'border-box', borderRadius: 6, padding: '8px 4px', margin: '-8px -4px', width: 'calc(100% + 8px)',
      cursor: open ? 'pointer' : 'default', fontFamily: mono ? MONO : undefined, fontSize: mono ? 12 : undefined,
      color: children ? 'var(--text-primary)' : 'var(--text-faint)' }}>{children || '—'}</span>
)

const actBtn = { display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 8px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
  borderRadius: 7, fontFamily: UI, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap', cursor: 'pointer' }

export default function RegistryRow({ it, open, onToggle, cellsOpen, canEditLocked, canEdit, canDelete, pdfBusy,
  onPick, onSaveTitle, onGenTitle, onOpenPlan, onExcel, onPdf, onDelete }) {
  const [edit, setEdit] = useState(null)        // черновик названия или null
  const tone = toneOf(it.stage_bucket)
  const upd = updatedLabel(it.updated_at)
  const editable = canEdit && cellsOpen
  const save = () => { const t = (edit || '').trim(); setEdit(null); if (t && t !== (it.title || '')) onSaveTitle(t) }
  return (
    <div onClick={onToggle} className={`mpr-row${open ? ' mpr-open' : ''}`}
      style={{ display: 'grid', gridTemplateColumns: GRID, alignItems: 'center', gap: '0 10px', minHeight: 46, boxSizing: 'border-box', paddingRight: 14,
        borderBottom: `1px solid ${open ? 'var(--border-inner)' : 'var(--border-row)'}`, fontSize: 12.5, color: 'var(--text-primary)', cursor: 'pointer' }}>
      {/* ID · Сделка — липкая */}
      <span className="mpr-stick" style={{ position: 'sticky', left: 0, zIndex: 2, alignSelf: 'stretch', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0,
        paddingLeft: 14, paddingRight: 10, boxShadow: '1px 0 0 var(--border-inner)' }}>
        <span style={{ flex: '0 0 14px', display: 'inline-flex', justifyContent: 'center' }}><Chevron open={open} color={open ? 'var(--accent-fg)' : 'var(--text-faint)'} /></span>
        <span style={{ flex: '0 0 64px', display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {it.id}<span style={{ color: 'var(--text-faint)' }}>v{it.version}</span>
          {!!it.lock && <LockIcon title={lockHint(it, canEditLocked)} color={it.lock === 'fixed' ? 'var(--warning-fg)' : 'var(--text-faint)'} />}
        </span>
        {edit != null ? (
          <input autoFocus value={edit} onClick={e => e.stopPropagation()} onChange={e => setEdit(e.target.value)} onBlur={save}
            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEdit(null) }}
            style={{ flex: 1, minWidth: 0, padding: '3px 6px', border: '1px solid var(--accent)', borderRadius: 6, fontSize: 12.5, fontFamily: UI, background: 'var(--bg-card)', color: 'inherit' }} />
        ) : (
          <span onClick={editable ? (e) => { e.stopPropagation(); setEdit(it.title || '') } : undefined}
            title={[it.title, editable ? 'клик — переименовать' : (it.lock ? CLOSED_HINT : '')].filter(Boolean).join('\n')}
            style={{ ...clip, flex: '1 1 auto', fontWeight: open ? 700 : 500, cursor: editable ? 'text' : 'pointer', color: it.title ? 'var(--text-primary)' : 'var(--text-faint)' }}>
            {it.title || 'без названия'}</span>
        )}
        {it.needs_visa && (
          <span title={VISA_HINT} style={{ flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', height: 19, padding: '0 6px', borderRadius: 6,
            background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', fontSize: 10.5, fontWeight: 700, color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}>нужна виза</span>
        )}
        {editable && edit == null && <span className="mpr-gen" onClick={e => e.stopPropagation()}><GenTitleBtn onClick={onGenTitle} size={20} /></span>}
      </span>

      {/* Услуга + поверхность */}
      <span title={it.surface ? `${it.product_label || ''} · ${SURFACE_HINT[it.surface] || ''}` : (it.product_label || '')}
        style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, whiteSpace: 'nowrap' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', color: it.product_label ? 'var(--text-primary)' : 'var(--text-faint)' }}>{it.product_label || '—'}</span>
        {!!SURFACE_LABEL[it.surface] && (
          <span style={{ flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 5px', borderRadius: 5, background: 'var(--bg-subtle)',
            border: '1px solid var(--border-inner)', fontFamily: MONO, fontSize: 9, fontWeight: 700, color: 'var(--text-secondary)' }}>{SURFACE_LABEL[it.surface]}</span>
        )}
      </span>
      <EditCell open={editable} onPick={e => onPick('agency', it, e)}>{it.agency}</EditCell>
      <EditCell open={editable} onPick={e => onPick('advertiser', it, e)}>{it.advertiser}</EditCell>
      <EditCell open={editable} onPick={e => onPick('brand', it, e)}>{it.brand}</EditCell>
      <EditCell open={editable} onPick={e => onPick('period', it, e)} mono>{it.period}</EditCell>
      {/* Сумма: с НДС крупно, под ней без НДС */}
      <span title={`с НДС ${fmtFull(it.amount_gross)}\nдо НДС ${fmtFull(it.amount_net)}`}
        style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, lineHeight: 1.15 }}>
        <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 800, whiteSpace: 'nowrap' }}>{shortMoney(it.amount_gross)}</span>
        <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{shortMoney(it.amount_net)} без НДС</span>
      </span>
      <EditCell open={editable} onPick={e => onPick('seller', it, e)}>{it.sales_rep ? shortName(it.sales_rep) : ''}</EditCell>
      <EditCell open={editable} onPick={e => onPick('account', it, e)}>{it.account_manager ? shortName(it.account_manager) : ''}</EditCell>
      <EditCell open={editable} onPick={e => onPick('payer', it, e)}>{it.payer}</EditCell>
      {/* Сделка · стадия */}
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        {it.deal_code ? (<>
          <a href={`/sales/deals/${it.deal_code}`} onClick={e => e.stopPropagation()}
            style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)', textDecoration: 'none', whiteSpace: 'nowrap' }}>{it.deal_code}</a>
          <span title={it.deal_stage || ''} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 20, padding: '0 7px', borderRadius: 6, minWidth: 0,
            background: tone[1], border: `1px solid ${tone[2]}`, fontSize: 10.5, fontWeight: 700, color: tone[3], whiteSpace: 'nowrap', overflow: 'hidden' }}>
            <span style={{ flex: '0 0 6px', width: 6, height: 6, borderRadius: '50%', background: tone[0] }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.deal_stage || '—'}</span>
          </span>
        </>) : <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-faint)' }}>без сделки</span>}
      </span>
      {/* Обновлён */}
      <span title={`${fmtDateTime(it.updated_at)} · ${it.updated_by || '—'}`} style={{ display: 'flex', flexDirection: 'column', gap: 1, lineHeight: 1.15, minWidth: 0 }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: upd.today ? 700 : 500, color: upd.today ? 'var(--text-primary)' : 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{upd.text}</span>
        <span style={{ ...clip, fontSize: 10.5, color: 'var(--text-muted)' }}>{it.updated_by_system ? it.updated_by : (it.updated_by ? shortName(it.updated_by) : '—')}</span>
      </span>
      {/* Действия */}
      <span onClick={e => e.stopPropagation()} style={{ display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
        <button type="button" onClick={onOpenPlan} style={actBtn}>Открыть</button>
        <button type="button" onClick={onExcel} style={actBtn}>Excel</button>
        <button type="button" onClick={onPdf} disabled={pdfBusy} style={actBtn}>{pdfBusy ? '…' : 'PDF'}</button>
        {canDelete && <button type="button" onClick={onDelete} title="Удалить медиаплан со всеми версиями" style={{ ...actBtn, color: 'var(--danger-fg)' }}>✕</button>}
      </span>
    </div>
  )
}

/** Расхлоп строки: план только для чтения. Растянут на видимую ширину таблицы и при прокрутке вбок не уезжает. */
export function RowDetail({ it, detail, onRetry }) {
  const wrap = { position: 'sticky', left: 0, width: 'var(--mpr-vw, 100cqw)', boxSizing: 'border-box', padding: '20px 30px 24px 46px',
    borderBottom: '1px solid var(--border-inner)', animation: 'm-drop var(--dur-slow) var(--ease-out) both' }
  if (!detail || detail.status === 'loading') {
    return <div style={wrap}><div style={{ height: 220, borderRadius: 12, background: 'var(--bg-subtle)', animation: 'm-pulse 1.4s ease-in-out infinite' }} /></div>
  }
  if (detail.status === 'error') {
    return (
      <div style={{ ...wrap, fontSize: 13, color: 'var(--danger-fg)' }}>
        Медиаплан не загрузился — <span onClick={onRetry} style={{ color: 'var(--accent-fg)', fontWeight: 700, cursor: 'pointer' }}>повторить</span>
      </div>
    )
  }
  const p = detail.data
  const params = [
    ['Рекламодатель', p.advertiser], ['Бренд', p.brand],
    ['Агентство', p.agency], ['Контрагент', p.payer],
    ['Период размещения', p.period ? `месяц · ${p.period}` : null], ['Гео', p.geo],
  ]
  const dates = p.date_from ? `${fmtDate(p.date_from)} — ${fmtDate(p.date_to)}` : null
  return (
    <div style={wrap} onClick={e => e.stopPropagation()}>
      <MpReadView plan={p} vatPct={p.vat_rate} params={params} dates={dates} openHref={`/accounts/mp/${it.id}`} />
    </div>
  )
}
