import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { MONO, UI } from '../salesTableKit'
import { makeApi as api } from '../../lib/http'
import { bankColor } from '../../lib/salesFormat'
import { T } from '../../lib/tokens'
import CardShell from './CardShell'
import { fmtDate as fmtCalendarDate } from '@/lib/dates'

const rub = (n) => (n || n === 0) ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' ₽' : '—'
const mln = (n) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format((n || 0) / 1e6)
const fmtDate = (s) => fmtCalendarDate(s)
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const fmtMonth = (p) => { if (!p) return ''; const [y, m] = String(p).split('-'); return `${MONTHS[+m - 1] || m} ${String(y).slice(2)}` }
const periodShort = (p) => String(p || '').replace(/^(\d{4})-(\d{2})$/, '$1-$2')
const normalizeUrl = (u) => !u ? null : (/^https?:\/\//i.test(u) ? u : 'https://' + u)

const STATUS_META = {
  'ОПЛАЧЕНО': { label: 'исполнено', bg: '#E6F5EF', fg: '#1F7D5E', dot: T.income },
  'ПЛАН ОПЛАТ': { label: 'план оплат', bg: T.warningTint, fg: T.warningText, dot: T.warning },
  'ПЛАН ПОСТУПЛЕНИЙ': { label: 'план поступл.', bg: T.accentTint, fg: T.accent, dot: T.accent },
}
const stMeta = (s) => STATUS_META[s] || { label: (s || '').toLowerCase(), bg: 'var(--bg-subtle)', fg: 'var(--text-secondary)', dot: 'var(--text-faint)' }

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

// парсинг даты окончания договора (ISO / dd.mm.yyyy) → бейдж «истёк»
function contractExpired(text) {
  if (!text) return false
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text); let d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : null
  if (!d) { m = /^(\d{2})\.(\d{2})\.(\d{4})/.exec(text); d = m ? new Date(+m[3], +m[2] - 1, +m[1]) : null }
  if (!d) return false
  return (d - new Date()) < 0
}

const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)' }
const monoLbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const sectionLbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', fontWeight: 700, margin: '4px 0 8px' }

function Chip({ label, bg, fg, href }) {
  const s = { display: 'inline-flex', alignItems: 'center', padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 600, background: bg, color: fg, whiteSpace: 'nowrap', textDecoration: 'none', flexShrink: 0 }
  return href ? <a href={href} target="_blank" rel="noreferrer" style={s}>{label}</a> : <span style={s}>{label}</span>
}

function ReqRow({ label, value, link, mono }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, padding: '9px 0', borderTop: '1px solid var(--border-inner)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', flexShrink: 0, paddingTop: 1 }}>{label}</span>
      {!value ? <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>—</span>
        : link ? <a href={normalizeUrl(value)} target="_blank" rel="noreferrer" style={{ fontSize: 12.5, color: 'var(--accent)', textAlign: 'right', wordBreak: 'break-all', textDecoration: 'none' }}>{value}</a>
          : <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', textAlign: 'right', wordBreak: 'break-word', fontFamily: mono ? MONO : UI }}>{value}</span>}
    </div>
  )
}

