import { useState } from 'react'
import { makeApi } from '@/lib/http'
import { card, btn, inp, sel, th, td, MONO, UI } from '@/components/salesTableKit'
import { fmtDateFull } from '@/lib/salesFormat'

// Импорт реестра документов Диадока (ручная выгрузка CSV из веб-интерфейса).
// Бэкенд: app/routers/diadoc.py — матч по ИНН + номеру счёта, слабое правило по сумме
// уходит в очередь на подтверждение.
// Внешнюю карточку и заголовок рисует страница /finance/import, здесь только содержимое.

const money = (n) => n == null ? '—' : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)

const STATE_META = {
  auto:      { label: 'Привяжутся сами',      tone: 'var(--income)',       hint: 'ИНН, номер счёта и сумма совпали' },
  combo:     { label: 'Несколько счетов на один платёж', tone: 'var(--accent)', hint: 'Сумма документов в наборе равна сумме операции — привяжутся все сразу' },
  queue:     { label: 'На подтверждение',     tone: 'var(--dot-current-dz)', hint: 'Совпадение слабее: только сумма в окне дат либо сумма разошлась' },
  ambiguous: { label: 'Несколько кандидатов', tone: 'var(--accent)',       hint: 'Под условие подходит больше одной операции — выберите нужную' },
  none:      { label: 'Операции не нашлось',  tone: 'var(--text-faint)',   hint: 'Счёт выставлен, платежа в базе нет либо он вне контрольного периода' },
  already:   { label: 'Уже привязаны',        tone: 'var(--text-muted)',   hint: 'Загружались раньше — повторный импорт их не трогает' },
}
const ORDER = ['auto', 'combo', 'queue', 'ambiguous', 'none', 'already']

const opAmount = (o) => o ? ((o.income > 0 ? o.income : o.expense) || 0) : 0

const chip = (tone) => ({
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 11px', borderRadius: 20,
  border: '1px solid var(--border-card)', background: 'var(--bg-card)',
  fontFamily: MONO, fontSize: 11, letterSpacing: '.04em', color: tone, whiteSpace: 'nowrap',
})

