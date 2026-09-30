/**
 * Доступность сайтов площадок — вкладка админки трафика (владелец 30.09.2026).
 *
 * Перенос внешнего скрипта трафика в систему. Проверка раз в час кроном
 * (`app/traffic/site_monitor.py`): обычный запрос, при антиботе — браузером. Здесь —
 * текущее состояние каждого сайта, полоска последних 24 проверок, режим проверки у
 * площадки и два списка настроек: доп. сайты вне реестра и исключения «пропали из показов».
 * Тревога «сайт недоступен» уходит трафик-админу и менеджеру паблишеров сама, на смене.
 */
import { useCallback, useEffect, useState } from 'react'
import { MONO, card, CAP, btn, inp, chip, cell, SortHead } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { fmtDateTime } from '@/lib/dates'
import safeHref from '@/lib/safeHref'

const ST = {
  ok: ['доступен', 'var(--income-tint)', 'var(--income-fg)'],
  antibot: ['антибот', 'var(--warning-tint)', 'var(--warning-fg)'],
  down: ['недоступен', 'var(--danger-tint)', 'var(--danger-fg)'],
}
const ST_HINT = {
  ok: 'Сайт открывается',
  antibot: 'Сайт режет робота (401/403), людям открывается — тревоги нет, только отметка',
  down: 'Сайт не открылся ни запросом, ни браузером — трафик-админу и менеджеру паблишеров ушла тревога',
}
const DOT = { ok: 'var(--income)', antibot: 'var(--warning)', down: 'var(--danger)' }
const MODE_LABEL = { http: 'запрос', browser: 'браузер', off: 'не проверять' }
const ORDER = { down: 0, antibot: 1, ok: 2 }
const GRID = 'minmax(180px,1.6fr) 120px 64px 136px 120px 120px minmax(160px,2fr) 170px'

const when = (v) => (v ? fmtDateTime(v) : '—')

