// «Взаимодействие → Сверки» (хендофф docs/паблишеры взаимодействие.zip, 26.10.2026): плитки-фильтры, месяц,
// жёлтая строка о прошлых месяцах, таблица площадка × месяц. Данные — /api/publisher-recon/board.
import { useCallback, useEffect, useMemo, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, card } from '@/components/salesTableKit'
import { grpDash, monthLabel } from '@/lib/salesFormat'
import { counts, deltaOf, passes, plural, shiftMonth, toneOf } from '@/lib/publisherRecon.mjs'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import ReconModal from './ReconModal'
import { CAPS, Dot, MonthSwitch, StatusPill, Toast, useToast } from './reconKit'

const COLS = 'minmax(150px,0.9fr) minmax(100px,0.6fr) minmax(110px,0.6fr) minmax(110px,0.6fr) minmax(90px,0.5fr) minmax(104px,0.6fr) minmax(168px,0.8fr) minmax(76px,0.4fr) minmax(140px,0.8fr) 112px'
const TILES = [
  ['all', 'Всего площадок', 'var(--text-primary)', 'var(--text-faint)'],
  ['answer', 'Есть ответ', 'var(--violet-fg)', 'var(--violet-fg)'],
  ['waitAll', 'Ожидает', 'var(--warning-fg)', 'var(--warning)'],
  ['ready', 'Готово к отправке', 'var(--accent-fg)', 'var(--accent)'],
  ['closing', 'Ждёт закрытия', 'var(--text-muted)', 'var(--text-faint)'],
  ['done', 'Согласовано', 'var(--income-fg)', 'var(--income)'],
]
const ACT = {
  ready: ['Отправить', 'var(--accent)', 'var(--accent)', 'var(--on-accent)'],
  answer: ['Ответить', 'var(--violet-fg)', 'var(--violet-fg)', 'var(--on-accent)'],
  view: ['Смотреть', 'var(--bg-card)', 'var(--border-card)', 'var(--text-secondary)'],
}

