import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Navbar from '@/components/Navbar'
import Head from 'next/head'
import { makeApi } from '@/lib/http'
import { getPermissions, can } from '@/lib/auth'
import { firstAllowedHref } from '@/lib/nav'
import DiadocImport from '@/components/DiadocImport'
import { card, btn, inp, CAP, MONO, UI } from '@/components/salesTableKit'

const FIELD_LABELS = {
  date: 'Дата', status: 'Статус', income: 'Доход', expense: 'Расход', bank: 'Банк',
  period: 'Период', vat_rate: 'Ставка НДС', vat_fact: 'НДС факт', article: 'Статья',
  counterparty: 'Контрагент', inn: 'ИНН', invoice_date: 'Дата счёта', description: 'Описание',
  document_link: 'Ссылка на документ'
}

const fmt = (n) => n ? new Intl.NumberFormat('ru-RU').format(Math.round(n)) : '—'

const STATUS_COLORS = {
  'ОПЛАЧЕНО': { bg: '#dcfce7', color: '#16a34a' },
  'ПЛАН ОПЛАТ': { bg: '#fef9c3', color: '#d97706' },
  'ПЛАН ПОСТУПЛЕНИЙ': { bg: '#dbeafe', color: '#2563eb' },
}

const BANK_STYLES = {
  'АльфаБанк':  { bg: '#fee2e2', color: '#dc2626', border: '#fca5a5' },
  'ОПТ Банк':   { bg: '#dcfce7', color: '#16a34a', border: '#86efac' },
  'Совкомбанк': { bg: '#f3f4f6', color: '#4b5563', border: '#d1d5db' },
  'Наличные':   { bg: '#dbeafe', color: '#2563eb', border: '#93c5fd' },
}

// Те же колонки и в том же порядке, что в таблице /operations — чтобы строки
// синхронизации читались привычно, без отдельной "легенды" полей.
const SYNC_TABLE_COLUMNS = [
  { key: 'date', label: 'Дата' },
  { key: 'status', label: 'Статус' },
  { key: 'income', label: 'Поступление' },
  { key: 'expense', label: 'Списание' },
  { key: 'bank', label: 'Банк' },
  { key: 'period', label: 'Период' },
  { key: 'article', label: 'Статья' },
  { key: 'counterparty', label: 'Контрагент' },
  { key: 'inn', label: 'ИНН' },
  { key: 'vat_rate', label: 'НДС%' },
  { key: 'vat_fact', label: 'НДС сумма' },
  { key: 'ds_num', label: '№ ДС' },
  { key: 'invoice', label: '№ Счёта' },
  { key: 'invoice_date', label: 'Дата счёта' },
  { key: 'description', label: 'Описание' },
  { key: 'document_link', label: 'Документ' },
]

const syncThS = { textAlign:'left', padding:'6px 8px', color:'#6b7280', fontWeight:'500', whiteSpace:'nowrap', borderBottom:'2px solid #e5e7eb', background:'#f9fafb', position:'sticky', top:0, fontSize:'13px' }
const syncTdS = { padding:'6px 8px', whiteSpace:'nowrap', fontSize:'14px' }

function SyncCell({ col, data, highlight }) {
  const v = data ? data[col.key] : null
  const hl = highlight ? { fontWeight: '700' } : {}
  if (col.key === 'status') {
    const s = STATUS_COLORS[v] || { bg: '#f3f4f6', color: '#6b7280' }
    return v ? <span style={{ fontSize:'13px', padding:'2px 8px', borderRadius:'20px', whiteSpace:'nowrap', background:s.bg, color:s.color, ...hl }}>{v}</span> : '—'
  }
  if (col.key === 'bank') {
    if (!v) return '—'
    const s = BANK_STYLES[v] || { bg:'#f3f4f6', color:'#6b7280', border:'#d1d5db' }
    return <span style={{ fontSize:'13px', padding:'2px 8px', borderRadius:'20px', whiteSpace:'nowrap', background:s.bg, color:s.color, border:`1px solid ${s.border}`, fontWeight:'500' }}>{v}</span>
  }
  if (col.key === 'income') return v > 0 ? <span style={{ color:'#16a34a', ...hl }}>{fmt(v)}</span> : '—'
  if (col.key === 'expense') return v > 0 ? <span style={{ color:'#dc2626', ...hl }}>{fmt(v)}</span> : '—'
  if (col.key === 'vat_rate') return v > 0 ? <span style={hl}>{v}%</span> : '—'
  if (col.key === 'vat_fact') return v > 0 ? <span style={hl}>{fmt(v)}</span> : '—'
  return <span style={hl}>{v === null || v === undefined || v === '' ? '—' : String(v)}</span>
}