export default function SiteMonitor({ mayEdit }) {
  const [rows, setRows] = useState([])
  const [extra, setExtra] = useState('')
  const [exclude, setExclude] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')
  const [q, setQ] = useState('')
  const [dsp, setDsp] = useState(null)

  const fromServer = (d) => {
    setRows(d.rows || [])
    if (d.dsp !== undefined) setDsp(d.dsp)
    if (d.extra !== undefined) setExtra(d.extra || '')
    if (d.dsp_exclude !== undefined) setExclude(d.dsp_exclude || '')
  }
  const load = useCallback(async () => {
    try { fromServer((await api.get('/traffic-catalog/site-monitor', auth())).data) }
    catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось загрузить список') }
  }, [])
  useEffect(() => { load() }, [load])

  const runOne = async (url) => {
    setBusy(url); setMsg('')
    try { fromServer((await api.post('/traffic-catalog/site-monitor/run', { url }, auth())).data) }
    catch (e) { setMsg(e?.response?.data?.detail || 'Проверка не удалась') }
    setBusy('')
  }
  const runAll = async () => {
    setBusy('all'); setMsg('')
    try {
      await api.post('/traffic-catalog/site-monitor/run', {}, auth())
      setMsg('Проверка всех сайтов запущена — займёт несколько минут; обновите список позже')
    } catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось запустить') }
    setBusy('')
  }
  const setMode = async (r, mode) => {
    try {
      // Площадка реестра — режим у её поверхности; доп. сайт — его строка в списке настроек.
      const res = r.publisher_id
        ? await api.put(`/traffic-catalog/site-monitor/publisher/${r.publisher_id}`, { site_check: mode }, auth())
        : await api.put('/traffic-catalog/site-monitor/extra-mode', { url: r.url, site_check: mode }, auth())
      fromServer(res.data)
    }
    catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось сменить режим') }
  }
  const saveLists = async () => {
    setBusy('lists'); setMsg('')
    try {
      fromServer((await api.put('/traffic-catalog/site-monitor/settings', { extra, dsp_exclude: exclude }, auth())).data)
      setMsg('Списки сохранены')
    } catch (e) { setMsg(e?.response?.data?.detail || 'Не удалось сохранить') }
    setBusy('')
  }

  const s = q.trim().toLowerCase()
  const shown = rows
    .filter(r => !s || [r.name, r.url].some(v => String(v || '').toLowerCase().includes(s)))
    .sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3)
      || String(a.name || a.url).localeCompare(String(b.name || b.url), 'ru'))
  const count = (st) => rows.filter(r => r.status === st).length

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 14 }}>
        {[['Сайтов на проверке', rows.filter(r => r.mode !== 'off').length, 'var(--text-primary)'],
          ['Доступны', count('ok'), 'var(--income-fg)'],
          ['Антибот', count('antibot'), 'var(--warning-fg)'],
          ['Недоступны', count('down'), count('down') ? 'var(--danger-fg)' : 'var(--text-primary)']]
          .map(([label, v, color]) => (
            <div key={label} style={{ ...card, padding: '13px 16px' }}>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: MONO, color }}>{v}</div>
              <div style={{ ...CAP, marginBottom: 0, marginTop: 2 }}>{label}</div>
            </div>
          ))}
      </div>

      {/* Вторая часть скрипта: сайты, у которых вчера были показы в DSP, а сегодня нет. */}
      {!!dsp && (
        <div style={{ ...card, padding: '10px 14px', marginBottom: 14, fontSize: 12.5,
          background: dsp.missing?.length ? 'var(--warning-tint)' : undefined,
          color: dsp.missing?.length ? 'var(--warning-fg)' : 'var(--text-secondary)' }}>
          <b>Пропали из показов DSP: </b>
          {!dsp.configured ? 'не настроено — нужны доступы админ-кабинета DSP в .env сервера'
            : dsp.missing?.length ? dsp.missing.join(', ')
              : dsp.checked_at ? 'нет — все сайты со вчерашними показами крутятся' : 'ещё не проверялось'}
          {!!dsp.checked_at && <span style={{ fontFamily: MONO, marginLeft: 8, opacity: .7 }}>· {when(dsp.checked_at)}</span>}
        </div>
      )}
      {!!msg && (
        <div style={{ ...card, padding: '9px 14px', marginBottom: 14, fontSize: 12.5,
          color: 'var(--text-secondary)' }}>{msg}</div>
      )}

      <div style={{ ...card, padding: '14px 18px 16px', marginBottom: 14 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <input style={{ ...inp, width: 240 }} placeholder="Площадка или адрес…"
            value={q} onChange={e => setQ(e.target.value)} />
          <span style={{ ...CAP, marginBottom: 0 }}>проверка раз в час · показано {shown.length} из {rows.length}</span>
          <span style={{ flex: 1 }} />
          {mayEdit && (
            <button style={btn(true)} disabled={!!busy} onClick={runAll}>
              {busy === 'all' ? 'Запускаем…' : 'Проверить все сейчас'}</button>
          )}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 1100 }}>
            <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8, borderBottom: '1px solid var(--border-card)' }}>
              {['Сайт', 'Статус', 'Код', 'Способ', 'Проверен', 'В статусе с', 'Ошибка / итоговый адрес', 'Последние 24 проверки']
                .map((l, i) => <SortHead key={l} label={l} right={i === 2} />)}
            </div>
            {[shown.filter(r => r.publisher_id), shown.filter(r => !r.publisher_id)].map((part, pi) => (
              <div key={pi}>
              {/* Доп. сайты вне реестра — вторым списком под разделителем (владелец 30.09.2026). */}
              {pi === 1 && part.length > 0 && (
                <div style={{ ...CAP, marginBottom: 0, marginTop: 14, padding: '8px 0 6px',
                  borderBottom: '1px solid var(--border-card)', color: 'var(--text-secondary)' }}>
                  Доп. сайты вне реестра · {part.length}</div>
              )}
              {part.map(r => {
              const st = ST[r.status]
              return (
                <div key={r.url} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8, alignItems: 'center',
                  padding: '8px 0', borderBottom: '1px solid var(--border-row)' }}>
                  <div style={{ ...cell, overflow: 'hidden' }}>
                    <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.name}
                    </div>
                    <a href={safeHref(r.url)} target="_blank" rel="noreferrer"
                      style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textDecoration: 'none' }}>{r.url}</a>
                  </div>
                  <div style={cell}>
                    {st ? <span title={ST_HINT[r.status]} style={chip(st[1], st[2], 'transparent')}>{st[0]}</span>
                      : <span style={{ color: 'var(--text-faint)' }}>{r.mode === 'off' ? 'выключено' : 'ещё не проверялся'}</span>}
                  </div>
                  <div style={{ ...cell, fontFamily: MONO, textAlign: 'right' }}>{r.http_status ?? '—'}</div>
                  <div style={cell}>
                    {mayEdit ? (
                      <select value={r.mode} onChange={e => setMode(r, e.target.value)}
                        title="Как проверять: браузер — для сайтов, которые режут простой запрос"
                        style={{ ...inp, height: 28, padding: '0 6px', fontSize: 12 }}>
                        {Object.entries(MODE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                    ) : <span style={{ fontSize: 12 }}>{MODE_LABEL[r.mode] || r.mode}</span>}
                  </div>
                  <div style={{ ...cell, fontFamily: MONO, fontSize: 11.5 }}>{when(r.checked_at)}</div>
                  <div style={{ ...cell, fontFamily: MONO, fontSize: 11.5 }}
                    title={r.streak ? `${r.streak} проверок подряд` : undefined}>{when(r.since)}</div>
                  <div style={{ ...cell, fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    title={[r.message, r.final_url].filter(Boolean).join(' · ')}>
                    {r.status === 'ok' ? (r.final_url && r.final_url.replace(/\/$/, '') !== r.url ? `→ ${r.final_url}` : '') : (r.message || '')}
                  </div>
                  <div style={{ ...cell, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ display: 'inline-flex', gap: 2 }}>
                      {(r.history || []).map((h, i) => (
                        <span key={i} title={ST[h]?.[0]} style={{ width: 4, height: 14, borderRadius: 1, background: DOT[h] || 'var(--border-inner)' }} />
                      ))}
                    </span>
                    {mayEdit && r.mode !== 'off' && (
                      <button style={{ ...btn(false), height: 26, padding: '0 8px', fontSize: 11.5 }}
                        disabled={!!busy} onClick={() => runOne(r.url)}>{busy === r.url ? '…' : 'Проверить'}</button>
                    )}
                  </div>
                </div>
              )
            })}
              </div>
            ))}
            {!shown.length && <div style={{ padding: '14px 8px', fontSize: 13, color: 'var(--text-faint)' }}>Ничего не найдено</div>}
          </div>
        </div>
      </div>

      <div style={{ ...card, padding: '14px 18px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <label style={{ fontSize: 12 }}>
          <div style={{ ...CAP, marginBottom: 4 }}>Доп. сайты вне реестра — строка на сайт; «browser» через пробел — проверять браузером; «#» в начале — не проверять</div>
          <textarea value={extra} disabled={!mayEdit} rows={8} onChange={e => setExtra(e.target.value)}
            style={{ ...inp, width: '100%', boxSizing: 'border-box', height: 'auto', padding: 8, fontFamily: MONO, fontSize: 12 }} />
        </label>
        <label style={{ fontSize: 12 }}>
          <div style={{ ...CAP, marginBottom: 4 }}>Исключения для «пропали из показов DSP» — домен на строку</div>
          <textarea value={exclude} disabled={!mayEdit} rows={8} onChange={e => setExclude(e.target.value)}
            style={{ ...inp, width: '100%', boxSizing: 'border-box', height: 'auto', padding: 8, fontFamily: MONO, fontSize: 12 }} />
        </label>
        {mayEdit && (
          <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end' }}>
            <button style={btn(true)} disabled={!!busy} onClick={saveLists}>Сохранить списки</button>
          </div>
        )}
      </div>
    </div>
  )
}
