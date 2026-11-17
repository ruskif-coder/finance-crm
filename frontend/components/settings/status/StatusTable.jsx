// Таблица проверок экрана «Статус системы» (макет design_handoff_status, 16.11.2026): одна таблица, группы секциями,
// «Требует внимания» первой. Клик по строке раскрывает историю за 14 дней; клики по кнопкам строку не раскрывают.
import { Fragment } from 'react'
import { MONO } from '@/components/salesTableKit'
import { TONE_DOT, detailsOf, historyOf, stateLabel } from './statusModel'

export const COLS = 'minmax(256px,1fr) 124px minmax(170px,0.85fr) minmax(240px,1.7fr) 232px'
const cap = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const plain = { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer' }
const smallBtn = { ...plain, display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', borderRadius: 8, fontSize: 11.5, fontWeight: 700, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }
const SQ = { ok: 'var(--income)', warn: 'var(--warning)', bad: 'var(--danger)', idle: 'var(--text-disabled)' }
const SUM_FG = { ok: 'var(--text-faint)', warn: 'var(--warning-fg)', bad: 'var(--danger-fg)', plain: 'var(--text-secondary)' }
const stop = (e) => e.stopPropagation()

function chipOf(c) {
  if (c.running) return { pad: '0 7px', bg: 'var(--bg-subtle)', bd: 'var(--border-card)', fg: 'var(--text-secondary)' }
  if (c.tone === 'ok' || c.tone === 'idle') return { pad: 0, bg: 'transparent', bd: 'transparent', fg: 'var(--text-faint)' }
  if (c.tone === 'warn') return { pad: '0 7px', bg: 'var(--warning-tint)', bd: 'var(--warning-border)', fg: 'var(--warning-fg)' }
  return { pad: '0 7px', bg: 'var(--danger-tint)', bd: 'var(--danger-border)', fg: 'var(--danger-fg)' }
}

function Action({ c, confirm, onAsk, onYes, onNo }) {
  if (confirm) return (
    <span onClick={stop} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>Запустить сейчас?</span>
      <button type="button" onClick={onYes} className="st-yes" style={{ ...smallBtn, border: 'none', background: 'var(--accent)', color: 'var(--bg-card)' }}>Да</button>
      <button type="button" onClick={onNo} style={{ ...smallBtn, padding: '0 9px', fontWeight: 600 }}>Нет</button>
    </span>
  )
  const ok = c.tone === 'ok' || c.tone === 'idle'
  return (
    <>
      {c.action && <a href={c.action.href} onClick={stop} className="st-btn" style={{ ...smallBtn, textDecoration: 'none' }}>{c.action.label}</a>}
      {c.runnable && !c.running && (
        <button type="button" onClick={(e) => { stop(e); onAsk() }} className="st-btn" title="Запустить задание вручную — запись попадёт в журнал"
          style={{ ...smallBtn, gap: 5, fontWeight: ok ? 600 : 700, color: ok ? 'var(--text-muted)' : 'var(--text-secondary)' }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M13.5 8a5.5 5.5 0 1 1-1.7-4M13.5 2.5V5H11" /></svg>
          {ok ? 'Запустить' : 'Перезапустить'}
        </button>
      )}
      {c.where && !c.action && !c.runnable && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{c.where}</span>}
    </>
  )
}

function History({ c }) {
  const h = historyOf(c)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 36, padding: '10px 20px 12px 35px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
      <span style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={cap}>{h.cap}</span>
        <span style={{ display: 'flex', gap: 3 }}>
          {h.squares.map((s, i) => <span key={i} title={s.t} style={{ width: 13, height: 13, borderRadius: 3, background: s.tone ? SQ[s.tone] : 'var(--border-inner)' }} />)}
        </span>
        <span style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}><span>{h.from}</span><span>сегодня</span></span>
      </span>
      <span style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={cap}>За 14 дней</span>
        <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{h.sum}</span>
      </span>
      <span style={{ flex: '1 1 auto', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={cap}>{h.errCap}</span>
        <span style={{ fontSize: 12, lineHeight: 1.4, color: h.errOn ? 'var(--text-primary)' : 'var(--text-muted)' }}>{h.err}</span>
      </span>
    </div>
  )
}

function Row({ c, open, confirm, onToggle, onAsk, onYes, onNo }) {
  const ch = chipOf(c)
  const { det, keyLine } = detailsOf(c)
  const ok = c.tone === 'ok' || c.tone === 'idle'
  const since = c.running ? `${c.running.at} · ${c.running.by || '—'}` : c.since
  return (
    <>
      <div onClick={onToggle} title={open ? 'Свернуть историю' : 'Показать историю за 14 дней'} className="st-row"
        style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', boxSizing: 'border-box', minHeight: 38,
          padding: '5px 20px', borderBottom: '1px solid var(--border-row)', background: open ? 'var(--bg-tint)' : 'transparent', cursor: 'pointer' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
          <span style={{ flex: '0 0 6px', width: 6, height: 6, borderRadius: 2, background: c.running ? 'var(--text-faint)' : TONE_DOT[c.tone] }} />
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
        </span>
        <span><span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: ch.pad, borderRadius: 6, background: ch.bg, border: `1px solid ${ch.bd}`,
          fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: ch.fg, whiteSpace: 'nowrap' }}>{stateLabel(c)}</span></span>
        <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span title={c.value || ''} style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {c.running ? 'запущено вручную' : (c.value || '—')}</span>
          {!!since && <span style={{ fontFamily: MONO, fontSize: 10, lineHeight: 1.5, fontWeight: 700, whiteSpace: 'nowrap',
            color: c.running ? 'var(--text-muted)' : c.tone === 'warn' ? 'var(--warning-fg)' : 'var(--danger-fg)' }}>{since}</span>}
        </span>
        <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 12, lineHeight: 1.35, color: ok ? 'var(--text-muted)' : 'var(--text-primary)' }}>{det}</span>
          {!!keyLine && <span title={keyLine} style={{ fontFamily: MONO, fontSize: 10, lineHeight: 1.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{keyLine}</span>}
        </span>
        <span style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 6 }}>
          <Action c={c} confirm={confirm} onAsk={onAsk} onYes={onYes} onNo={onNo} />
        </span>
      </div>
      {open && <History c={c} />}
    </>
  )
}

