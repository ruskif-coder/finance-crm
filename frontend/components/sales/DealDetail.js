import { useState, useEffect } from 'react'
import api, { auth } from '../../lib/api'
import { MONO, UI, card, btn, primaryBtn } from '../salesTableKit'
import { fmtMoney, fmtDate } from '../../lib/salesFormat'

// ── Детализация сделки (раскрытие строки в реестре /sales и дашборде) ──
// Стили — из эталона (salesTableKit): токены var(--*) + шрифты MONO/UI.
// Секции: Реквизиты → Медиаплан и документы → История → Оплаты (последняя).
// Пока частично заглушки (платежи/история) — «потом доработаем».

const rub = (n) => (n == null ? '—' : `${new Intl.NumberFormat('ru-RU').format(Math.round(n))} ₽`)

// audit_log хранит UTC (func.now()); добавляем 'Z', если нет маркера зоны, и показываем
// в московском времени (UTC+3) — как в Журнале действий.
const fmtWhen = (str) => {
  if (!str) return ''
  const s = /[zZ]|[+-]\d{2}:?\d{2}$/.test(str) ? str : str + 'Z'
  return new Date(s).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}
// цвет точки события по типу действия
const EVENT_COLOR = {
  create_deal: 'var(--text-faint)',
  patch_sales_deal: 'var(--dot-current-dz)',
  save_deal_brief: 'var(--income)',
  push_deal_to_bitrix: 'var(--accent)',
  sync_deal_from_bitrix: 'var(--accent)',
}

const HDR = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-faint)', marginBottom: 12 }
const LBL = { fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }
const VAL = { fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={LBL}>{label}</div>
      <div style={VAL}>{children ?? '—'}</div>
    </div>
  )
}

function DocCard({ children }) {
  return <div style={{ border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'flex-start' }}>{children}</div>
}
const DocIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" style={{ flexShrink: 0, fill: 'none', stroke: 'var(--text-faint)', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />
  </svg>
)

export default function DealDetail({ deal, canEdit, onOpen, onEdit, onAddMp }) {
  const d = deal
  const mp = (d.files || []).find(f => f.kind === 'mp')

  // История сделки из журнала действий (audit_log): событие · инициатор · время.
  const [history, setHistory] = useState(null)
  useEffect(() => {
    let alive = true
    api.get(`/sales/deals/${d.id}/history`, auth())
      .then(r => { if (alive) setHistory(r.data.items || []) })
      .catch(() => { if (alive) setHistory([]) })
    return () => { alive = false }
  }, [d.id])

  return (
    <div style={{ ...card, padding: '20px 22px', margin: '2px 0 10px', fontFamily: UI }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 28 }}>

        {/* 1. Реквизиты сделки */}
        <div>
          <div style={HDR}>Реквизиты сделки</div>
          <Field label="Рекламодатель / бренд">{[d.advertiser, d.brand].filter(Boolean).join(' · ') || '—'}</Field>
          <Field label="Агентство">{d.agency || '—'}</Field>
          <Field label="Плательщик">{d.payer || '—'}</Field>
          <Field label="Услуга">{d.product || '—'}</Field>
          <Field label="Период / стадия">{[d.period, d.bitrix_stage].filter(Boolean).join(' · ') || '—'}</Field>
          <Field label="Аккаунт">{d.account_manager || '—'}</Field>
          <Field label="Название">{d.title || '—'}</Field>
        </div>

        {/* 2. Медиаплан и документы (пока только МП) */}
        <div>
          <div style={HDR}>Медиаплан и документы</div>
          {mp ? (
            <DocCard>
              <DocIcon />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Медиаплан · {mp.filename}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                  {d.date_modify ? `обновлён ${fmtDate(d.date_modify)}` : 'загружен'}{d.amount != null ? ` · ${fmtMoney(d.amount)}` : ''}
                </div>
              </div>
            </DocCard>
          ) : (
            <button onClick={() => onAddMp && onAddMp(d)} disabled={!canEdit}
              style={{ ...btn(false), width: '100%', justifyContent: 'center', display: 'inline-flex', alignItems: 'center', gap: 6, padding: '12px 14px', borderStyle: 'dashed', color: 'var(--accent)', opacity: canEdit ? 1 : 0.6, cursor: canEdit ? 'pointer' : 'default' }}>
              + МП
            </button>
          )}
        </div>

        {/* 3. История — из журнала действий (audit_log): событие · инициатор · время */}
        <div>
          <div style={HDR}>История</div>
          {history === null ? (
            <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Загрузка…</div>
          ) : history.length ? history.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 9, marginBottom: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: EVENT_COLOR[e.action] || 'var(--text-faint)', marginTop: 5, flexShrink: 0 }} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{e.label}{e.details ? <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}> · {e.details}</span> : ''}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: MONO, marginTop: 1 }}>{fmtWhen(e.at)}{e.who ? ` · ${e.who}` : ''}</div>
              </div>
            </div>
          )) : (
            <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              {d.date_create ? <>Сделка создана · {fmtWhen(d.date_create)}<div style={{ marginTop: 4 }}>Событий в журнале пока нет.</div></> : 'Событий пока нет'}
            </div>
          )}
        </div>

        {/* 4. Оплаты (последняя) */}
        <div>
          <div style={HDR}>Оплаты</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--income)' }} />
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>Поступило</span>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: MONO, color: 'var(--text-primary)' }}>{rub(0)}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>Ожидается</span>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: MONO, color: 'var(--text-primary)' }}>{rub(d.amount)}</span>
          </div>
          <div style={{ height: 6, borderRadius: 4, background: 'var(--border-row)', overflow: 'hidden', marginBottom: 12 }}>
            <div style={{ width: '0%', height: '100%', background: 'var(--income)' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>Наша сумма</span>
            <span style={{ fontSize: 14, fontWeight: 800, fontFamily: MONO, color: 'var(--income)' }}>{rub(d.our_sum)}</span>
          </div>
        </div>
      </div>

      {/* Действия */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
        {onOpen && <button onClick={() => onOpen(d)} style={primaryBtn}>Открыть сделку</button>}
        {onEdit && <button onClick={() => onEdit(d)} style={btn(false)}>Редактировать</button>}
      </div>
    </div>
  )
}
