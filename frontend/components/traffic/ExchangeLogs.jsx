// Вкладка «Логи» админки трафика (владелец 01.10.2026): обмен с DSP и с Weborama, каждая
// строка — сделка + площадка + креатив. Сводит сервер (`/traffic-balancer/logs`,
// app/traffic/logs.py); здесь только показ, фильтры и раскрытие тела запроса/ответа.
import { Fragment, useCallback, useEffect, useState } from 'react'
import { MONO, btnSm, card, inp, th } from '@/components/salesTableKit'
import api, { auth } from '@/lib/api'
import { fmtDateTime } from '@/lib/dates'

const GRID = '138px 82px 150px minmax(0,1fr) minmax(0,1.1fr) 70px'

export default function ExchangeLogs() {
  const [sys, setSys] = useState('dsp')
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [deal, setDeal] = useState('')
  const [onlyErr, setOnlyErr] = useState(false)
  const [prodOnly, setProdOnly] = useState(true)
  const [open, setOpen] = useState(null)

  const load = useCallback(async () => {
    setErr(''); setRows(null)
    try {
      const q = new URLSearchParams({ system: sys, limit: '300', only_errors: String(onlyErr),
        prod_only: String(prodOnly) })
      if (deal.trim()) q.set('deal', deal.trim())
      const r = await api.get(`/traffic-balancer/logs?${q}`, auth())
      setRows(r.data.rows)
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Не удалось загрузить лог'); setRows([])
    }
  }, [sys, onlyErr, prodOnly, deal])

  useEffect(() => { load() }, [sys, onlyErr, prodOnly]) // eslint-disable-line react-hooks/exhaustive-deps

  // Подпись колонки — стиль заголовка из кита, без его отступов и линии (сетка, не таблица).
  const head = { ...th, padding: 0, borderBottom: 'none' }
  return (
    <div style={{ ...card, padding: 16 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        {[['dsp', 'DSP'], ['weborama', 'Weborama']].map(([k, l]) => (
          <button key={k} style={btnSm(sys === k)} onClick={() => { setSys(k); setOpen(null) }}>{l}</button>
        ))}
        <input style={{ ...inp, width: 150, fontFamily: MONO, fontSize: 12, padding: '6px 9px' }}
          placeholder="код сделки" value={deal} onChange={e => setDeal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') load() }} />
        <button style={btnSm(false)} onClick={load}>найти</button>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'inline-flex', gap: 5, alignItems: 'center' }}>
          <input type="checkbox" checked={onlyErr} onChange={e => setOnlyErr(e.target.checked)} /> только ошибки
        </label>
        {sys === 'dsp' && (
          <label title="Демо-экран DSP пишет в тот же журнал с пометкой demo"
            style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'inline-flex', gap: 5, alignItems: 'center' }}>
            <input type="checkbox" checked={prodOnly} onChange={e => setProdOnly(e.target.checked)} /> только боевые
          </label>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-faint)' }}>
          {rows ? `${rows.length} записей, новые сверху` : 'загрузка…'}
        </span>
      </div>
      {err && <div style={{ color: 'var(--danger-fg)', fontSize: 12.5, marginBottom: 8 }}>⚠ {err}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '6px 4px',
        borderBottom: '1px solid var(--border-inner)' }}>
        {['Время', 'Сделка', 'Площадка', 'Креатив', 'Вызов', 'Итог'].map(h => <span key={h} style={head}>{h}</span>)}
      </div>
      {rows && !rows.length && !err && (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-faint)', fontSize: 12.5 }}>Записей нет</div>
      )}
      {(rows || []).map(r => {
        const on = open === r.id
        return (
          <Fragment key={r.id}>
            <div onClick={() => setOpen(on ? null : r.id)}
              style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '7px 4px', cursor: 'pointer',
                borderBottom: '1px solid var(--border-row)', background: on ? 'var(--bg-subtle)' : 'transparent',
                fontSize: 12, alignItems: 'baseline' }}>
              <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)' }}>{fmtDateTime(r.ts)}</span>
              <span style={{ fontFamily: MONO, fontWeight: 700, color: r.deal ? 'var(--accent)' : 'var(--text-faint)' }}>{r.deal || '—'}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.publisher || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                color: r.creative ? 'var(--text-primary)' : 'var(--text-faint)' }}>{r.creative || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                title={r.method}>{r.method}</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: r.ok ? 'var(--income-fg)' : 'var(--danger-fg)' }}
                title={r.error || undefined}>{r.ok ? 'ок' : 'ошибка'}</span>
            </div>
            {on && (
              <div style={{ padding: '8px 4px 12px', borderBottom: '1px solid var(--border-row)', fontSize: 11.5,
                display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {r.entity} · ссылка {String(r.ref ?? '—')}{r.hash ? ` · хеш ${r.hash}` : ''}
                  {r.http_status ? ` · HTTP ${r.http_status}` : ''}{r.contour ? ` · контур ${r.contour}` : ''}
                </span>
                {r.error && <span style={{ color: 'var(--danger-fg)' }}>{r.error}</span>}
                {[['запрос', r.request], ['ответ', r.response]].filter(([, v]) => v).map(([l, v]) => (
                  <div key={l}>
                    <span style={head}>{l}</span>
                    <pre style={{ margin: '4px 0 0', padding: 8, background: 'var(--bg-subtle)', borderRadius: 8,
                      fontFamily: MONO, fontSize: 10.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                      maxHeight: 220, overflow: 'auto' }}>{v}</pre>
                  </div>
                ))}
              </div>
            )}
          </Fragment>
        )
      })}
    </div>
  )
}
