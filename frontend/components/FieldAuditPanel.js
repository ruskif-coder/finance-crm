import { useState, useEffect, useMemo } from 'react'
import { MONO, UI } from './salesTableKit'
import { makeApi } from '../lib/http'
import { T } from '../lib/tokens'

const api = () => makeApi(typeof window !== 'undefined' ? localStorage.getItem('token') : '')

const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 18, boxShadow: 'var(--shadow-card)' }
const lbl = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const inp = { width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)', borderRadius: 10, padding: '8px 11px', fontSize: 13, background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none', fontFamily: UI }
const btnPrimary = { background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '8px 14px', fontFamily: MONO, fontSize: 12, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }
const btnLink = { border: '1px solid var(--border-card)', background: 'var(--bg-card)', borderRadius: 10, padding: '8px 12px', fontSize: 12, fontWeight: 600, color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap' }

// ── одна карточка (сделка ИЛИ компания) ──────────────────────────
function AuditCard({ mode }) {                       // mode: 'deal' | 'company'
  const [kind, setKind] = useState('agency')          // для компании
  const [q, setQ] = useState('')
  const [opts, setOpts] = useState([])                // результаты пикера
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState(null)          // { id, label, bx_id? }
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [bxSearch, setBxSearch] = useState('')

  // загрузка вариантов пикера
  useEffect(() => {
    let alive = true
    const run = async () => {
      try {
        if (mode === 'deal') {
          if (!q.trim()) { setOpts([]); return }
          const r = await api().get(`/sales/deals?search=${encodeURIComponent(q.trim())}&limit=20`)
          if (alive) setOpts((r.data.items || []).map(d => ({ id: d.id, bx_id: d.bitrix_id, label: `${d.bitrix_id} · ${d.advertiser || d.agency || d.title || ''}`.trim() })))
        } else {
          const r = await api().get(`/sales/${kind === 'agency' ? 'agencies' : 'advertisers'}`)
          const items = (r.data.items || []).filter(a => a.bx_id).map(a => ({ id: a.id, bx_id: a.bx_id, label: a.short_name || a.name || a.full_name }))
          const f = q.trim().toLowerCase()
          if (alive) setOpts(f ? items.filter(o => o.label.toLowerCase().includes(f)) : items.slice(0, 50))
        }
      } catch (e) { if (alive) setOpts([]) }
    }
    const t = setTimeout(run, mode === 'deal' ? 300 : 0)
    return () => { alive = false; clearTimeout(t) }
  }, [q, mode, kind])

  const fetchAudit = async (p) => {
    const sel = p || picked
    if (!sel) return
    setLoading(true); setErr(''); setData(null)
    try {
      const url = mode === 'deal' ? `/sales/field-audit/deal/${sel.id}` : `/sales/field-audit/company/${kind}/${sel.id}`
      const r = await api().get(url)
      setData(r.data)
    } catch (e) { setErr(e.response?.data?.detail || 'Не удалось прочитать карточку') }
    finally { setLoading(false) }
  }

  const pick = (o) => { setPicked(o); setQ(o.label); setOpen(false); fetchAudit(o) }

  const bxMap = useMemo(() => Object.fromEntries((data?.bitrix || []).map(b => [b.code, b.value])), [data])
  const bxRows = useMemo(() => {
    const f = bxSearch.trim().toLowerCase()
    return (data?.bitrix || []).filter(b => !f || b.code.toLowerCase().includes(f) || String(b.value || '').toLowerCase().includes(f))
  }, [data, bxSearch])

  return (
    <div style={{ ...CARD, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      {/* заголовок карточки */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>{mode === 'deal' ? 'Сделка' : 'Компания'}</span>
        {mode === 'company' && (
          <div style={{ display: 'flex', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10, padding: 3 }}>
            {[['advertiser', 'Рекламодатель'], ['agency', 'Агентство']].map(([k, l]) => (
              <button key={k} onClick={() => { setKind(k); setPicked(null); setData(null); setQ('') }}
                style={{ border: 'none', borderRadius: 7, padding: '5px 11px', cursor: 'pointer', fontFamily: MONO, fontSize: 11, fontWeight: kind === k ? 700 : 600, background: kind === k ? 'var(--accent-tint)' : 'transparent', color: kind === k ? 'var(--accent)' : 'var(--text-secondary)' }}>{l}</button>
            ))}
          </div>
        )}
        {data && <a href={data.bitrix_url} target="_blank" rel="noreferrer" style={{ ...btnLink, marginLeft: 'auto' }}>Битрикс ↗</a>}
        <button onClick={() => fetchAudit()} disabled={!picked || loading} style={{ ...btnPrimary, marginLeft: data ? 0 : 'auto', opacity: (!picked || loading) ? 0.5 : 1 }}>
          {loading ? 'Чтение…' : '⟳ Обновить структуру'}
        </button>
      </div>

      {/* пикер */}
      <div style={{ position: 'relative' }}>
        <span style={{ ...lbl, display: 'block', marginBottom: 5 }}>{mode === 'deal' ? 'Сделка из базы (поиск по BX_ID / рекламодателю)' : 'Выбор из базы'}</span>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
          placeholder={mode === 'deal' ? 'начните вводить…' : 'поиск…'} style={inp} />
        {open && opts.length > 0 && (
          <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 30, marginTop: 4, maxHeight: 260, overflowY: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, boxShadow: 'var(--shadow-card)', padding: 5 }}>
            {opts.map(o => (
              <div key={o.id} onClick={() => pick(o)} style={{ padding: '7px 9px', borderRadius: 7, fontSize: 12.5, cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>{o.label}</div>
            ))}
          </div>
        )}
      </div>

      {err && <div style={{ background: 'var(--danger-tint)', color: T.danger, borderRadius: 10, padding: '8px 12px', fontSize: 12.5 }}>{err}</div>}

      {data && (
        <>
          {/* наши поля ↔ значение из Битрикса по известному коду */}
          <div>
            <div style={{ ...lbl, marginBottom: 8 }}>Наши поля · сопоставление</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1.3fr 1.2fr', gap: 0, fontSize: 12.5, border: '1px solid var(--border-inner)', borderRadius: 10, overflow: 'hidden' }}>
              <HeadCell>Поле у нас</HeadCell><HeadCell>Наше значение</HeadCell><HeadCell>Код и значение BX</HeadCell>
              {data.our.map((f, i) => {
                const known = !!f.bx_code
                const bxVal = known ? bxMap[f.bx_code] : undefined
                return (
                  <RowCells key={f.field} striped={i % 2 === 1}>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{f.label}</span>
                    <span style={{ color: 'var(--text-secondary)', wordBreak: 'break-word' }}>{f.value ?? <span style={{ color: 'var(--text-faint)' }}>—</span>}</span>
                    <span style={{ minWidth: 0 }}>
                      {known ? (
                        <>
                          <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--accent)', background: 'var(--accent-tint)', borderRadius: 5, padding: '1px 5px' }}>{f.bx_code}</span>
                          <div style={{ marginTop: 3, color: bxVal != null ? 'var(--text-secondary)' : 'var(--text-faint)', wordBreak: 'break-word' }}>{bxVal != null ? bxVal : 'нет в payload'}</div>
                        </>
                      ) : (
                        <span title="Код не опознан — найдите совпадение в полном списке BX ниже" style={{ fontFamily: MONO, fontSize: 10.5, color: T.warningText, background: 'var(--warning-tint)', borderRadius: 5, padding: '1px 5px' }}>❓ опознать</span>
                      )}
                    </span>
                  </RowCells>
                )
              })}
            </div>
          </div>

          {/* полный payload Битрикса */}
          <details>
            <summary style={{ cursor: 'pointer', ...lbl, marginBottom: 8, listStyle: 'none' }}>▸ Все поля Битрикса ({data.bitrix.length}) — для опознания ❓</summary>
            <input value={bxSearch} onChange={e => setBxSearch(e.target.value)} placeholder="фильтр по коду или значению…" style={{ ...inp, margin: '8px 0' }} />
            <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid var(--border-inner)', borderRadius: 10 }}>
              {bxRows.map((b, i) => (
                <div key={b.code} style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: 10, padding: '6px 10px', fontSize: 12, background: i % 2 ? 'var(--bg-subtle)' : 'transparent', borderBottom: '1px solid var(--border-row)' }}>
                  <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-primary)', wordBreak: 'break-all' }}>{b.code}</span>
                  <span style={{ color: 'var(--text-secondary)', wordBreak: 'break-word' }}>{b.value ?? <span style={{ color: 'var(--text-faint)' }}>—</span>}</span>
                </div>
              ))}
              {!bxRows.length && <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)' }}>ничего не найдено</div>}
            </div>
          </details>
        </>
      )}

      {!data && !err && <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-faint)', fontSize: 13 }}>Выберите {mode === 'deal' ? 'сделку' : 'компанию'} из базы для сверки</div>}
    </div>
  )
}

const HeadCell = ({ children }) => (
  <div style={{ ...lbl, padding: '7px 10px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>{children}</div>
)
const RowCells = ({ children, striped }) => (
  <>{children.map((c, i) => <div key={i} style={{ padding: '8px 10px', background: striped ? 'var(--bg-subtle)' : 'transparent', borderBottom: '1px solid var(--border-row)', minWidth: 0 }}>{c}</div>)}</>
)

export default function FieldAuditPanel() {
  return (
    <div style={{ fontFamily: UI }}>
      <div style={{ marginBottom: 14, fontSize: 13, color: 'var(--text-muted)' }}>
        Сверка структуры полей нашей системы с живой карточкой Битрикса. Выберите конкретную запись — увидите наши поля рядом с реальными кодами и значениями Битрикса. «⟳ Обновить структуру» перечитывает карточку из Битрикса. Поля с меткой <span style={{ fontFamily: MONO, fontSize: 11, color: T.warningText, background: 'var(--warning-tint)', borderRadius: 5, padding: '1px 5px' }}>❓ опознать</span> — код в Битриксе ещё не сопоставлен; найдите его в полном списке.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
        <AuditCard mode="deal" />
        <AuditCard mode="company" />
      </div>
    </div>
  )
}
