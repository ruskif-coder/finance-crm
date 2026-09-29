/**
 * Админка трафика → вкладка «Особенности площадок» (владелец 27–29.09.2026).
 *
 * По каждой поверхности площадки: канал размещения (наша DSP / Adfox / вне контура),
 * ссылки для app (веб-ссылка в href / диплинк в href + веб в url/adomain) и доп. код Adfox
 * для макроса %user6%. Право — своё, «Трафики · Особенности площадок» («трафик админ»).
 * Что из этого получается в креативе — docs/ШПАРГАЛКА_креатив_под_площадку.md.
 *
 * Таблица — шаблон реестра: CSS-grid, фильтры и счётчик внутри карточки, SortHead из кита.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { MONO, card, inp, sel, SortHead } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'

const GRID = '220px 70px 170px 250px minmax(260px,1fr)'
const CH_TONE = { dsp: 'var(--accent)', adfox: 'var(--dot-current-dz)', outside: 'var(--text-faint)' }

/** Строка поверхности. Модульный уровень — иначе поле кода теряет фокус на каждом символе. */
function RuleRow({ r, channels, links, mayEdit, onSave }) {
  const [code, setCode] = useState(r.adfox_extra_code || '')
  useEffect(() => { setCode(r.adfox_extra_code || '') }, [r.adfox_extra_code])
  const adfoxWeb = r.placement_channel === 'adfox' && r.kind === 'web'
  return (
    <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, alignItems: 'start', padding: '10px 0', borderBottom: '1px solid var(--border-row)' }}>
      <div style={{ padding: '6px 8px', fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.publisher}</div>
      <div style={{ padding: '6px 8px', fontFamily: MONO, fontSize: 11, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{r.kind}</div>
      <div style={{ padding: '0 8px' }}>
        <select disabled={!mayEdit} value={r.placement_channel || ''} style={{ ...sel, width: '100%', padding: '6px 8px', color: CH_TONE[r.placement_channel] || 'var(--text-faint)', fontWeight: 600 }}
          onChange={e => onSave(r, { placement_channel: e.target.value || null })}>
          <option value="">не задано</option>
          {Object.entries(channels).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </div>
      <div style={{ padding: '0 8px' }}>
        {r.kind === 'app' ? (
          <select disabled={!mayEdit} value={r.app_links || ''} style={{ ...sel, width: '100%', padding: '6px 8px' }}
            onChange={e => onSave(r, { app_links: e.target.value || null })}>
            <option value="">как было — макрос DSP в href</option>
            {Object.entries(links).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        ) : <span style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: '30px' }}>—</span>}
      </div>
      <div style={{ padding: '0 8px' }}>
        {adfoxWeb ? (
          <>
            <textarea readOnly={!mayEdit} value={code} rows={3} placeholder="iframe-ы площадки для %user6%"
              onChange={e => setCode(e.target.value)}
              onBlur={() => { if (code !== (r.adfox_extra_code || '')) onSave(r, { adfox_extra_code: code }) }}
              style={{ ...inp, width: '100%', fontFamily: MONO, fontSize: 11, resize: 'vertical', boxSizing: 'border-box' }} />
            {!!r.problem && <div style={{ fontSize: 11.5, color: 'var(--danger-fg)', marginTop: 4 }}>{r.problem}</div>}
          </>
        ) : <span style={{ fontSize: 12, color: 'var(--text-faint)', lineHeight: '30px' }}>—</span>}
      </div>
    </div>
  )
}

export default function PublisherRules({ mayEdit }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [only, setOnly] = useState('')
  const [sort, setSort] = useState({ key: 'publisher', dir: 'asc' })

  const load = useCallback(() => {
    api.get('/traffic-catalog/publisher-rules', auth())
      .then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить особенности площадок'))
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  const save = (r, patch) => {
    const body = { placement_channel: r.placement_channel, app_links: r.app_links,
      adfox_extra_code: r.adfox_extra_code, ...patch }
    api.put(`/traffic-catalog/publisher-rules/${r.surface_id}`, body, auth())
      .then(res => { setErr(''); setData(d => ({ ...d, items: d.items.map(x => (x.surface_id === r.surface_id ? { ...x, ...res.data } : x)) })) })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось сохранить'))
  }

  const rows = useMemo(() => {
    let xs = data?.items || []
    const s = q.trim().toLowerCase()
    if (s) xs = xs.filter(x => x.publisher.toLowerCase().includes(s))
    if (only === 'special') xs = xs.filter(x => x.placement_channel !== 'dsp' || x.app_links)
    if (only === 'problem') xs = xs.filter(x => x.problem || !x.placement_channel)
    const k = sort.dir === 'asc' ? 1 : -1
    const v = x => (sort.key === 'publisher' ? `${x.publisher} ${x.kind}` : (x[sort.key] || '￿'))
    return [...xs].sort((a, b) => String(v(a)).localeCompare(String(v(b)), 'ru') * k)
  }, [data, q, only, sort])

  const head = (key, label) => (
    <SortHead label={label} active={sort.key === key} dir={sort.dir}
      onClick={() => setSort(s => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }))} />
  )

  return (
    <div style={{ ...card, padding: '18px 22px 14px' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
        <input style={{ ...inp, width: 240 }} placeholder="площадка…" value={q} onChange={e => setQ(e.target.value)} />
        <select style={{ ...sel, width: 230 }} value={only} onChange={e => setOnly(e.target.value)}>
          <option value="">все поверхности</option>
          <option value="special">только с особенностями</option>
          <option value="problem">не задано или с проблемой</option>
        </select>
        {!mayEdit && <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>только просмотр</span>}
      </div>
      <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-muted)', padding: '2px 0 8px' }}>
        показано {rows.length} из {data?.items.length ?? 0}</div>
      {!!err && <div style={{ color: 'var(--danger-fg)', fontSize: 12.5, padding: '4px 0 8px' }}>{err}</div>}
      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 1000 }}>
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, borderBottom: '1px solid var(--border-card)' }}>
            {head('publisher', 'Площадка')}{head('kind', 'Поверх.')}{head('placement_channel', 'Канал размещения')}
            {head('app_links', 'Ссылки для app')}{head('adfox_extra_code', 'Доп. код Adfox (%user6%)')}
          </div>
          {!data && !err && <div style={{ padding: 24, color: 'var(--text-muted)' }}>Загрузка…</div>}
          {rows.map(r => <RuleRow key={r.surface_id} r={r} channels={data.channels} links={data.app_links} mayEdit={mayEdit} onSave={save} />)}
        </div>
      </div>
    </div>
  )
}