// ── Пиксельные бары оборота (язык ДДС): приход вверх, расход вниз ──
function TurnoverChart({ monthly }) {
  const [sel, setSel] = useState(null)
  if (!monthly || !monthly.length) return <div style={{ fontSize: 12, color: 'var(--text-faint)', padding: '8px 0' }}>Нет данных</div>
  const CELLS = 4
  // шкала = максимум по месяцам + 20% (иначе на малых объёмах бары пустые)
  const peak = Math.max(1, ...monthly.map(m => Math.max(m.income || 0, m.expense || 0)))
  const half = peak * 1.2
  const cell = half / CELLS
  const s = sel != null ? monthly[sel] : null
  const cellBox = (filled, color) => <div style={{ height: 5, borderRadius: 2, background: filled ? color : 'var(--border-inner)' }} />
  return (
    <div>
      {/* сводка */}
      <div style={{ background: '#F6F8FF', borderRadius: 12, padding: '11px 14px', minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
        {s ? <>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{fmtMonth(s.period)}</span>
          <span style={{ display: 'flex', gap: 12, fontFamily: MONO, fontSize: 13, fontWeight: 700 }}>
            <span style={{ color: 'var(--income)' }}>+{mln(s.income)} млн</span>
            <span style={{ color: 'var(--text-secondary)' }}>−{mln(s.expense)} млн</span>
          </span>
        </> : <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>нажмите на столбец</span>}
      </div>
      {/* бары */}
      <div style={{ display: 'flex', gap: 3, alignItems: 'stretch' }}>
        {monthly.map((m, i) => {
          const up = (m.income || 0) > 0 ? Math.min(CELLS, Math.max(1, Math.round(m.income / cell))) : 0
          const dn = (m.expense || 0) > 0 ? Math.min(CELLS, Math.max(1, Math.round(m.expense / cell))) : 0
          return (
            <div key={i} onClick={() => setSel(sel === i ? null : i)} style={{ flex: 1, minWidth: 0, cursor: 'pointer', background: sel === i ? '#F0F3FF' : 'transparent', borderRadius: 5, padding: '3px 1px', display: 'flex', flexDirection: 'column', gap: 2 }}>
              {Array.from({ length: CELLS }).map((_, k) => cellBox(k >= CELLS - up, 'var(--income)'))}
              {Array.from({ length: CELLS }).map((_, k) => cellBox(k < dn, '#8B93A6'))}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 3, marginTop: 5 }}>
        {monthly.map((m, i) => <span key={i} style={{ flex: 1, textAlign: 'center', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)', overflow: 'hidden' }}>{i % 6 === 0 ? fmtMonth(m.period).split(' ')[0] : ''}</span>)}
      </div>
    </div>
  )
}

export default function CounterpartyCardMobile({ id, card, relation, analytics, canEdit, onBack, onEdit, copyRequisites, copied,
  editMode, editData, setEditData, onSave, saving, saveErr, onCancelEdit }) {
  const [tab, setTab] = useState('analytics')
  const stats = card.stats || {}
  const isActive = card.status === 'действующий'

  // операции — грузим сами, с накоплением «показать ещё»
  const LIMIT = 50
  const [ops, setOps] = useState([])
  const [opsTotal, setOpsTotal] = useState(0)
  const [opsPage, setOpsPage] = useState(0)
  const [opsStatus, setOpsStatus] = useState('')
  const [opsDir, setOpsDir] = useState('desc')
  const [opsLoading, setOpsLoading] = useState(false)

  const loadOps = useCallback(async (page, status, dir, append) => {
    const token = localStorage.getItem('token')
    setOpsLoading(true)
    try {
      const params = new URLSearchParams({ counterparty_id: id, skip: page * LIMIT, limit: LIMIT, sort_col: 'date', sort_dir: dir })
      if (status) params.append('status', status)
      const r = await api(token).get(`/counterparties/${id}/operations?${params}`)
      setOps(prev => append ? [...prev, ...(r.data.items || [])] : (r.data.items || []))
      setOpsTotal(r.data.total || 0)
    } catch { } finally { setOpsLoading(false) }
  }, [id])

  useEffect(() => { if (id && tab === 'operations' && ops.length === 0) loadOps(0, '', 'desc', false) }, [id, tab])

  const setStatusFilter = (v) => { setOpsStatus(v); setOpsPage(0); loadOps(0, v, opsDir, false) }
  const setDir = (v) => { setOpsDir(v); setOpsPage(0); loadOps(0, opsStatus, v, false) }
  const more = () => { const p = opsPage + 1; setOpsPage(p); loadOps(p, opsStatus, opsDir, true) }

  // KPI под-значения
  const planCnt = (analytics?.by_status || []).filter(s => /ПЛАН/.test(s.status)).reduce((a, s) => a + (s.cnt || 0), 0)
  const factCnt = (analytics?.by_status || []).filter(s => s.status === 'ОПЛАЧЕНО').reduce((a, s) => a + (s.cnt || 0), 0)
  const saldo = stats.saldo || 0

  const TABS = [
    { key: 'analytics', label: 'Аналитика' },
    { key: 'requisites', label: 'Реквизиты' },
    { key: 'contracts', label: 'Договоры' },
    { key: 'operations', label: 'Операции' },
  ]

  // ── режим правки реквизитов ──
  if (editMode && editData) {
    const setF = (k, v) => setEditData(d => ({ ...d, [k]: v }))
    const setBank = (i, k, v) => setEditData(d => ({ ...d, bank_accounts: d.bank_accounts.map((b, j) => j === i ? { ...b, [k]: v } : b) }))
    const addBank = () => setEditData(d => ({ ...d, bank_accounts: [...d.bank_accounts, { bank_name: '', bank_city: '', rs: '', ks: '', bik: '' }] }))
    const delBank = (i) => setEditData(d => ({ ...d, bank_accounts: d.bank_accounts.filter((_, j) => j !== i) }))
    const fld = (label, k, ml) => (
      <div key={k} style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>{label}</div>
        {ml ? <textarea value={editData[k] || ''} onChange={e => setF(k, e.target.value)} rows={2} style={{ ...inpS, resize: 'vertical' }} />
          : <input value={editData[k] || ''} onChange={e => setF(k, e.target.value)} style={inpS} />}
      </div>
    )
    return (
      <div style={{ padding: 14, fontFamily: UI, paddingBottom: 90 }}>
        <div style={{ ...CARD, padding: '14px 16px' }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>Редактирование реквизитов</div>
          {fld('КПП', 'kpp')}{fld('ОГРН', 'ogrn')}{fld('ОКПО', 'okpo')}
          {fld('Юр. адрес', 'address', true)}{fld('Факт. адрес', 'address_fact', true)}
          {fld('Телефон', 'phone')}{fld('Email', 'email')}{fld('Сайт', 'website')}
          {fld('ЭДО', 'edo_id')}{fld('Примечание', 'note', true)}
          {/* Те же три поля, что и на десктопе: они печатаются в приложении к договору. */}
          <div style={{ ...sectionLbl, marginTop: 14 }}>Подписант документов</div>
          {fld('ФИО подписанта', 'director_name')}
          {fld('Должность', 'signer_position')}{fld('Основание полномочий', 'signer_basis')}
          <div style={{ ...sectionLbl, marginTop: 14 }}>Банковские счета</div>
          {(editData.bank_accounts || []).map((b, i) => (
            <div key={i} style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '12px 12px 4px', marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                <input value={b.bank_name || ''} onChange={e => setBank(i, 'bank_name', e.target.value)} placeholder="Банк" style={{ ...inpS, flex: 1 }} />
                <button onClick={() => delBank(i)} aria-label="Удалить счёт" style={{ width: 38, flexShrink: 0, border: '1px solid #F3C9CC', background: 'var(--bg-card)', color: T.danger, borderRadius: 10, cursor: 'pointer' }}>✕</button>
              </div>
              <div style={{ marginBottom: 8 }}><input value={b.rs || ''} onChange={e => setBank(i, 'rs', e.target.value)} placeholder="Р/С" style={{ ...inpS, fontFamily: MONO }} /></div>
              <div style={{ marginBottom: 8 }}><input value={b.ks || ''} onChange={e => setBank(i, 'ks', e.target.value)} placeholder="К/С" style={{ ...inpS, fontFamily: MONO }} /></div>
              <div style={{ marginBottom: 8 }}><input value={b.bik || ''} onChange={e => setBank(i, 'bik', e.target.value)} placeholder="БИК" style={{ ...inpS, fontFamily: MONO }} /></div>
            </div>
          ))}
          <button onClick={addBank} style={{ width: '100%', border: '1px dashed var(--border-card)', background: 'var(--bg-card)', color: 'var(--accent)', borderRadius: 10, padding: '10px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>+ Добавить счёт</button>
          {saveErr && <div style={{ color: T.danger, fontSize: 12.5, marginTop: 10 }}>{saveErr}</div>}
        </div>
        <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, padding: '12px 14px', background: 'var(--bg-card)', borderTop: '1px solid var(--border-inner)', display: 'flex', gap: 8 }}>
          <button onClick={onSave} disabled={saving} style={{ flex: 1, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 12, padding: '14px', fontSize: 15, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Сохранение…' : 'Сохранить'}</button>
          <button onClick={onCancelEdit} style={{ flex: '0 0 auto', padding: '14px 20px', border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', borderRadius: 12, fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>Отмена</button>
        </div>
      </div>
    )
  }

  // шапка сущности: назад · имя+подпись · редактировать — переезжает в title CardShell
  const titleNode = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <button onClick={onBack} aria-label="Назад" style={{ width: 36, height: 36, flexShrink: 0, borderRadius: 10, border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>‹</button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{card.name}</div>
        <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Контрагент · #{id}</div>
      </div>
      {canEdit && <button onClick={onEdit} aria-label="Редактировать" style={{ width: 36, height: 36, flexShrink: 0, borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><svg width="15" height="15" viewBox="0 0 24 24" style={stroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg></button>}
    </div>
  )

  // лента чипов — переезжает в badges CardShell
  const badgesNode = (
    <>
      <Chip label={card.status} bg={isActive ? '#E6F5EF' : 'var(--bg-subtle)'} fg={isActive ? 'var(--income)' : 'var(--text-muted)'} />
      {relation && <Chip label={relation} bg="#F1EDFC" fg="#7B62D6" />}
      {card.website && <Chip label={card.website.replace(/^https?:\/\//i, '').replace(/\/$/, '')} bg="var(--bg-card)" fg="var(--accent)" href={normalizeUrl(card.website)} />}
      {(card.linked_agencies || []).map(a => <Chip key={a.id} label={a.name_en || a.name} bg="var(--bg-card)" fg="var(--text-secondary)" />)}
    </>
  )

  // KPI 2×2 — переезжает в слот kpi CardShell (между шапкой и рядом табов, как в оригинале)
  const kpiNode = (
    <div style={{ ...CARD, padding: '2px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
      {[
        { l: 'Операций всего', v: stats.op_count || 0, sub: `${planCnt} плана · ${factCnt} факт`, c: 'var(--text-primary)', br: true, bb: true },
        { l: 'Дебиторка', v: mln(stats.receivable), sub: stats.receivable > 0 ? 'есть задолженность' : 'нет просрочки', c: 'var(--accent)', bb: true },
        { l: 'Кредиторка', v: mln(stats.payable), sub: 'млн ₽', c: T.warning, br: true },
        { l: 'Сальдо', v: (saldo < 0 ? '−' : '') + mln(Math.abs(saldo)), sub: `млн ₽ · ${saldo < 0 ? 'мы должны' : 'нам должны'}`, c: saldo < 0 ? T.danger : 'var(--income)' },
      ].map((k, i) => (
        <div key={i} style={{ padding: '14px 4px 14px 0', borderRight: k.br ? '1px solid var(--border-row)' : 'none', borderBottom: k.bb ? '1px solid var(--border-row)' : 'none', paddingLeft: (i % 2) ? 14 : 0 }}>
          <div style={monoLbl}>{k.l}</div>
          <div style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, letterSpacing: '-.02em', color: k.c, margin: '4px 0 2px' }}>{k.v}</div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{k.sub}</div>
        </div>
      ))}
    </div>
  )

  return (
    <CardShell title={titleNode} badges={badgesNode} kpi={kpiNode} tabs={TABS} tab={tab} setTab={setTab} tabsLayout="equal">
      {/* контент таба */}
      <div key={tab} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {tab === 'analytics' && (
          <div style={{ ...CARD, padding: '14px 16px' }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>Оборот по месяцам</div>
            {!analytics ? <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div> : <>
              <TurnoverChart monthly={analytics.monthly} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, margin: '16px 0 4px' }}>
                {[
                  ['Ср. приход', rub(analytics.avg_income), 'var(--income)'],
                  ['Ср. расход', rub(analytics.avg_expense), 'var(--text-secondary)'],
                  ['Доля в выручке', analytics.share_income_12m ? `${analytics.share_income_12m} %` : '—', 'var(--income)'],
                  ['Доля в закупках', analytics.share_expense_12m ? `${analytics.share_expense_12m} %` : '—', 'var(--text-primary)'],
                ].map(([l, v, c]) => (
                  <div key={l} style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '12px 14px' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{l}</div>
                    <div style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: c }}>{v}</div>
                  </div>
                ))}
              </div>
              {(analytics.top_articles || []).length > 0 && <>
                <div style={{ ...sectionLbl, marginTop: 14 }}>Топ статей</div>
                {analytics.top_articles.map((a, i) => {
                  const total = (a.income || 0) + (a.expense || 0)
                  const max = (analytics.top_articles[0].income || 0) + (analytics.top_articles[0].expense || 0) || 1
                  return (
                    <div key={i} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.article}</span>
                        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', flexShrink: 0 }}>{rub(total)}</span>
                      </div>
                      <div style={{ height: 5, borderRadius: 2, background: 'var(--border-inner)', overflow: 'hidden' }}>
                        <div style={{ height: '100%', borderRadius: 2, width: `${Math.round(total / max * 100)}%`, background: (a.income || 0) >= (a.expense || 0) ? 'var(--income)' : '#8B93A6' }} />
                      </div>
                    </div>
                  )
                })}
              </>}
              {(analytics.by_status || []).length > 0 && <>
                <div style={{ ...sectionLbl, marginTop: 14 }}>По статусам</div>
                {analytics.by_status.map(s => {
                  const meta = stMeta(s.status)
                  const amt = (s.income || 0) > 0 ? s.income : s.expense
                  return (
                    <div key={s.status} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: meta.dot, flexShrink: 0 }} />
                      <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-secondary)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.status}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-faint)', flexShrink: 0 }}>{s.cnt} оп.</span>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: meta.dot, flexShrink: 0 }}>{rub(amt)}</span>
                    </div>
                  )
                })}
              </>}
            </>}
          </div>
        )}

        {tab === 'requisites' && (
          <div style={{ ...CARD, padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={sectionLbl}>Реквизиты</span>
              <button onClick={copyRequisites} style={{ border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--text-secondary)', borderRadius: 10, padding: '7px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>{copied ? '✓ Скопировано' : 'Копировать'}</button>
            </div>
            <div>
              <ReqRow label="ИНН" value={card.inn} mono />
              <ReqRow label="КПП" value={card.kpp} mono />
              <ReqRow label="ОГРН" value={card.ogrn} mono />
              {card.okpo && <ReqRow label="ОКПО" value={card.okpo} mono />}
              <ReqRow label="Юр. адрес" value={card.address} />
              {card.address_fact && <ReqRow label="Факт. адрес" value={card.address_fact} />}
              <ReqRow label="Телефон" value={card.phone} mono />
              <ReqRow label="Email" value={card.email} />
              <ReqRow label="Сайт" value={card.website} link />
              <ReqRow label="ЭДО" value={card.edo_id} mono />
              <ReqRow label="ФИО подписанта" value={card.director_name} />
              <ReqRow label="Должность подписанта" value={card.signer_position} />
              <ReqRow label="Основание полномочий" value={card.signer_basis} />
              {card.note && <ReqRow label="Примечание" value={card.note} />}
            </div>
            {(card.bank_accounts || []).filter(b => b.bank_name || b.rs).map((b, i) => (
              <div key={i} style={{ marginTop: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', margin: '6px 0 2px' }}>{b.bank_name || 'Банк'}</div>
                <ReqRow label="Р/С" value={b.rs} mono />
                <ReqRow label="К/С" value={b.ks} mono />
                <ReqRow label="БИК" value={b.bik} mono />
              </div>
            ))}
            <div style={{ ...sectionLbl, marginTop: 16 }}>Условия по умолчанию</div>
            <ReqRow label="НДС приход" value={card.vat_rate_income != null ? `${card.vat_rate_income}%` : null} mono />
            <ReqRow label="НДС расход" value={card.vat_rate_expense != null ? `${card.vat_rate_expense}%` : null} mono />
            <ReqRow label="Статья прихода" value={card.default_article_income} />
            <ReqRow label="Статья расхода" value={card.default_article_expense} />
          </div>
        )}

        {tab === 'contracts' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 2px' }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Договоры <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-muted)' }}>{(card.contracts || []).length}</span></span>
              {/* `next/link`, а не голый `<a>`: переход внутри приложения не должен
                  перезагружать страницу — это теряет снимок прав и состояние экрана.
                  Единственная ошибка `npm run lint` в проекте (F0-04), чинится строкой. */}
              <Link href="/directory/contracts" style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', textDecoration: 'none' }}>В реестр →</Link>
            </div>
            {(card.contracts || []).length === 0 ? <div style={{ ...CARD, padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Договоров нет</div>
              : card.contracts.map(c => {
                const exp = contractExpired(c.end_date_text)
                return (
                  <div key={c.id} style={{ ...CARD, padding: '14px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{c.contract_number || '—'}</span>
                      {exp && <span style={{ marginLeft: 'auto', background: 'var(--danger-tint)', color: T.danger, borderRadius: 6, padding: '2px 8px', fontSize: 10.5, fontWeight: 700 }}>истёк</span>}
                    </div>
                    <div style={{ background: 'var(--bg-subtle)', borderRadius: 12, padding: '2px 12px' }}>
                      {[
                        ['Дата', fmtDate(c.contract_date)],
                        ['Формат', c.cooperation_format || '—'],
                        ['Пролонгация', c.prolongation || '—'],
                        ['Срок оплаты', c.payment_term_days != null ? `${c.payment_term_days} дн.` : '—'],
                        ['Окончание', c.end_date_text || '—'],
                        ['Документ', (c.document_link || c.attached_filename) ? 'есть' : '—'],
                      ].map(([l, v], i) => (
                        <div key={l} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '9px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border-inner)' }}>
                          <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{l}</span>
                          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', fontFamily: (l === 'Дата' || l === 'Срок оплаты') ? MONO : UI }}>{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
          </>
        )}

        {tab === 'operations' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <select value={opsStatus} onChange={e => setStatusFilter(e.target.value)} style={selStyle}>
                <option value="">Все статусы</option><option value="ОПЛАЧЕНО">Оплачено</option><option value="ПЛАН ПОСТУПЛЕНИЙ">План поступл.</option><option value="ПЛАН ОПЛАТ">План оплат</option>
              </select>
              <select value={opsDir} onChange={e => setDir(e.target.value)} style={selStyle}>
                <option value="desc">Дата ↓</option><option value="asc">Дата ↑</option>
              </select>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{opsTotal} записей</span>
            </div>
            {opsLoading && !ops.length ? <div style={{ ...CARD, padding: 30, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
              : ops.length === 0 ? <div style={{ ...CARD, padding: 30, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Операций нет</div>
                : ops.map(op => {
                  const meta = stMeta(op.status)
                  const isIncome = (op.income || 0) > 0
                  const amount = isIncome ? op.income : -(op.expense || 0)
                  return (
                    <div key={op.id} style={{ ...CARD, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 7 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 70, flexShrink: 0, fontFamily: MONO, fontSize: 11, color: op.date ? 'var(--text-muted)' : 'var(--text-faint)' }}>{op.date ? fmtDate(op.date) : 'без даты'}</span>
                        <span style={{ width: 104, flexShrink: 0, textAlign: 'center', background: meta.bg, color: meta.fg, borderRadius: 8, padding: '4px 0', fontFamily: MONO, fontSize: 11, fontWeight: 700 }}>{meta.label}</span>
                        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 14, fontWeight: 700, color: isIncome ? 'var(--income)' : 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{isIncome ? '+' : '−'}{rub(Math.abs(amount)).replace(' ₽', '')} ₽</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                        <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{op.article || '—'}</span>
                        {op.period && <span style={{ width: 1, height: 11, background: 'var(--border-card)', flexShrink: 0 }} />}
                        {op.period && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>{periodShort(op.period)}</span>}
                        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
                          <span style={{ width: 7, height: 7, borderRadius: 2, background: bankColor(op.bank) }} />
                          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{op.bank || 'не указан'}</span>
                        </span>
                      </div>
                    </div>
                  )
                })}
            {ops.length < opsTotal && <button onClick={more} disabled={opsLoading} style={{ ...CARD, padding: '13px', fontSize: 13, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer', textAlign: 'center' }}>{opsLoading ? 'Загрузка…' : `Показать ещё ${Math.min(LIMIT, opsTotal - ops.length)}`}</button>}
          </>
        )}
      </div>
    </CardShell>
  )
}

const selStyle = { appearance: 'none', WebkitAppearance: 'none', border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '8px 12px', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', fontFamily: UI, cursor: 'pointer', outline: 'none' }
const inpS = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: UI, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }
