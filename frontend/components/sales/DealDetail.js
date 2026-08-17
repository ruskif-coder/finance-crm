import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import api, { auth } from '../../lib/api'
import { BITRIX_DEAL_URL } from '../../lib/salesLayers'
import { MONO, UI, CAP, docCard, addBtn, iconSq, DocIcon, DownloadIcon, EditIcon, StageLayerBar } from '../salesTableKit'
import { DEAL_DOCS, downloadBlob, pickAndUploadDoc, deleteDoc } from '../../lib/dealDocs'

// ── Раскрытая сводка сделки (раскрытие строки реестра /sales и дашборда) ──
// Четыре колонки: Данные сделки → Медиаплан и документы → История → Оплаты.
// ТЗ «форма сделки» + ds.jsx. Стили/примитивы — из salesTableKit (единый справочник).
// Данные — из строки реестра; история — из audit_log; файлы/синк — реальные эндпоинты.

const rub = (n) => (n == null ? '—' : `${new Intl.NumberFormat('ru-RU').format(Math.round(n))} ₽`)
// audit_log хранит UTC; добавляем 'Z' если нет зоны и показываем в UTC+3 (как в Журнале).
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

// Скачивание blob по URL (файлы сделки, PDF/XLS медиаплана) — общий хелпер.
const blobGet = downloadBlob

