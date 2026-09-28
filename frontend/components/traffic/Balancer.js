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
import { MONO, UI, card, CAP, btn, btnSm, inp, chip, cell, SortHead } from '@/components/salesTableKit'
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
// Поле ввода числа в клетке сетки: кит + прижатие вправо, как у чисел в соседних колонках.
const NUM_INP = { ...inp, width: '100%', padding: '5px 7px', fontFamily: MONO, textAlign: 'right' }

const grp = (n) => (n === null || n === undefined || n === '' ? '' : Number(n).toLocaleString('ru-RU',
  { maximumFractionDigits: 0 }))

// Колонки таблицы: подпись, ширина и значение для сортировки — одним описанием, чтобы
// заголовок и порядок строк не разошлись на первой правке. `num` — числовая колонка:
// первый клик по ней сортирует по убыванию (сначала крупное), текстовая — по алфавиту.
// Ширины — под 1920 с запасом до 1366: колонки резиновые (минимум + доля), на 1920
// растягиваются на всю карточку, на 1366 сжимаются до минимумов. Домен — второй строкой под площадкой (у большинства
// площадок он совпадает с именем, и отдельная колонка дублировала бы его), подписи шапки
// переносятся в две строки, числовые колонки — по ширине значения.
const COLS = [
  { key: 'name', label: 'Площадка', w: 'minmax(150px,2fr)', get: (r) => r.name },
  { key: 'code', label: 'Код', w: '52px', get: (r) => r.code },
  { key: 'ms_publisher_id', label: 'ID в МС', w: '56px', num: true, get: (r) => r.ms_publisher_id },
  { key: 'scope', label: 'Поверх\u00adность', w: '92px', get: (r) => r.scope_label },
  { key: 'services', label: 'Услуги', w: 'minmax(90px,1.4fr)', get: (r) => (r.services || []).join(', ') },
  { key: 'volume', label: 'Объём', w: 'minmax(92px,1fr)', num: true, get: (r) => r.volume },
  { key: 'depth', label: 'Глубина', w: 'minmax(60px,.6fr)', num: true, get: (r) => r.depth },
  { key: 'requests', label: 'Запросы кода', w: 'minmax(96px,1fr)', num: true, get: (r) => r.requests },
  { key: 'index_auto', label: 'Индекс расчётный', w: 'minmax(146px,1.2fr)', num: true, get: (r) => r.index_auto },
  { key: 'index_manual', label: 'Индекс ручной', w: 'minmax(96px,1fr)', num: true, get: (r) => r.index_manual },
  { key: 'external_score', label: 'Внешняя оценка', w: 'minmax(84px,.9fr)', num: true, get: (r) => r.external_score },
  { key: 'is_locked', label: 'Заперт', w: '50px', num: true, center: true, get: (r) => (r.is_locked ? 1 : 0) },
  { key: 'note', label: 'Примечание', w: 'minmax(90px,1.6fr)', get: (r) => r.note },
]

// Пустое — всегда в конце, в какую сторону ни сортируй: «нет замера» не меньше и не
// больше любого числа, и в начале списка оно заслоняло бы строки с данными.
const GRID = COLS.map((c) => c.w).join(' ')

const key = (r) => `${r.publisher_id}:${r.scope}`

const blank = (v) => v === null || v === undefined || v === ''
const cmp = (a, b, col) => {
  if (col.num) return Number(String(a).replace(',', '.')) - Number(String(b).replace(',', '.'))
  return String(a).localeCompare(String(b), 'ru', { numeric: true, sensitivity: 'base' })
}

