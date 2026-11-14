/**
 * Три блока контуров «Моих сделок» (v5, разметка эталона «три контура» дословно; README §2). Клик по блоку — весь контур (фильтры
 * сбрасываются), клик по стадии — фильтр по ней (повторный снимает, Ctrl/Shift — добавить). При выбранной стадии итоги блока
 * считаются по ней, полоски остаются полными. Выбранный контур — белый фон и тень, без синей обводки.
 */
import { MONO } from '@/components/salesTableKit'
import { CONTOURS, DOC_STAGES, summary, hot, mine, good, packMine } from './contours'
import { mln } from '@/components/accounts/dashboard/ladder'

const BAR = { sandbox: 'var(--text-faint)', work: 'var(--warning)', docs: 'var(--income)' }

function Block({ no, title, sub, on, count, unit, sum, mineN, hotN, goodN, aside, asideTitle, bars, contour, picked, onPick, onStage }) {
  return (
    <button type="button" onClick={onPick} aria-pressed={on}
      style={{ minWidth: 0, overflow: 'hidden', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 8, padding: '14px 18px',
        borderRadius: 16, cursor: 'pointer', background: on ? 'var(--bg-card)' : 'var(--bg-subtle)', border: '1px solid var(--border-card)',
        boxShadow: on ? 'var(--shadow-card)' : 'none', color: 'var(--text-primary)', fontFamily: 'inherit' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', minWidth: 0 }}>
        <span style={{ fontFamily: MONO, flex: '0 0 22px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22,
          borderRadius: 7, background: on ? 'var(--accent)' : 'var(--bg-card)', color: on ? 'var(--bg-card)' : 'var(--text-muted)', fontSize: 11.5, fontWeight: 700 }}>{no}</span>
        <span style={{ flex: '0 0 auto', fontSize: 15.5, fontWeight: 800, whiteSpace: 'nowrap' }}>{title}</span>
        <span title={sub} style={{ flex: '1 1 0', minWidth: 0, fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</span>
        {mineN > 0 && (
          <span style={{ flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 5, height: 24, padding: '0 9px', borderRadius: 8,
            background: 'var(--accent-tint)', color: 'var(--accent-fg)', fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--accent)' }} />ваш ход {mineN}</span>)}
        {hotN > 0 && (
          <span style={{ fontFamily: MONO, flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--danger)' }} />горит {hotN}</span>)}
        {goodN > 0 && (
          <span style={{ fontFamily: MONO, flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--income-fg)', whiteSpace: 'nowrap' }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--income)' }} />всё хорошо {goodN}</span>)}
      </span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, width: '100%', minWidth: 0, whiteSpace: 'nowrap' }}>
        <span style={{ fontFamily: MONO, flex: '0 0 auto', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>{count}</span>
        <span style={{ flex: '0 0 auto', fontSize: 12.5, color: 'var(--text-secondary)' }}>{unit}</span>
        <span style={{ fontFamily: MONO, flex: '0 0 auto', fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)' }}>{mln(sum)}</span>
        {!!aside && <span title={asideTitle} style={{ fontFamily: MONO, marginLeft: 'auto', flex: '0 1 auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
          fontSize: 11.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{aside}</span>}
      </span>
      <span style={{ display: 'flex', gap: 3, width: '100%' }}>
        {bars.map(b => {
          const here = on, sel = here && picked.includes(b.key), dim = here && picked.length > 0 && !sel
          return (
            <span key={b.key} role="button" aria-pressed={sel} title={`${b.label}: ${b.n}${sel ? ' — снять фильтр' : ' — показать только эту стадию'}`}
              onClick={(e) => { e.stopPropagation(); onStage(contour, b.key, e.ctrlKey || e.metaKey || e.shiftKey) }}
              style={{ flex: `${Math.max(1, b.n)} 1 0`, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3, padding: '4px 0 2px', margin: '-4px 0 -2px',
                opacity: dim ? 0.45 : 1, cursor: 'pointer' }}>
              <span style={{ height: 5, borderRadius: 3, background: b.bg || BAR[contour] }} />
              <span style={{ fontFamily: MONO, display: 'flex', gap: 5, fontSize: 10, color: 'var(--text-muted)', minWidth: 0 }}>
                <span style={{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: sel ? 700 : 400,
                  color: sel ? 'var(--text-primary)' : 'inherit' }}>{b.label}</span>
                <span style={{ flex: '0 0 auto', fontWeight: 700, color: sel ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{b.n}</span>
              </span>
            </span>
          )
        })}
      </span>
    </button>
  )
}

const unitOf = (key, picked, labels) => {
  if (!picked.length) return null
  const what = key === 'docs' ? 'пакетов' : key === 'sandbox' ? 'МП' : 'сделок'
  return `${what} · ${picked.length === 1 ? labels[picked[0]] : `${picked.length} стадии`}`
}

/** rows — строки очереди (сделки), packs — пакеты мастер-сделок (могут быть null — нет права или ещё не загружены). */
export default function ContourCards({ rows, packs, contour, picked, onContour, onStage }) {
  const blocks = CONTOURS.map(c => {
    const all = rows.filter(r => r.__contour === c.key)
    const sel = contour === c.key && picked.length ? all.filter(r => c.stages.some(st => picked.includes(st.key) && st.match(r))) : all
    const s = summary(sel, c.key)
    const full = summary(all, c.key)
    const labels = Object.fromEntries(c.stages.map(st => [st.key, st.label]))
    return <Block key={c.key} no={c.n} title={c.title} sub={c.sub} on={contour === c.key} count={s.n}
      unit={(contour === c.key && unitOf(c.key, picked, labels)) || c.unit} sum={s.sum} mineN={sel.filter(mine).length}
      hotN={sel.filter(r => mine(r) && hot(r)).length} goodN={sel.filter(good).length}
      bars={full.stages} contour={c.key} picked={contour === c.key ? picked : []}
      onPick={() => onContour(c.key)} onStage={onStage} />
  })
  const pk = packs || []
  const active = pk.filter(p => p.status !== 'ждём оплату')
  const pay = pk.filter(p => p.status === 'ждём оплату')
  const docBars = DOC_STAGES.map(st => ({ key: st.key, label: st.label, n: pk.filter(p => p.status === st.key).length,
    bg: st.key === 'ждём оплату' ? 'var(--border-hover)' : undefined }))
  const dSel = contour === 'docs' && picked.length ? pk.filter(p => picked.includes(p.status)) : active
  const pMine = packMine
  const docLabels = Object.fromEntries(DOC_STAGES.map(st => [st.key, st.label]))
  blocks.push(
    <Block key="docs" no={3} title="Документы" sub="мастер-сделки до выставления" on={contour === 'docs'}
      count={dSel.length} unit={(contour === 'docs' && unitOf('docs', picked, docLabels)) || 'пакетов в работе'}
      sum={dSel.reduce((s, p) => s + (p.net || 0), 0)} mineN={dSel.filter(pMine).length}
      hotN={dSel.filter(p => pMine(p) && p.todo?.tone === 'bad').length} goodN={0}
      aside={pay.length ? `ждут оплату: ${pay.length} пак. · ${pay.reduce((s, p) => s + (p.deals || 0), 0)} сделок · ${mln(pay.reduce((s, p) => s + (p.net || 0), 0))}` : ''}
      asideTitle="После выставления пакет уходит из фокуса аккаунта — оплату ведут финансы"
      bars={docBars} contour="docs" picked={contour === 'docs' ? picked : []}
      onPick={() => onContour('docs')} onStage={onStage} />)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.25fr) minmax(0,1.25fr)', gap: 10 }}>{blocks}</div>
  )
}
