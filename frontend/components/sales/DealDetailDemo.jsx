import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import api, { auth } from '../../lib/api'
import { MONO, UI, CAP, docCard, addBtn, iconSq, DocIcon, DownloadIcon, EditIcon, PlusIcon } from '../salesTableKit'

// ── ДЕМО раскрытой сводки сделки (ТЗ «форма сделки» + ds.jsx) ──
// Четыре колонки: Данные сделки → Медиаплан и документы → История → Оплаты.
// Стили/примитивы — из salesTableKit (единый справочник), данные — из строки реестра.

const rub = (n) => (n == null ? '—' : `${new Intl.NumberFormat('ru-RU').format(Math.round(n))} ₽`)
const fmtWhen = (str) => {
  if (!str) return ''
  const s = /[zZ]|[+-]\d{2}:?\d{2}$/.test(str) ? str : str + 'Z'
  return new Date(s).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const EVENT_COLOR = {
  create_deal: 'var(--text-faint)', patch_sales_deal: 'var(--dot-current-dz)',
  save_deal_brief: 'var(--accent)', push_deal_to_bitrix: 'var(--accent)', sync_deal_from_bitrix: 'var(--accent)',
}

const LBL = { fontSize: 12, color: 'var(--text-muted)', flex: '0 0 132px' }
const VAL = { fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }

// Строка «лейбл — значение».
function Row({ label, children, mono }) {
  const empty = children == null || children === '—'
  return (
    <div style={{ display: 'flex', gap: 14, fontSize: 12, paddingBottom: 9, marginBottom: 9, borderBottom: '1px solid var(--border-inner)' }}>
      <span style={LBL}>{label}</span>
      <span style={{ ...VAL, fontFamily: mono ? MONO : UI, color: empty ? 'var(--text-faint)' : 'var(--text-primary)' }}>{empty ? '—' : children}</span>
    </div>
  )
}

// Карточка документа: пусто (двухстрочная + «+ Добавить») или с файлом (иконка «Скачать»).
function DocLine({ title, meta, empty, onAdd, right }) {
  return (
    <div style={docCard}>
      <DocIcon />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</div>
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', marginTop: 2 }}>{empty ? 'не загружено' : meta}</div>
      </div>
      {right ?? <button style={addBtn} onClick={onAdd}>+ Добавить</button>}
    </div>
  )
}

export default function DealDetailDemo({ deal, onClose }) {
  const d = deal
  const router = useRouter()
  const [history, setHistory] = useState(null)
  const [grow, setGrow] = useState(false)

  useEffect(() => {
    let alive = true
    api.get(`/sales/deals/${d.id}/history`, auth())
      .then(r => { if (alive) setHistory(r.data.items || []) })
      .catch(() => { if (alive) setHistory([]) })
    const t = setTimeout(() => alive && setGrow(true), 40)
    return () => { alive = false; clearTimeout(t) }
  }, [d.id])

  const mpBx = (d.files || []).find(f => f.kind === 'mp')          // МП из Битрикса
  const mpOur = (d.our_mps || [])[0]                               // наш МП (конструктор)
  const paid = 0, expected = d.amount || 0
  const pct = expected ? Math.min(100, (paid / expected) * 100) : 0
  const stop = (e) => e.stopPropagation()

  return (
    <div onClick={stop} style={{
      margin: '2px 0 10px', padding: '18px 20px', background: '#F6F8FF',
      border: '1px solid var(--border-card)', borderRadius: 14, fontFamily: UI,
      display: 'grid', gridTemplateColumns: '1.3fr 1.1fr 1.1fr 1fr', gap: 24,
      animation: 'riseIn .26s cubic-bezier(0.22,1,0.36,1) both',
    }}>
      {/* 1. Данные сделки */}
      <div>
        <div style={CAP}>Данные сделки</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
          <div style={{ flex: 1, minWidth: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '6px 7px 6px 11px', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.title}>{d.title || '—'}</div>
          <button title="Сгенерировать название" style={{ ...iconSq(true) }}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></button>
        </div>
        <Row label="Рекламодатель / бренд">{[d.advertiser, d.brand].filter(Boolean).join(' · ') || '—'}</Row>
        <Row label="Агентство">{d.agency || '—'}</Row>
        <Row label="Плательщик">{d.payer || '—'}</Row>
        <Row label="Услуга">{d.product || '—'}</Row>
        <Row label="Период / стадия" mono>{[d.period, d.our_stage?.name].filter(Boolean).join(' · ') || '—'}</Row>
        <Row label="Продавец">{d.sales_rep || '—'}</Row>
        <Row label="Аккаунт">{d.account_manager || '—'}</Row>
      </div>

      {/* 2. Медиаплан и документы */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={CAP}>Медиаплан и документы</div>
        <DocLine title="МП (Битрикс)" meta={mpBx?.filename} empty={!mpBx}
          right={mpBx ? <button style={iconSq(false)} title={mpBx.filename}><DownloadIcon /></button> : undefined} />
        <DocLine title="МП наш" meta={mpOur ? `v${mpOur.version} · ${mpOur.status || ''}` : ''} empty={!mpOur}
          right={mpOur ? (
            <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
              <button style={{ ...iconSq(false), width: 'auto', padding: '0 7px', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>PDF</button>
              <button style={{ ...iconSq(false), width: 'auto', padding: '0 7px', fontFamily: MONO, fontSize: 10, fontWeight: 700 }}>XLS</button>
              <button style={iconSq(true)} title="Открыть конструктор" onClick={() => router.push(`/accounts/mp/${mpOur.id}`)}><EditIcon /></button>
            </span>
          ) : undefined} />
        {[['ДС', 'ds'], ['Отчёт', 'report'], ['УПД', 'upd'], ['Счёт', 'invoice']].map(([t, k]) => (
          <DocLine key={k} title={t} empty />
        ))}
      </div>

      {/* 3. История */}
      <div>
        <div style={CAP}>История</div>
        {history === null ? (
          <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Загрузка…</div>
        ) : history.length ? history.map((e, i) => (
          <div key={i} style={{ display: 'flex', gap: 9, marginBottom: 12 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: EVENT_COLOR[e.action] || 'var(--text-faint)', marginTop: 5, flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{e.label}{e.details ? <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}> · {e.details}</span> : ''}</div>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: MONO, marginTop: 1 }}>{fmtWhen(e.at)}{e.who ? ` · ${e.who}` : ''}</div>
            </div>
          </div>
        )) : (
          <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
            {d.date_create ? <>Сделка создана · {fmtWhen(d.date_create)}</> : 'Событий пока нет'}
          </div>
        )}
      </div>

      {/* 4. Оплаты */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={CAP}>Оплаты</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--income)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', flex: 1 }}>Поступило</span>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{rub(paid)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--dot-current-dz)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1 }}>Ожидается</span>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{rub(expected)}</span>
        </div>
        <div style={{ height: 8, borderRadius: 2, background: 'var(--border-inner)', overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ width: grow ? `${pct}%` : 0, height: '100%', background: 'var(--income)', transition: 'width .55s cubic-bezier(0.22,1,0.36,1)' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 10, borderTop: '1px solid var(--border-inner)' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', flex: 1 }}>Наша сумма</span>
          <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 800, color: 'var(--income)' }}>{rub(d.our_sum)}</span>
        </div>
        {/* действия — прижаты к правому краю */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 'auto', paddingTop: 14 }}>
          <button onClick={() => router.push(`/sales/deals/${d.id}`)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 34, padding: '0 14px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>
            <DocIcon /> Карточка
          </button>
          <button title="Бриф" style={{ ...iconSq(false), width: 34, height: 34 }}><DocIcon /></button>
          <button title="Редактировать" style={{ ...iconSq(false), width: 34, height: 34 }}><EditIcon /></button>
        </div>
      </div>
    </div>
  )
}