// Разделы экрана — строками, не колонкой карточек. Компонент объявлен на модульном
// уровне: внутри тела страницы он пересоздавался бы каждый рендер и вложенные input
// теряли бы фокус.
function Section({ title, hint, count, open, onToggle, children }) {
  return (
    <div style={{ ...card, borderRadius: 14, marginBottom: 10, overflow: 'hidden' }}>
      <div onClick={onToggle}
        style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 18px', cursor: 'pointer' }}>
        <div style={{ flex: '1 1 auto', minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, fontFamily: UI, color: 'var(--text-primary)' }}>{title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{hint}</div>
        </div>
        {count != null && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{count}</span>}
        <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{open ? '▲' : '▼'}</span>
      </div>
      {open && <div style={{ padding: '0 18px 18px', borderTop: '1px solid var(--border-card)', paddingTop: 16 }}>{children}</div>}
    </div>
  )
}

export default function Import() {
  const router = useRouter()
  const [openSec, setOpenSec] = useState({ ops: false, diadoc: false })
  const toggle = (k) => setOpenSec(s => ({ ...s, [k]: !s[k] }))

  const [syncFile, setSyncFile] = useState(null)
  const [syncLoading, setSyncLoading] = useState(false)
  const [syncError, setSyncError] = useState(null)
  const [preview, setPreview] = useState(null)
  const [checkedKeys, setCheckedKeys] = useState({})
  const [applyLoading, setApplyLoading] = useState(false)
  const [applyResult, setApplyResult] = useState(null)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { router.push('/login'); return }
    if (!can(getPermissions(), 'import', 'view')) { router.push(firstAllowedHref(getPermissions(), localStorage.getItem('role') === 'admin')); return }
  }, [])

  // Одноразовый импорт («/operations/import», всегда вставляет и на повторе плодит
  // дубли) убран из интерфейса 2026-08-20 по решению владельца: рабочий путь один —
  // синхронизация с проверкой. Эндпоинт на бэкенде намеренно оставлен, не удалён.

  const handlePreview = async () => {
    if (!syncFile) { alert('Выберите файл'); return }
    setSyncLoading(true)
    setSyncError(null)
    setPreview(null)
    setApplyResult(null)
    setCheckedKeys({})
    try {
      const token = localStorage.getItem('token')
      const formData = new FormData()
      formData.append('file', syncFile)
      const res = await makeApi(token).post('/operations/import/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setPreview(res.data)
    } catch (e) {
      setSyncError(e.response?.data?.detail || 'Ошибка проверки файла')
    } finally {
      setSyncLoading(false)
    }
  }

  const toggleKey = (key) => setCheckedKeys(prev => ({ ...prev, [key]: !prev[key] }))

  const toggleAll = (checked) => {
    if (!preview) return
    const next = {}
    preview.conflicts.forEach(c => { next[c.key] = checked })
    setCheckedKeys(next)
  }

  const handleApply = async () => {
    if (!preview) return
    const confirmed_keys = Object.keys(checkedKeys).filter(k => checkedKeys[k])
    setApplyLoading(true)
    setSyncError(null)
    try {
      const token = localStorage.getItem('token')
      const res = await makeApi(token).post('/operations/import/apply', {
        import_id: preview.import_id,
        confirmed_keys
      })
      setApplyResult(res.data)
      setPreview(null)
      setSyncFile(null)
      setCheckedKeys({})
    } catch (e) {
      setSyncError(e.response?.data?.detail || 'Ошибка применения')
    } finally {
      setApplyLoading(false)
    }
  }

  return (
    <div style={{minHeight:'100vh',background:'var(--bg)'}}>
      <Navbar active="import" />
      <Head><title>Импорт | Финансовый учёт</title></Head>

      <div style={{ padding: '24px 32px', maxWidth: 1920, margin: '0 auto' }}>
        <div style={{ ...CAP, marginBottom: 14 }}>Импорт</div>

        <Section
          title="Операции из Excel"
          hint="Сверка по № ДС и № счёта: новые строки добавляются сами, изменения — только те, что подтвердите"
          open={openSec.ops} onToggle={() => toggle('ops')}>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <input type="file" accept=".xlsx,.xls" id="syncFileInput" style={{ display: 'none' }}
              onChange={e => setSyncFile(e.target.files[0])} />
            <label htmlFor="syncFileInput"
              style={{ ...inp, cursor: 'pointer', borderStyle: 'dashed', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {syncFile ? syncFile.name : 'Выбрать xlsx'}
            </label>
            <button onClick={handlePreview} disabled={syncLoading || !syncFile}
              style={{ ...btn(true), opacity: (syncLoading || !syncFile) ? .5 : 1 }}>
              {syncLoading ? 'Проверяем…' : 'Проверить'}
            </button>
            {syncError && <span style={{ fontSize: 12, color: 'var(--danger)' }}>✗ {syncError}</span>}
            {applyResult && <span style={{ fontSize: 12, color: 'var(--income)' }}>✓ {applyResult.message}</span>}
          </div>

          {preview && (
            <div style={{marginTop:'20px'}}>
              <div style={{display:'flex',gap:'12px',marginBottom:'16px',fontSize:'15px',flexWrap:'wrap'}}>
                <div style={{padding:'8px 12px',borderRadius:'8px',background:'#dcfce7',color:'var(--success)'}}>Новых: {preview.summary.new}</div>
                <div style={{padding:'8px 12px',borderRadius:'8px',background:'#fef9c3',color:'#854d0e'}}>Конфликтов: {preview.summary.conflict}</div>
                <div style={{padding:'8px 12px',borderRadius:'8px',background:'var(--bg)',color:'var(--muted)'}}>Без изменений: {preview.summary.unchanged}</div>
              </div>

              {preview.conflicts.length > 0 && (
                <div style={{marginBottom:'24px'}}>
                  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'8px'}}>
                    <div style={{fontWeight:'500',fontSize:'15px'}}>
                      Конфликты — отметь строки для перезаписи (
                      <span style={{color:'#dc2626',fontWeight:'700'}}>было</span> / <span style={{color:'#16a34a',fontWeight:'700'}}>станет</span>, изменившиеся поля выделены жирным)
                    </div>
                    <label style={{fontSize:'14px',color:'var(--muted)',cursor:'pointer',display:'flex',alignItems:'center',gap:'4px'}}>
                      <input type="checkbox" onChange={e => toggleAll(e.target.checked)} /> Выбрать все
                    </label>
                  </div>
                  <div style={{maxHeight:'560px',overflow:'auto',border:'1px solid var(--border)',borderRadius:'8px'}}>
                    <table style={{width:'100%',borderCollapse:'collapse'}}>
                      <thead>
                        <tr>
                          <th style={{...syncThS,width:'32px'}}></th>
                          <th style={{...syncThS,width:'52px'}}></th>
                          {SYNC_TABLE_COLUMNS.map(col => <th key={col.key} style={syncThS}>{col.label}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.conflicts.map((c) => ([
                          <tr key={c.key + '-old'} style={{background:'#fef2f2'}}>
                            <td rowSpan={2} style={{...syncTdS,textAlign:'center',verticalAlign:'middle'}}>
                              <input type="checkbox" checked={!!checkedKeys[c.key]} onChange={() => toggleKey(c.key)} />
                            </td>
                            <td style={{...syncTdS,fontSize:'13px',fontWeight:'700',color:'#dc2626'}}>было</td>
                            {SYNC_TABLE_COLUMNS.map(col => (
                              <td key={col.key} style={syncTdS}>
                                <SyncCell
                                  col={col}
                                  data={(col.key === 'ds_num' || col.key === 'invoice') ? c.incoming : c.existing}
                                  highlight={c.diff_fields.includes(col.key)}
                                />
                              </td>
                            ))}
                          </tr>,
                          <tr key={c.key + '-new'} style={{background:'#f0fdf4',borderBottom:'2px solid var(--border)'}}>
                            <td style={{...syncTdS,fontSize:'13px',fontWeight:'700',color:'#16a34a'}}>станет</td>
                            {SYNC_TABLE_COLUMNS.map(col => (
                              <td key={col.key} style={syncTdS}>
                                <SyncCell col={col} data={c.incoming} highlight={c.diff_fields.includes(col.key)} />
                              </td>
                            ))}
                          </tr>
                        ]))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {preview.new_rows.length > 0 && (
                <div style={{marginBottom:'8px'}}>
                  <div style={{fontWeight:'500',fontSize:'15px',marginBottom:'8px'}}>
                    Новые операции ({preview.new_rows.length}) — добавятся автоматически
                  </div>
                  <div style={{maxHeight:'400px',overflow:'auto',border:'1px solid var(--border)',borderRadius:'8px'}}>
                    <table style={{width:'100%',borderCollapse:'collapse'}}>
                      <thead>
                        <tr>
                          {SYNC_TABLE_COLUMNS.map(col => <th key={col.key} style={syncThS}>{col.label}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.new_rows.map((r, i) => (
                          <tr key={i} style={{background:'#f0fdf4',borderBottom:'1px solid var(--border)'}}>
                            {SYNC_TABLE_COLUMNS.map(col => (
                              <td key={col.key} style={syncTdS}><SyncCell col={col} data={r} /></td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <button onClick={handleApply} disabled={applyLoading}
                style={{ ...btn(true), marginTop: 16, opacity: applyLoading ? .5 : 1 }}>
                {applyLoading ? 'Применяем…' : 'Перепровести'}
              </button>
            </div>
          )}
        </Section>

        <Section
          title="Документы из Диадока"
          hint="Реестр из Диадока привязывается к операциям по ИНН и номеру счёта; ссылка на документ строится сама"
          open={openSec.diadoc} onToggle={() => toggle('diadoc')}>
          <DiadocImport />
        </Section>
      </div>
    </div>
  )
}
