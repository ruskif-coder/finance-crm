// «Согласования → Подвисшие» (владелец 03.10.2026): экран менеджера паблишеров — что
// подвисло на площадках. Данные — /publisher-approvals/stuck (app/launch_prep/stuck.py).
//
// Вид — хендофф docs/подвисшие.zip (design_handoff_publishers_stuck): KPI, одна карточка
// списка на всю оставшуюся высоту со скроллом внутри, шапка колонок на одной сетке со
// строками; строка — информация слева, замечание площадки справа. Группы по площадке
// (звонят площадке, а не по сделке), внутри — старшие сверху. Цвет = состояние:
// доработка — синий (действие за нами), ждём — жёлтый, отказ — красный.
// Без периода: всё, что висит сейчас по сделкам до «Итоговой сверки». Только переходы.
// Горящие (старт прошёл) — сверху внутри площадки, площадки с горящими — первыми.
import { useCallback, useEffect, useMemo, useState } from 'react'
import api, { auth } from '@/lib/http'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { MONO, UI } from '@/components/salesTableKit'
import { tgHref } from '@/components/publishers/kit'
import safeHref from '@/lib/safeHref'

const ST = {
  rework:  { label: 'на доработке', bg: 'var(--accent-tint)', bd: 'var(--accent-border)', fg: 'var(--accent-fg)', dot: 'var(--accent)', event: 'вернули' },
  waiting: { label: 'ждём ответа', bg: 'var(--warning-tint)', bd: 'var(--warning-border)', fg: 'var(--warning-fg)', dot: 'var(--warning)', event: 'отправили' },
  refused: { label: 'отказ', bg: 'var(--danger-tint)', bd: 'var(--danger-border)', fg: 'var(--danger-fg)', dot: 'var(--danger)', event: 'отказали' },
}
const FILTERS = [['', 'Всё'], ['burning', 'горит'], ['waiting', 'ждём ответа'], ['rework', 'на доработке'], ['refused', 'отказ']]
// Старт размещения у площадки (владелец 03.10.2026): то же правило и те же слова, что в
// кабинете площадки — старт прошёл = горит, ≤ 3 раб. дн. = срочно, иначе терпит.
const URG = {
  burning: { label: 'горит', fg: 'var(--danger-fg)' },
  urgent:  { label: 'срочно', fg: 'var(--warning-fg)' },
  calm:    { label: 'терпит', fg: 'var(--text-faint)' },
}
// Нет поля — «терпит»: экран не падает на ответе старого бэкенда (случай 03.10.2026).
const urgOf = (r) => URG[r.urgency] || URG.calm
const matches = (r, k) => !k || (k === 'burning' ? r.urgency === 'burning' : r.kind === k)
const COLS = '120px 120px minmax(180px,0.85fr) 104px minmax(0,1.6fr) 28px'
const PAD = '0 24px'
const CAPS = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const panel = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
const ellipsis = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }

const days = (n) => `${n} раб. дн.`
const startTxt = (r) => (r.start ? `старт ${ddmm(r.start)} · ${urgOf(r).label}` : 'старт не задан')
const ddmm = (iso) => (iso ? String(iso).slice(0, 10).split('-').reverse().slice(0, 2).join('.') : '—')
const creativeOf = (r) => `№${r.set_no}${r.title ? ` · ${r.title}` : ''}`
const twinKey = (r) => `${r.deal_id}|${r.set_no}|${r.title || ''}`
const TG_PATH = 'M21.5 3.6L2.9 10.8c-1.3.5-1.3 1.2-.2 1.5l4.8 1.5 1.8 5.6c.2.6.4.8.9.8.4 0 .6-.2.9-.4l2.3-2.2 4.7 3.5c.9.5 1.5.2 1.7-.8l3.1-14.6c.3-1.3-.5-1.8-1.4-1.5zM8.8 13.4l9.7-6.1c.5-.3.9-.1.5.2l-8 7.3-.3 3.4-1.9-4.8z'

function ChatIcon({ href, kind }) {
  const tg = kind === 'tg'
  const box = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7,
    fontFamily: MONO, fontSize: 10, fontWeight: 700, textDecoration: 'none', flex: '0 0 auto' }
  const glyph = tg ? <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d={TG_PATH} /></svg> : 'M'
  return href
    ? <a href={href} target="_blank" rel="noreferrer" title={tg ? 'Чат площадки в Телеграме' : 'Чат площадки в MAX'}
        style={{ ...box, background: tg ? 'var(--brand-tg)' : 'var(--brand-max)', color: 'var(--on-accent)' }}>{glyph}</a>
    : <span title={tg ? 'Чата в Телеграме нет' : 'Чата в MAX нет'}
        style={{ ...box, background: 'var(--bg-subtle)', color: 'var(--text-disabled)' }}>{glyph}</span>
}