// Строка «лейбл — значение».
function Row({ label, children, mono }) {
  const empty = children == null || children === '—'
  return (
    <div style={{ display: 'flex', gap: 14, fontSize: 12, paddingBottom: 9, marginBottom: 9, borderBottom: '1px solid var(--border-inner)' }}>
      <span style={LBL}>{label}</span>
      <span style={{ fontFamily: mono ? MONO : UI, fontSize: 12, fontWeight: 600, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', color: empty ? 'var(--text-faint)' : 'var(--text-primary)' }}>{empty ? '—' : children}</span>
    </div>
  )
}

// Карточка документа: пусто (двухстрочная + «+ Добавить») или с действиями справа.
function DocLine({ title, meta, empty, onAdd, addLabel = '+ Добавить', right }) {
  return (
    <div style={docCard}>
      <DocIcon />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</div>
        <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', marginTop: 2 }}>{empty ? 'не загружено' : meta}</div>
      </div>
      {right ?? <button style={addBtn} onClick={onAdd} disabled={!onAdd}>{addLabel}</button>}
    </div>
  )
}

export default function DealDetail({ deal, canEdit, onOpen, onEdit, onAddMp, onOpenBrief, onGenerate, onChanged }) {
  const d = deal
  const router = useRouter()
  const [history, setHistory] = useState(null)
  const [grow, setGrow] = useState(false)
  const [checking, setChecking] = useState(false)
  // Название: редактируется по клику; генератор собирает имя по шаблону.
  const [title, setTitle] = useState(d.title || '')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  useEffect(() => {
    let alive = true
    setTitle(d.title || '')
    api.get(`/sales/deals/${d.id}/history`, auth())
      .then(r => { if (alive) setHistory(r.data.items || []) })
      .catch(() => { if (alive) setHistory([]) })
    const t = setTimeout(() => alive && setGrow(true), 40)
    return () => { alive = false; clearTimeout(t) }
  }, [d.id, d.title])

  // Маска названия: Рекламодатель | Бренд | Агентство | Услуга | Период (как в реестре).
  const templateTitle = () => [d.advertiser, d.brand, d.agency, d.product, d.period].filter(v => v != null && String(v).trim() !== '').join(' | ')
  const saveTitle = async (val) => {
    const t = (val || '').trim()
    setEditing(false)
    if (!t || t === title) return
    try { await api.patch(`/sales/deals/${d.id}`, { title: t }, auth()); setTitle(t); onChanged?.() }
    catch { alert('Не удалось сохранить название') }
  }
  const startEdit = () => { if (canEdit) { setDraft(title); setEditing(true) } }
  // «+ Добавить» у «МП наш» → всегда конструктор МП этой сделки (страничные onAddMp бывают заглушками).
  const addMp = () => router.push(`/accounts/mp/new?deal=${d.id}`)
  const [docBusy, setDocBusy] = useState('')   // вид документа в процессе загрузки/удаления
  const genTitle = () => {
    const t = templateTitle()
    if (!t) { alert('Нечего собрать: нет рекламодателя / бренда / агентства / услуги / периода.'); return }
    setDraft(t); setEditing(true)
  }

  const mpBx = (d.files || []).find(f => f.kind === 'mp')          // МП из Битрикса
  const mpOur = (d.our_mps || [])[0]                               // наш МП (конструктор)
  const paid = 0, expected = d.amount || 0
  const pct = expected ? Math.min(100, (paid / expected) * 100) : 0
  const local = String(d.bitrix_id || '').startsWith('local-')
  const stop = (e) => e.stopPropagation()

  // «Проверить» — подтянуть поля и файлы из Битрикса (МП появится, если он там есть).
  const checkBitrix = async () => {
    if (checking || local) return
    setChecking(true)
    try { await api.post(`/sales/deals/${d.id}/sync-from-bitrix`, {}, { ...auth(), timeout: 0 }); onChanged?.() }
    catch (e) { alert(e.response?.data?.detail || 'Проверка недоступна') }
    finally { setChecking(false) }
  }

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
          {editing ? (
            <input autoFocus value={draft} onChange={e => setDraft(e.target.value)}
              onBlur={() => saveTitle(draft)}
              onKeyDown={e => { if (e.key === 'Enter') saveTitle(draft); else if (e.key === 'Escape') setEditing(false) }}
              style={{ flex: 1, minWidth: 0, background: 'var(--bg-card)', border: '1px solid var(--accent)', borderRadius: 10, padding: '6px 7px 6px 11px', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', outline: 'none', fontFamily: UI }} />
          ) : (
            <div onClick={startEdit} title={canEdit ? 'Изменить название' : title}
              style={{ flex: 1, minWidth: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '6px 7px 6px 11px', fontSize: 12, fontWeight: 600, color: title ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: canEdit ? 'text' : 'default' }}>{title || 'без названия'}</div>
          )}
          {canEdit && <button title="Сгенерировать название по шаблону" onClick={genTitle} style={iconSq(true)}><svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></svg></button>}
        </div>
        <Row label="Рекламодатель / бренд">{[d.advertiser, d.brand].filter(Boolean).join(' · ') || '—'}</Row>
        <Row label="Агентство">{d.agency || '—'}</Row>
        <Row label="Контрагент">{d.payer || '—'}</Row>
        <Row label="Услуга">{d.product || '—'}</Row>
        <Row label="Период / стадия" mono>{[d.period, d.our_stage?.name].filter(Boolean).join(' · ') || '—'}</Row>
        <Row label="Продавец">{d.sales_rep || '—'}</Row>
        <Row label="Аккаунт">{d.account_manager || '—'}</Row>
      </div>

      {/* 2. Медиаплан и документы */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={CAP}>Медиаплан и документы</div>
        {/* МП (Битрикс): есть → «Скачать»; нет → «Проверить» (синк из Битрикса) */}
        <DocLine title="МП (Битрикс)" meta={mpBx?.filename} empty={!mpBx}
          right={mpBx
            ? <button style={iconSq(false)} title={`Скачать · ${mpBx.filename || ''}`} onClick={() => blobGet(`/sales/deals/${d.id}/files/mp/download`, mpBx.filename)}><DownloadIcon /></button>
            : <button style={{ ...addBtn, opacity: (checking || local) ? 0.6 : 1, cursor: (checking || local) ? 'default' : 'pointer' }} onClick={checkBitrix} disabled={checking || local}
                title={local ? 'Локальная сделка — нет в Битриксе' : 'Проверить наличие МП в Битриксе'}>{checking ? 'Проверка…' : 'Проверить'}</button>} />
        {/* МП наш: PDF · XLS · конструктор */}
        <DocLine title="МП наш" meta={mpOur ? `v${mpOur.version}${mpOur.status ? ' · ' + mpOur.status : ''}` : ''} empty={!mpOur}
          onAdd={canEdit ? addMp : undefined}
          right={mpOur ? (
            <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
              <button style={{ ...iconSq(false), width: 'auto', padding: '0 7px', fontFamily: MONO, fontSize: 10, fontWeight: 700 }} title="Скачать PDF" onClick={() => blobGet(`/media-plans/${mpOur.id}/pdf`, `MP_${mpOur.id}_v${mpOur.version}.pdf`)}>PDF</button>
              <button style={{ ...iconSq(false), width: 'auto', padding: '0 7px', fontFamily: MONO, fontSize: 10, fontWeight: 700 }} title="Скачать XLSX" onClick={() => blobGet(`/media-plans/${mpOur.id}/export.xlsx`, `MP_${mpOur.id}_v${mpOur.version}.xlsx`)}>XLS</button>
              <button style={iconSq(true)} title="Открыть конструктор" onClick={() => router.push(`/accounts/mp/${mpOur.id}`)}><EditIcon /></button>
            </span>
          ) : undefined} />
        {/* Реальные документы сделки: загрузка/замена/скачивание/удаление.
            Список видов — общий с карточкой и доской (lib/dealDocs); битриксовые
            (договор) сюда не берём, они выше отдельными строками. */}
        {DEAL_DOCS.filter(x => !x.bx).map(({ kind, label }) => {
          const f = (d.files || []).find(x => x.kind === kind)
          const busy = docBusy === kind
          return (
            <DocLine key={kind} title={label} empty={!f}
              meta={busy ? 'загрузка…' : (f ? f.filename : '')}
              right={
                <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                  {f && <button style={iconSq(false)} title={`Скачать · ${f.filename || ''}`}
                    onClick={() => downloadBlob(`/sales/deals/${d.id}/files/${kind}/download`, f.filename)}><DownloadIcon /></button>}
                  {canEdit && <button style={addBtn} onClick={() => pickAndUploadDoc(d.id, kind, onChanged, setDocBusy)}>{f ? 'Заменить' : '+ Добавить'}</button>}
                  {canEdit && f && <button style={{ ...addBtn, color: 'var(--danger)' }} title="Удалить"
                    onClick={() => deleteDoc(d.id, kind, onChanged, setDocBusy)}>×</button>}
                </span>
              } />
          )
        })}
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

      {/* 4. Стадия (бар 2\2\2 во всю ширину) + Оплаты */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={CAP}>Стадия</div>
        <div style={{ marginBottom: 18 }}>
          <StageLayerBar os={d.our_stage} full h={16} />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, display: 'flex', gap: 6 }}>
            {/* Прочерк вместо стадии выглядел как «не загрузилось». Пустая стадия —
                это состояние сделки («требует разбора»), и говорить о нём надо словами. */}
            <span style={{ fontWeight: 600, color: d.our_stage ? 'var(--text-primary)' : 'var(--danger)' }}>
              {d.our_stage?.name || 'стадия не определена — требует разбора'}
            </span>
            {d.our_stage?.money_layer && <span style={{ fontFamily: MONO, color: 'var(--text-faint)' }}>· {d.our_stage.money_layer}</span>}
          </div>
        </div>
        {/* Материнский годовой план — если сделка создана конвейером из плана */}
        {d.year_plan && (
          <div style={{ marginBottom: 18 }}>
            <div style={CAP}>Годовой план</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, padding: '9px 11px' }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  title={[d.year_plan.title, d.year_plan.comment].filter(Boolean).join(' · ')}>
                  {d.year_plan.title || `План ${d.year_plan.year || ''}`}
                  {d.year_plan.comment ? <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}> · {d.year_plan.comment}</span> : null}
                </div>
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', marginTop: 2 }}>
                  {d.year_plan.year}{d.plan_month != null ? ` · мес. ${d.plan_month + 1}` : ''}
                </div>
              </div>
              <button onClick={() => router.push(`/sales/year-plan?year=${d.year_plan.year}${d.year_plan.rep_id ? `&rep=${d.year_plan.rep_id}` : ''}`)}
                title="Открыть годовой план" style={{ ...addBtn, whiteSpace: 'nowrap' }}>Открыть план</button>
            </div>
          </div>
        )}
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
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 'auto', paddingTop: 14 }}>
          <button onClick={() => router.push(`/sales/deals/${d.code || d.id}`)} title="Открыть карточку сделки"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 34, padding: '0 14px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>
            <DocIcon /> Карточка
          </button>
          {d.bitrix_id && !local && (
            <button onClick={() => window.open(BITRIX_DEAL_URL(d.bitrix_id), '_blank', 'noopener')} title="Открыть сделку в Битрикс24 (в новой вкладке)"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 34, padding: '0 12px', borderRadius: 10, border: '1px solid var(--accent)', background: 'var(--accent-tint)', color: 'var(--accent)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>
              Битрикс ↗
            </button>
          )}
          <button title="Бриф" onClick={() => (onOpenBrief ? onOpenBrief(d) : router.push(`/sales/deals/${d.id}`))} style={{ ...iconSq(false), width: 34, height: 34 }}><DocIcon /></button>
          {onEdit && <button title="Редактировать" onClick={() => onEdit(d)} style={{ ...iconSq(false), width: 34, height: 34 }}><EditIcon /></button>}
        </div>
      </div>
    </div>
  )
}