function CandRow({ r }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', boxSizing: 'border-box', minHeight: 38,
      padding: '5px 20px', borderBottom: '1px solid var(--border-row)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
        <span style={{ flex: '0 0 6px', width: 6, height: 6, borderRadius: 2, background: 'var(--text-disabled)' }} />
        <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r[0]}</span>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>нет проверки</span>
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--text-disabled)' }}>—</span>
      <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontSize: 12, lineHeight: 1.35, color: 'var(--text-muted)' }}>{r[1]}</span>
        <span style={{ fontFamily: MONO, fontSize: 10, lineHeight: 1.5, color: 'var(--text-faint)' }}>{r[2]}</span>
      </span>
      <span />
    </div>
  )
}

export default function StatusTable({ view, closed, onSection, open, onRow, confirm, setConfirm, onRun }) {
  return (
    <div style={{ flex: '1 1 auto', minWidth: 0, background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18, overflow: 'auto' }}>
      <div style={{ minWidth: 1040 }}>
        <div style={{ position: 'sticky', top: 0, zIndex: 5, display: 'grid', gridTemplateColumns: COLS, gap: 14, alignItems: 'center', padding: '12px 20px 10px',
          background: 'var(--bg-card)', borderBottom: '1px solid var(--border-card)', ...cap }}>
          <span>Проверка</span><span>Состояние</span><span>Значение</span><span>Детали</span><span style={{ textAlign: 'right' }}>Действие</span>
        </div>
        {view.sections.map(s => {
          const isClosed = !!closed[s.key]
          return (
            <Fragment key={s.key}>
              <div onClick={() => onSection(s.key)} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 20px', background: 'var(--bg-subtle)',
                borderBottom: '1px solid var(--border-inner)', cursor: 'pointer' }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: s.tone === 'none' ? 'var(--text-disabled)' : TONE_DOT[s.tone] }} />
                <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-primary)' }}>{s.title}</span>
                <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{s.hint}</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', color: SUM_FG[s.sumTone] }}>{s.sum}</span>
                <span style={{ fontSize: 8, color: 'var(--text-faint)', width: 10, textAlign: 'right' }}>{isClosed ? '▾' : '▴'}</span>
              </div>
              {!isClosed && (s.cand
                ? s.rows.map(r => <CandRow key={r[0]} r={r} />)
                : s.rows.map(c => {
                  const k = `${s.key}:${c.key}`
                  return <Row key={k} c={c} open={!!open[k]} confirm={confirm === c.key} onToggle={() => onRow(k)}
                    onAsk={() => setConfirm(c.key)} onNo={(e) => { stop(e); setConfirm('') }}
                    onYes={(e) => { stop(e); setConfirm(''); onRun(c.key) }} />
                }))}
            </Fragment>
          )
        })}
        {view.empty && <div style={{ padding: '36px 20px', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>Проверок нет — измените фильтры</div>}
        <div style={{ padding: '12px 20px 14px', fontSize: 11.5, lineHeight: 1.5, color: 'var(--text-faint)' }}>
          Экран не показывает контейнеры, их аптайм и политики перезапуска: у бэкенда нет доступа к докеру, это решение.
          Живые запросы к внешним сервисам делает фоновый прогон, а не открытие экрана.
        </div>
      </div>
    </div>
  )
}
