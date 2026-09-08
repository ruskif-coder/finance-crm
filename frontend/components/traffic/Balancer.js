/**
 * Балансировщик — вкладка админки трафика.
 *
 * Строка = площадка × поверхность (web / app android / app ios): веса web и app правятся
 * отдельно, услуги привязаны к поверхности. Индекс — АБСОЛЮТНАЯ ёмкость (показов/мес),
 * доля считается уже внутри РК от участников.
 *
 * Замеры (объём / глубина / запросы кода) — те же данные, что в карточке площадки
 * (sales_publisher_traffic): правятся и там, и здесь, здесь просто «всё с листа».
 * Правка сохраняется по уходу из клетки (blur), как в каталоге блоков.
 *
 * Коэффициенты оценки заведены ПУСТЫМИ: пока их не задали, оценочная ветка не считается —
 * в строке прочерк, а не выдуманное число. Источник индекса виден в строке.
 */
import { useCallback, useEffect, useState } from 'react'
import { MONO, UI, card, CAP, btn, btnSm, inp, th, td, chip } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'

const SRC_LABEL = { ad_requests: 'замер', estimate: 'оценка', manual: 'рука' }
const SRC_TONE = {
  ad_requests: ['var(--income-tint)', 'var(--income)'],
  estimate: ['var(--warning-tint)', 'var(--warning-text)'],
  manual: ['var(--accent-tint, #e6eeff)', 'var(--accent)'],
}
const SCOPE_TONE = {
  web: ['var(--accent-tint, #e6eeff)', 'var(--accent)'],
  app_android: ['var(--income-tint)', 'var(--income)'],
  app_ios: ['var(--warning-tint)', 'var(--warning-text)'],
}

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(',', '.')))
const grp = (n) => (n === null || n === undefined || n === '' ? '' : Number(n).toLocaleString('ru-RU',
  { maximumFractionDigits: 0 }))