function Row({ r, sla, twins }) {
  const t = ST[r.kind]
  const deal = `/sales/deals/${r.deal_id}`
  const n = (twins[twinKey(r)] || 1) - 1
  const meta = [r.service, r.surface_kind, r.code].filter(Boolean).join(' · ')
  return (
    <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', padding: '7px 0', borderTop: '1px solid var(--border-row)' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, justifySelf: 'start', padding: '3px 9px', borderRadius: 8,
        background: t.bg, border: `1px solid ${t.bd}`, color: t.fg, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>
        <span style={{ width: 6, height: 6, borderRadius: 2, background: t.dot }} />{t.label}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        <a href={deal} target="_blank" rel="noreferrer" style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none' }}>{r.deal_code}</a>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', ...ellipsis }} title={r.brand}>{r.brand}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600, ...ellipsis }} title={creativeOf(r)}>{creativeOf(r)}</span>
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.04em', color: 'var(--text-faint)', ...ellipsis }} title={meta}>{meta || '—'}</span>
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{t.event} {ddmm(r.kind === 'waiting' ? r.sent_at : r.decided_at)}</span>
        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap',
          color: r.days > sla ? 'var(--warning-fg)' : 'var(--text-secondary)' }}>{days(r.days)}</span>
        <span style={{ fontSize: 11, fontWeight: r.urgency === 'calm' ? 500 : 700, whiteSpace: 'nowrap', color: urgOf(r).fg }}>{startTxt(r)}</span>
      </span>
      {r.kind === 'waiting'
        ? <span style={{ fontSize: 12, color: 'var(--text-faint)', padding: '0 11px' }}>площадка ещё не ответила</span>
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '7px 11px', background: 'var(--bg-subtle)', borderRadius: 10, minWidth: 0 }}>
            <span style={{ fontSize: 12, lineHeight: 1.4, color: r.reason ? 'var(--text-primary)' : 'var(--text-faint)', textWrap: 'pretty' }}>
              {r.reason ? `«${r.reason}»` : 'комментария нет'}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', fontSize: 10.5, color: 'var(--text-faint)' }}>
              <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{r.decided_by || 'площадка'}</span>
              {!!r.decided_email && <span>{r.decided_email}</span>}
              {!!r.source && <><span style={{ color: 'var(--text-disabled)' }}>·</span><span>{r.source}</span></>}
              {n > 0 && (
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9, letterSpacing: '0.04em', color: 'var(--accent)' }}>
                  то же замечание ещё у {n} {n === 1 ? 'площадки' : 'площадок'}
                </span>
              )}
            </span>
          </div>
        )}
      <a href={`${deal}#sec-creatives`} target="_blank" rel="noreferrer" title="Открыть креативы сделки"
        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, border: '1px solid var(--border-card)',
          borderRadius: 9, color: 'var(--text-secondary)', textDecoration: 'none' }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 5h6v6" /><path d="M19 5l-8 8" /><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
        </svg>
      </a>
    </div>
  )
}

