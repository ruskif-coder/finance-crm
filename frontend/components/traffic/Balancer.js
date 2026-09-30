/**
 * Балансировщик — вкладка админки трафика.
 *
 * Строка = площадка × поверхность (web / app android / app ios): веса web и app правятся
 * отдельно, услуги привязаны к поверхности. Индекс — АБСОЛЮТНАЯ ёмкость (показов/мес),
 * доля считается уже внутри РК от участников.
 *
 * Два набора данных (владелец 30.09.2026): «площадка + наш код» (объём, глубина,
 * запросы кода — те же замеры, что в карточке площадки) и «оценка SimilarWeb» (visits, PpV,
 * BR — только web, правятся только здесь; Swtraffic считается). Индекс — каскад A/B/C
 * (`app/ad/balance.py`): запросы в коридоре ×3 от SW → SW × k → объём × k; k калибруются
 * сами по площадкам с обоими числами. Потолок доли площадки в РК — настройка сверху.
 * Правка сохраняется по уходу из клетки (blur), как в каталоге блоков.
 */
import { useCallback, useEffect, useState } from 'react'
import { MONO, card, CAP, btn, inp, chip, cell, SortHead } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'

const SRC_LABEL = { ad_requests: 'A · код', req_sw_clamp: 'A · зажат', similarweb: 'B · SW',
  estimate: 'C · объём', manual: 'рука' }
const SRC_HINT = {
  ad_requests: 'Доверие A: запросы рекламного кода',
  req_sw_clamp: 'Доверие A, но запросы вне коридора ×3 от оценки SimilarWeb — индекс зажат по краю коридора',
  similarweb: 'Доверие B: запросов кода нет, оценка по SimilarWeb (Swtraffic × k)',
  estimate: 'Доверие C: нет ни запросов, ни SimilarWeb — объём площадки × k',
  manual: 'Ручной индекс — перекрывает расчёт и потолок доли',
}
const SRC_TONE = {
  ad_requests: ['var(--income-tint)', 'var(--income-fg)'],
  req_sw_clamp: ['var(--danger-tint)', 'var(--danger-fg)'],
  similarweb: ['var(--accent-tint)', 'var(--accent-fg)'],
  estimate: ['var(--warning-tint)', 'var(--warning-fg)'],
  manual: ['var(--violet-tint)', 'var(--violet-fg)'],
}
const SCOPE_TONE = {
  web: ['var(--accent-tint)', 'var(--accent-fg)'],
  app_android: ['var(--income-tint)', 'var(--income-fg)'],
  app_ios: ['var(--warning-tint)', 'var(--warning-fg)'],
}

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(',', '.')))
// Поле ввода числа в клетке сетки: кит + прижатие вправо, как у чисел в соседних колонках.
const NUM_INP = { ...inp, width: '100%', padding: '5px 7px', fontFamily: MONO, textAlign: 'right' }

const grp = (n) => (n === null || n === undefined || n === '' ? '' : Number(n).toLocaleString('ru-RU',
  { maximumFractionDigits: 0 }))
const dec = (n, d = 2) => (n === null || n === undefined || n === '' ? '' : Number(n).toLocaleString('ru-RU',
  { maximumFractionDigits: d }))

