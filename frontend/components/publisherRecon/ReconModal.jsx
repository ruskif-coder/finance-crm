// Модалка сверки площадки за месяц (хендофф 26.10.2026): наши / площадки / итог менеджера, кампании, переписка.
// «Ответить площадке» уходит вместе с цифрой из поля итога — в кабинете она становится «предлагает N».
import { useCallback, useEffect, useRef, useState } from 'react'
import useLatest from '@/lib/useLatest'
import api, { auth } from '@/lib/http'
import { MONO, Modal } from '@/components/salesTableKit'
import { grpDash, monthLabel } from '@/lib/salesFormat'
import { downloadFile } from '@/lib/download'
import { fmtDayOfMoment, fmtDayTime } from '@/lib/dates'
import { SVC_DOT } from '@/lib/masterStatus'
import { money, parseShows, toneOf } from '@/lib/publisherRecon.mjs'
import { CAPS, Dot, StatusPill, actBtn } from './reconKit'

const CAMP = 'minmax(160px,1.5fr) minmax(104px,0.8fr) 50px 98px 96px 92px 92px'
const dm = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}` : '')
const rub = (v) => (v == null ? 'нет CPM' : `${grpDash(v)} ₽`)

const HINT = {
  ready: (r) => `Карточка появится в кабинете площадки; срок ответа — 2 рабочих дня.`,
  wait: () => 'Ход за площадкой. Итог можно зафиксировать и без ответа.',
  late: () => 'Срок ответа прошёл. Напомните или зафиксируйте итог без ответа.',
  answer: () => 'Без возврата: в базу пишутся наша цифра, цифра площадки и итог; итог раскладывается по РК периода пропорционально доле.',
  closing: () => 'Есть РК в размещении — сверку не отправить. Станет «готово» само, когда окончатся все РК.',
  done: (r) => `Согласовано ${fmtDayOfMoment(r.decided_at)}${r.decided_by ? ' · ' + r.decided_by : ''}. Итог зафиксирован.`
    + (r.changed ? ` После итога наш факт или состав размещений изменился (сейчас ${grpDash(r.fact_now)}) — итог не пересчитывается.` : ''),
}


export default function ReconModal({ publisherId, period, canEdit, onClose, onChanged }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [final, setFinal] = useState('')
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)

  const latest = useLatest()
  const finalSet = useRef(false)     // итог подставляем один раз: после «Ответить» перечитывание стирало набранную цифру
  const load = useCallback(() => {
    const fresh = latest()
    api.get(`/publisher-recon/detail?publisher_id=${publisherId}&period=${period}`, auth())
      .then(r => {
        if (!fresh()) return
        setD(r.data); setErr('')
        const row = r.data.row
        if (!finalSet.current || row.agreed != null) { setFinal(String(row.agreed ?? row.theirs ?? row.ours)); finalSet.current = true }
      })
      .catch(e => { if (fresh()) setErr(e?.response?.data?.detail || 'Не удалось открыть сверку') })
  }, [publisherId, period, latest])
  useEffect(() => { finalSet.current = false; load() }, [load])

  const run = async (fn, okMsg) => {
    if (busy) return
    setBusy(true)
    try { await fn(); onChanged?.(okMsg); load(); setReply('') } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось сохранить') } finally { setBusy(false) }
  }

  if (!d) {
    return (
      <Modal title="Сверка" width={520} onClose={onClose}>
        <div style={{ padding: '18px 0', fontSize: 13, color: err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>{err || 'Загружаю…'}</div>
      </Modal>
    )
  }
  const r = d.row
  const T = toneOf(r)
  const k = T.key
  const fin = parseShows(final)
  const fd = fin == null ? null : fin - r.ours
  const locked = k === 'done' || k === 'closing' || !canEdit
  const rid = r.request_id

  const send = () => run(() => api.post('/publisher-recon/send', { publisher_id: r.publisher_id, period }, auth()), `${r.site}: сверка отправлена`)
  const remind = () => run(() => api.post(`/publisher-recon/${rid}/remind`, {}, auth()), 'Напоминание отправлено')
  const agree = () => {
    if (fin == null) { setErr('Укажите итог показов'); return }
    run(() => api.post(`/publisher-recon/${rid}/agree`, { volume: fin }, auth()), `${r.site}: итог ${grpDash(fin)} зафиксирован`)
  }
  const answer = () => {
    if (!reply.trim()) { setErr('Напишите ответ площадке'); return }
    const fd2 = new FormData()
    fd2.append('body', reply)
    if (fin != null) fd2.append('volume', String(fin))
    run(() => api.post(`/publisher-recon/${rid}/reply`, fd2, auth()), 'Ответ отправлен · срок снова +2 раб. дня')
  }

  const buttons = !canEdit ? [] : k === 'ready' ? [['Отправить площадке', send, 'p']]
    : (k === 'wait' || k === 'late') ? [['Напомнить', remind, 'g'], [`Согласовать итог ${grpDash(fin)}`, agree, 'ok']]
      : k === 'answer' ? [['Ответить площадке', answer, 'g'], [`Согласовать итог ${grpDash(fin)}`, agree, 'ok']]
        : k === 'closing' ? [['Отправить', null, 'off']] : []

  const title = (
    <span style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700 }}>{r.site}</span>
      <span style={{ fontSize: 15, fontWeight: 700 }}>· сверка за {monthLabel(period)}</span>
      <StatusPill t={T} />
    </span>
  )
  const meta = `кампаний ${r.done} из ${r.total} окончены · CPM договора ${r.cpm ? r.cpm + ' ₽' : 'не задан'}`
    + ((k === 'wait' || k === 'late') && r.due_at ? ` · ответ площадки до ${dm(r.due_at)}` : '')
  const lastTheirs = [...(d.thread || [])].reverse().find(m => m.side === 'площадка' && m.volume != null)

  return (
    <Modal width={1240} onClose={onClose} title={title}
      summary={<span style={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.04em', color: 'var(--text-muted)' }}>{meta}</span>}
      footer={<>
        <span style={{ fontSize: 12, color: err ? 'var(--danger-fg)' : 'var(--text-muted)', lineHeight: 1.45, flex: '1 1 300px' }}>{err || HINT[k](r)}</span>
        {buttons.map(([label, fn, kind]) => (
          <button key={label} type="button" disabled={!fn || busy} onClick={fn || undefined} style={actBtn(kind, !fn || busy)}>{label}</button>))}
      </>}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 12, padding: '6px 0 0' }}>
        <Tile cap="Показы · наши данные" value={grpDash(r.ours)} note={`${rub(money(r.ours, r.cpm))} · за вычетом Block SIMB`} />
        <Tile cap="Показы · данные площадки" value={r.theirs != null ? grpDash(r.theirs) : '—'} faint={r.theirs == null}
          note={r.theirs != null ? `${rub(money(r.theirs, r.cpm))}${lastTheirs ? ' · прислано ' + fmtDayOfMoment(lastTheirs.created_at) : ''}` : 'площадка ещё не ответила'} />
        <span style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '12px 14px', background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', borderRadius: 14 }}>
          <span style={{ ...CAPS, fontSize: 9, fontWeight: 400, letterSpacing: '0.08em', color: 'var(--accent-fg)' }}>Итог сверки — решение менеджера</span>
          {locked ? (
            <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, color: k === 'done' ? 'var(--income-fg)' : 'var(--text-disabled)' }}>
              {k === 'done' ? grpDash(r.agreed) : '—'}</span>
          ) : (<>
            <input value={final} onChange={e => setFinal(e.target.value)} inputMode="numeric"
              style={{ width: '100%', boxSizing: 'border-box', height: 36, padding: '0 10px', background: 'var(--bg-card)', border: '1px solid var(--accent-border)', borderRadius: 12, fontFamily: MONO, fontSize: 17, fontWeight: 700, outline: 'none' }} />
            <span style={{ display: 'flex', gap: '4px 12px', flexWrap: 'wrap', fontSize: 11.5, whiteSpace: 'nowrap' }}>
              <span onClick={() => setFinal(String(r.ours))} style={{ color: 'var(--accent)', fontWeight: 600, cursor: 'pointer' }}>взять нашу</span>
              {r.theirs != null && <span onClick={() => setFinal(String(r.theirs))} style={{ color: 'var(--accent)', fontWeight: 600, cursor: 'pointer' }}>взять площадки</span>}
            </span>
          </>)}
          {(k !== 'closing') && fin != null && (
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{rub(money(k === 'done' ? r.agreed : fin, r.cpm))} · <span
              style={{ color: fd === 0 ? 'var(--text-muted)' : 'var(--warning-fg)' }}>
              {k === 'done' ? '' : fd === 0 ? 'как наша' : `${fd > 0 ? '+' : '−'}${grpDash(Math.abs(fd))} к нашей`}</span></span>)}
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, padding: '16px 0 6px' }}>
        <div style={{ flex: '1 1 760px', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingBottom: 8, minWidth: 0 }}>
            <span style={{ fontSize: 13.5, fontWeight: 700, whiteSpace: 'nowrap' }}>Кампании периода</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>детализация — согласуется итог месяца</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: CAMP, gap: 10, padding: '0 4px 6px', borderBottom: '1px solid var(--border-card)', ...CAPS, fontSize: 8.5, fontWeight: 400, letterSpacing: '0.08em' }}>
            <span>Рекламодатель · бренд</span><span>Услуга</span><span>Пов.</span><span>Флайт</span><span>ЕРИД</span><span style={{ textAlign: 'right' }}>Показы</span><span style={{ textAlign: 'right' }}>Сумма</span>
          </div>
          {d.campaigns.map(c => (
            <div key={c.placement_id} style={{ display: 'grid', gridTemplateColumns: CAMP, gap: 10, alignItems: 'center', padding: '6px 4px', borderBottom: '1px solid var(--border-row)' }}>
              <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.brand}</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                <Dot c={c.service_color || SVC_DOT[c.service] || 'var(--text-faint)'} />{c.service || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 10, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{c.surface || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-secondary)' }}>{dm(c.date_from)} — {dm(c.date_to)}</span>
              <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.erid || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right' }}>{grpDash(c.fact)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right' }}>{c.amount == null ? '—' : grpDash(c.amount)}</span>
            </div>))}
          <div style={{ display: 'grid', gridTemplateColumns: CAMP, gap: 10, padding: '8px 4px 0', fontWeight: 700 }}>
            <span style={{ ...CAPS, fontSize: 9, letterSpacing: '0.08em' }}>Итого · {d.campaigns.length} РК</span><span /><span /><span /><span />
            <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{grpDash(r.ours)}</span>
            <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{r.cpm ? grpDash(money(r.ours, r.cpm)) : '—'}</span>
          </div>
        </div>

        <div style={{ flex: '0 1 320px', display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 16, borderLeft: '1px solid var(--border-inner)', minWidth: 260 }}>
          <span style={{ fontSize: 13.5, fontWeight: 700 }}>Переписка</span>
          {(d.thread || []).map(m => m.side === 'система' ? (
            <span key={m.id} style={{ alignSelf: 'center', textAlign: 'center', fontSize: 11, color: 'var(--text-muted)' }}>{m.body} · {fmtDayTime(m.created_at)}</span>
          ) : (
            <span key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '8px 10px', borderRadius: 14,
              background: m.side === 'мы' ? 'var(--bg-tint)' : 'var(--bg-subtle)', border: `1px solid ${m.side === 'мы' ? 'var(--accent-border)' : 'var(--border-inner)'}` }}>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                {m.side === 'мы' ? 'SIMB-AD' : 'площадка'}{m.author_name ? ' · ' + m.author_name : ''} · {fmtDayTime(m.created_at)}</span>
              {m.body && <span style={{ fontSize: 12, lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>{m.body}</span>}
              {m.volume != null && <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent-fg)' }}>предлагает {grpDash(m.volume)}</span>}
              {m.files.map(f => (
                <span key={f.id} onClick={() => downloadFile(`/publisher-recon/file/${f.id}`, f.name, setErr)}
                  style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--accent)', cursor: 'pointer' }}>↓ {f.name}</span>))}
            </span>
          ))}
          {!(d.thread || []).some(m => m.side !== 'система') && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Сообщений нет</span>}
          {canEdit && rid && k !== 'done' && (
            <textarea value={reply} onChange={e => setReply(e.target.value)} placeholder="Ответ площадке — уйдёт вместе с цифрой из поля итога"
              style={{ width: '100%', boxSizing: 'border-box', minHeight: 64, padding: '8px 10px', border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 12, resize: 'vertical', outline: 'none', fontFamily: 'inherit' }} />)}
        </div>
      </div>
    </Modal>
  )
}

function Tile({ cap, value, note, faint }) {
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '12px 14px', background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 14 }}>
      <span style={{ ...CAPS, fontSize: 9, fontWeight: 400, letterSpacing: '0.08em' }}>{cap}</span>
      <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, color: faint ? 'var(--text-disabled)' : 'var(--text-primary)' }}>{value}</span>
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{note}</span>
    </span>
  )
}
