// Окно «Запустить РК» (владелец 01.10.2026, первый боевой запуск 54ZYCH). Раньше запуск
// спрашивал confirm только про ОТКЛЮЧЁННЫЕ площадки и не поднимал «ждёт запуска» вовсе —
// РК запускалась, а площадки приходилось включать по одной. Теперь план по каждой
// площадке считает сервер (`/campaign/{id}/start-plan`, то же правило, что у кнопки
// площадки), человек видит, что поднимется и что нет и почему, а после запуска — итог:
// статус в DSP, сверку, перевод сделки по стадии.
import { useEffect, useState } from 'react'
import { Modal, btnSm, primaryBtn, MONO, th, td } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'
import api from '@/lib/api'

const ACT = {
  start:   ['поднимется', 'var(--income-fg)', 'var(--income-tint)'],
  running: ['уже крутит', 'var(--accent)', 'var(--accent-tint)'],
  skip:    ['не поднимется', 'var(--warning-text)', 'var(--warning-tint)'],
}

export default function StartRkModal({ row, auth, onClose, onDone, note }) {
  const [plan, setPlan] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)

  useEffect(() => {
    let alive = true
    api.get(`/traffic-dashboard/campaign/${row.id}/start-plan`, auth())
      .then(r => { if (alive) setPlan(r.data) })
      .catch(e => { if (alive) setErr(e?.response?.data?.detail || 'Не удалось получить план запуска') })
    return () => { alive = false }
  }, [row.id, auth])

  const go = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.put(`/traffic-dashboard/campaign/${row.id}/status`,
        { status: 'запущена', with_placements: true }, auth())
      setRes(r.data)
      // План перечитываем: окно должно показать, что площадки действительно «запущен»,
      // а не то, что мы надеялись поднять.
      const p = await api.get(`/traffic-dashboard/campaign/${row.id}/start-plan`, auth())
      setPlan(p.data)
      onDone && onDone()
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Не удалось запустить РК')
    } finally { setBusy(false) }
  }

  const summary = plan
    ? `Поднимется площадок: ${plan.start} · уже крутят: ${plan.running} · не поднимутся: ${plan.skip}`
    : null
  const footer = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
      {err && <span style={{ fontSize: 12.5, color: 'var(--danger-fg)', marginRight: 'auto' }}>⚠ {err}</span>}
      <button style={btnSm(false)} onClick={onClose} disabled={busy}>{res ? 'Закрыть' : 'Отмена'}</button>
      {!res && (
        <button style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 8,
          cursor: busy ? 'progress' : 'pointer', opacity: !plan || plan.dsp_block ? 0.6 : 1 }}
          disabled={busy || !plan || !!plan.dsp_block} onClick={go}>
          {busy && <Cube variant="spinner" size={14} />}
          {busy ? 'запускаю площадки…' : plan?.start ? `Запустить РК и ${plan.start} площ.` : 'Запустить РК'}
        </button>
      )}
    </div>
  )

  return (
    <Modal title={`Запуск РК · ${row.deal_code}`} summary={summary} footer={footer} width={720}
      onClose={() => { if (!busy) onClose() }}>
      {!plan && !err && <div style={{ padding: 16, color: 'var(--text-muted)' }}>считаю план…</div>}
      {plan?.dsp_block && (
        <div style={{ padding: '8px 0', color: 'var(--danger-fg)', fontSize: 13 }}>⚠ {plan.dsp_block}</div>
      )}
      {res && (
        <div style={{ padding: '10px 12px', margin: '6px 0 10px', borderRadius: 10, background: 'var(--income-tint)',
          color: 'var(--income-fg)', fontSize: 13, lineHeight: 1.5 }}>
          РК {res.status}{res.placements_raised ? ` · поднято площадок: ${res.placements_raised}` : ''}
          {note ? note(res) : ''}
          {res.stage?.moved && <div>Сделка переведена в «{res.stage.stage}».</div>}
          {res.stage?.refused && <div style={{ color: 'var(--warning-text)' }}>⚠ {res.stage.refused}</div>}
          {res.targeting && (res.targeting.woken
            ? <div>Нацеливание для скриншотов включено на 2 дня: комплектов {res.targeting.woken}.</div>
            : null)}
          {!!res.targeting?.errors?.length && (
            <div style={{ color: 'var(--warning-text)' }}>⚠ Нацеливание: {res.targeting.errors.join('; ')}</div>
          )}
        </div>
      )}
      {busy && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', color: 'var(--accent)', fontSize: 13 }}>
          <Cube variant="spinner" size={14} /> Запускаю РК и площадки в DSP, сверяю статусы — это несколько секунд
        </div>
      )}
      {plan && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr>
              <th style={th}>Площадка</th>
              <th style={th}>Сейчас</th>
              <th style={th}>При запуске</th>
            </tr>
          </thead>
          <tbody>
            {plan.rows.map(r => {
              const [label, fg, bg] = ACT[r.action]
              return (
                <tr key={r.placement_id}>
                  <td style={{ ...td, padding: '7px 10px' }}>
                    <div style={{ fontWeight: 600 }}>{r.publisher}</div>
                    {r.external && <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>не наш код — заводится вручную</div>}
                  </td>
                  <td style={{ ...td, padding: '7px 10px', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)' }}>{r.status}</td>
                  <td style={{ ...td, padding: '7px 10px' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 6, color: fg, background: bg }}>{label}</span>
                    {r.why && <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 3 }}>{r.why}</div>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </Modal>
  )
}