export default function ReconBoard({ month, setMonth, current, canEdit, onAnswers, openPub, setOpenPub }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState(null)
  const [busy, setBusy] = useState(false)
  const [toast, flash] = useToast()

  const load = useCallback(() => {
    api.get(`/publisher-recon/board?period=${month}`, auth())
      .then(r => { setData(r.data); setErr('') })
      .catch(e => { setData(null); setErr(e?.response?.data?.detail || 'Не удалось загрузить сверки') })
  }, [month])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  const rows = useMemo(() => data?.rows || [], [data])
  const c = useMemo(() => counts(rows), [rows])
  useEffect(() => { onAnswers?.(c.answer) }, [c.answer, onAnswers])
  const shown = rows.filter(r => passes(r, filter))

  const send = async (r) => {
    setBusy(true)
    try {
      await api.post('/publisher-recon/send', { publisher_id: r.publisher_id, period: month }, auth())
      flash(`${r.site}: сверка отправлена`)
      load()
    } catch (e) { flash(e?.response?.data?.detail || 'Не удалось отправить') } finally { setBusy(false) }
  }
  const sendAll = async () => {
    if (!c.ready || busy) return
    setBusy(true)
    try {
      const { data: d } = await api.post('/publisher-recon/send-all', { period: month }, auth())
      flash(`Отправлено площадкам: ${d.sent}`)
      load()
    } catch (e) { flash(e?.response?.data?.detail || 'Не удалось отправить') } finally { setBusy(false) }
  }

  const tileVal = { all: c.all, answer: c.answer, waitAll: c.wait + c.late, ready: c.ready, closing: c.closing, done: c.done }
  const tileHint = { answer: 'ход за нами', waitAll: c.late ? `просрочено ${c.late}` : 'в срок', closing: 'РК в размещении' }
  const label = monthLabel(month)
  const filterNote = filter && filter !== 'all'
    ? 'фильтр: ' + TILES.find(t => t[0] === filter)[1].toLowerCase() : 'сначала «есть ответ», внутри — по сумме'

  return (
    <>
      <div style={{ ...card, display: 'grid', gridTemplateColumns: 'repeat(6,minmax(0,1fr))', overflow: 'hidden' }}>
        {TILES.map(([key, lab, fg, dot], i) => {
          const on = filter === key || (key === 'all' && !filter)
          return (
            <div key={key} onClick={() => setFilter(f => (f === key || key === 'all' ? null : key))}
              style={{ padding: '14px 20px', display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0, cursor: 'pointer',
                borderLeft: `1px solid ${i ? 'var(--border-inner)' : 'transparent'}`, background: on ? 'var(--bg-tint)' : 'transparent' }}>
              <span style={{ ...CAPS, display: 'inline-flex', alignItems: 'center', gap: 7, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                <Dot c={dot} size={7} />{lab}
              </span>
              <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: fg }}>{tileVal[key]}</span>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tileHint[key] || ' '}</span>
            </div>
          )
        })}
      </div>

      <div style={{ ...card, padding: '14px 18px 12px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingBottom: 10, minWidth: 0 }}>
          <span style={{ fontSize: 16, fontWeight: 700, whiteSpace: 'nowrap' }}>Сверки · {label}</span>
          <span style={{ ...CAPS, fontSize: 9.5, color: 'var(--text-faint)', fontWeight: 400, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            строка — площадка × отчётный месяц · {filterNote}</span>
          {filter && filter !== 'all' && (
            <span onClick={() => setFilter(null)} style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer', whiteSpace: 'nowrap' }}>сбросить фильтр</span>)}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
            <MonthSwitch title={label.charAt(0).toUpperCase() + label.slice(1)} canPrev={month > (data?.start || '2026-10')}
              canNext={month < current} onPrev={() => setMonth(shiftMonth(month, -1))} onNext={() => setMonth(shiftMonth(month, 1))} />
            {month !== current && (
              <span onClick={() => setMonth(current)} style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer', whiteSpace: 'nowrap' }}>к текущему</span>)}
            {canEdit && (
              <span onClick={sendAll} title={c.ready ? 'Активировать карточки в кабинетах всех готовых площадок' : 'Готовых сверок нет'}
                style={{ display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 16px', borderRadius: 10, fontSize: 12.5, fontWeight: 700, color: 'var(--on-accent)', whiteSpace: 'nowrap',
                  background: c.ready && !busy ? 'var(--accent)' : 'var(--text-disabled)', cursor: c.ready && !busy ? 'pointer' : 'default' }}>
                Отправить все готовые&nbsp;·&nbsp;{c.ready}</span>)}
          </span>
        </div>

        {month === current && (data?.past || []).map(p => (
          <div key={p.period} style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '0 0 10px', padding: '9px 12px', background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
            <Dot c="var(--warning)" size={7} />
            <span style={{ fontSize: 12.5, color: 'var(--warning-fg)' }}>
              За {monthLabel(p.period).split(' ')[0]} не согласовано {p.count} {plural(p.count, 'сверка', 'сверки', 'сверок')} — итог не ушёл в себестоимость и ОРД</span>
            <span onClick={() => setMonth(p.period)} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 12px', borderRadius: 10, border: '1px solid var(--warning-border)', background: 'var(--bg-card)', color: 'var(--warning-fg)', fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', cursor: 'pointer' }}>
              Открыть {monthLabel(p.period).split(' ')[0]}</span>
          </div>
        ))}

        {err && <div style={{ padding: '18px 0', fontSize: 13, color: 'var(--danger-fg)' }}>{err}</div>}
        {data && !data.active && <div style={{ padding: '28px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Сверки ведутся с октября 2026 — раньше месяцы закрывались без них.</div>}

        {data?.active && (
          <div style={{ overflowX: 'auto', overflowY: 'hidden', margin: '0 -6px', padding: '0 6px' }}>
            <div style={{ minWidth: 1240, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, padding: '0 10px 8px', borderBottom: '1px solid var(--border-card)', ...CAPS, fontSize: 9, fontWeight: 400, letterSpacing: '0.08em' }}>
                <span>Площадка</span><span>Кампании</span><span style={{ textAlign: 'right' }}>Показы · наши</span><span style={{ textAlign: 'right' }}>Показы · площадки</span>
                <span style={{ textAlign: 'right' }}>Δ</span><span style={{ textAlign: 'right' }}>Сумма, ₽</span><span>Статус</span><span>Срок</span><span>Переписка</span><span />
              </div>
              {shown.map(r => <Row key={r.publisher_id} r={r} canEdit={canEdit} busy={busy}
                onOpen={() => setOpenPub(r.publisher_id)} onSend={() => send(r)} />)}
            </div>
          </div>
        )}
        {data?.active && !shown.length && (
          <span style={{ padding: '28px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
            {rows.length ? 'Под фильтр ничего не попало' : 'За этот месяц размещений нет'}</span>)}
        <span style={{ padding: '10px 10px 0', fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          «Готово» — все РК площадки за месяц окончены. «Ждёт закрытия» — есть РК в размещении: сверку не отправить. Сверка не блокирует сделки аккаунтов и не меняет прайс клиенту — меняется только себестоимость.</span>
      </div>

      {openPub && <ReconModal publisherId={openPub} period={month} canEdit={canEdit}
        onClose={() => setOpenPub(null)} onChanged={(msg) => { if (msg) flash(msg); load() }} />}
      <Toast text={toast} />
    </>
  )
}

function Row({ r, canEdit, busy, onOpen, onSend }) {
  const T = toneOf(r)
  const d = deltaOf(r.ours, r.theirs)
  const dFg = d.tone === 'none' ? 'var(--text-disabled)' : d.tone === 'zero' ? 'var(--income-fg)' : 'var(--warning-fg)'
  const act = T.key === 'closing' ? null : T.key === 'ready' ? (canEdit ? ACT.ready : ACT.view) : T.key === 'answer' && canEdit ? ACT.answer : ACT.view
  const full = r.total && r.done >= r.total
  return (
    <div onClick={onOpen} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', padding: '9px 10px', borderBottom: '1px solid var(--border-row)', borderRadius: 9, cursor: 'pointer' }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-subtle)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
      <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.site}</span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontFamily: MONO, fontSize: 11, color: r.orphan ? 'var(--warning-fg)' : 'var(--text-secondary)' }}
          title={r.orphan ? 'Сверка отправлена, а размещений площадки за этот месяц больше нет — сделку перенесли или удалили' : undefined}>
          {r.orphan ? 'нет размещений' : `${r.done} / ${r.total}`}</span>
        <span style={{ display: 'block', height: 4, borderRadius: 2, background: 'var(--border-inner)', overflow: 'hidden' }}>
          <span style={{ display: 'block', height: 4, width: `${r.total ? r.done / r.total * 100 : 0}%`, background: full ? 'var(--income)' : 'var(--warning)' }} /></span>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, textAlign: 'right' }}>{grpDash(r.ours)}</span>
      <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right', color: r.theirs != null ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{r.theirs != null ? grpDash(r.theirs) : '—'}</span>
      <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: dFg }}>{d.text}</span>
        <span style={{ fontFamily: MONO, fontSize: 9.5, color: dFg }}>{d.pct}</span>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, textAlign: 'right', color: r.cpm ? 'var(--text-primary)' : 'var(--warning-fg)' }}>
        {r.cpm ? grpDash(r.amount) : 'нет CPM'}</span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <StatusPill t={T} />
        {r.changed && <span title={`После итога наш факт сейчас ${grpDash(r.fact_now)}; итог не пересчитывается`}
          style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}>изменилось после итога</span>}
      </span>
      <span style={{ fontFamily: MONO, fontSize: 11, whiteSpace: 'nowrap', color: T.key === 'late' ? 'var(--danger-fg)' : 'var(--text-secondary)' }}>
        {(T.key === 'wait' || T.key === 'late') && r.due_at ? 'до ' + r.due_at.slice(8, 10) + '.' + r.due_at.slice(5, 7) : ''}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0, overflow: 'hidden', fontFamily: MONO, fontSize: 11, whiteSpace: 'nowrap',
        color: r.new ? 'var(--violet-fg)' : r.messages ? 'var(--text-secondary)' : 'var(--text-disabled)', fontWeight: r.new ? 700 : 500 }}>
        <Dot c={r.new ? 'var(--violet-fg)' : r.messages ? 'var(--text-faint)' : 'transparent'} size={6} />
        {r.messages ? `${r.messages} сообщ.${r.new ? ' · новое' : ''}` : '—'}</span>
      <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {act && (
          <span onClick={e => { e.stopPropagation(); if (act === ACT.ready) { if (!busy) onSend() } else onOpen() }}
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 112, height: 28, boxSizing: 'border-box', borderRadius: 10,
              background: act[1], border: `1px solid ${act[2]}`, color: act[3], fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>{act[0]}</span>)}
      </span>
    </div>
  )
}