export default function Balancer({ mayEdit }) {
  const [rows, setRows] = useState([])
  const [coef, setCoef] = useState({ k: null, depth_default: null })
  const [month, setMonth] = useState('')
  const [q, setQ] = useState('')
  const [scope, setScope] = useState('all')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const r = await api.get('/traffic-catalog/balancer', auth())
    setRows(r.data.rows || [])
    setCoef(r.data.coefficients || {})
    setMonth(r.data.month || '')
  }, [])
  useEffect(() => { load() }, [load])

  const key = (r) => `${r.publisher_id}:${r.scope}`
  const patch = (r, p) => setRows((xs) => xs.map((x) => (key(x) === key(r) ? { ...x, ...p } : x)))

  const save = async (r) => {
    if (!mayEdit) return
    try {
      const res = await api.put(`/traffic-catalog/balancer/row/${r.publisher_id}/${r.scope}`, {
        volume: num(r.volume), depth: num(r.depth), requests: num(r.requests),
        index_manual: num(r.index_manual), is_locked: !!r.is_locked, note: r.note || null,
      }, auth())
      setRows(res.data.rows || [])
    } catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось сохранить строку') }
  }

  const recalc = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.post('/traffic-catalog/balancer/recalc', {}, auth())
      setRows(r.data.rows || [])
      setMsg(`Пересчитано ${r.data.updated}; заперто ${r.data.locked_skipped}; без данных ${r.data.no_data}`)
    } catch (e) { setMsg(e?.response?.data?.detail || 'Пересчёт не удался') } finally { setBusy(false) }
  }

  const saveCoef = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.put('/traffic-catalog/balancer/settings',
        { k: num(coef.k), depth_default: num(coef.depth_default) }, auth())
      setCoef(r.data.coefficients); setRows(r.data.rows || [])
      setMsg('Коэффициенты сохранены — нажмите «Пересчитать индексы»')
    } catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось сохранить') } finally { setBusy(false) }
  }

  const download = async () => {
    const r = await api.get('/traffic-catalog/balancer/export', { ...auth(), responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([r.data]))
    const a = document.createElement('a')
    a.href = url; a.download = 'Балансировщик.xlsx'; document.body.appendChild(a); a.click()
    a.remove(); URL.revokeObjectURL(url)
  }

  const upload = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setBusy(true); setMsg('')
    try {
      const form = new FormData(); form.append('file', f)
      const r = await api.post('/traffic-catalog/balancer/import', form,
        { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
      setRows(r.data.rows || [])
      setMsg(`Загружено: применено ${r.data.applied}, пропущено ${r.data.skipped}`)
    } catch (e2) { setMsg(e2?.response?.data?.detail || 'Импорт не удался') } finally { setBusy(false) }
  }

  const inScope = (r) => (scope === 'all' ? true
    : scope === 'app' ? r.scope.startsWith('app')      // весь ап отдельно от веба
      : r.scope === scope)

  const shown = rows.filter((r) => {
    if (!inScope(r)) return false
    const s = q.trim().toLowerCase()
    return !s || [r.name, r.code, r.domain, r.ms_publisher_id].some(
      (v) => String(v || '').toLowerCase().includes(s))
  })

  const withIndex = rows.filter((r) => r.index_effective).length
  const noCoef = !coef.k || !coef.depth_default

  // Суммы по ТЕКУЩЕЙ выборке (фильтр поверхности + поиск) — мини-виджеты сверху.
  const sum = (f) => shown.reduce((a, r) => a + (Number(f(r)) || 0), 0)
  const KPI = [
    ['Площадок в выборке', new Set(shown.map((r) => r.publisher_id)).size],
    ['Объём, Σ', grp(sum((r) => r.volume))],
    ['Запросы кода, Σ', grp(sum((r) => r.requests))],
    ['Индекс, Σ', grp(sum((r) => r.index_effective))],
  ]

  return (
    <div>
      {/* коэффициенты + действия */}
      <div style={{ ...card, padding: '13px 16px', marginBottom: 14, display: 'flex',
        alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <label style={{ fontSize: 12 }}>
          <div style={{ ...CAP, marginBottom: 4 }}>K — запросов кода на просмотр</div>
          <input style={{ ...inp, width: 110, fontFamily: MONO }} disabled={!mayEdit}
            value={coef.k ?? ''} placeholder="не задан"
            onChange={(e) => setCoef({ ...coef, k: e.target.value })} />
        </label>
        <label style={{ fontSize: 12 }}>
          <div style={{ ...CAP, marginBottom: 4 }}>Глубина по умолчанию</div>
          <input style={{ ...inp, width: 110, fontFamily: MONO }} disabled={!mayEdit}
            value={coef.depth_default ?? ''} placeholder="не задана"
            onChange={(e) => setCoef({ ...coef, depth_default: e.target.value })} />
        </label>
        {mayEdit && <button style={btn(false)} onClick={saveCoef} disabled={busy}>Сохранить коэффициенты</button>}
        {mayEdit && <button style={btn(true)} onClick={recalc} disabled={busy}>Пересчитать индексы</button>}
        <span style={{ flex: 1 }} />
        <button style={btn(false)} onClick={download}>Выгрузить в Excel</button>
        {mayEdit && (
          <label style={{ ...btn(false), display: 'inline-block', cursor: 'pointer' }}>
            Загрузить из Excel
            <input type="file" accept=".xlsx" onChange={upload} style={{ display: 'none' }} />
          </label>
        )}
      </div>

      {noCoef && (
        <div style={{ ...card, padding: '10px 14px', marginBottom: 14,
          background: 'var(--warning-tint)', borderColor: 'var(--warning-border)',
          color: 'var(--warning-text)', fontSize: 12.5 }}>
          Коэффициенты не заданы — оценочная ветка не считается. Индекс посчитан только там, где
          есть замер запросов рекламного кода ({withIndex} из {rows.length}). Впишите K и глубину
          по умолчанию, затем нажмите «Пересчитать индексы».
        </div>
      )}
      {!!msg && (
        <div style={{ ...card, padding: '9px 14px', marginBottom: 14, fontSize: 12.5,
          color: 'var(--text-secondary)' }}>{msg}</div>
      )}

      {/* мини-виджеты по выборке */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 14 }}>
        {KPI.map(([label, v]) => (
          <div key={label} style={{ ...card, padding: '13px 16px' }}>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-.02em',
              fontFamily: MONO }}>{v || 0}</div>
            <div style={{ ...CAP, marginBottom: 0, marginTop: 2 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* фильтры */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
        <input style={{ ...inp, width: 240 }} placeholder="Площадка, код, домен, ID в МС…"
          value={q} onChange={(e) => setQ(e.target.value)} />
        {[['all', 'Все'], ['web', 'Web'], ['app', 'App (всё)'],
          ['app_android', 'App Android'], ['app_ios', 'App iOS']]
          .map(([k, l]) => (
            <span key={k} onClick={() => setScope(k)} style={{
              ...chip(scope === k ? 'var(--accent-tint, #e6eeff)' : 'var(--bg-card)',
                scope === k ? 'var(--accent)' : 'var(--text-secondary)', 'var(--border-card)'),
              cursor: 'pointer', fontWeight: scope === k ? 700 : 600,
            }}>{l}</span>
          ))}
        <span style={{ ...CAP, marginBottom: 0 }}>
          показано {shown.length} из {rows.length} · замер за {month}
        </span>
      </div>

      {/* таблица */}
      <div style={{ ...card, padding: '10px 14px 16px', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1400 }}>
          <thead><tr>
            <th style={{ ...th, width: 190 }}>Площадка</th>
            <th style={{ ...th, width: 150 }}>Домен</th>
            <th style={{ ...th, width: 70 }}>Код</th>
            <th style={{ ...th, width: 80 }}>ID в МС</th>
            <th style={{ ...th, width: 110 }}>Поверхность</th>
            <th style={{ ...th, width: 150 }}>Услуги</th>
            <th style={{ ...th, width: 110 }}>Объём</th>
            <th style={{ ...th, width: 80 }}>Глубина</th>
            <th style={{ ...th, width: 120 }}>Запросы кода</th>
            <th style={{ ...th, width: 130 }}>Индекс расчётный</th>
            <th style={{ ...th, width: 120 }}>Индекс ручной</th>
            <th style={{ ...th, width: 60 }}>Заперт</th>
            <th style={{ ...th, width: 140 }}>Примечание</th>
          </tr></thead>
          <tbody>
            {shown.map((r) => {
              const [bg, fg] = SCOPE_TONE[r.scope] || SCOPE_TONE.web
              const [sbg, sfg] = SRC_TONE[r.source] || ['var(--bg-soft, #f1f4f9)', 'var(--text-faint)']
              return (
                <tr key={key(r)}>
                  {/* Ссылка на карточку площадки — в НОВОЙ вкладке: балансировщик это
                      рабочая таблица на 76 строк, и уход из неё стоит потерянного места
                      в списке. Правка полей от этого не теряется: они сохраняются по
                      уходу из клетки, а не по кнопке. */}
                  <td style={{ ...td, fontWeight: 600 }}>
                    {r.name}
                    <a href={`/publishers/${r.publisher_id}`} target="_blank" rel="noreferrer"
                       title={`Карточка площадки «${r.name}»`}
                       style={{ marginLeft: 6, color: 'var(--accent)', textDecoration: 'none',
                                fontWeight: 400 }}>↗</a>
                  </td>
                  <td style={{ ...td, fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>{r.domain}</td>
                  <td style={{ ...td, fontFamily: MONO, fontSize: 12, fontWeight: 700,
                    color: r.code ? 'var(--accent)' : 'var(--danger)' }}>{r.code || '—'}</td>
                  <td style={{ ...td, fontFamily: MONO, fontSize: 12 }}>{r.ms_publisher_id || '—'}</td>
                  <td style={td}><span style={chip(bg, fg, 'transparent')}>{r.scope_label}</span></td>
                  <td style={{ ...td, fontSize: 12, color: 'var(--text-secondary)' }}
                    title={r.services.join(', ')}>
                    {r.services.length ? r.services.join(', ') : '—'}
                  </td>
                  <td style={td}>
                    <input style={{ ...inp, width: '100%', padding: '5px 7px', fontFamily: MONO }}
                      disabled={!mayEdit} value={r.volume ?? ''}
                      onChange={(e) => patch(r, { volume: e.target.value })} onBlur={() => save(r)} />
                  </td>
                  <td style={td}>
                    <input style={{ ...inp, width: '100%', padding: '5px 7px', fontFamily: MONO }}
                      disabled={!mayEdit} value={r.depth ?? ''}
                      onChange={(e) => patch(r, { depth: e.target.value })} onBlur={() => save(r)} />
                  </td>
                  <td style={td}>
                    <input style={{ ...inp, width: '100%', padding: '5px 7px', fontFamily: MONO }}
                      disabled={!mayEdit} value={r.requests ?? ''}
                      onChange={(e) => patch(r, { requests: e.target.value })} onBlur={() => save(r)} />
                  </td>
                  <td style={{ ...td, fontFamily: MONO, fontWeight: 700 }}>
                    {r.index_auto ? grp(r.index_auto) : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                    {!!r.source && (
                      <span style={{ ...chip(sbg, sfg, 'transparent'), marginLeft: 6, fontSize: 10 }}>
                        {SRC_LABEL[r.source] || r.source}</span>
                    )}
                  </td>
                  <td style={td}>
                    <input style={{ ...inp, width: '100%', padding: '5px 7px', fontFamily: MONO }}
                      disabled={!mayEdit} value={r.index_manual ?? ''} placeholder="—"
                      onChange={(e) => patch(r, { index_manual: e.target.value })} onBlur={() => save(r)} />
                  </td>
                  <td style={{ ...td, textAlign: 'center' }}>
                    <input type="checkbox" checked={!!r.is_locked} disabled={!mayEdit}
                      title="Не перетирать пересчётом"
                      onChange={(e) => { patch(r, { is_locked: e.target.checked }); save({ ...r, is_locked: e.target.checked }) }} />
                  </td>
                  <td style={td}>
                    <input style={{ ...inp, width: '100%', padding: '5px 7px' }} disabled={!mayEdit}
                      value={r.note ?? ''} onChange={(e) => patch(r, { note: e.target.value })}
                      onBlur={() => save(r)} />
                  </td>
                </tr>
              )
            })}
            {!shown.length && (
              <tr><td style={{ ...td, color: 'var(--text-faint)' }} colSpan={13}>Ничего не найдено</td></tr>
            )}
          </tbody>
        </table>
        <div style={{ ...CAP, marginTop: 10, marginBottom: 0 }}>
          Индекс = запросы кода, иначе объём × глубина × K. Действующий = ручной, если задан.
          Замеры — те же, что в карточке площадки.
        </div>
      </div>
    </div>
  )
}
