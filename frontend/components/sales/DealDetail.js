import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import api, { auth } from '../../lib/api'
import { MONO, UI, CAP, docCard, addBtn, iconSq, DocIcon, DownloadIcon, EditIcon, StageLayerBar } from '../salesTableKit'

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

// Скачивание blob по URL (файлы сделки, PDF/XLS медиаплана).
async function blobGet(url, filename) {
  try {
    const r = await api.get(url, { ...auth(), responseType: 'blob' })
    const href = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = href; a.download = filename || 'file'; a.click(); URL.revokeObjectURL(href)
  } catch { alert('Не удалось скачать файл') }
}

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
  const addMp = () => router.push(`/deals/mp/new?deal=${d.id}`)
  // Прочие документы (ДС/Отчёт/УПД/Счёт): пока просто форма выбора файла (бэка под эти типы нет).
  const [picked, setPicked] = useState({})
  const pickFile = (kind) => {
    const inp = document.createElement('input')
    inp.type = 'file'
    inp.onchange = () => { const f = inp.files && inp.files[0]; if (f) setPicked(p => ({ ...p, [kind]: f.name })) }
    inp.click()
  }
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
        <Row label="Плательщик">{d.payer || '—'}</Row>
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
              <button style={iconSq(true)} title="Открыть конструктор" onClick={() => router.push(`/deals/mp/${mpOur.id}`)}><EditIcon /></button>
            </span>
          ) : undefined} />
        {/* Реализация: бэка под эти типы ещё нет — «+ Добавить» открывает форму выбора файла */}
        {[['ДС', 'ds'], ['Отчёт', 'report'], ['УПД', 'upd'], ['Счёт', 'invoice']].map(([t, k]) => (
          <DocLine key={k} title={t} empty={!picked[k]} meta={picked[k] ? `выбран: ${picked[k]}` : ''}
            onAdd={canEdit ? () => pickFile(k) : undefined} addLabel={picked[k] ? 'Заменить' : '+ Добавить'} />
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

      {/* 4. Стадия (бар 2\2\2 во всю ширину) + Оплаты */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={CAP}>Стадия</div>
        <div style={{ marginBottom: 18 }}>
          <StageLayerBar os={d.our_stage} full h={16} />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, display: 'flex', gap: 6 }}>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{d.our_stage?.name || '—'}</span>
            {d.our_stage?.money_layer && <span style={{ fontFamily: MONO, color: 'var(--text-faint)' }}>· {d.our_stage.money_layer}</span>}
          </div>
        </div>
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
          <button onClick={() => router.push(`/deals/${d.id}`)} title="Открыть карточку сделки"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 34, padding: '0 14px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: UI }}>
            <DocIcon /> Карточка
          </button>
          <button title="Бриф" onClick={() => (onOpenBrief ? onOpenBrief(d) : router.push(`/deals/${d.id}`))} style={{ ...iconSq(false), width: 34, height: 34 }}><DocIcon /></button>
          {onEdit && <button title="Редактировать" onClick={() => onEdit(d)} style={{ ...iconSq(false), width: 34, height: 34 }}><EditIcon /></button>}
        </div>
      </div>
    </div>
  )
}
