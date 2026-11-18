/**
 * Контур «Документы» «Моих сделок» списком (экраны 06–07 хендоффа v5): пакеты мастер-сделок по группам «Ваш ход» / «Ждём: кто».
 * Строка — код, контрагент и договор, рекламодатели, сделки, бюджет, статус, период, «что сделать», действие. Действие и расхлоп —
 * те же, что в реестре мастер-сделок (`ActionCell`, `ExpandedRow`): шаги считает сервер (`master_deal/status.py`).
 */
import { Collapse } from '@/lib/motion'
import { Fragment, useEffect, useState } from 'react'
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { CopyIcon } from '@/components/CopyCode'
import { monthLabel } from '@/lib/salesFormat'
import { MasterStatusPill, TODO_DOT } from '@/lib/masterStatus'
import { mln } from '@/components/accounts/dashboard/ladder'
import PackAction from '@/components/accounts/deals/packAction'
import ExpandedRow, { navyZone } from '@/components/master/registry/ExpandedRow'
import { packGroups, packTurn } from '@/components/accounts/deals/contours'
import { plural } from '@/components/master/kit'
import { STICKY_TOP } from '@/components/accounts/deals/TurnGroups'
import { useThemeKey } from '@/lib/theme'

const COLS = '96px minmax(180px,1.4fr) minmax(120px,1fr) 92px 110px 150px 90px minmax(160px,1.2fr) 190px'
const CAPH = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', fontWeight: 700 }
const DOT = { mine: 'var(--acc-turn, var(--danger))', wait: 'var(--text-disabled)' }   // «ваш ход» в NAVY — оранжевый (README §4)

function Row({ p, canEdit, open, asking, setAsking, onDone, onToggle }) {
  const t = p.todo
  const turn = packTurn(p)
  const toggle = (ev) => { if (ev.target.closest('a,button,input,label,[data-noexp],[data-pop-root]')) return; onToggle(p.code) }
  return (
    <div onClick={toggle} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, alignItems: 'center', padding: '10px 18px', borderTop: '1px solid var(--border-row)',
      cursor: 'pointer', background: open ? 'var(--bg-subtle)' : 'transparent' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span aria-hidden style={{ fontSize: 9, color: 'var(--text-faint)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform var(--dur-base) ease' }}>▸</span>
        <Link href={`/accounts/master/${p.code}`} target="_blank" style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent)', whiteSpace: 'nowrap' }}>{p.code}</Link>
        <CopyIcon text={p.code} size={12} title="Скопировать код мастер-сделки" />
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <b style={{ fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={p.counterparty || ''}>{p.counterparty || '—'}</b>
        <span style={{ fontSize: 11.5, color: 'var(--accent-fg)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>договор № {p.contract?.number || '—'}</span>
      </span>
      <span title={(p.advertisers || []).join(', ')} style={{ fontSize: 12.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{(p.advertisers || []).join(', ') || '—'}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12.5 }}>
        <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--text-disabled)' }} />{(p.deal_codes || []).length} {plural((p.deal_codes || []).length, ['сделка', 'сделки', 'сделок'])}</span>
      <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{mln(p.net)}</span>
      <span style={{ display: 'inline-flex' }}><MasterStatusPill status={p.status} label={p.status} /></span>
      <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{monthLabel(p.period)}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <span aria-hidden style={{ width: 7, height: 7, borderRadius: 2, background: t ? TODO_DOT[t.tone] : 'transparent', flex: '0 0 7px' }} />
        <span style={{ fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: turn.mine ? 'var(--text-primary)' : 'var(--text-secondary)' }} title={t?.text || ''}>{t?.text || '—'}</span>
      </span>
      {turn.mine ? (
        <PackAction p={p} canEdit={canEdit} asking={asking} setAsking={setAsking} onDone={onDone} onGo={() => onToggle(p.code, true)} />
      ) : <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>ждём: {turn.who}</span>}
    </div>
  )
}

export default function PackList({ packs, canEdit, onReload }) {
  const zone = navyZone(useThemeKey())     // расхлоп пакета в NAVY — продолжение строки с зонами (README §2)
  const [expanded, setExpanded] = useState(null)
  const [asking, setAsking] = useState(null)
  const [closed, setClosed] = useState({})
  useEffect(() => {
    if (!asking) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setAsking(null) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [asking])
  const toggle = (code, only) => setExpanded(x => (only ? code : x === code ? null : code))
  const groups = packGroups(packs)
  if (!groups.length) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-faint)', fontSize: 13 }}>Пакетов нет</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {groups.map(g => {
        const shut = closed[g.key] ?? g.tone !== 'mine'
        return (
          <div key={g.key} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 16, boxShadow: 'var(--shadow-card)' }}>
            <div onClick={() => setClosed(c => ({ ...c, [g.key]: !shut }))} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '12px 18px', cursor: 'pointer' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: DOT[g.tone], alignSelf: 'center' }} />
              <b style={{ fontSize: 14 }}>{g.title}</b>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: g.tone === 'mine' ? 'var(--acc-turn-num, var(--text-secondary))' : 'var(--text-secondary)' }}>{g.rows.length}</span>
              <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)' }}>{mln(g.rows.reduce((s, p) => s + (p.net || 0), 0))}</span>
              {g.tone !== 'mine' && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>от вас ничего не нужно</span>}
              <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)' }}>{shut ? 'развернуть ▾' : 'свернуть ▴'}</span>
            </div>
            {!shut && <>
              <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 12, padding: '6px 18px', borderTop: '1px solid var(--border-row)', ...CAPH,
                position: 'sticky', top: STICKY_TOP, zIndex: 4, background: 'var(--bg-card)' }}>
                <span>Код</span><span>Контрагент / договор</span><span>Рекламодатель</span><span>Услуга</span><span style={{ textAlign: 'right' }}>Бюджет до НДС</span>
                <span>Стадия</span><span>Период</span><span>Что сделать</span><span />
              </div>
              {g.rows.map(p => (
                <Fragment key={p.code}>
                  <Row p={p} canEdit={canEdit} open={expanded === p.code} asking={asking} setAsking={setAsking}
                    onDone={() => { setAsking(null); onReload() }} onToggle={toggle} />
                  {expanded === p.code && <Collapse><ExpandedRow code={p.code} channel={p.channel} canEdit={canEdit} onChanged={onReload} zone={zone} /></Collapse>}
                </Fragment>
              ))}
            </>}
          </div>
        )
      })}
    </div>
  )
}