// Колонки таблицы: подпись, ширина, группа и значение для сортировки — одним описанием, чтобы
// заголовок и порядок строк не разошлись на первой правке. `num` — числовая колонка:
// первый клик по ней сортирует по убыванию (сначала крупное), текстовая — по алфавиту.
// Домен — второй строкой под площадкой. `grp` — набор данных, надпись над колонками.
const COLS = [
  { key: 'name', label: 'Площадка', w: 'minmax(150px,2fr)', get: (r) => r.name },
  { key: 'code', label: 'Код', w: '52px', get: (r) => r.code },
  { key: 'ms_publisher_id', label: 'ID в МС', w: '56px', num: true, get: (r) => r.ms_publisher_id },
  { key: 'scope', label: 'Поверх­ность', w: '92px', get: (r) => r.scope_label },
  { key: 'services', label: 'Услуги', w: 'minmax(90px,1.3fr)', get: (r) => (r.services || []).join(', ') },
  { key: 'volume', label: 'Объём', w: 'minmax(88px,1fr)', num: true, grp: 'pub', get: (r) => r.volume },
  { key: 'depth', label: 'Глубина', w: 'minmax(56px,.6fr)', num: true, grp: 'pub', get: (r) => r.depth },
  { key: 'requests', label: 'Запросы кода', w: 'minmax(92px,1fr)', num: true, grp: 'pub', get: (r) => r.requests },
  { key: 'sw_visits', label: 'SW visits', w: 'minmax(84px,1fr)', num: true, grp: 'sw', get: (r) => r.sw_visits },
  { key: 'sw_ppv', label: 'PpV', w: 'minmax(66px,.6fr)', num: true, grp: 'sw', get: (r) => r.sw_ppv },
  { key: 'sw_br', label: 'BR, %', w: 'minmax(66px,.6fr)', num: true, grp: 'sw', get: (r) => r.sw_br },
  { key: 'swtraffic', label: 'Swtraffic', w: 'minmax(84px,.9fr)', num: true, grp: 'sw', get: (r) => r.swtraffic },
  { key: 'index_auto', label: 'Индекс расчётный', w: 'minmax(150px,1.2fr)', num: true, grp: 'idx', get: (r) => r.index_auto },
  { key: 'index_manual', label: 'Индекс ручной', w: 'minmax(92px,1fr)', num: true, grp: 'idx', get: (r) => r.index_manual },
  { key: 'is_locked', label: 'Заперт', w: '50px', num: true, center: true, grp: 'idx', get: (r) => (r.is_locked ? 1 : 0) },
  { key: 'note', label: 'Примечание', w: 'minmax(90px,1.4fr)', grp: 'idx', get: (r) => r.note },
]

// Надписи над группами колонок: два набора данных и итог (владелец 30.09.2026).
const GROUPS = [
  { grp: 'pub', label: 'Данные площадки + наш код', tone: 'var(--income-fg)', bg: 'var(--income-tint)' },
  { grp: 'sw', label: 'Оценка SimilarWeb · только web', tone: 'var(--accent-fg)', bg: 'var(--accent-tint)' },
  { grp: 'idx', label: 'Индекс', tone: 'var(--text-secondary)', bg: 'var(--bg-subtle)' },
].map((g) => {
  const idx = COLS.map((c, i) => (c.grp === g.grp ? i : -1)).filter((i) => i >= 0)
  return { ...g, from: idx[0] + 1, to: idx[idx.length - 1] + 2 }
})
const SW_FIELDS = ['sw_visits', 'sw_ppv', 'sw_br']

// Пустое — всегда в конце, в какую сторону ни сортируй: «нет замера» не меньше и не
// больше любого числа, и в начале списка оно заслоняло бы строки с данными.
const GRID = COLS.map((c) => c.w).join(' ')

const key = (r) => `${r.publisher_id}:${r.scope}`

const blank = (v) => v === null || v === undefined || v === ''
const cmp = (a, b, col) => {
  if (col.num) return Number(String(a).replace(',', '.')) - Number(String(b).replace(',', '.'))
  return String(a).localeCompare(String(b), 'ru', { numeric: true, sensitivity: 'base' })
}
const kTxt = (v) => (v ? dec(v, 1) : 'нет данных')

