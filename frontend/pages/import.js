import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

function getPermissions() {
  if (typeof window === 'undefined') return {}
  try { return JSON.parse(localStorage.getItem('permissions') || '{}') } catch (e) { return {} }
}

const can = (perms, section, action = 'view') => !!(perms && perms[section] && perms[section][action])

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

export default function Import() {
  const router = useRouter()
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

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
    if (!can(getPermissions(), 'import', 'view')) { router.push('/dashboard'); return }
  }, [])

  const handleImport = async () => {
    if (!file) { alert('Выберите файл'); return }
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const token = localStorage.getItem('token')
      const formData = new FormData()
      formData.append('file', file)
      const res = await axios.post('http://localhost:8000/api/operations/import', formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      })
      setResult(res.data.message)
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка импорта')
    } finally {
      setLoading(false)
    }
  }

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
      const res = await axios.post('http://localhost:8000/api/operations/import/preview', formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
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
      const res = await axios.post('http://localhost:8000/api/operations/import/apply', {
        import_id: preview.import_id,
        confirmed_keys
      }, { headers: { Authorization: `Bearer ${token}` } })
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
      <div style={{background:'var(--card)',borderBottom:'1px solid var(--border)',padding:'0 32px',display:'flex',alignItems:'center',justifyContent:'space-between',height:'56px'}}>
        <div style={{fontWeight:'600',fontSize:'18px'}}>Импорт данных</div>
        <button onClick={() => router.push('/dashboard')} style={{fontSize:'15px',padding:'6px 14px',borderRadius:'8px',border:'1px solid var(--border)',background:'transparent',cursor:'pointer'}}>← Дашборд</button>
      </div>

      <div style={{padding:'24px 32px'}}>
        <div style={{maxWidth:'600px'}}>
        <div style={{background:'var(--card)',borderRadius:'12px',padding:'24px'}}>
          <div style={{fontWeight:'500',marginBottom:'8px'}}>Импорт из Excel</div>
          <div style={{fontSize:'15px',color:'var(--muted)',marginBottom:'24px'}}>
            Загрузи файл Excel с листом "CF BEST". Система автоматически создаст статьи, контрагентов и загрузит все операции.
          </div>

          <div style={{border:'2px dashed var(--border)',borderRadius:'12px',padding:'32px',textAlign:'center',marginBottom:'16px',background:'var(--bg)'}}>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={e => setFile(e.target.files[0])}
              style={{display:'none'}}
              id="fileInput"
            />
            <label htmlFor="fileInput" style={{cursor:'pointer'}}>
              <div style={{fontSize:'34px',marginBottom:'8px'}}>📂</div>
              <div style={{fontSize:'16px',fontWeight:'500',marginBottom:'4px'}}>
                {file ? file.name : 'Нажми чтобы выбрать файл'}
              </div>
              <div style={{fontSize:'14px',color:'var(--muted)'}}>xlsx, xls</div>
            </label>
          </div>

          <button
            onClick={handleImport}
            disabled={loading || !file}
            style={{width:'100%',padding:'12px',borderRadius:'8px',border:'none',
              background: loading || !file ? 'var(--border)' : 'var(--primary)',
              color: loading || !file ? 'var(--muted)' : 'white',
              cursor: loading || !file ? 'default' : 'pointer',
              fontSize:'16px',fontWeight:'500'}}
          >
            {loading ? 'Импортируем...' : 'Загрузить'}
          </button>

          {result && (
            <div style={{marginTop:'16px',padding:'12px 16px',borderRadius:'8px',background:'#dcfce7',color:'var(--success)',fontSize:'15px'}}>
              ✓ {result}
            </div>
          )}
          {error && (
            <div style={{marginTop:'16px',padding:'12px 16px',borderRadius:'8px',background:'#fee2e2',color:'var(--danger)',fontSize:'15px'}}>
              ✗ {error}
            </div>
          )}
        </div>

        <div style={{background:'var(--card)',borderRadius:'12px',padding:'24px',marginTop:'16px'}}>
          <div style={{fontWeight:'500',marginBottom:'12px'}}>Что происходит при импорте</div>
          {[
            'Читается лист "CF BEST" из твоего файла',
            'Автоматически создаются все статьи расходов',
            'Автоматически создаются все контрагенты',
            'Загружаются все операции с января 2025',
            'При повторном импорте создаются дубликаты — для повторной загрузки используй блок «Синхронизация» ниже',
          ].map((s,i) => (
            <div key={i} style={{display:'flex',gap:'8px',padding:'6px 0',fontSize:'15px',color:'var(--muted)'}}>
              <span style={{color:'var(--success)'}}>✓</span>{s}
            </div>
          ))}
        </div>
        </div>

        <div style={{background:'var(--card)',borderRadius:'12px',padding:'24px',marginTop:'16px'}}>
          <div style={{fontWeight:'500',marginBottom:'8px'}}>Синхронизация (с проверкой)</div>
          <div style={{maxWidth:'600px'}}>
          <div style={{fontSize:'15px',color:'var(--muted)',marginBottom:'24px'}}>
            Временное решение на время, пока система не переехала на сервер: загрузи актуальный файл из Google Таблицы —
            система сама найдёт совпадения по № ДС + № Счёта, покажет что изменилось, и обновит только то, что ты подтвердишь.
            Новые строки добавляются автоматически, неизменные пропускаются.
          </div>

          <div style={{border:'2px dashed var(--border)',borderRadius:'12px',padding:'32px',textAlign:'center',marginBottom:'16px',background:'var(--bg)'}}>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={e => setSyncFile(e.target.files[0])}
              style={{display:'none'}}
              id="syncFileInput"
            />
            <label htmlFor="syncFileInput" style={{cursor:'pointer'}}>
              <div style={{fontSize:'34px',marginBottom:'8px'}}>🔄</div>
              <div style={{fontSize:'16px',fontWeight:'500',marginBottom:'4px'}}>
                {syncFile ? syncFile.name : 'Нажми чтобы выбрать файл'}
              </div>
              <div style={{fontSize:'14px',color:'var(--muted)'}}>xlsx, xls</div>
            </label>
          </div>

          <button
            onClick={handlePreview}
            disabled={syncLoading || !syncFile}
            style={{width:'100%',padding:'12px',borderRadius:'8px',border:'none',
              background: syncLoading || !syncFile ? 'var(--border)' : 'var(--primary)',
              color: syncLoading || !syncFile ? 'var(--muted)' : 'white',
              cursor: syncLoading || !syncFile ? 'default' : 'pointer',
              fontSize:'16px',fontWeight:'500'}}
          >
            {syncLoading ? 'Проверяем...' : 'Проверить'}
          </button>

          {syncError && (
            <div style={{marginTop:'16px',padding:'12px 16px',borderRadius:'8px',background:'#fee2e2',color:'var(--danger)',fontSize:'15px'}}>
              ✗ {syncError}
            </div>
          )}
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

              <div style={{maxWidth:'600px'}}>
              <button
                onClick={handleApply}
                disabled={applyLoading}
                style={{width:'100%',padding:'12px',borderRadius:'8px',border:'none',marginTop:'16px',
                  background: applyLoading ? 'var(--border)' : 'var(--primary)',
                  color: applyLoading ? 'var(--muted)' : 'white',
                  cursor: applyLoading ? 'default' : 'pointer',
                  fontSize:'16px',fontWeight:'500'}}
              >
                {applyLoading ? 'Применяем...' : 'Перепровести'}
              </button>
              </div>
            </div>
          )}

          {applyResult && (
            <div style={{marginTop:'16px',padding:'12px 16px',borderRadius:'8px',background:'#dcfce7',color:'var(--success)',fontSize:'15px'}}>
              ✓ {applyResult.message}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}