export default function Balancer({ mayEdit }) {
  const [rows, setRows] = useState([])
  const [coef, setCoef] = useState({ k: null, depth_default: null })
  const [month, setMonth] = useState('')
  const [q, setQ] = useState('')
  const [scope, setScope] = useState('all')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  // Сортировка идёт по СОХРАНЁННЫМ значениям (снимок с сервера), а не по тому, что
  // человек печатает: иначе строка уезжала бы из-под курсора на каждом символе.
  const [saved, setSaved] = useState({})
  const [sort, setSort] = useState({ key: null, dir: 'asc' })

  const fromServer = useCallback((list) => {
    setRows(list || [])
    setSaved(Object.fromEntries((list || []).map((r) => [key(r), r])))
  }, [])
  const load = useCallback(async () => {
    const r = await api.get('/traffic-catalog/balancer', auth())
    fromServer(r.data.rows)
    setCoef(r.data.coefficients || {})
    setMonth(r.data.month || '')
  }, [fromServer])
  useEffect(() => { load() }, [load])

  const onSort = (col) => setSort((st) => (st.key !== col.key
    ? { key: col.key, dir: col.num ? 'desc' : 'asc' }
    : { key: col.key, dir: st.dir === 'asc' ? 'desc' : 'asc' }))
  const patch = (r, p) => setRows((xs) => xs.map((x) => (key(x) === key(r) ? { ...x, ...p } : x)))

  const save = async (r) => {
    if (!mayEdit) return
    try {
      const res = await api.put(`/traffic-catalog/balancer/row/${r.publisher_id}/${r.scope}`, {
        volume: num(r.volume), depth: num(r.depth), requests: num(r.requests),
        index_manual: num(r.index_manual), is_locked: !!r.is_locked, note: r.note || null,
        external_score: num(r.external_score),
      }, auth())
      fromServer(res.data.rows)
    } catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось сохранить строку') }
  }

  const recalc = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.post('/traffic-catalog/balancer/recalc', {}, auth())
      fromServer(r.data.rows)
      setMsg(`Пересчитано ${r.data.updated}; заперто ${r.data.locked_skipped}; без данных ${r.data.no_data}`)
    } catch (e) { setMsg(e?.response?.data?.detail || 'Пересчёт не удался') } finally { setBusy(false) }
  }

  const saveCoef = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.put('/traffic-catalog/balancer/settings',
        { k: num(coef.k), depth_default: num(coef.depth_default) }, auth())
      setCoef(r.data.coefficients); fromServer(r.data.rows)
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
      fromServer(r.data.rows)
      setMsg(`Загружено: применено ${r.data.applied}, пропущено ${r.data.skipped}`)
    } catch (e2) { setMsg(e2?.response?.data?.detail || 'Импорт не удался') } finally { setBusy(false) }
  }

  const inScope = (r) => (scope === 'all' ? true
    : scope === 'app' ? r.scope.startsWith('app')      // весь ап отдельно от веба
      : r.scope === scope)

  const filtered = rows.filter((r) => {
    if (!inScope(r)) return false
    const s = q.trim().toLowerCase()
    return !s || [r.name, r.code, r.domain, r.ms_publisher_id].some(
      (v) => String(v || '').toLowerCase().includes(s))
  })
  const sortCol = COLS.find((c) => c.key === sort.key)
  const shown = !sortCol ? filtered : [...filtered].sort((a, b) => {
    const va = sortCol.get(saved[key(a)] || a)
    const vb = sortCol.get(saved[key(b)] || b)
    if (blank(va) || blank(vb)) return blank(va) - blank(vb)
    return (sort.dir === 'asc' ? 1 : -1) * cmp(va, vb, sortCol)
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

      {/* Реестр — по канону «Контрагентов»: фильтры и счётчик внутри карточки, CSS-grid
          одной сеткой на шапку и строки, скролл внутри. Числа — вправо, моноширинным. */}
      <div style={{ ...card, padding: '14px 18px 16px' }}>
        {/* поиск, поверхности и счётчик — внутри карточки реестра, как в каноне */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
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
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 1180 }}>
            <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8,
              borderBottom: '1px solid var(--border-card)' }}>
              {COLS.map((c) => (
                <SortHead key={c.key} label={c.label} right={c.num && !c.center} wrap
                  active={sort.key === c.key} dir={sort.dir} onClick={() => onSort(c)} />
              ))}
            </div>
            {shown.map((r) => {
              const [bg, fg] = SCOPE_TONE[r.scope] || SCOPE_TONE.web
              const [sbg, sfg] = SRC_TONE[r.source] || ['var(--bg-subtle)', 'var(--text-faint)']
              return (
                <div key={key(r)} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8,
                  alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border-row)',
                  borderRadius: 10 }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-subtle)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}>
                  {/* Ссылка на карточку площадки — в НОВОЙ вкладке: балансировщик это
                      рабочая таблица на 76 строк, и уход из неё стоит потерянного места
                      в списке. Правка полей от этого не теряется: они сохраняются по
                      уходу из клетки, а не по кнопке. */}
                  <div style={{ ...cell, fontWeight: 600, overflow: 'hidden' }}>
                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                      title={r.name}>
                      {r.name}
                      <a href={`/publishers/${r.publisher_id}`} target="_blank" rel="noreferrer"
                         title={`Карточка площадки «${r.name}»`}
                         style={{ marginLeft: 6, color: 'var(--accent)', textDecoration: 'none',
                                  fontWeight: 400 }}>↗</a>
                    </div>
                    {!!r.domain && r.domain.toLowerCase() !== String(r.name || '').toLowerCase() && (
                      <div style={{ fontFamily: MONO, fontSize: 11, fontWeight: 400,
                        color: 'var(--text-faint)', whiteSpace: 'nowrap', overflow: 'hidden',
                        textOverflow: 'ellipsis' }} title={r.domain}>{r.domain}</div>
                    )}
                  </div>
                  <div style={{ ...cell, fontFamily: MONO, fontSize: 12, fontWeight: 700,
                    color: r.code ? 'var(--accent)' : 'var(--danger)' }}>{r.code || '—'}</div>
                  <div style={{ ...cell, fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{r.ms_publisher_id || '—'}</div>
                  <div style={cell}><span style={chip(bg, fg, 'transparent')}>{r.scope_label}</span></div>
                  <div style={{ ...cell, fontSize: 12, color: 'var(--text-secondary)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    title={r.services.join(', ')}>
                    {r.services.length ? r.services.join(', ') : '—'}
                  </div>
                  <div style={cell}>
                    <input style={NUM_INP} disabled={!mayEdit} value={r.volume ?? ''}
                      onChange={(e) => patch(r, { volume: e.target.value })} onBlur={() => save(r)} />
                  </div>
                  <div style={cell}>
                    <input style={NUM_INP} disabled={!mayEdit} value={r.depth ?? ''}
                      onChange={(e) => patch(r, { depth: e.target.value })} onBlur={() => save(r)} />
                  </div>
                  <div style={cell}>
                    <input style={NUM_INP} disabled={!mayEdit} value={r.requests ?? ''}
                      onChange={(e) => patch(r, { requests: e.target.value })} onBlur={() => save(r)} />
                  </div>
                  <div style={{ ...cell, fontFamily: MONO, fontWeight: 700, textAlign: 'right',
                    whiteSpace: 'nowrap' }}>
                    {!!r.source && (
                      <span style={{ ...chip(sbg, sfg, 'transparent'), marginRight: 6, fontSize: 10 }}>
                        {SRC_LABEL[r.source] || r.source}</span>
                    )}
                    {r.index_auto ? grp(r.index_auto) : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                  </div>
                  <div style={cell}>
                    <input style={NUM_INP} disabled={!mayEdit} value={r.index_manual ?? ''} placeholder="—"
                      onChange={(e) => patch(r, { index_manual: e.target.value })} onBlur={() => save(r)} />
                  </div>
                  <div style={cell}>
                    <input style={NUM_INP} disabled={!mayEdit} value={r.external_score ?? ''} placeholder="—"
                      title="Внешняя оценка — справочная, в индекс и доли площадок не входит"
                      onChange={(e) => patch(r, { external_score: e.target.value })} onBlur={() => save(r)} />
                  </div>
                  <div style={{ ...cell, textAlign: 'center' }}>
                    <input type="checkbox" checked={!!r.is_locked} disabled={!mayEdit}
                      title="Не перетирать пересчётом"
                      onChange={(e) => { patch(r, { is_locked: e.target.checked }); save({ ...r, is_locked: e.target.checked }) }} />
                  </div>
                  <div style={cell}>
                    <input style={{ ...inp, width: '100%', padding: '5px 7px' }} disabled={!mayEdit}
                      value={r.note ?? ''} onChange={(e) => patch(r, { note: e.target.value })}
                      onBlur={() => save(r)} />
                  </div>
                </div>
              )
            })}
            {!shown.length && (
              <div style={{ padding: '14px 8px', fontSize: 13, color: 'var(--text-faint)' }}>Ничего не найдено</div>
            )}
          </div>
        </div>
        <div style={{ ...CAP, marginTop: 10, marginBottom: 0 }}>
          Индекс = запросы кода, иначе объём × глубина × K. Действующий = ручной, если задан.
          Замеры — те же, что в карточке площадки.
        </div>
      </div>
    </div>
  )
}