export default function Balancer({ mayEdit }) {
  const [rows, setRows] = useState([])
  const [coef, setCoef] = useState({ share_cap_pct: null })
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
        ...(r.scope === 'web' ? { sw_visits: num(r.sw_visits), sw_ppv: num(r.sw_ppv), sw_br: num(r.sw_br) } : {}),
      }, auth())
      fromServer(res.data.rows)
    } catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось сохранить строку') }
  }

  const recalc = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.post('/traffic-catalog/balancer/recalc', {}, auth())
      fromServer(r.data.rows)
      if (r.data.coefficients) setCoef(r.data.coefficients)
      setMsg(`Пересчитано ${r.data.updated}; заперто ${r.data.locked_skipped}; без данных ${r.data.no_data}`)
    } catch (e) { setMsg(e?.response?.data?.detail || 'Пересчёт не удался') } finally { setBusy(false) }
  }

  const saveCoef = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.put('/traffic-catalog/balancer/settings',
        { share_cap_pct: num(coef.share_cap_pct) }, auth())
      setCoef(r.data.coefficients); fromServer(r.data.rows)
      setMsg(`Потолок доли сохранён${r.data.campaigns_updated ? ' — доли в РК пересчитаны' : ''}`)
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
      setMsg(`Загружено: применено ${r.data.applied}, пропущено ${r.data.skipped} — нажмите «Пересчитать индексы»`)
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

  const flagged = rows.filter((r) => r.flag).length

  // Суммы по ТЕКУЩЕЙ выборке (фильтр поверхности + поиск) — мини-виджеты сверху.
  const sum = (f) => shown.reduce((a, r) => a + (Number(f(r)) || 0), 0)
  const KPI = [
    ['Площадок в выборке', new Set(shown.map((r) => r.publisher_id)).size],
    ['Запросы кода, Σ', grp(sum((r) => r.requests))],
    ['Swtraffic, Σ', grp(sum((r) => r.swtraffic))],
    ['Индекс, Σ', grp(sum((r) => r.index_effective))],
  ]

  return (
    <div>
      {/* потолок доли, калибровка, действия */}
      <div style={{ ...card, padding: '13px 16px', marginBottom: 14, display: 'flex',
        alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <label style={{ fontSize: 12 }}>
          <div style={{ ...CAP, marginBottom: 4 }}>Потолок доли площадки в РК, %</div>
          <input style={{ ...inp, width: 110, fontFamily: MONO }} disabled={!mayEdit}
            value={coef.share_cap_pct ?? ''} placeholder="15"
            title="Одна площадка берёт не больше этой доли объёма РК; излишек — остальным по весам. 0 — без потолка, пусто — 15 по умолчанию. Ручной индекс потолку не подчиняется"
            onChange={(e) => setCoef({ ...coef, share_cap_pct: e.target.value })} />
        </label>
        {mayEdit && <button style={btn(false)} onClick={saveCoef} disabled={busy}>Сохранить потолок</button>}
        {mayEdit && <button style={btn(true)} onClick={recalc} disabled={busy}>Пересчитать индексы</button>}
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}
          title="Коэффициенты считаются сами: медиана отношения запросов кода к Swtraffic / объёму по площадкам, где есть оба числа">
          <div style={{ ...CAP, marginBottom: 4 }}>k, откалиброваны по данным</div>
          <span style={{ fontFamily: MONO }}>
            SW {kTxt(coef.k_sw)} · объём web {kTxt(coef.k_vol_web)} · объём app {kTxt(coef.k_vol_app)}
          </span>
        </div>
        <span style={{ flex: 1 }} />
        <button style={btn(false)} onClick={download}>Выгрузить в Excel</button>
        {mayEdit && (
          <label style={{ ...btn(false), display: 'inline-block', cursor: 'pointer' }}>
            Загрузить из Excel
            <input type="file" accept=".xlsx" onChange={upload} style={{ display: 'none' }} />
          </label>
        )}
      </div>

      {!!flagged && (
        <div style={{ ...card, padding: '10px 14px', marginBottom: 14,
          background: 'var(--danger-tint)', borderColor: 'var(--danger-border)',
          color: 'var(--danger-fg)', fontSize: 12.5 }}>
          У {flagged} строк запросы кода расходятся с оценкой SimilarWeb больше чем в 3 раза — индекс
          зажат по краю коридора (метка «A · зажат»). Стоит проверить: много мест на странице или
          лишние вызовы кода.
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
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <input style={{ ...inp, width: 240 }} placeholder="Площадка, код, домен, ID в МС…"
            value={q} onChange={(e) => setQ(e.target.value)} />
          {[['all', 'Все'], ['web', 'Web'], ['app', 'App (всё)'],
            ['app_android', 'App Android'], ['app_ios', 'App iOS']]
            .map(([k, l]) => (
              <span key={k} onClick={() => setScope(k)} style={{
                ...chip(scope === k ? 'var(--accent-tint)' : 'var(--bg-card)',
                  scope === k ? 'var(--accent)' : 'var(--text-secondary)', 'var(--border-card)'),
                cursor: 'pointer', fontWeight: scope === k ? 700 : 600,
              }}>{l}</span>
            ))}
          <span style={{ ...CAP, marginBottom: 0 }}>
            показано {shown.length} из {rows.length} · замер за {month}
          </span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 1520 }}>
            <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8, marginBottom: 4 }}>
              {GROUPS.map((g) => (
                <div key={g.grp} style={{ gridColumn: `${g.from} / ${g.to}`, ...CAP, marginBottom: 0,
                  padding: '4px 8px', borderRadius: 8, background: g.bg, color: g.tone,
                  textAlign: 'center', whiteSpace: 'nowrap' }}>{g.label}</div>
              ))}
            </div>
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
                      рабочая таблица, и уход из неё стоит потерянного места в списке. */}
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
                  {['volume', 'depth', 'requests'].map((f) => (
                    <div key={f} style={cell}>
                      <input style={NUM_INP} disabled={!mayEdit} value={r[f] ?? ''}
                        title={f === 'depth' ? 'Справочно: в формулу индекса не входит — глубина учтена в калибровке k объёма' : undefined}
                        onChange={(e) => patch(r, { [f]: e.target.value })} onBlur={() => save(r)} />
                    </div>
                  ))}
                  {SW_FIELDS.map((f) => (
                    <div key={f} style={cell}>
                      {r.scope === 'web'
                        ? <input style={NUM_INP} disabled={!mayEdit} value={r[f] ?? ''} placeholder="—"
                            onChange={(e) => patch(r, { [f]: e.target.value })} onBlur={() => save(r)} />
                        : <span title="У приложений данных SimilarWeb нет" style={{ display: 'block',
                            textAlign: 'right', color: 'var(--text-faint)', fontFamily: MONO }}>—</span>}
                    </div>
                  ))}
                  <div style={{ ...cell, fontFamily: MONO, textAlign: 'right', color: 'var(--text-secondary)' }}
                    title="SW visits × PpV × (100 − BR) / 100">
                    {r.swtraffic ? grp(r.swtraffic) : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                  </div>
                  <div style={{ ...cell, fontFamily: MONO, fontWeight: 700, textAlign: 'right',
                    whiteSpace: 'nowrap' }}>
                    {!!r.source && (
                      <span title={SRC_HINT[r.source]}
                        style={{ ...chip(sbg, sfg, 'transparent'), marginRight: 6, fontSize: 10 }}>
                        {SRC_LABEL[r.source] || r.source}</span>
                    )}
                    {r.index_auto ? grp(r.index_auto) : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                  </div>
                  <div style={cell}>
                    <input style={NUM_INP} disabled={!mayEdit} value={r.index_manual ?? ''} placeholder="—"
                      onChange={(e) => patch(r, { index_manual: e.target.value })} onBlur={() => save(r)} />
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
          Индекс: A — запросы кода (в коридоре ×3 от оценки SW), B — Swtraffic × k, C — объём × k.
          Действующий = ручной, если задан; ручной не подчиняется потолку доли.
        </div>
      </div>
    </div>
  )
}