export default function DiadocImport() {
  const [file, setFile] = useState(null)
  const [direction, setDirection] = useState('outgoing')
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  // document_id -> operation_id. Отсутствие ключа = строка не выбрана.
  const [picked, setPicked] = useState({})
  const [open, setOpen] = useState({ auto: false, queue: true, ambiguous: true, none: false, already: false })
  const [loadUnlinked, setLoadUnlinked] = useState(true)

  const runPreview = async () => {
    if (!file) return
    setLoading(true); setError(null); setResult(null); setPreview(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await makeApi(localStorage.getItem('token'))
        .post(`/diadoc/import/preview?direction=${direction}`, fd)
      const init = {}
      for (const r of res.data.rows) {
        if (r.state === 'auto' && r.candidates.length) init[r.document_id] = r.candidates[0].id
      }
      // Набор «несколько счетов на один платёж» отмечается целиком: смысл склейки
      // теряется, если привязать половину документов.
      for (const c of (res.data.combos || [])) {
        for (const did of c.document_ids) init[did] = c.operation.id
      }
      setPicked(init)
      setPreview(res.data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Не удалось разобрать файл')
    } finally { setLoading(false) }
  }

  const apply = async () => {
    if (!preview) return
    setApplying(true); setError(null)
    try {
      const rows = []
      for (const r of preview.rows) {
        if (r.state === 'already') continue
        const opId = picked[r.document_id]
        if (!opId && !loadUnlinked) continue
        rows.push({
          document_id: r.document_id, box_id: r.box_id, letter_id: r.letter_id,
          doc_type: r.doc_type, number: r.number, number_norm: r.number_norm,
          doc_date: r.doc_date, total: r.total, vat: r.vat,
          counterparty_inn: r.counterparty_inn, counterparty_kpp: r.counterparty_kpp,
          counterparty_name: r.counterparty_name, status: r.status,
          file_name: r.file_name, link: r.link, comment: r.comment,
          operation_id: opId || null,
          match_rule: !opId ? 'manual'
            : r.state === 'combo' ? 'combo'
            : (r.state === 'none' || r.rule === 'ambiguous') ? 'manual'
            : r.rule,
        })
      }
      const res = await makeApi(localStorage.getItem('token'))
        .post('/diadoc/import/apply', { direction: preview.direction, rows })
      setResult(res.data)
      setPreview(null); setFile(null); setPicked({})
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка применения')
    } finally { setApplying(false) }
  }

  const groups = {}
  if (preview) for (const r of preview.rows) (groups[r.state] = groups[r.state] || []).push(r)
  const willLink = Object.values(picked).filter(Boolean).length

  // Справочник операций, встреченных где угодно в ответе: кандидаты, подсказки и наборы.
  // Нужен, чтобы посчитать сумму склейки для операции, выбранной вручную.
  const opIndex = {}
  const docById = {}
  if (preview) {
    for (const r of preview.rows) {
      docById[r.document_id] = r
      for (const c of (r.candidates || [])) opIndex[c.id] = c
      for (const c of (r.near || [])) opIndex[c.id] = c
    }
    for (const c of (preview.combos || [])) opIndex[c.operation.id] = c.operation
  }

  // Склейка = операция, которой досталось больше одного документа. Показываем сумму
  // операции против суммы документов: расхождение здесь — единственный способ понять,
  // что набор собран неверно.
  const glued = []
  if (preview) {
    const byOp = {}
    for (const [did, opId] of Object.entries(picked)) {
      if (opId) (byOp[opId] = byOp[opId] || []).push(did)
    }
    for (const [opId, dids] of Object.entries(byOp)) {
      if (dids.length < 2) continue
      const op = opIndex[opId]
      const total = dids.reduce((s, d) => s + (docById[d]?.total || 0), 0)
      glued.push({ op, opId, dids, total: Math.round(total * 100) / 100,
                   diff: Math.round((opAmount(op) - total) * 100) / 100 })
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <input type="file" accept=".csv" id="diadocFile" style={{ display: 'none' }}
          onChange={e => { setFile(e.target.files[0]); setPreview(null); setResult(null) }} />
        <label htmlFor="diadocFile"
          style={{ ...inp, cursor: 'pointer', borderStyle: 'dashed', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {file ? file.name : 'Выбрать CSV'}
        </label>
        <select value={direction} onChange={e => { setDirection(e.target.value); setPreview(null) }} style={{ ...sel, width: 380 }}>
          <option value="outgoing">Исходящие — наши счета, ищем поступления</option>
          <option value="incoming">Входящие — счета контрагентов, ищем списания</option>
        </select>
        <button onClick={runPreview} disabled={!file || loading} style={{ ...btn(true), opacity: (!file || loading) ? .5 : 1 }}>
          {loading ? 'Разбираем…' : 'Проверить'}
        </button>
        {error && <span style={{ fontSize: 12, color: 'var(--danger)' }}>✗ {error}</span>}
        {result && (
          <span style={{ fontSize: 12, color: 'var(--income)' }}>
            ✓ новых {result.created_documents}, обновлено {result.updated_documents}, привязок {result.created_links}
          </span>
        )}
      </div>

      {preview && (
        <>
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', margin: '14px 0 12px' }}>
            {ORDER.filter(s => groups[s]?.length).map(s => (
              <span key={s} title={STATE_META[s].hint} style={chip(STATE_META[s].tone)}>
                {STATE_META[s].label} · {groups[s].length}
              </span>
            ))}
            {preview.counts.skipped_status > 0 && (
              <span title={'Не грузим: ' + preview.skipped_statuses.join(', ')} style={chip('var(--text-faint)')}>
                Отсеяно по статусу · {preview.counts.skipped_status}
              </span>
            )}
          </div>

          {ORDER.filter(s => groups[s]?.length).map(s => (
            <Group key={s} state={s} rows={groups[s]} open={!!open[s]}
              onToggle={() => setOpen(o => ({ ...o, [s]: !o[s] }))}
              picked={picked} setPicked={setPicked} />
          ))}

          {glued.length > 0 && (
            <div style={{ ...card, borderRadius: 12, padding: '12px 14px', marginTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, fontFamily: UI, marginBottom: 10 }}>
                Склейки — по нескольку документов на одну операцию
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={th}>Операция</th>
                    <th style={{ ...th, textAlign: 'right' }}>Сумма операции</th>
                    <th style={{ ...th, textAlign: 'right' }}>Документов</th>
                    <th style={{ ...th, textAlign: 'right' }}>Сумма документов</th>
                    <th style={{ ...th, textAlign: 'right' }}>Разница</th>
                  </tr>
                </thead>
                <tbody>
                  {glued.map(g => (
                    <tr key={g.opId}>
                      <td style={td}><OpLine c={g.op} /></td>
                      <td style={{ ...td, fontFamily: MONO, textAlign: 'right' }}>{money(opAmount(g.op))}</td>
                      <td style={{ ...td, fontFamily: MONO, textAlign: 'right' }}>{g.dids.length}</td>
                      <td style={{ ...td, fontFamily: MONO, textAlign: 'right' }}>{money(g.total)}</td>
                      <td style={{ ...td, fontFamily: MONO, textAlign: 'right', fontWeight: 700,
                                   color: g.diff === 0 ? 'var(--income)' : 'var(--dot-current-dz)' }}>
                        {g.diff === 0 ? 'сошлось' : money(g.diff)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginTop: 14 }}>
            <button onClick={apply} disabled={applying} style={{ ...btn(true), opacity: applying ? .5 : 1 }}>
              {applying ? 'Применяем…' : `Применить · привязок ${willLink}`}
            </button>
            <label style={{ display: 'flex', gap: 7, alignItems: 'center', fontSize: 12, color: 'var(--text-muted)', fontFamily: UI, cursor: 'pointer' }}>
              <input type="checkbox" checked={loadUnlinked} onChange={e => setLoadUnlinked(e.target.checked)} />
              грузить и непривязанные — тогда повторный импорт не создаст дублей,
              а строки «операции не нашлось» станут отчётом о дырах
            </label>
          </div>
        </>
      )}
    </div>
  )
}

// Объявлено на модульном уровне: компонент оборачивает input, внутри тела страницы
// он пересоздавался бы каждый рендер и фокус слетал бы после каждого клика.
function Group({ state, rows, open, onToggle, picked, setPicked }) {
  const meta = STATE_META[state]
  return (
    <div style={{ ...card, borderRadius: 12, marginBottom: 8, overflow: 'hidden' }}>
      <div onClick={onToggle}
        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', cursor: 'pointer' }}>
        <span style={{ width: 7, height: 7, borderRadius: 4, background: meta.tone, flex: '0 0 auto' }} />
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', fontFamily: UI }}>{meta.label}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', flex: '1 1 auto', minWidth: 0 }}>{meta.hint}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>{rows.length} {open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{ maxHeight: 420, overflow: 'auto', borderTop: '1px solid var(--border-card)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ ...th, width: 34, paddingTop: 10 }}></th>
                <th style={{ ...th, paddingTop: 10 }}>Счёт</th>
                <th style={{ ...th, paddingTop: 10 }}>Дата</th>
                <th style={{ ...th, paddingTop: 10, textAlign: 'right' }}>Сумма</th>
                <th style={{ ...th, paddingTop: 10 }}>Контрагент</th>
                <th style={{ ...th, paddingTop: 10 }}>Операция</th>
                <th style={{ ...th, width: 36, paddingTop: 10 }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const chosen = picked[r.document_id]
                const single = r.candidates.length === 1
                return (
                  <tr key={r.document_id}>
                    <td style={{ ...td, textAlign: 'center' }}>
                      {state !== 'already' && (single || chosen) && (
                        <input type="checkbox" checked={!!chosen}
                          onChange={e => setPicked(p => {
                            const n = { ...p }
                            if (e.target.checked && single) n[r.document_id] = r.candidates[0].id
                            else delete n[r.document_id]
                            return n
                          })} />
                      )}
                    </td>
                    <td style={{ ...td, fontFamily: MONO }}>№ {r.number}</td>
                    <td style={{ ...td, fontFamily: MONO, color: 'var(--text-secondary)' }}>{fmtDateFull(r.doc_date)}</td>
                    <td style={{ ...td, fontFamily: MONO, textAlign: 'right' }}>{money(r.total)}</td>
                    <td style={{ ...td, maxWidth: 240, whiteSpace: 'normal' }}>
                      {r.counterparty_name}
                      {r.counterparty_known === false && (
                        <span title="Такого ИНН нет в справочнике контрагентов"
                          style={{ marginLeft: 6, color: 'var(--dot-current-dz)' }}>⚠</span>
                      )}
                      {(r.counterparty_inn || r.counterparty_kpp) && (
                        <span style={{ display: 'block', fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>
                          ИНН {r.counterparty_inn || '—'}
                          {r.counterparty_kpp ? ` · КПП ${r.counterparty_kpp}` : ''}
                        </span>
                      )}
                    </td>
                    <td style={{ ...td, whiteSpace: 'normal' }}>
                      {r.candidates.length === 0 && !r.near?.length && (
                        <span style={{ color: 'var(--text-faint)' }}>—</span>
                      )}
                      {/* Ручная склейка: документ можно повесить на любую операцию того же
                          контрагента, в том числе на ту, которой уже достался другой
                          документ — тогда внизу появится строка сверки сумм. */}
                      {r.candidates.length === 0 && r.near?.length > 0 && (
                        <select value={chosen || ''} style={{ ...sel, width: 300, padding: '4px 7px', fontSize: 12 }}
                          onChange={e => setPicked(p => {
                            const n = { ...p }
                            if (e.target.value) n[r.document_id] = Number(e.target.value)
                            else delete n[r.document_id]
                            return n
                          })}>
                          <option value="">— привязать к операции —</option>
                          {r.near.map(c => (
                            <option key={c.id} value={c.id}>
                              #{c.id} · {c.date ? fmtDateFull(c.date) : c.status} · {money(c.income > 0 ? c.income : c.expense)}
                              {c.invoice ? ` · счёт ${c.invoice}` : ''}
                            </option>
                          ))}
                        </select>
                      )}
                      {single && <OpLine c={r.candidates[0]} />}
                      {r.candidates.length > 1 && r.candidates.map(c => (
                        <label key={c.id} style={{ display: 'block', cursor: 'pointer', padding: '1px 0' }}>
                          <input type="radio" name={'c' + r.document_id} checked={chosen === c.id}
                            onChange={() => setPicked(p => ({ ...p, [r.document_id]: c.id }))}
                            style={{ marginRight: 6 }} />
                          <OpLine c={c} />
                        </label>
                      ))}
                    </td>
                    <td style={{ ...td, textAlign: 'center' }}>
                      <a href={r.link} target="_blank" rel="noreferrer" title="Открыть в Диадоке"
                        style={{ textDecoration: 'none', color: 'var(--accent)' }}>↗</a>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// Ссылка внутри <label> иначе переключала бы радиокнопку вместо перехода.
const stop = (e) => e.stopPropagation()

function OpLine({ c }) {
  if (!c) return null
  const sum = c.income > 0 ? c.income : c.expense
  return (
    <span style={{ fontSize: 12, display: 'inline-block' }}>
      <a href={`/finance/operations?op=${c.id}`} target="_blank" rel="noreferrer" onClick={stop}
        title="Открыть операцию в реестре"
        style={{ fontFamily: MONO, color: 'var(--accent)', textDecoration: 'none' }}>#{c.id} ↗</a>{' '}
      <span style={{ fontFamily: MONO }}>{c.date ? fmtDateFull(c.date) : c.status}</span>
      <span style={{ color: 'var(--text-faint)' }}> · </span>
      <span style={{ fontFamily: MONO }}>{money(sum)}</span>
      {c.invoice ? <span style={{ color: 'var(--text-faint)' }}> · счёт {c.invoice}</span> : null}
      {c.amount_mismatch != null && (
        <span title="Сумма операции отличается от суммы документа"
          style={{ marginLeft: 6, fontFamily: MONO, color: 'var(--dot-current-dz)' }}>
          Δ {money(c.amount_mismatch)}
        </span>
      )}
      {/* Второй строкой — чем этот кандидат отличается от соседнего: контрагент,
          его ИНН и ссылки. По сумме и дате варианты часто неразличимы. */}
      {(c.counterparty || c.counterparty_inn || c.document_link) && (
        <span style={{ display: 'block', color: 'var(--text-muted)', marginTop: 1 }}>
          {c.counterparty_id ? (
            <a href={`/directory/counterparties/${c.counterparty_id}`} target="_blank" rel="noreferrer"
              onClick={stop} title="Открыть карточку контрагента"
              style={{ color: 'var(--accent)', textDecoration: 'none' }}>{c.counterparty} ↗</a>
          ) : <span>{c.counterparty}</span>}
          {c.counterparty_inn && (
            <span style={{ fontFamily: MONO, color: 'var(--text-faint)' }}> · ИНН {c.counterparty_inn}</span>
          )}
          {c.document_link && (
            <a href={c.document_link} target="_blank" rel="noreferrer" onClick={stop}
              title="Документ, привязанный к операции вручную"
              style={{ marginLeft: 6, color: 'var(--accent)', textDecoration: 'none' }}>документ ↗</a>
          )}
        </span>
      )}
    </span>
  )
}