export default function StuckView() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')

  const load = useCallback(() => {
    api.get('/publisher-approvals/stuck', auth())
      .then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить подвисшие'))
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)

  const sla = data?.late_workdays ?? 3
  const all = useMemo(() => (data?.publishers || []).flatMap(p => p.rows), [data])
  // Один креатив вернули несколько площадок — подсказка «исправить один раз для всех».
  const twins = useMemo(() => {
    const t = {}
    all.filter(r => r.kind !== 'waiting').forEach(r => { t[twinKey(r)] = (t[twinKey(r)] || 0) + 1 })
    return t
  }, [all])
  const count = (k) => all.filter(r => matches(r, k)).length

  const pubs = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (data?.publishers || []).map(p => {
      const rows = p.rows.filter(r => matches(r, kind)
        && (!s || [p.name, p.code, r.deal_code, r.brand, creativeOf(r)].join(' ').toLowerCase().includes(s)))
      if (!rows.length) return null
      const by = {}
      rows.forEach(r => { by[r.kind] = (by[r.kind] || 0) + 1 })
      const hot = rows.filter(r => r.urgency === 'burning').length
      return { ...p, rows, max: Math.max(...rows.map(r => r.days)), hot,
        summary: Object.keys(ST).filter(k => by[k]).map(k => `${by[k]} ${ST[k].label}`).join(' · ') }
    }).filter(Boolean)
  }, [data, q, kind])

  const overdue = all.filter(r => r.kind === 'waiting').length
  const kpiVal = (v, tone) => ({ value: v, color: v ? tone : 'var(--text-faint)' })
  const kpis = [
    { label: 'Площадок', ...kpiVal(data?.publishers.length ?? 0, 'var(--text-primary)'), hint: 'с подвисшими креативами' },
    { label: 'Горит', ...kpiVal(count('burning'), 'var(--danger-fg)'), hint: 'старт уже прошёл' },
    { label: `Ждём > ${sla} раб. дн.`, ...kpiVal(overdue, 'var(--danger-fg)'), hint: overdue ? 'напомнить площадке' : 'все в срок' },
    { label: 'На доработке', ...kpiVal(count('rework'), 'var(--accent)'), hint: 'действие за нами' },
    { label: 'Отказ', ...kpiVal(count('refused'), 'var(--danger-fg)'), hint: 'креатив не принят' },
  ]
  const reset = () => { setKind(''); setQ('') }

  return (
    <>
      <div style={{ ...panel, flex: '0 0 auto', padding: '16px 24px', display: 'grid', gridTemplateColumns: 'repeat(5,minmax(0,1fr))' }}>
        {kpis.map((k, i) => (
          <div key={k.label} style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '0 22px', borderLeft: `1px solid ${i ? 'var(--border-inner)' : 'transparent'}` }}>
            <span style={CAPS}>{k.label}</span>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, color: k.color }}>{k.value}</span>
              <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{k.hint}</span>
            </span>
          </div>
        ))}
      </div>

      <div style={{ ...panel, flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '14px 24px', borderBottom: '1px solid var(--border-inner)' }}>
          {FILTERS.map(([k, label]) => {
            const n = count(k), on = kind === k, off = !n && !!k
            return (
              <span key={label} onClick={() => { if (!off) setKind(k) }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 32, padding: '0 12px', borderRadius: 10, fontSize: 12.5, whiteSpace: 'nowrap',
                  background: on ? 'var(--accent-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                  color: off ? 'var(--text-disabled)' : on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontWeight: on ? 700 : 600,
                  cursor: off ? 'default' : 'pointer', transition: 'background-color 150ms ease, color 150ms ease' }}>
                {label}
                <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: off ? 'var(--text-disabled)' : on ? 'var(--accent)' : 'var(--text-faint)' }}>{n}</span>
              </span>
            )
          })}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, width: 320, maxWidth: '100%', height: 34, boxSizing: 'border-box',
            padding: '0 12px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 10 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="1.9" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.2-3.2" /></svg>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Площадка, сделка или креатив"
              style={{ flex: 1, minWidth: 0, height: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: UI, fontSize: 12.5, color: 'var(--text-primary)' }} />
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, padding: '9px 24px', borderBottom: '1px solid var(--border-inner)', ...CAPS, fontSize: 9 }}>
          <span>Статус</span><span>Сделка</span><span>Креатив · услуга</span><span>Событие · ждёт</span><span>Замечание площадки</span><span />
        </div>
        <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: PAD, paddingBottom: 12 }}>
          {!!err && <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--danger-fg)' }}>{err}</div>}
          {!data && !err && <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>Загрузка…</div>}
          {data && !pubs.length && (
            <div style={{ padding: '40px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)' }}>{all.length ? 'Ничего не найдено' : 'Ничего не подвисло'}</span>
              {!!all.length && <span onClick={reset} style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>сбросить фильтры</span>}
            </div>
          )}
          {pubs.map(p => (
            <div key={p.id} style={{ display: 'flex', flexDirection: 'column', padding: '10px 0 4px', borderBottom: '1px solid var(--border-inner)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 4, minWidth: 0 }}>
                <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em', ...ellipsis }} title={p.name}>{p.name}</span>
                {!!p.code && <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, color: 'var(--text-faint)' }}>{p.code}</span>}
                <ChatIcon href={safeHref(tgHref(p.tg))} kind="tg" />
                <ChatIcon href={safeHref(p.max)} kind="max" />
                <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'baseline', gap: 6, fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                  {p.hot > 0 && <><b style={{ color: 'var(--danger-fg)' }}>{p.hot} горит</b><span style={{ color: 'var(--text-disabled)' }}>·</span></>}
                  {p.summary}
                  <span style={{ color: 'var(--text-disabled)' }}>·</span>
                  дольше всего
                  <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: p.max > sla ? 'var(--warning-fg)' : 'var(--text-secondary)' }}>{days(p.max)}</span>
                </span>
              </div>
              {p.rows.map(r => <Row key={r.pair_id} r={r} sla={sla} twins={twins} />)}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
